from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from endpoint_discovery import resolve_base_url  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, str]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class EndpointDiscoveryTests(unittest.TestCase):
    @patch.dict(os.environ, {"CELL_RAG_DEMO_URL": "https://env.example/"}, clear=True)
    def test_explicit_url_has_highest_priority(self) -> None:
        self.assertEqual(resolve_base_url("https://explicit.example/"), "https://explicit.example")

    @patch.dict(os.environ, {"CELL_RAG_DEMO_URL": "https://env.example/"}, clear=True)
    def test_environment_url_is_used(self) -> None:
        self.assertEqual(resolve_base_url(), "https://env.example")

    @patch.dict(os.environ, {}, clear=True)
    @patch("endpoint_discovery.urllib.request.urlopen")
    def test_manifest_url_is_used(self, urlopen: object) -> None:
        urlopen.return_value = FakeResponse({"base_url": "https://manifest.example/"})
        self.assertEqual(resolve_base_url(manifest_url="https://registry.example"), "https://manifest.example")

    @patch.dict(os.environ, {}, clear=True)
    @patch("endpoint_discovery.urllib.request.urlopen")
    def test_empty_manifest_is_rejected(self, urlopen: object) -> None:
        urlopen.return_value = FakeResponse({})
        with self.assertRaisesRegex(RuntimeError, "did not contain base_url"):
            resolve_base_url(manifest_url="https://registry.example")


if __name__ == "__main__":
    unittest.main()
