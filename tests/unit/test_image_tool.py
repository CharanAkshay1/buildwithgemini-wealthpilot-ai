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
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.agent import generate_financial_product_image


@pytest.mark.asyncio
async def test_generate_financial_product_image():
    mock_context = MagicMock()
    mock_context.save_artifact = AsyncMock(return_value=1)

    res_str = await generate_financial_product_image(
        prompt="Gold investment coin infographic icon",
        tool_context=mock_context,
    )
    res = json.loads(res_str)

    assert res["status"] == "success"
    assert "public_url" in res
    assert res["public_url"].startswith("https://storage.googleapis.com/wealthpilot-ai-media-qwiklabs-gcp-03-3385ae631b8e/")
    assert mock_context.save_artifact.called
