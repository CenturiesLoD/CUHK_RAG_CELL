#!/usr/bin/env python3
"""Rebuild CELLxGENE aliases and chunks from existing processed count rows."""

from __future__ import annotations

import json
from pathlib import Path

from build_cellxgene_census_top_celltypes import make_aliases, make_chunks, write_jsonl


SOURCE_ID = "cellxgene_census"
IN_PATH = Path("processed/cellxgene_census_human_primary_counts.jsonl")
OUT_PATH = Path("processed/cellxgene_census_human_primary_aliases.jsonl")
CHUNKS_OUT_PATH = Path("chunks/cellxgene_census_human_primary_chunks.jsonl")


rows = [json.loads(line) for line in IN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
aliases = make_aliases(rows, SOURCE_ID)
chunks = make_chunks(rows, SOURCE_ID)
write_jsonl(OUT_PATH, aliases)
write_jsonl(CHUNKS_OUT_PATH, chunks)
print(
    json.dumps(
        {
            "input_rows": len(rows),
            "aliases_written": len(aliases),
            "chunks_written": len(chunks),
            "aliases_out": str(OUT_PATH),
            "chunks_out": str(CHUNKS_OUT_PATH),
        },
        indent=2,
    )
)
