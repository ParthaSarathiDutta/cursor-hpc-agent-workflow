#!/usr/bin/env python3
"""CLI: python -m blast_lib.property_comparison <build|plot|validate|regenerate> --config PATH"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from blast_lib.property_comparison.config import load_config
from blast_lib.property_comparison.pipeline import build_outputs, plot_outputs, validate_outputs_strict
from blast_lib.property_comparison.validate import validate_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BLAST parameter-set property comparison")
    parser.add_argument("command", choices=["build", "plot", "validate", "regenerate"])
    parser.add_argument("--config", type=Path, required=True, help="comparison.json config file")
    parser.add_argument(
        "--allow-missing-elastic",
        action="store_true",
        help="Do not require elastic predictions for every potential (validate only)",
    )
    args = parser.parse_args(argv)
    config = load_config(args.config.resolve())

    if args.command == "build":
        build_outputs(config)
        return 0
    if args.command == "plot":
        plot_outputs(config)
        return 0
    if args.command == "validate":
        errs = validate_outputs(config, require_elastic_values=not args.allow_missing_elastic)
        if errs:
            for e in errs:
                print("FAIL:", e, file=sys.stderr)
            return 1
        print("Validation OK")
        return 0
    if args.command == "regenerate":
        build_outputs(config)
        plot_outputs(config)
        errs = validate_outputs(config, require_elastic_values=not args.allow_missing_elastic)
        if errs:
            for e in errs:
                print("FAIL:", e, file=sys.stderr)
            return 1
        print("Regenerate OK")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
