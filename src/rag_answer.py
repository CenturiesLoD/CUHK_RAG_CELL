#!/usr/bin/env python3
"""Generate cited RAG answers from the local hybrid retrieval service."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

DEFAULT_SEARCH_URL = "http://127.0.0.1:8010/search"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL = "qwen3-32b"

SYSTEM_PROMPT = """You answer single-cell biology questions using only the retrieved context.
Rules:
- Use only facts supported by the retrieved context.
- Cite every factual sentence with one or more retrieved source block IDs.
- Use only source block IDs shown at the start of retrieved context blocks as citations. Do not cite related IDs that only appear inside the body text unless they are also source block IDs.
- Repeat citations on every sentence that makes a factual claim. Do not use one citation at the end of a paragraph to cover earlier uncited sentences.
- For CELLxGENE evidence, cite the full source block ID such as [cellxgene_census:cl_0000815:uberon_0000178:normal:10x_3_v2:316], not shorter embedded IDs such as [CL:0000815] or [UBERON:0000178].
- If the context does not contain enough information, say that the retrieved context is insufficient.
- Keep the answer concise and directly address the question.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Answer a question using Cell RAG retrieval and an LLM.")
    parser.add_argument("query", help="Question to answer.")
    parser.add_argument("--search-url", default=DEFAULT_SEARCH_URL)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--base-url", default=os.environ.get("LUOSS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("LUOSS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-key-env", default="LUOSS_API_KEY")
    parser.add_argument("--fallback-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--max-context-chars", type=int, default=9000)
    parser.add_argument("--dry-run", action="store_true", help="Print retrieval/context prompt without calling the LLM.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    return parser.parse_args()


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def post_json(url: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def retrieve(search_url: str, query: str, top_k: int) -> list[dict[str, Any]]:
    data = post_json(search_url, {"query": query, "top_k": top_k})
    return list(data.get("results", []))


def build_context(results: list[dict[str, Any]], max_chars: int) -> str:
    blocks: list[str] = []
    used = 0
    for result in results:
        doc_id = result.get("doc_id")
        title = result.get("title")
        score = result.get("score")
        text = str(result.get("text") or "")
        block = f"Source block ID: [{doc_id}]\nTitle: {title}\nRetrieval score: {score}\n{text}".strip()
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining <= 200:
                break
            block = block[:remaining].rstrip() + "\n[truncated]"
        blocks.append(block)
        used += len(block) + 2
        if used >= max_chars:
            break
    return "\n\n".join(blocks)


def build_messages(query: str, context: str) -> list[dict[str, str]]:
    user_prompt = f"""Question:
{query}

Retrieved context:
{context}

Answer with citations using only the retrieved source block IDs shown in square brackets at the start of context blocks. Every factual sentence must include its own citation."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def get_api_key(args: argparse.Namespace) -> str | None:
    return os.environ.get(args.api_key_env) or os.environ.get(args.fallback_api_key_env)


def call_chat(args: argparse.Namespace, messages: list[dict[str, str]]) -> str:
    api_key = get_api_key(args)
    if not api_key:
        raise RuntimeError(
            f"Missing API key. Set {args.api_key_env} or {args.fallback_api_key_env}, "
            "or run with --dry-run to inspect retrieval/context only."
        )
    url = args.base_url.rstrip("/") + "/chat/completions"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": args.model,
            "messages": messages,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        },
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def compact_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": item.get("rank"),
            "doc_id": item.get("doc_id"),
            "title": item.get("title"),
            "score": item.get("score"),
            "reasons": item.get("reasons", []),
        }
        for item in results
    ]


def main() -> int:
    args = parse_args()
    load_dotenv()

    results = retrieve(args.search_url, args.query, args.top_k)
    context = build_context(results, args.max_context_chars)
    messages = build_messages(args.query, context)

    if args.dry_run:
        output = {
            "query": args.query,
            "sources": compact_sources(results),
            "messages": messages,
        }
        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print("Retrieved sources:")
            for source in output["sources"]:
                print(f"- [{source['doc_id']}] {source['title']} score={source['score']} reasons={'; '.join(source['reasons'])}")
            print("\nPrompt messages:")
            for message in messages:
                print(f"\n--- {message['role'].upper()} ---\n{message['content']}")
        return 0

    try:
        answer = call_chat(args, messages)
    except Exception as exc:
        print(f"LLM call failed: {exc}", file=sys.stderr)
        print("Retrieved sources were:", file=sys.stderr)
        for source in compact_sources(results):
            print(f"- [{source['doc_id']}] {source['title']} score={source['score']}", file=sys.stderr)
        return 2

    output = {"query": args.query, "answer": answer, "sources": compact_sources(results)}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(answer)
        print("\nSources:")
        for source in output["sources"]:
            print(f"- [{source['doc_id']}] {source['title']} score={source['score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
