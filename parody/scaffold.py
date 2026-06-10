"""`parody init` — scaffold a content repo.

Templates live in parody/templates/content_repo/ and are instantiated with
string.Template.safe_substitute (so GitHub Actions ``${{ }}`` expressions in
the workflow template pass through untouched). Dotfiles are stored without
the leading dot (packaging-friendly) and renamed on the way out.
"""

from importlib.resources import files
from pathlib import Path
from string import Template

from . import __version__

RENAMES = {
    "gitignore": ".gitignore",
    "github": ".github",
    "gitkeep": ".gitkeep",
}


def _out_name(name):
    return RENAMES.get(name, name)


def init_project(target_dir, title=None, slug=None, author=None):
    """Create a new content repo at target_dir. Returns the created path."""
    target_dir = Path(target_dir)
    if target_dir.exists() and any(target_dir.iterdir()):
        raise SystemExit(f"refusing to scaffold into non-empty directory {target_dir}")

    slug = slug or target_dir.name
    context = {
        "title": title or slug.replace("-", " ").title(),
        "slug": slug,
        "author": author or "Author Name",
        "parody_version": __version__,
    }

    template_root = files("parody") / "templates" / "content_repo"

    def walk(node, rel=Path(".")):
        for child in node.iterdir():
            out_rel = rel / _out_name(child.name)
            if child.is_dir():
                (target_dir / out_rel).mkdir(parents=True, exist_ok=True)
                walk(child, out_rel)
            else:
                dest = target_dir / out_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                text = child.read_text(encoding="utf-8")
                dest.write_text(
                    Template(text).safe_substitute(context), encoding="utf-8"
                )

    target_dir.mkdir(parents=True, exist_ok=True)
    walk(template_root)

    print(f"✓ Scaffolded content repo at {target_dir}")
    print("  next: cd in, `git init`, then `parody build . artifact.json`")
    return target_dir
