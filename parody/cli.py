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
    from .build import build_editions, build_project
    from .config import load_project

    kwargs = dict(
        convert_jupytext=not args.no_execute,
        media_root=args.media_root,
        online_only=getattr(args, "online_only", False),
        cloze_mode=getattr(args, "clozes", None),
    )

    project = load_project(args.input_dir)
    edition = getattr(args, "edition", None)

    if project.editions and not edition:
        # Edition-aware book, no --edition: build one artifact per edition into
        # the output directory (a .json output path is treated as its parent).
        out_dir = Path(args.output)
        if out_dir.suffix == ".json":
            out_dir = out_dir.parent
        paths = build_editions(args.input_dir, out_dir, **kwargs)
        print(f"Built {len(paths)} edition artifacts: "
              f"{', '.join(p.name for p in paths)}")
        return 0

    ed = None
    if edition:
        ed = next((e for e in project.editions if e["id"] == edition), None)
        if ed is None:
            known = ", ".join(e["id"] for e in project.editions) or "none"
            print(f"error: unknown edition {edition!r} (known: {known})",
                  file=sys.stderr)
            return 1

    build_project(args.input_dir, args.output, edition=ed, **kwargs)
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
        cloze_mode=args.clozes,
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


def cmd_migrate(args):
    from .migrate import migrate_meta_book

    dest = Path(args.dest)
    if not (dest / "parody.yaml").is_file():
        print(f"error: {dest} is not a parody content repo "
              "(no parody.yaml; run `parody init` first)", file=sys.stderr)
        return 2
    migrate_meta_book(args.src, dest)
    print("reminder: re-apply the book's re-hash loser list "
          "(`parody rehash`) before building")
    return 0


def cmd_rehash(args):
    from .migrate import rehash_duplicates
    from .migrate.rehash import load_losers

    dest = Path(args.dest)
    losers_path = Path(args.losers) if args.losers \
        else dest / "scripts" / "rehash_losers.yaml"
    if not losers_path.is_file():
        print(f"error: loser list not found at {losers_path}",
              file=sys.stderr)
        return 2
    salt = args.salt
    if not salt:
        import yaml as _yaml
        meta = _yaml.safe_load((dest / "parody.yaml").read_text())
        salt = meta.get("slug", dest.resolve().name)
    rehash_duplicates(dest, load_losers(losers_path), salt)
    return 0


def cmd_parity(args):
    from .parity import compare, format_report

    report = compare(Path(args.reference), Path(args.candidate),
                     low=args.low, visual=args.visual)
    print(format_report(report, low=args.low))
    return 0


def cmd_gaps(args):
    from .gaps import (
        _numbered_eq_by_section,
        format_gaps,
        format_triage,
        scan,
        triage_listings,
    )

    rep = scan(Path(args.project_dir))
    print(format_gaps(rep, limit=args.limit))
    if args.against:
        from .parity import extract_text
        ref_text = extract_text(Path(args.against))
        matches = triage_listings(rep, ref_text)
        eq_ref = _numbered_eq_by_section(ref_text)
        eq_cand = (_numbered_eq_by_section(extract_text(Path(args.candidate)))
                   if args.candidate else None)
        print()
        print(format_triage(matches, eq_ref, eq_cand))
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

    p_mig = sub.add_parser(
        "migrate", help="migrate a meta-book (System B) repo into this content repo")
    p_mig.add_argument("src", help="meta-book source repo directory")
    p_mig.add_argument("--dest", default=".",
                       help="parody content repo (default: cwd)")
    p_mig.set_defaults(func=cmd_migrate)

    p_rehash = sub.add_parser(
        "rehash", help="re-key duplicate short hashes per the book's loser list")
    p_rehash.add_argument("--dest", default=".",
                          help="parody content repo (default: cwd)")
    p_rehash.add_argument("--losers",
                          help="loser list YAML (default: scripts/rehash_losers.yaml)")
    p_rehash.add_argument("--salt",
                          help="hash salt (default: the book slug; the "
                               "already-migrated books use their source "
                               "repo's short name)")
    p_rehash.set_defaults(func=cmd_rehash)

    p_build = sub.add_parser("build", help="build the JSON artifact")
    p_build.add_argument("input_dir", help="project directory (parody.yaml or legacy __meta.yaml)")
    p_build.add_argument("output", help="output JSON artifact path")
    p_build.add_argument("--no-execute", action="store_true",
                         help="skip jupytext conversion/execution; use existing .md files")
    p_build.add_argument("--media-root",
                         help="directory to receive the media/ tree (figures, code copies); "
                              "defaults to the project directory for content repos")
    p_build.add_argument("--edition",
                         help="build only this edition (by id); default builds "
                              "every edition declared in parody.yaml")
    p_build.add_argument("--online-only", action="store_true",
                         help="emit only the public web subset (online-only sections + "
                              "per-section online-resources) — the partial artifact a "
                              "standalone book host (e.g. rtcbook.org) imports")
    p_build.add_argument("--clozes", metavar="MODE",
                         help="cloze rendering: blank (student handout, the "
                              "default), key (instructor copy), or full "
                              "(cloze-free publication build)")
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
    p_pdf.add_argument("--clozes", metavar="MODE",
                       help="cloze rendering: blank (student handout, the "
                            "default), key (instructor copy), or full "
                            "(cloze-free publication build)")
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

    p_parity = sub.add_parser(
        "parity",
        help="compare a built PDF against a reference/original PDF (triage aid)")
    p_parity.add_argument("reference", help="reference (original) PDF")
    p_parity.add_argument("candidate", help="candidate (parody-built) PDF")
    p_parity.add_argument("--low", type=float, default=0.90,
                          help="flag matched sections below this similarity (0..1)")
    p_parity.add_argument("--visual", action="store_true",
                          help="also render each aligned section's page in both "
                               "PDFs and report image differences (needs Pillow)")
    p_parity.set_defaults(func=cmd_parity)

    p_gaps = sub.add_parser(
        "gaps",
        help="scan source for structural-labeling gaps (unnumbered listings/eqs)")
    p_gaps.add_argument("project_dir", help="project directory")
    p_gaps.add_argument("--limit", type=int, default=25,
                        help="max files to list per category")
    p_gaps.add_argument("--against", metavar="REFERENCE.pdf",
                        help="triage: flag only the listings the original "
                             "numbered, matched to source blocks")
    p_gaps.add_argument("--candidate", metavar="CANDIDATE.pdf",
                        help="parody-built PDF, for the per-chapter equation gap")
    p_gaps.set_defaults(func=cmd_gaps)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
