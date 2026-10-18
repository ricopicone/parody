"""Translation files and glossaries, as they live in the book repo (task #825).

One file per section per language, at
``translations/<lang>/<chapter>/<section>.md``::

    ---
    language: zh
    source: chapters/fundamentals/voltage-dividers.md
    title: 分压器
    title_hash: 1a2b3c4d5e6f
    engine: claude-code
    model: claude-opus-5-5
    updated: 2026-10-17
    ---

    <!-- parody:chunk h=3f2a9c01aa77 -->

    # 分压器 {#lec:voltage_dividers h="o5"}

Each chunk is filed under the hash of the English it was translated from, in
English order. A chunk with no checked translation is simply absent. The
build reads these files too, so this format is a contract.
"""

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .chunks import split_frontmatter

_MARKER = re.compile(r"^<!-- parody:chunk h=([0-9a-f]{12}) -->[ \t]*$", re.M)
_META_KEYS = ("language", "source", "title", "title_hash", "engine", "model", "updated")


class TranslationFileError(Exception):
    pass


def translation_path(project_dir, language, chapter_slug, section_slug):
    return (Path(project_dir) / "translations" / language / chapter_slug
            / f"{section_slug}.md")


def glossary_path(project_dir, language):
    return Path(project_dir) / "translations" / language / "glossary.yaml"


@dataclass
class TranslationFile:
    language: str
    source: str
    title: str | None = None
    title_hash: str | None = None
    chunks: list = field(default_factory=list)  # [(source hash, text)]
    engine: str = ""
    model: str = ""
    updated: str = ""

    @classmethod
    def read(cls, path):
        raw = Path(path).read_text(encoding="utf-8")
        meta, body = split_frontmatter(raw)
        if "language" not in meta:
            raise TranslationFileError(f"{path}: no translation front matter")
        pieces = _MARKER.split(body)
        if pieces[0].strip():
            raise TranslationFileError(
                f"{path}: text before the first <!-- parody:chunk --> marker")
        chunks = [(pieces[k], pieces[k + 1].strip("\n").rstrip())
                  for k in range(1, len(pieces), 2)]
        return cls(chunks=chunks,
                   **{k: (str(meta[k]) if meta.get(k) is not None else None)
                      for k in _META_KEYS if k in meta})

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {k: getattr(self, k) for k in _META_KEYS
                if getattr(self, k) not in (None, "")}
        parts = ["---\n", yaml.safe_dump(meta, allow_unicode=True, sort_keys=False),
                 "---\n"]
        for h, text in self.chunks:
            parts.append(f"\n<!-- parody:chunk h={h} -->\n\n{text.strip()}\n")
        _atomic_write(path, "".join(parts))


def load_glossary(path):
    path = Path(path)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()}


def save_glossary(path, glossary):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, yaml.safe_dump(dict(sorted(glossary.items())),
                                       allow_unicode=True, sort_keys=False))


def _atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
