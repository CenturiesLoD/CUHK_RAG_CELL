#!/usr/bin/env python3
"""Compatibility wrapper for resolving the public Cell RAG endpoint."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hosted_endpoint import DEFAULT_ENDPOINT_MANIFEST_URL, resolve_base_url  # noqa: E402


if __name__ == "__main__":
    print(resolve_base_url())
