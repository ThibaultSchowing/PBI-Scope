#!/usr/bin/env python

import argparse
import csv
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "mergers"))
from schema_contracts import load_contract, normalize_df_schema


def infer_sep(path):
    suffix = Path(path).suffix.lower()
    if suffix in {".tsv", ".tab"}:
        return "\t"
    return ","


def main():
    parser = argparse.ArgumentParser(description="Report schema drift using a schema contract.")
    parser.add_argument("--contract", required=True, help="Path to schema contract YAML")
    parser.add_argument("--input", required=True, help="Path to CSV/TSV input file")
    parser.add_argument("--dataset-name", default=None, help="Optional dataset name for reporting")
    parser.add_argument("--sep", default=None, help="Delimiter override (default: inferred)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    sep = args.sep if args.sep is not None else infer_sep(args.input)

    contract = load_contract(args.contract)
    dataframe = pd.read_csv(args.input, sep=sep, quoting=csv.QUOTE_NONNUMERIC)

    try:
        _, report = normalize_df_schema(
            dataframe,
            contract,
            dataset_name=args.dataset_name or Path(args.input).name,
            logger=logging.getLogger(__name__),
        )
    except ValueError as exc:
        print("❌ Schema drift check failed")
        print(str(exc))
        return 1

    print("✅ Schema drift check passed")
    print(f"Missing optional before normalization: {report['missing_optional']}")
    print(f"Added optional columns: {report['added_optional']}")
    print(f"Aliases applied: {report['aliases_applied']}")
    print(f"Collisions: {report['collisions']}")
    print(f"Unknown columns preserved: {report['unknown_columns']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
