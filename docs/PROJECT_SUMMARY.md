# Single-Cell RAG Project Summary

## Project Goal

This project builds a domain-specific retrieval-augmented generation system for
single-cell biology. It collects structured and text-heavy biological knowledge,
turns it into retrievable chunks, embeds those chunks with Qwen3-Embedding-8B,
and serves cited answers through a local RAG API backed by Qwen3-32B.

The current system supports the internship prompt scenarios:

- single-cell foundational knowledge questions;
- cell-type definition and synonym lookup;
- cell-type annotation and marker lookup;
- gene-symbol normalization and alias resolution;
- gene/protein function Q&A;
- atlas evidence questions using summarized CELLxGENE Census metadata;
- abstention when retrieved evidence is insufficient.

## Active Sources

| Source | Source type | Main role |
|---|---|---|
| Cell Ontology | `cell_ontology` | Cell type IDs, names, definitions, synonyms, hierarchy, relationships. |
| Uberon | `anatomy_ontology` | Tissue, organ, and anatomy context. |
| Gene Ontology | `gene_ontology` | Biological process, molecular function, and cellular component definitions. |
| PATO | `phenotype_quality_ontology` | Phenotype quality terms such as size, color, shape, and morphology. |
| CELLxGENE Census | `single_cell_atlas_metadata` | Aggregated cell type, tissue, disease, assay, cell-count, and dataset-count evidence. |
| HGNC | `gene_nomenclature` | Official human gene symbols, names, aliases, previous symbols, and cross-references. |
| NCBI Gene Human | `gene_reference` | Entrez IDs, chromosomes, map locations, gene descriptions, and gene metadata. |
| UniProtKB Reviewed Human | `protein_function` | Reviewed protein names, function comments, GO links, and cross-references. |
| CellMarker 3.0 | `cell_marker_database` | Marker gene sets by cell type, species, tissue, disease, method, and PMID. |
| PanglaoDB | `cell_marker_database` | Curated mouse/human marker gene associations and marker evidence fields. |

## Build Pipeline

Each source follows the same general shape:

```text
raw source file or API export
  -> normalized processed records
  -> aliases for exact matching
  -> retrievable text chunks
  -> combined chunks and aliases
  -> Qwen3 embedding matrix
  -> optional FAISS ANN vector index
  -> optional neural reranker
  -> answer grounding and citation audit
  -> public API wrapper
  -> live RAG API
```

Runtime artifacts:

- `chunks/rag_chunks.jsonl`
- `processed/rag_aliases.jsonl`
- `embeddings/rag_qwen3_embedding_8b.npz`
- `embeddings/rag_qwen3_embedding_8b.metadata.json`
- optional `embeddings/rag_qwen3_embedding_8b.ivfflat.faiss`
- optional `models/ms-marco-MiniLM-L-6-v2`
- server-side `sources/source_registry.json`

These runtime artifacts stay on CCI and are not committed to the GitHub repo.
The repo is meant to carry implementation, docs, examples, and tests; the hosted
CCI backend carries the large model and corpus state.

Current combined index:

- chunks: `325,815`
- aliases: `2,712,338`
- embedding shape: `[325815, 4096]`
- embedding model: `models/Qwen3-Embedding-8B`
- answer model: local `qwen3-32b` served through vLLM
- public API wrapper on `127.0.0.1:8020`

## Retrieval And Ranking

The search API combines:

- exact alias/name/ID matching;
- BM25-style lexical scoring;
- Qwen3 vector similarity, either exact NumPy search or optional FAISS ANN candidate search;
- lightweight lexical reranking;
- optional neural cross-encoder reranking over the strongest hybrid candidates;
- source-aware ranking.

Source-aware ranking chooses the likely source family for a query. For example:

- cell definition questions prefer Cell Ontology;
- tissue questions prefer Uberon;
- official gene-symbol questions prefer HGNC;
- Entrez/chromosome questions prefer NCBI Gene;
- protein-function questions prefer UniProt;
- marker questions prefer CellMarker or PanglaoDB;
- atlas evidence questions prefer CELLxGENE Census summaries.

When enabled, the neural reranker compares the question and each candidate
passage together. This is different from embedding search, where document
vectors are precomputed independently. The reranker is slower, but it can make a
better final top-K choice among candidates found by aliases, BM25, and vector
search.

## Answer Grounding

The answer endpoint retrieves context, calls the local LLM, and returns cited
answers. Grounding controls currently include:

- abstention for low-confidence retrieval;
- prompt rules requiring use of retrieved context only;
- source-block citations;
- deterministic cleanup for incomplete trailing generations;
- citation normalization so embedded IDs map back to retrieved source IDs when
  possible;
- structured `citation_check` output that lists retrieved source IDs, answer
  citations, invalid citations, uncited factual-looking claim units, and whether
  the final answer passed citation hygiene;
- answer evaluation that checks required citations, source routing, abstention,
  the API citation audit, and obvious uncited factual claims.

## Public Demonstration API

The public API wrapper is a lightweight layer around the internal RAG API. It
does not load a second model and it does not change retrieval behavior. It exposes:

- `GET /health` for readiness;
- `GET /examples` for suggested demo questions;
- `POST /ask` for cited answers with retrieval quality and citation checks;
- `POST /search` for retrieval-only inspection.

For external access, it is intended to be reached through the hosted CCI demo URL
created by `scripts/ensure_hosted_demo.sh`. SSH tunneling remains available for
local debugging.

## Validation

Primary commands:

```bash
scripts/smoke_all.sh
scripts/smoke_public_api.sh
scripts/audit_all.sh
scripts/run_demo_pack.sh
```

Current smoke coverage:

- main retrieval cases: `33`
- CELLxGENE retrieval cases: `5`
- main answer cases: `21`
- CELLxGENE answer cases: `2`

The audit command saves reproducibility logs under:

```text
reports/audits/<timestamp>/
```

The demo command saves curated showcase answers under:

```text
reports/demos/<timestamp>/
```

## Demo Pack

Run:

```bash
scripts/run_demo_pack.sh
```

The demo pack uses `demo/showcase_queries.jsonl`, currently covering:

- foundational single-cell definitions;
- ontology context;
- gene normalization;
- NCBI Gene reference lookup;
- UniProt protein function;
- cell marker lookup;
- CELLxGENE atlas evidence;
- abstention.

Outputs:

- `summary.txt`: pass/fail summary by category;
- `answers.jsonl`: machine-readable answers, sources, citations, and validation;
- `answers.md`: human-readable demo answers;
- status and startup logs.

## Known Limits

- The evaluation suite is still smoke-level, not a full scientific benchmark.
- CELLxGENE is summarized from `obs` metadata only. It does not yet include
  dataset titles, publication links, donor-level metadata, expression matrices,
  marker-expression evidence, or differential expression.
- Literature sources are not yet included. Adding PMC/Europe PMC/PubMed scale
  needs licensing controls, citation policies, and broader quality evaluation.
- Vector retrieval now supports an optional FAISS ANN backend, but the current
  BM25 helper still scans chunks in-process. Literature-scale ingestion should
  add a persistent lexical index and may eventually need a managed vector
  database or distributed FAISS.
- The default reranker is a general MiniLM cross-encoder, not a fine-tuned
  single-cell biology model. It improves query-passage relevance ranking, but it
  should still be evaluated before increasing its score weight.
