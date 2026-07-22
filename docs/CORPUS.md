# Corpus

The default runtime corpus is the combined RAG corpus configured in `.env`.
The older Cell Ontology-only corpus still exists for focused debugging, but it is
not the default runtime target.

## Runtime Files

- `chunks/rag_chunks.jsonl`: combined retrievable text chunks.
- `processed/rag_aliases.jsonl`: combined aliases for exact matching.
- `embeddings/rag_qwen3_embedding_8b.npz`: Qwen3 embedding matrix.
- `embeddings/rag_qwen3_embedding_8b.metadata.json`: row metadata aligned to the embedding matrix.
- `embeddings/rag_qwen3_embedding_8b.manifest.json`: text hashes and reuse status for each embedded chunk.
- `embeddings/rag_qwen3_embedding_8b.summary.json`: embedding build summary.
- `sources/source_registry.json`: server-side source provenance, license, scope, and intended use.

These runtime files are kept on CCI. They are intentionally excluded from the
GitHub repo so a mentor can clone the code and call the hosted API without
downloading models or rebuilding source artifacts.

Current combined embedding summary:

- chunks: `325,815`
- aliases: `2,712,338`
- embedding dimension: `4,096`
- embedding model: `models/Qwen3-Embedding-8B`
- pooling: last-token pooling
- normalized vectors: yes

## Active Sources

| Source | Source type | Purpose | Chunks |
|---|---|---|---:|
| Cell Ontology | `cell_ontology` | Cell type names, IDs, definitions, synonyms, hierarchy, and relationships. | `3,335` |
| Uberon | `anatomy_ontology` | Anatomy, tissue, and organ terms used as biological context. | `14,977` |
| Gene Ontology | `gene_ontology` | Biological process, molecular function, and cellular component definitions. | `38,245` |
| PATO | `phenotype_quality_ontology` | Phenotype quality terms such as color, size, and morphology qualities. | `1,887` |
| CELLxGENE Census | `single_cell_atlas_metadata` | Aggregated cell type/tissue/disease/assay evidence from Census `obs` metadata. | `975` |
| HGNC | `gene_nomenclature` | Official human gene symbols, names, aliases, previous symbols, and cross-references. | `45,021` |
| NCBI Gene Human | `gene_reference` | Entrez Gene IDs, symbols, synonyms, descriptions, chromosome/map location, gene type, and cross-references. | `193,802` |
| UniProtKB Reviewed Human | `protein_function` | Reviewed human protein names, function comments, GO IDs, and cross-references. | `20,431` |
| CellMarker 3.0 | `cell_marker_database` | Cell-type marker gene sets by species, tissue, disease context, method, PMID, and ontology ID. | `6,801` |
| PanglaoDB | `cell_marker_database` | Curated mouse/human marker gene associations with organ, germ-layer, sensitivity, and specificity fields. | `341` |

## Source Links

The source registry JSON is server-side and ignored by Git. These public links
are included here so the repo still documents provenance without committing
source-data snapshots.

