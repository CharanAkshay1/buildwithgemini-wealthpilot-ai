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
from app.agent import calculate_tax_liability


def test_calculate_tax_liability():
    # Test income of 1,200,000 with 150,000 in 80C and 25,000 in 80D
    res_str = calculate_tax_liability(
        annual_income=1200000.0,
        deductions_80c=150000.0,
        health_insurance_80d=25000.0,
    )
    res = json.loads(res_str)

    assert "annual_gross_income" in res
    assert res["annual_gross_income"] == 1200000.0
    assert "old_regime" in res
    assert "new_regime" in res
    assert "recommended_regime" in res
    assert res["recommended_regime"] in ["Old Tax Regime", "New Tax Regime"]
