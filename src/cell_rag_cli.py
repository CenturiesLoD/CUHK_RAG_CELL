#!/usr/bin/env python3
"""Interactive user-mode terminal for the hosted single-cell RAG API."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from src.hosted_endpoint import resolve_base_url


DEFAULT_QUESTION = "What is a regulatory T cell?"
DEFAULT_TOP_K = 5
DEFAULT_MAX_TOKENS = 350


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def color(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def title(self, text: str) -> str:
        return self.color(text, "1;36")

    def label(self, text: str) -> str:
        return self.color(text, "1;37")

    def muted(self, text: str) -> str:
        return self.color(text, "2")

    def error(self, text: str) -> str:
        return self.color(text, "1;31")


@dataclass
class ChatConfig:
    base_url: str
    api_key: str
    top_k: int
    max_tokens: int
    show_sources: bool
    timeout: int
    style: Style


def terminal_width(default: int = 88) -> int:
    return max(64, min(shutil.get_terminal_size((default, 24)).columns, 120))


def wrap_text(text: str, *, indent: str = "", width: int | None = None) -> str:
    width = width or terminal_width()
    paragraphs = str(text or "").strip().splitlines() or [""]
    wrapped: list[str] = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            wrapped.append("")
            continue
        wrapped.append(
            textwrap.fill(
                paragraph,
                width=width,
                initial_indent=indent,
                subsequent_indent=indent,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return "\n".join(wrapped)


def request_json(
    method: str,
    url: str,
    *,
    api_key: str = "",
    payload: dict[str, Any] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
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
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            raise RuntimeError(
                "API key was rejected. Refresh CELL_RAG_DEMO_API_KEY or pass --api-key."
            ) from exc
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach the hosted API at {url}: {exc.reason}\n"
            "If the backend is stopped or the tunnel URL is stale, restart and publish it:\n"
            "  cd <CCI_RUNTIME_DIR> && scripts/init_public_demo.sh --publish-endpoint"
        ) from exc


def prompt_api_key(existing: str) -> str:
    if existing:
        return existing
    if not sys.stdin.isatty():
        raise RuntimeError("Set CELL_RAG_DEMO_API_KEY or pass --api-key.")
    value = getpass.getpass("API key: ").strip()
    if not value:
        raise RuntimeError("No API key provided.")
    return value


def format_sources(sources: list[dict[str, Any]], *, style: Style, limit: int = 5) -> str:
    if not sources:
        return ""

    lines = [style.label("Sources")]
    for index, source in enumerate(sources[:limit], start=1):
        doc_id = str(source.get("doc_id") or "unknown")
        title = str(source.get("title") or "untitled")
        source_id = str(source.get("source_id") or source.get("source_type") or "source")
        lines.append(f"  {index}. {doc_id} | {title} | {source_id}")
    return "\n".join(lines)


def format_answer(response: dict[str, Any], *, style: Style, show_sources: bool) -> str:
    answer = str(response.get("answer") or "").strip()
    retrieval_quality = response.get("retrieval_quality") or {}
    citation_check = response.get("citation_check") or {}
    sources = response.get("sources") or []

    lines = [style.title("Answer")]
    lines.append(wrap_text(answer or "No answer text returned."))

    confidence = retrieval_quality.get("confidence")
    if confidence:
        lines.append("")
        lines.append(f"{style.label('Confidence')}: {confidence}")

    if citation_check:
        status = "passed" if citation_check.get("passed") else "needs review"
        lines.append(f"{style.label('Citation check')}: {status}")

    if show_sources:
        rendered_sources = format_sources(sources, style=style)
        if rendered_sources:
            lines.append("")
            lines.append(rendered_sources)

    return "\n".join(lines)


def ask_question(question: str, config: ChatConfig) -> dict[str, Any]:
    payload = {
        "question": question,
        "top_k": config.top_k,
        "max_tokens": config.max_tokens,
    }
    return request_json(
        "POST",
        f"{config.base_url}/ask",
        api_key=config.api_key,
        payload=payload,
        timeout=config.timeout,
    )


def print_help(style: Style) -> None:
    print(style.title("Commands"))
    print("  /help       show this help")
    print("  /sources    toggle compact source list")
    print("  /example    ask a default example question")
    print("  /clear      clear the screen")
    print("  /exit       leave user mode")


def run_interactive(config: ChatConfig) -> int:
    print(config.style.title("SLAI RAG Cell - User Mode"))
    print(config.style.muted(f"Endpoint: {config.base_url}"))
    print(config.style.muted("Ask a single-cell biology question. Type /help for commands."))
    print()

    while True:
        try:
            question = input(config.style.label("rag> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not question:
            continue

        command = question.lower()
        if command in {"/exit", "/quit", "exit", "quit"}:
            return 0
        if command == "/help":
            print_help(config.style)
            print()
            continue
        if command == "/sources":
            config.show_sources = not config.show_sources
            state = "on" if config.show_sources else "off"
            print(config.style.muted(f"Source display: {state}"))
            print()
            continue
        if command == "/example":
            question = DEFAULT_QUESTION
        elif command == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        print(config.style.muted("Thinking..."))
        try:
            response = ask_question(question, config)
            print(format_answer(response, style=config.style, show_sources=config.show_sources))
        except Exception as exc:
            print(config.style.error(str(exc)))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the clean interactive user-mode CLI for SLAI RAG Cell."
    )
    parser.add_argument("--base-url", default=os.environ.get("CELL_RAG_DEMO_URL", ""))
    parser.add_argument("--api-key", default=os.environ.get("CELL_RAG_DEMO_API_KEY", ""))
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--show-sources", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument(
        "--question",
        default="",
        help="Ask one question and exit. Omit this flag to enter user mode.",
    )
    args = parser.parse_args()

    style = Style(enabled=not args.no_color and sys.stdout.isatty())
    config = ChatConfig(
        base_url=resolve_base_url(args.base_url),
        api_key=prompt_api_key(args.api_key),
        top_k=args.top_k,
        max_tokens=args.max_tokens,
        show_sources=args.show_sources,
        timeout=args.timeout,
        style=style,
    )

    if args.question:
        response = ask_question(args.question, config)
        print(format_answer(response, style=style, show_sources=args.show_sources))
        return 0

    return run_interactive(config)
