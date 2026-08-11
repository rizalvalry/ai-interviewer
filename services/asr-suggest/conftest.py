import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))


class FakeGeminiResponse:
    """Minimal httpx.Response stand-in for testing Gemini REST error mapping (suggest.py,
    translate.py) without a real network call. Shared here since both modules' tests need it."""

    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data
