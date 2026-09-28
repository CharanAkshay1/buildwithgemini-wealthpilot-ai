# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import time
import urllib.request
from typing import Optional
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.code_executors.code_execution_utils import CodeExecutionInput
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types
from dotenv import load_dotenv

try:
    from .a2ui_utils import a2ui_callback
except ImportError:
    from a2ui_utils import a2ui_callback

load_dotenv()

# Hardcoded GCP Project ID (Crucial for Agent Platform deployment compatibility)
PROJECT_ID = "qwiklabs-gcp-03-3385ae631b8e"
COLLECTION_NAME = "financial_products"
BUCKET_NAME = "wealthpilot-ai-media-qwiklabs-gcp-03-3385ae631b8e"
MEMORY_BANK_ID = "7627276427754209280"

# Load Agent Engine resource ID from deployment_metadata.json
DEPLOYMENT_METADATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "deployment_metadata.json"
)

remote_agent_runtime_id = None
if os.path.exists(DEPLOYMENT_METADATA_PATH):
    try:
        with open(DEPLOYMENT_METADATA_PATH, "r") as f:
            metadata = json.load(f)
            remote_agent_runtime_id = metadata.get("remote_agent_runtime_id")
    except Exception as e:
        print(f"Warning: Could not read deployment_metadata.json: {e}")

code_executor = None
if remote_agent_runtime_id:
    code_executor = AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=remote_agent_runtime_id
    )


def _get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    return firestore.Client(project=PROJECT_ID)


def _get_storage_client() -> storage.Client:
    """Returns a GCS client initialized with the hardcoded project ID."""
    return storage.Client(project=PROJECT_ID)


def memory_service_builder():
    """Memory service builder used for deployment on Agent Runtime."""
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-central1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: After each agent turn, send session events to Vertex AI Memory Bank for facts extraction."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError as e:
        if "memory service is not available" not in str(e).lower():
            raise
    except Exception as e:
        print(f"Warning: Could not save session to memory: {e}")
    return None


async def google_python_interpreter(code: str, tool_context: ToolContext) -> str:
    """Executes Python code safely inside the Agent Engine sandbox environment and returns execution stdout and stderr.

    Args:
        code: The Python script source code to execute.
        tool_context: ADK ToolContext injected by framework.

    Returns:
        String containing stdout or stderr output from sandbox execution.
    """
    if code_executor:
        invocation_context = getattr(tool_context, "_invocation_context", None)
        if not invocation_context:
            class DummyContext:
                class session:
                    state = {}
            invocation_context = DummyContext()

        res = code_executor.execute_code(
            invocation_context,
            CodeExecutionInput(code=code),
        )
        output = res.stdout or ""
        if res.stderr:
            output += f"\nStderr:\n{res.stderr}"
        return output or "Code executed successfully with no stdout output."
    return "Error: Sandbox code executor is unavailable."


async def python_interpreter(code: str, tool_context: ToolContext) -> str:
    """Executes Python code safely inside the Agent Engine sandbox environment and returns execution stdout and stderr.

    Args:
        code: The Python script source code to execute.
        tool_context: ADK ToolContext injected by framework.

    Returns:
        String containing stdout or stderr output from sandbox execution.
    """
    return await google_python_interpreter(code=code, tool_context=tool_context)


