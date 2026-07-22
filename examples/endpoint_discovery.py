#!/usr/bin/env python3
"""Resolve the public Cell RAG endpoint from arguments, env, or GitHub manifest."""

from __future__ import annotations

import json
import os
import urllib.request


DEFAULT_ENDPOINT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "CenturiesLoD/CUHK_RAG_CELL/main/docs/current_endpoint.json"
)


def resolve_base_url(
    explicit_base_url: str = "",
    *,
    env_var: str = "CELL_RAG_DEMO_URL",
    manifest_url: str = "",
    timeout: int = 20,
) -> str:
    """Resolve endpoint priority: explicit arg, env var, then stable manifest."""

    base_url = explicit_base_url or os.environ.get(env_var, "")
    if base_url:
        return base_url.rstrip("/")

    manifest = manifest_url or os.environ.get(
        "CELL_RAG_ENDPOINT_MANIFEST_URL", DEFAULT_ENDPOINT_MANIFEST_URL
    )
    with urllib.request.urlopen(manifest, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    discovered = str(payload.get("base_url", "")).strip()
    if not discovered:
        raise RuntimeError(f"Endpoint manifest did not contain base_url: {manifest}")
    return discovered.rstrip("/")
