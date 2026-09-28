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
from app.agent import add_financial_product, get_financial_products


def test_firestore_tools_read_and_write():
    # Test reading existing seeded products
    res = get_financial_products(category="tax_saving")
    assert "ELSS Tax Saver Fund" in res

    # Test adding a new test product
    add_res = add_financial_product(
        id="test-bond-fund",
        name="Government Green Bond 2026",
        category="investment",
        tax_benefit_section="Section 80C",
        expected_return_or_perks="7.5% fixed annual interest",
        risk_level="Low",
        description="Sovereign green bond supporting renewable infrastructure.",
    )
    assert "Successfully added/updated" in add_res

    # Test reading back the new item
    read_res = get_financial_products(category="investment")
    assert "Government Green Bond 2026" in read_res