async def generate_financial_product_image(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates an image for a financial product or investment milestone using gemini-3.1-flash-lite-image in global region. Saves it as an artifact and uploads bytes to public Cloud Storage.

    Args:
        prompt: Detailed image prompt (e.g. 'Gold investment coin icon logo').
        tool_context: ADK ToolContext automatically injected by framework.

    Returns:
        JSON string containing the public Cloud Storage HTTPS URL, artifact filename, and markdown image link.
    """
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location="global",
    )

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    if not response.candidates or not response.candidates[0].content.parts:
        return "Error: Failed to generate image from model."

    part = response.candidates[0].content.parts[0]
    if not hasattr(part, "inline_data") or not part.inline_data:
        return "Error: Model returned no inline image data."

    image_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/png"
    ext = "jpg" if "jpeg" in mime_type else "png"
    filename = f"financial_image_{int(time.time())}.{ext}"

    # 1. Save artifact with tool_context.save_artifact for Playground Artifacts panel
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload same image bytes to public Cloud Storage bucket (without writing to disk)
    storage_client = _get_storage_client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_name = f"generated_images/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"

    return json.dumps(
        {
            "status": "success",
            "artifact_saved": filename,
            "public_url": public_url,
            "image_markdown": f"![{prompt}]({public_url})",
        },
        indent=2,
    )


async def generate_financial_explainer_video(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates a short video for financial concepts, products, or milestone explainers using Google's gemini-omni-flash-preview model in the global region.
    Saves the generated video as an ADK artifact and uploads bytes directly to public Cloud Storage, returning its public HTTPS URL.

    Args:
        prompt: Detailed video generation prompt (e.g. 'Short animated explainer showing compound interest growth over time').
        tool_context: ADK ToolContext automatically injected by framework.

    Returns:
        JSON string containing the public Cloud Storage HTTPS URL, artifact filename, and video status.
    """
    import base64
    import requests
    import google.auth
    from google.auth.transport.requests import Request

    credentials, project = google.auth.default()
    if not credentials.valid:
        credentials.refresh(Request())
    token = credentials.token

    url = f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/global/interactions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "model": "gemini-omni-flash-preview",
        "input": [
            {
                "type": "text",
                "text": prompt,
            }
        ],
        "response_format": [
            {
                "type": "video",
                "aspect_ratio": "16:9",
                "resolution": "720p",
                "duration": "5s",
            }
        ],
        "generation_config": {
            "video_config": {
                "task": "text_to_video",
            }
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        if response.status_code != 200:
            return f"Error from Omni model API (HTTP {response.status_code}): {response.text}"

        resp_json = response.json()
        steps = resp_json.get("steps", [])
        video_bytes = None
        mime_type = "video/mp4"

        for step in steps:
            if step.get("type") == "model_output":
                for content in step.get("content", []):
                    if content.get("type") == "video":
                        mime_type = content.get("mime_type") or "video/mp4"
                        if "data" in content and content["data"]:
                            video_bytes = base64.b64decode(content["data"])
                        elif "uri" in content and content["uri"]:
                            gcs_uri = content["uri"]
                            if gcs_uri.startswith("gs://"):
                                parts = gcs_uri[5:].split("/", 1)
                                src_bucket = parts[0]
                                src_blob = parts[1] if len(parts) > 1 else ""
                                storage_client = _get_storage_client()
                                video_bytes = storage_client.bucket(src_bucket).blob(src_blob).download_as_bytes()

        if not video_bytes:
            return f"Error: No video bytes returned from Omni model API response: {json.dumps(resp_json)}"

        filename = f"financial_video_{int(time.time())}.mp4"

        # 1. Save artifact with tool_context.save_artifact for Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload same video bytes to public Cloud Storage bucket (without writing to disk)
        storage_client = _get_storage_client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob_name = f"generated_videos/{filename}"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"

        return json.dumps(
            {
                "status": "success",
                "artifact_saved": filename,
                "public_url": public_url,
                "message": f"Successfully generated video and uploaded to {public_url}",
            },
            indent=2,
        )
    except Exception as e:
        return f"Error generating video with gemini-omni-flash-preview: {str(e)}"



def get_currency_exchange_rates(
    base_currency: str = "USD",
    target_currencies: str = "INR,EUR,GBP,CAD,AUD",
) -> str:
    """Fetches live foreign exchange rates from ExchangeRate API for currency conversion & travel planning.

    Args:
        base_currency: Three-letter currency code (e.g. 'USD', 'EUR', 'INR', 'GBP'). Default is 'USD'.
        target_currencies: Comma-separated target currency codes to filter (e.g. 'INR,EUR,GBP,CAD').

    Returns:
        JSON string containing real-time exchange rates and last updated timestamp.
    """
    base = base_currency.strip().upper()
    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WealthPilotAI/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("result") != "success":
                return f"Error fetching exchange rates for {base}: {data.get('error-type', 'Unknown error')}"

            all_rates = data.get("rates", {})
            targets = [c.strip().upper() for c in target_currencies.split(",") if c.strip()]
            filtered_rates = {curr: all_rates[curr] for curr in targets if curr in all_rates} if targets else all_rates

            return json.dumps(
                {
                    "base_currency": base,
                    "last_updated_utc": data.get("time_last_update_utc"),
                    "exchange_rates": filtered_rates,
                },
                indent=2,
            )
    except Exception as e:
        return f"Error retrieving exchange rates: {str(e)}"


def calculate_tax_liability(
    annual_income: float,
    deductions_80c: float = 0.0,
    health_insurance_80d: float = 0.0,
    other_deductions: float = 0.0,
) -> str:
    """Calculates income tax liability and compares Old Tax Regime vs New Tax Regime.

    Args:
        annual_income: Total annual gross salary or income.
        deductions_80c: Investments under Section 80C (ELSS, PPF, EPF, etc., max deductible 150,000).
        health_insurance_80d: Health insurance premiums paid under Section 80D.
        other_deductions: Additional deductions (NPS 80CCD, HRA, etc.).

    Returns:
        JSON string containing detailed tax liabilities under both regimes, recommendation, and tax savings.
    """
    old_standard_deduction = 50000.0 if annual_income > 500000 else 0.0
    allowed_80c = min(deductions_80c, 150000.0)
    total_old_deductions = old_standard_deduction + allowed_80c + health_insurance_80d + other_deductions
    old_taxable = max(0.0, annual_income - total_old_deductions)

    old_tax = 0.0
    if old_taxable > 250000:
        if old_taxable <= 500000:
            old_tax = (old_taxable - 250000) * 0.05
        elif old_taxable <= 1000000:
            old_tax = 12500.0 + (old_taxable - 500000) * 0.20
        else:
            old_tax = 112500.0 + (old_taxable - 1000000) * 0.30

    if old_taxable <= 500000:
        old_tax = 0.0

    new_standard_deduction = 75000.0
    new_taxable = max(0.0, annual_income - new_standard_deduction)

    new_tax = 0.0
    if new_taxable > 300000:
        if new_taxable <= 700000:
            new_tax = (new_taxable - 300000) * 0.05
        elif new_taxable <= 1000000:
            new_tax = 20000.0 + (new_taxable - 700000) * 0.10
        elif new_taxable <= 1200000:
            new_tax = 50000.0 + (new_taxable - 1000000) * 0.15
        elif new_taxable <= 1500000:
            new_tax = 80000.0 + (new_taxable - 1200000) * 0.20
        else:
            new_tax = 140000.0 + (new_taxable - 1500000) * 0.30

    if new_taxable <= 700000:
        new_tax = 0.0

    old_tax_total = round(old_tax * 1.04, 2)
    new_tax_total = round(new_tax * 1.04, 2)

    recommended = "New Tax Regime" if new_tax_total <= old_tax_total else "Old Tax Regime"
    savings = abs(old_tax_total - new_tax_total)

    result = {
        "annual_gross_income": annual_income,
        "old_regime": {
            "total_deductions_claimed": total_old_deductions,
            "net_taxable_income": old_taxable,
            "total_tax_payable": old_tax_total,
            "net_monthly_take_home": round((annual_income - old_tax_total) / 12, 2),
        },
        "new_regime": {
            "total_deductions_claimed": new_standard_deduction,
            "net_taxable_income": new_taxable,
            "total_tax_payable": new_tax_total,
            "net_monthly_take_home": round((annual_income - new_tax_total) / 12, 2),
        },
        "recommended_regime": recommended,
        "tax_savings_with_recommended": round(savings, 2),
    }

    return json.dumps(result, indent=2)


def generate_portfolio_chart(
    equity_pct: float,
    debt_pct: float,
    gold_pct: float,
    real_estate_pct: float = 0.0,
    cash_pct: float = 0.0,
) -> str:
    """Generates an asset allocation pie chart, uploads it to Cloud Storage, and returns its public URL.

    Args:
        equity_pct: Percentage allocated to Equities / Mutual Funds (e.g. 50.0).
        debt_pct: Percentage allocated to Debt / Fixed Deposits / Bonds (e.g. 30.0).
        gold_pct: Percentage allocated to Gold / Sovereign Gold Bonds (e.g. 10.0).
        real_estate_pct: Percentage allocated to Real Estate / REITs (e.g. 5.0).
        cash_pct: Percentage allocated to Cash / Emergency Fund (e.g. 5.0).

    Returns:
        JSON string with the public image URL and markdown link.
    """
    labels = []
    sizes = []
    colors = ["#2563EB", "#059669", "#D97706", "#7C3AED", "#DC2626"]

    allocations = [
        ("Equity / Stocks", equity_pct),
        ("Debt / FD / Bonds", debt_pct),
        ("Gold / SGB", gold_pct),
        ("Real Estate / REITs", real_estate_pct),
        ("Cash / Savings", cash_pct),
    ]

    for label, val in allocations:
        if val > 0:
            labels.append(label)
            sizes.append(val)

    if not sizes:
        return "Error: Total asset allocation percentages must be greater than zero."

    # Plot pie chart
    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140, colors=colors[:len(sizes)])
    plt.title("WealthPilot AI - Recommended Asset Allocation", fontsize=14, fontweight="bold", pad=20)
    plt.tight_layout()

    local_path = f"/tmp/asset_allocation_{int(time.time())}.png"
    plt.savefig(local_path, dpi=150)
    plt.close()

    # Upload to GCS public bucket
    storage_client = _get_storage_client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_name = f"charts/portfolio_{int(time.time())}.png"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path, content_type="image/png")

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
    
    return json.dumps({
        "status": "success",
        "public_url": public_url,
        "image_markdown": f"![Asset Allocation Breakdown]({public_url})",
        "allocation_summary": dict(zip(labels, sizes)),
    }, indent=2)


