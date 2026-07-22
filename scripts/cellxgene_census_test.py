#!/usr/bin/env python3
"""Small CELLxGENE Census API smoke test.

Queries human primary regulatory T cells in blood, prints raw metadata rows,
then prints grouped RAG-friendly summary rows.
"""

from __future__ import annotations

import json

import cellxgene_census


CENSUS_VERSION = "latest"
COLUMNS = [
    "cell_type",
    "cell_type_ontology_term_id",
    "tissue",
    "tissue_ontology_term_id",
    "tissue_general",
    "tissue_general_ontology_term_id",
    "disease",
    "assay",
    "dataset_id",
    "is_primary_data",
]
VALUE_FILTER = (
    "is_primary_data == True "
    "and cell_type_ontology_term_id == 'CL:0000815' "
    "and tissue_ontology_term_id == 'UBERON:0000178'"
)


def main() -> int:
    with cellxgene_census.open_soma(census_version=CENSUS_VERSION) as census:
        obs = (
            census["census_data"]["homo_sapiens"]
            .obs.read(value_filter=VALUE_FILTER, column_names=COLUMNS)
            .concat()
            .to_pandas()
        )

    print("QUERY")
    print(json.dumps({"census_version": CENSUS_VERSION, "value_filter": VALUE_FILTER, "columns": COLUMNS}, indent=2))

    print("\nRAW_ROWS_SAMPLE")
    print(obs.head(5).to_json(orient="records", force_ascii=False, indent=2))

    group_cols = [
        "cell_type",
        "cell_type_ontology_term_id",
        "tissue",
        "tissue_ontology_term_id",
        "disease",
        "assay",
    ]
    summary = (
        obs.groupby(group_cols, dropna=False, observed=True)
        .agg(cell_count=("dataset_id", "size"), dataset_count=("dataset_id", "nunique"))
        .reset_index()
        .sort_values(["cell_count", "dataset_count"], ascending=False)
    )

    out_rows = []
    for record in summary.head(10).to_dict(orient="records"):
        out_rows.append(
            {
                "cell_type": record["cell_type"],
                "cell_type_ontology_term_id": record["cell_type_ontology_term_id"],
                "tissue": record["tissue"],
                "tissue_ontology_term_id": record["tissue_ontology_term_id"],
                "disease": record["disease"],
                "assay": record["assay"],
                "cell_count": int(record["cell_count"]),
                "dataset_count": int(record["dataset_count"]),
                "source_id": "cellxgene_census",
                "census_version": CENSUS_VERSION,
            }
        )

    print("\nSUMMARY_ROWS")
    print(json.dumps(out_rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