| Source | Homepage | Access | License |
|---|---|---|---|
| Cell Ontology | [OBO Foundry CL](https://obofoundry.org/ontology/cl.html) | [cl.obo](http://purl.obolibrary.org/obo/cl.obo) | CC BY 4.0 |
| Uberon | [OBO Foundry Uberon](https://obofoundry.org/ontology/uberon.html) | [uberon.obo](https://purl.obolibrary.org/obo/uberon.obo) | CC BY 3.0 |
| Gene Ontology | [GO Downloads](https://geneontology.org/docs/download-ontology/) | [go.obo](https://current.geneontology.org/ontology/go.obo) | CC BY 4.0 |
| PATO | [OBO Foundry PATO](https://obofoundry.org/ontology/pato.html) | [pato.obo](https://raw.githubusercontent.com/pato-ontology/pato/master/pato.obo) | CC BY 4.0 |
| CELLxGENE Census | [Census Docs](https://chanzuckerberg.github.io/cellxgene-census/) | Python API: `cellxgene_census.open_soma` | CC BY 4.0 |
| HGNC | [HGNC](https://www.genenames.org/) | [complete set JSON](https://storage.googleapis.com/public-download-files/hgnc/json/json/hgnc_complete_set.json) | free use with attribution |
| NCBI Gene Human | [NCBI Gene](https://www.ncbi.nlm.nih.gov/gene/) | [Homo_sapiens.gene_info.gz](https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Homo_sapiens.gene_info.gz) | public domain / cite NCBI Gene |
| UniProtKB Reviewed Human | [UniProt](https://www.uniprot.org/) | [UniProt REST search](https://rest.uniprot.org/uniprotkb/search?query=organism_id:9606%20AND%20reviewed:true) | CC BY 4.0 |
| CellMarker 3.0 | [CellMarker](https://bio-bigdata.hrbmu.edu.cn/CellMarker/) | [all_cell_marker.zip](https://bio-bigdata.hrbmu.edu.cn/CellMarker/file/all_cell_marker.zip) | academic use; verify CellMarker terms |
| PanglaoDB | [PanglaoDB Markers](https://panglaodb.se/markers.html?cell_type=%27choose%27) | [PanglaoDB markers TSV](https://panglaodb.se/markers/PanglaoDB_markers_27_Mar_2020.tsv.gz) | free download; cite PanglaoDB Database 2019 |

## Source Roles

The sources intentionally overlap. The RAG server uses source-aware ranking to
prefer the right source type for the query:

- Cell type definition questions should prefer Cell Ontology.
- Tissue/anatomy questions should prefer Uberon.
- Biological-process/function ontology questions should prefer GO.
- Phenotype-quality questions should prefer PATO.
- Atlas evidence questions should prefer CELLxGENE Census.
- Official gene-symbol and alias questions should prefer HGNC.
- Entrez ID, chromosome, map-location, and gene-description questions should prefer NCBI Gene.
- Protein function questions should prefer UniProt.
- Cell annotation marker questions should prefer CellMarker or PanglaoDB.

## CELLxGENE Census Scope

The current CELLxGENE source is summarized from Census `obs` metadata. Each row
is an aggregated evidence group, not an individual cell and not a full
expression matrix.

Current scope:

- organism: `homo_sapiens`
- Census version: `2025-11-17`
- primary-data filter enabled
- top `200` human primary-data cell types
- top `5` tissue/disease/assay evidence groups per cell type
- minimum unique cells per selected cell type: `1,000`
- output chunks: `975`

Each CELLxGENE chunk includes:

- cell type and Cell Ontology ID
- organism
- Census version
- cell count
- dataset count
- tissue and Uberon tissue ID
- disease label
- assay label

This source is appropriate for atlas-presence questions, such as whether a cell
type appears in a tissue/disease/assay combination. It is not currently designed
to answer dataset-title, publication-link, donor-level, expression-matrix,
marker-expression, or differential-expression questions.

Those richer CELLxGENE extensions are intentionally left out for now.

## Older Cell Ontology-Only Corpus

The Cell Ontology-only artifacts still exist:

- `processed/cl_terms.jsonl`
- `processed/cl_aliases.jsonl`
- `chunks/cl_chunks.jsonl`
- `embeddings/cl_qwen3_embedding_8b.npz`
- `embeddings/cl_qwen3_embedding_8b.metadata.json`

They are useful for ontology-only debugging and rebuilds, but the runtime `.env`
points at the combined corpus.

## Current Known Gaps

- Evaluation is still smoke-level. It now covers all active source families, but
  it is not yet a full quality benchmark. Use `scripts/audit_all.sh` to create a
  saved reproducibility report for the current smoke-test coverage.
- CELLxGENE remains summarized by design; provenance and expression-level
  expansion are deferred.
- Literature sources are not yet included. Adding full-text literature will need
  tighter citation handling, licensing controls, and broader evaluation.
- Vector retrieval supports exact in-process NumPy search and an optional FAISS
  ANN index. A managed vector database such as Chroma or Milvus is still
  deferred because the current hosted demo scale is manageable on CCI.

## Extending The Corpus

Additional documents can be supplied as JSONL with `doc_id`, `title`, `text`,
optional `aliases`, and optional `metadata`.

Example:

```json
{"doc_id":"paper:1","title":"Example","text":"Document text...","aliases":["optional alias"],"metadata":{"source":"optional"}}
```

Use `scripts/build_extra_jsonl_corpus.sh` for ad hoc JSONL additions.

Use `scripts/build_combined_rag_with_cellxgene.sh` to rebuild the maintained
combined corpus from the active source chunk and alias files.