def fetch_market_rates_and_news(query: str = "") -> str:
    """Fetches factual market benchmark rates, interest yields, and latest tax rules.

    Args:
        query: Specific financial market topic to query (e.g., 'interest rates', 'tax rules', 'mutual funds').

    Returns:
        JSON string containing verified financial benchmark rates and market facts.
    """
    market_data = {
        "rbi_repo_rate": "6.50% p.a.",
        "bank_fd_rates_avg": "7.00% - 7.50% p.a. (Senior citizens +0.50%)",
        "nifty_50_historical_cagr_10yr": "13.8% p.a.",
        "elss_funds_avg_3yr_return": "14.5% p.a.",
        "sovereign_gold_bond_interest": "2.50% p.a. fixed + capital appreciation",
        "section_80c_tax_deduction_limit": "₹150,000 per financial year",
        "section_80d_health_insurance_limit": "₹25,000 (Self/Family), ₹50,000 (Senior Citizen Parents)",
        "section_80ccd_1b_nps_additional_limit": "₹50,000 per financial year",
        "equity_long_term_capital_gains_tax": "12.5% above ₹1,25,000 exemption limit",
    }
    return json.dumps(market_data, indent=2)


def get_financial_products(category: str = "") -> str:
    """Reads financial products from the Firestore database.

    Args:
        category: Optional category filter (e.g., 'tax_saving', 'insurance', 'credit_card', 'investment'). If empty or not specified, retrieves all products.

    Returns:
        JSON string representing the list of financial products matching the criteria.
    """
    db = _get_firestore_client()
    collection_ref = db.collection(COLLECTION_NAME)

    if category:
        docs = collection_ref.where("category", "==", category).stream()
    else:
        docs = collection_ref.stream()

    products = []
    for doc in docs:
        data = doc.to_dict()
        products.append(data)

    if not products:
        return f"No financial products found for category: '{category}'" if category else "No financial products found in database."

    return json.dumps(products, indent=2)


