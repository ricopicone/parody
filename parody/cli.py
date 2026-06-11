"""parody CLI: init | build | preview | watch | check."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def cmd_init(args):
    from .scaffold import init_project

    init_project(args.directory, title=args.title, slug=args.slug, author=args.author)
    return 0


def cmd_build(args):
    from .build import build_project

    build_project(
        args.input_dir,
        args.output,
        convert_jupytext=not args.no_execute,
        media_root=args.media_root,
    )
    return 0


def cmd_preview(args):
    from .config import load_project
    from .writers.preview import write_preview

    project = load_project(args.project_dir)
    if args.artifact:
        artifact = args.artifact
    else:
        from .build import build_project

        artifact = build_project(
            args.project_dir,
            Path(args.output) / f"{project.slug}.json",
            convert_jupytext=args.execute,
            media_root=args.media_root,
        )
    write_preview(
        artifact,
        args.output,
        media_src=args.media_root or args.project_dir,
        bib_path=args.bib or project.bibliography,
        include_solutions=not args.no_solutions,
    )
    return 0


def cmd_watch(args):
    from .config import load_project
    from .watch import watch_project

    project = load_project(args.project_dir)
    artifact = args.artifact or Path(args.project_dir) / "artifact" / f"{project.slug}.json"
    watch_project(
        args.project_dir,
        artifact,
        preview_dir=args.preview,
        media_root=args.media_root,
        bib_path=args.bib,
    )
    return 0


def cmd_pdf(args):
    from .writers.latex import build_pdf

    if not args.no_execute:
        from .build import build_project
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            build_project(args.project_dir, Path(td) / "artifact.json",
                          convert_jupytext=True)
    build_pdf(
        args.project_dir,
        output_pdf=args.output,
        solutions=args.solutions,
        section=args.section,
        profile_dir=args.profile,
    )
    return 0


def cmd_check(args):
    if args.toolchain:
        from .toolchain import (PANDOC_CROSSREF_VERSION, PANDOC_VERSION,
                                check_pandoc, check_pandoc_crossref)

        ok, local = check_pandoc(warn=False)
        print(f"pandoc: pinned {PANDOC_VERSION}, local {local or 'not found'}"
              f" {'✓' if ok else '✗'}")
        xok, xlocal = check_pandoc_crossref(warn=False)
        print(f"pandoc-crossref: pinned {PANDOC_CROSSREF_VERSION}, "
              f"local {xlocal or 'not found'} {'✓' if xok else '✗'}")
        return 0 if ok and xok else 1

    if not args.artifact:
        print("error: provide an artifact path or --toolchain", file=sys.stderr)
        return 2

    import jsonschema

    with open(args.artifact, encoding="utf-8") as f:
        artifact = json.load(f)

    version = artifact.get("schema_version", 1)
    schema_path = Path(__file__).parent / "schemas" / f"artifact-v{version}.json"
    if not schema_path.is_file():
        print(f"error: unknown schema_version {version!r} "
              f"(no {schema_path.name})", file=sys.stderr)
        return 2
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    if errors:
        for err in errors:
            loc = "/".join(str(p) for p in err.path) or "<root>"
            print(f"✗ {loc}: {err.message}")
        return 1
    print(f"✓ {args.artifact} is a valid schema-v{version} artifact")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="parody",
        description="Unified book/notebook toolchain (a play on parity).",
    )
    parser.add_argument("--version", action="version", version=f"parody {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold a new content repo")
    p_init.add_argument("directory", help="target directory (created if missing)")
    p_init.add_argument("--title", help="work title (default: derived from slug)")
    p_init.add_argument("--slug", help="slug (default: directory name)")
    p_init.add_argument("--author", help="author name")
    p_init.set_defaults(func=cmd_init)

    p_build = sub.add_parser("build", help="build the JSON artifact")
    p_build.add_argument("input_dir", help="project directory (parody.yaml or legacy __meta.yaml)")
    p_build.add_argument("output", help="output JSON artifact path")
    p_build.add_argument("--no-execute", action="store_true",
                         help="skip jupytext conversion/execution; use existing .md files")
    p_build.add_argument("--media-root",
                         help="directory to receive the media/ tree (figures, code copies); "
                              "defaults to the project directory for content repos")
    p_build.set_defaults(func=cmd_build)

    p_prev = sub.add_parser("preview", help="render a static HTML preview site")
    p_prev.add_argument("project_dir", help="project directory")
    p_prev.add_argument("-o", "--output", default="preview", help="output directory")
    p_prev.add_argument("--artifact", help="use an existing artifact instead of rebuilding")
    p_prev.add_argument("--execute", action="store_true",
                        help="execute jupytext code when rebuilding (default: skip)")
    p_prev.add_argument("--media-root", help="media tree location (default: project dir)")
    p_prev.add_argument("--bib", help="bibliography file (default: auto-detect *.bib)")
    p_prev.add_argument("--no-solutions", action="store_true",
                        help="omit exercise solutions from the preview")
    p_prev.set_defaults(func=cmd_preview)

    p_watch = sub.add_parser("watch", help="rebuild artifact (+preview) on save")
    p_watch.add_argument("project_dir", help="project directory")
    p_watch.add_argument("--artifact", help="artifact output path")
    p_watch.add_argument("--preview", help="also write a preview site to this directory")
    p_watch.add_argument("--media-root", help="media tree location")
    p_watch.add_argument("--bib", help="bibliography file")
    p_watch.set_defaults(func=cmd_watch)

    p_pdf = sub.add_parser("pdf", help="build the print PDF via LaTeX (Phase 3)")
    p_pdf.add_argument("project_dir", help="project directory")
    p_pdf.add_argument("-o", "--output", help="output PDF path")
    p_pdf.add_argument("--solutions", action="store_true",
                       help="build the solutions manual (\\issolution)")
    p_pdf.add_argument("--section", metavar="CH/SEC",
                       help="build a single section (chapter-slug/section-slug)")
    p_pdf.add_argument("--profile",
                       help="LaTeX profile directory (default: bundled generic profile; "
                            "book-private profiles, e.g. MIT Press, live in content repos)")
    p_pdf.add_argument("--no-execute", action="store_true",
                       help="skip jupytext execution before the PDF build")
    p_pdf.set_defaults(func=cmd_pdf)

    p_check = sub.add_parser("check", help="validate an artifact against the schema")
    p_check.add_argument("artifact", nargs="?", help="artifact JSON path")
    p_check.add_argument("--toolchain", action="store_true",
                         help="check local toolchain versions against the pins")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
