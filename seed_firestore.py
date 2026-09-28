#!/usr/bin/env python3
"""Seed script for Firestore financial_products collection in WealthPilot AI."""

import google.auth
from google.cloud import firestore

# HARDCODED GCP PROJECT ID (Required for Agent Platform compatibility)
PROJECT_ID = "qwiklabs-gcp-03-3385ae631b8e"
COLLECTION_NAME = "financial_products"

SEED_PRODUCTS = [
    {
        "id": "elss-tax-saver",
        "name": "ELSS Tax Saver Fund",
        "category": "tax_saving",
        "tax_benefit_section": "Section 80C",
        "expected_return_or_perks": "12-15% p.a.",
        "risk_level": "Moderate",
        "description": "Equity Linked Savings Scheme with a 3-year lock-in period providing tax deduction under Section 80C up to $1,800/year.",
    },
    {
        "id": "health-shield",
        "name": "Health Shield Super Top-Up Insurance",
        "category": "insurance",
        "tax_benefit_section": "Section 80D",
        "expected_return_or_perks": "$50,000 health coverage with cashless hospitalization",
        "risk_level": "Low",
        "description": "Comprehensive health insurance top-up policy with tax benefits under Section 80D for medical premiums.",
    },
    {
        "id": "sapphire-card",
        "name": "Sapphire Preferred Travel & Rewards Card",
        "category": "credit_card",
        "tax_benefit_section": "N/A",
        "expected_return_or_perks": "3x points on dining & travel, zero foreign exchange markup",
        "risk_level": "Low",
        "description": "Premium rewards credit card tailored for frequent travelers with airport lounge access and zero FX markup.",
    },
    {
        "id": "nps-tier-1",
        "name": "National Pension Scheme (NPS) Tier I",
        "category": "investment",
        "tax_benefit_section": "Section 80CCD(1B)",
        "expected_return_or_perks": "9-11% p.a. compound growth",
        "risk_level": "Low to Moderate",
        "description": "Government-backed pension scheme offering additional tax deduction under Section 80CCD(1B).",
    },
]


def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    credentials, _ = google.auth.default()
    db = firestore.Client(project=PROJECT_ID, credentials=credentials)
    collection_ref = db.collection(COLLECTION_NAME)

    for item in SEED_PRODUCTS:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(item)
        print(f"  [+] Seeded product: {item['name']} ({doc_id})")

    print(f"✅ Successfully seeded {len(SEED_PRODUCTS)} items into collection '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    seed_database()