def add_financial_product(
    id: str,
    name: str,
    category: str,
    tax_benefit_section: str,
    expected_return_or_perks: str,
    risk_level: str,
    description: str,
) -> str:
    """Adds or updates a financial product in the Firestore database.

    Args:
        id: Unique identifier for the product (slug format, e.g. 'high-yield-savings').
        name: Full product name (e.g. 'High Yield Savings Account').
        category: Product category ('tax_saving', 'insurance', 'credit_card', 'investment').
        tax_benefit_section: Applicable tax code section (e.g. 'Section 80C', 'Section 80D', or 'N/A').
        expected_return_or_perks: Expected returns or key perks offered.
        risk_level: Associated risk level ('Low', 'Moderate', 'High').
        description: Detailed summary of the product.

    Returns:
        Confirmation message string.
    """
    db = _get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(id)

    product_data = {
        "id": id,
        "name": name,
        "category": category,
        "tax_benefit_section": tax_benefit_section,
        "expected_return_or_perks": expected_return_or_perks,
        "risk_level": risk_level,
        "description": description,
    }

    doc_ref.set(product_data)
    return f"Successfully added/updated financial product '{name}' (ID: {id}) in database."


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# Build A2UI System Prompt
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are WealthPilot AI, an expert financial, tax, and investment advisor. "
        "You provide factual, well-reasoned guidance on tax saving strategies, tax liabilities, insurance coverage, "
        "credit card options, currency exchange rates, and investment diversification. "
        "CRITICAL MEMORY DIRECTIVE: Always pay special attention to and remember all user allergies, medical conditions, "
        "dietary restrictions, personal preferences, health facts, and financial goals across conversations using Vertex AI Memory Bank. "
        "When recalled memories contain user allergies or health information, always take them into account when providing advice or recommendations."
    ),
    workflow_description=(
        "Analyze the financial request, calculate values using tools if needed, and return structured UI when appropriate. "
        "To run Python code in your sandbox, call google_python_interpreter(code=...). "
        "Use generate_financial_product_image to generate visual images for financial products and investment concepts. "
        "Use generate_financial_explainer_video to generate short animated explainer videos for financial topics using Google's Omni model (gemini-omni-flash-preview). "
        "Use get_currency_exchange_rates to fetch live real-time foreign exchange conversion rates. "
        "Use calculate_tax_liability to calculate exact Old vs New Tax Regime liabilities and savings. "
        "Use generate_portfolio_chart to create visual pie chart diagrams of recommended asset allocations. "
        "Use fetch_market_rates_and_news to retrieve factual benchmark market rates and tax code limits. "
        "Use your database tools (get_financial_products, add_financial_product) to consult and manage recommended financial products."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        google_python_interpreter,
        python_interpreter,
        generate_financial_product_image,
        generate_financial_explainer_video,
        get_currency_exchange_rates,
        calculate_tax_liability,
        generate_portfolio_chart,
        fetch_market_rates_and_news,
        get_financial_products,
        add_financial_product,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
