"""parody CLI: build | check (init, watch, preview arrive in Phase 2)."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def cmd_build(args):
    from .writers.artifact import convert_notebook

    convert_notebook(
        args.input_dir,
        args.output,
        convert_jupytext=not args.no_execute,
        media_root=args.media_root,
    )
    return 0


def cmd_check(args):
    if args.toolchain:
        from .toolchain import PANDOC_VERSION, check_pandoc

        ok, local = check_pandoc(warn=False)
        print(f"pandoc: pinned {PANDOC_VERSION}, local {local or 'not found'}"
              f" {'✓' if ok else '✗'}")
        return 0 if ok else 1

    if not args.artifact:
        print("error: provide an artifact path or --toolchain", file=sys.stderr)
        return 2

    import jsonschema

    schema_path = Path(__file__).parent / "schemas" / "artifact-v1.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    with open(args.artifact, encoding="utf-8") as f:
        artifact = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    if errors:
        for err in errors:
            loc = "/".join(str(p) for p in err.path) or "<root>"
            print(f"✗ {loc}: {err.message}")
        return 1
    print(f"✓ {args.artifact} is a valid schema-v1 artifact")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="parody",
        description="Unified book/notebook toolchain (a play on parity).",
    )
    parser.add_argument("--version", action="version", version=f"parody {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="build the JSON artifact from a notebook source dir")
    p_build.add_argument("input_dir", help="notebook source directory (contains __meta.yaml)")
    p_build.add_argument("output", help="output JSON artifact path")
    p_build.add_argument("--no-execute", action="store_true",
                         help="skip jupytext conversion/execution; use existing .md files")
    p_build.add_argument("--media-root",
                         help="directory to receive media/notebooks/<slug>/ code-file copies")
    p_build.set_defaults(func=cmd_build)

    p_check = sub.add_parser("check", help="validate an artifact against the schema")
    p_check.add_argument("artifact", nargs="?", help="artifact JSON path")
    p_check.add_argument("--toolchain", action="store_true",
                         help="check local toolchain versions against the pins")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
