# Single-Cell RAG Benchmark

This benchmark is a small, auditable test set for showing whether the RAG is
good at its intended job: single-cell biology Q&A with grounded citations.

It is not a claim that this project beats every online research assistant on
all research tasks. The defensible claim is narrower:

> For curated single-cell biology questions, this RAG can be evaluated for
> domain-specific retrieval, citation grounding, source specificity, and
> guardrail behavior against general online alternatives.

## Files

- `eval/single_cell_benchmark.jsonl`: curated benchmark cases.
- `src/evaluate_single_cell_benchmark.py`: hosted API runner for this RAG.
- `scripts/run_single_cell_benchmark.sh`: Linux/macOS wrapper for the runner.
- `eval/online_baseline_scores_template.csv`: manual scoring sheet for online
  systems such as Perplexity, Elicit, SciSpace, or Consensus.

## Case Types

The benchmark covers:

- `guardrail_chat`: casual or non-domain prompts should not retrieve or cite.
- `cell_type_definition`: Cell Ontology style cell-type questions.
- `ontology_id_lookup`: exact ontology ID lookup.
- `gene_ontology` and `phenotype_ontology`: GO/PATO definition questions.
- `gene_normalization`: HGNC symbol and alias resolution.
- `gene_reference`: NCBI Gene-style identifier questions.
- `protein_function`: UniProt-style protein function questions.
- `cell_marker_question`: CellMarker/PanglaoDB marker questions.
- `cellxgene_summary`: current CELLxGENE Census summary metadata questions.
- `cross_source_synthesis`: questions that should combine source families.
- `hard_negative`: questions where the system should avoid overclaiming.

## Run Against The Hosted RAG

Set the hosted API key in your shell first.

Windows PowerShell:

```powershell
$env:CELL_RAG_DEMO_API_KEY = "<api-key>"
python src\evaluate_single_cell_benchmark.py
```

Linux/macOS:

```bash
export CELL_RAG_DEMO_API_KEY="<api-key>"
scripts/run_single_cell_benchmark.sh
```

The runner discovers the current public endpoint from
`docs/current_endpoint.json`, unless `CELL_RAG_DEMO_URL` or `--base-url` is set.

Useful options:

```bash
python src/evaluate_single_cell_benchmark.py --limit 10
python src/evaluate_single_cell_benchmark.py --category guardrail_chat
python src/evaluate_single_cell_benchmark.py --json
python src/evaluate_single_cell_benchmark.py --output reports/benchmark/latest.json
```

If the hosted URL is stale or unreachable, restart and publish the stack on CCI:

```bash
cd <runtime-dir>
scripts/init_public_demo.sh --publish-endpoint
```

## Compare With Online Alternatives

Use the same questions from `eval/single_cell_benchmark.jsonl`.

For each external system, paste the answer or a share link into
`eval/online_baseline_scores_template.csv`, then score manually:

| Metric | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| correctness | wrong | partly wrong | mostly right | right |
| citation_support | no support | weak/irrelevant | mostly supports | directly supports claims |
| source_specificity | generic | some source info | useful source IDs/names | precise, traceable source IDs |
| scope_handling | unsafe overclaim | weak caveats | mostly scoped | clearly scoped/abstains when needed |
| hallucination_penalty | severe | moderate | minor | none observed |

Suggested systems to compare:

- this RAG;
- Qwen3-32B without RAG, if available;
- Perplexity;
- Elicit;
- SciSpace;
- Consensus.

For a credible presentation, blind the system names during grading if possible.
Even one reviewer grading 30-50 cases is stronger than a vague claim that the
RAG is "better."

## What A Good Result Means

A good result means the RAG is strong on the project-specific task:

- it retrieves the expected single-cell source family;
- cited IDs are present in retrieved sources;
- answers include expected biological facts;
- casual or out-of-scope prompts do not get random biomedical citations;
- hard-negative questions produce caveats instead of unsupported claims.

It does not prove broader literature coverage, current-paper discovery, or
general research superiority over dedicated literature tools.
