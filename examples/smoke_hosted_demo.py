#!/usr/bin/env python3
"""Dependency-free smoke test for the hosted Cell RAG API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from endpoint_discovery import resolve_base_url


HOSTED_BACKEND_RECOVERY_HINT = """Hosted backend may be down or the published tunnel URL may be stale.
If you have CCI SSH access, restart and republish the hosted stack:

Linux/macOS:
ssh -p <CCI_SSH_PORT> -i /path/to/private_key <CCI_USER>@<CCI_HOST> \\
  "cd <CCI_RUNTIME_DIR> && scripts/init_public_demo.sh --publish-endpoint"

Windows PowerShell:
ssh -p <CCI_SSH_PORT> -i C:\\path\\to\\private_key <CCI_USER>@<CCI_HOST> "cd <CCI_RUNTIME_DIR> && scripts/init_public_demo.sh --publish-endpoint"

Then rerun:
python examples/smoke_hosted_demo.py"""


def request_json(
    method: str,
    url: str,
    *,
    api_key: str = "",
    payload: dict | None = None,
    expect_error: set[int] | None = None,
    timeout: int = 300,
) -> tuple[int, dict | str]:
    headers = {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if expect_error and exc.code in expect_error:
            return exc.code, body
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the hosted Cell RAG API.")
    parser.add_argument("--base-url", default=os.environ.get("CELL_RAG_DEMO_URL", ""))
    parser.add_argument("--api-key", default=os.environ.get("CELL_RAG_DEMO_API_KEY", ""))
    parser.add_argument("--question", default="What is a regulatory T cell?")
    args = parser.parse_args()

    base_url = resolve_base_url(args.base_url)
    errors: list[str] = []

    health_status, health = request_json("GET", f"{base_url}/health", timeout=60)
    examples_status, examples = request_json("GET", f"{base_url}/examples", timeout=60)
    unauth_status, _ = request_json(
        "POST",
        f"{base_url}/ask",
        payload={"question": args.question, "top_k": 1, "max_tokens": 64},
        expect_error={401, 403},
        timeout=60,
    )

    if not args.api_key:
        errors.append("missing API key for authenticated endpoints")
        answer = {}
        greeting_answer = {}
        search = {}
        greeting_search = {}
    else:
        _, answer = request_json(
            "POST",
            f"{base_url}/ask",
            api_key=args.api_key,
            payload={"question": args.question, "top_k": 3, "max_tokens": 180},
        )
        _, greeting_answer = request_json(
            "POST",
            f"{base_url}/ask",
            api_key=args.api_key,
            payload={"question": "hi", "top_k": 3, "max_tokens": 80},
        )
        _, search = request_json(
            "POST",
            f"{base_url}/search",
            api_key=args.api_key,
            payload={"query": args.question, "top_k": 3},
            timeout=120,
        )
        _, greeting_search = request_json(
            "POST",
            f"{base_url}/search",
            api_key=args.api_key,
            payload={"query": "hi", "top_k": 3},
            timeout=120,
        )

        if not answer.get("answer"):
            errors.append("authenticated /ask returned no answer")
        if not answer.get("sources"):
            errors.append("authenticated /ask returned no sources")
        if not answer.get("citation_check", {}).get("passed"):
            errors.append("citation_check did not pass")
        if not search.get("results"):
            errors.append("authenticated /search returned no results")
        greeting_text = str(greeting_answer.get("answer", ""))
        if "[" in greeting_text or greeting_answer.get("sources"):
            errors.append("conversational greeting returned citations or sources")
        if not greeting_answer.get("citation_check", {}).get("passed"):
            errors.append("conversational greeting citation_check did not pass")
        if greeting_search.get("results"):
            errors.append("conversational search returned retrieval results")

    if health_status != 200:
        errors.append(f"/health status was {health_status}")
    if examples_status != 200:
        errors.append(f"/examples status was {examples_status}")
    if unauth_status not in {401, 403}:
        errors.append(f"unauthenticated /ask was not rejected: {unauth_status}")

    summary = {
        "base_url": base_url,
        "health": health,
        "example_count": len(examples.get("examples", [])) if isinstance(examples, dict) else 0,
        "unauthenticated_ask_status": unauth_status,
        "answer_preview": str(answer.get("answer", ""))[:220] if isinstance(answer, dict) else "",
        "citation_check": answer.get("citation_check") if isinstance(answer, dict) else None,
        "greeting_answer": greeting_answer.get("answer") if isinstance(greeting_answer, dict) else None,
        "greeting_citation_check": greeting_answer.get("citation_check") if isinstance(greeting_answer, dict) else None,
        "greeting_search_result_count": len(greeting_search.get("results", [])) if isinstance(greeting_search, dict) else None,
        "ask_source_ids": [
            source.get("doc_id") for source in answer.get("sources", [])
        ]
        if isinstance(answer, dict)
        else [],
        "search_result_ids": [
            result.get("doc_id") for result in search.get("results", [])
        ]
        if isinstance(search, dict)
        else [],
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "errors": [str(exc)],
                    "recovery_hint": HOSTED_BACKEND_RECOVERY_HINT,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)
