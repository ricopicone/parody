"""`parody publish`: build the print PDF and the web artifact together.

Order is not negotiable — the PDF builds first, because the artifact consumes
the page-map sidecar the PDF build emits. Doing it the other way round yields
an artifact with no print page ranges and therefore a book site with no PDF
downloads, silently.
"""

from pathlib import Path

from .build import build_project
from .config import load_project
from .writers.latex import build_pdf
from .writers.pagemap import sidecar_path


def publish(project_dir, output_dir, convert_jupytext=True, media_root=None,
            online_only=False, cloze_mode=None, profile_dir=None,
            skip_pdf=False, pdf_only=False):
    """Build print + web for every edition (or once, for a single-edition book).

    Returns every path written, PDFs and artifacts alike.
    """
    # Resolve before anything derives paths from these. build_pdf hands the
    # generated section .md to pandoc with cworkdir set to its own directory,
    # so a RELATIVE build dir stops resolving the moment pandoc changes
    # directory — `parody publish .` died on its first section with
    # "source_file is not a valid path" while `parody publish /abs/path`
    # worked. Same reasoning as build_pdf's own resolve().
    project_dir = Path(project_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    project = load_project(project_dir)

    editions = project.editions or [None]
    written = []
    for edition in editions:
        suffix = f".{edition['id']}" if edition else ""
        pdf_out = output_dir / f"{project.slug}{suffix}.pdf"
        sidecar = sidecar_path(pdf_out)

        if not skip_pdf:
            produced = build_pdf(
                project_dir,
                output_pdf=pdf_out,
                profile_dir=profile_dir,
                cloze_mode=cloze_mode,
                edition=edition,
                build_dir=project_dir / "build" / f"print{suffix}",
            )
            if produced is None:
                print(f"⚠️  no PDF produced for {project.slug}{suffix} "
                      "(is latexmk installed?)")
            else:
                written.append(Path(produced))
        elif pdf_out.is_file():
            written.append(pdf_out)

        if pdf_only:
            continue

        artifact_out = output_dir / f"{project.slug}{suffix}.json"
        build_project(
            project_dir, artifact_out,
            convert_jupytext=convert_jupytext,
            media_root=media_root,
            online_only=online_only,
            cloze_mode=cloze_mode,
            edition=edition,
            print_pages=sidecar if sidecar.is_file() else None,
        )
        written.append(artifact_out)

    return written
