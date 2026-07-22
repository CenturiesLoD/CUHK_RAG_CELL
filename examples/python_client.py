#!/usr/bin/env python3
"""Minimal client for the hosted Cell RAG API."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the hosted Cell RAG API.")
    parser.add_argument("--base-url", default=os.environ.get("CELL_RAG_DEMO_URL", "http://127.0.0.1:8020"))
    parser.add_argument("--api-key", default=os.environ.get("CELL_RAG_DEMO_API_KEY", ""))
    parser.add_argument("--question", default="What is a regulatory T cell?")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=300)
    args = parser.parse_args()

    payload = json.dumps(
        {"question": args.question, "top_k": args.top_k, "max_tokens": args.max_tokens}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/ask",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {body}") from exc

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
