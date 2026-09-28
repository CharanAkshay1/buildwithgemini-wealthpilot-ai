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
import json
from app.agent import generate_portfolio_chart, fetch_market_rates_and_news


def test_fetch_market_rates_and_news():
    res_str = fetch_market_rates_and_news()
    res = json.loads(res_str)
    assert "rbi_repo_rate" in res
    assert "section_80c_tax_deduction_limit" in res


def test_generate_portfolio_chart():
    res_str = generate_portfolio_chart(equity_pct=50.0, debt_pct=30.0, gold_pct=20.0)
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert "public_url" in res
    assert res["public_url"].startswith("https://storage.googleapis.com/")
    assert "image_markdown" in res
