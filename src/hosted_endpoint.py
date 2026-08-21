#!/usr/bin/env python3
"""Resolve the public hosted Cell RAG endpoint."""

from __future__ import annotations

import json
import os
import urllib.request
from base64 import b64decode


DEFAULT_ENDPOINT_MANIFEST_URL = (
    "https://api.github.com/repos/"
    "CenturiesLoD/CUHK_RAG_BACKEND/contents/docs/current_endpoint.json?ref=main"
)
RAW_ENDPOINT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "CenturiesLoD/CUHK_RAG_BACKEND/main/docs/current_endpoint.json"
)


def _load_manifest(manifest_url: str, timeout: int) -> dict[str, object]:
    request = urllib.request.Request(
        manifest_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "CUHK_RAG_BACKEND endpoint discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if "content" in payload:
        content = str(payload["content"])
        if payload.get("encoding") == "base64":
            content = b64decode(content).decode("utf-8")
        return json.loads(content)

    return payload


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
    try:
        payload = _load_manifest(manifest, timeout)
    except Exception:
        if manifest != DEFAULT_ENDPOINT_MANIFEST_URL:
            raise
        payload = _load_manifest(RAW_ENDPOINT_MANIFEST_URL, timeout)

    discovered = str(payload.get("base_url", "")).strip()
    if not discovered:
        raise RuntimeError(f"Endpoint manifest did not contain base_url: {manifest}")
    return discovered.rstrip("/")
