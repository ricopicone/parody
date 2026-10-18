"""Which languages a book is translated into, and how (task #825).

A book opts in with a ``translations:`` key in parody.yaml::

    translations:
      languages: [zh, ko, de, fr, es]
      engine: claude-code        # or anthropic-api
      model: claude-opus-5-5

The prompt names are what the translator is told, so they carry the variety
too: "Chinese" alone would leave Simplified vs Traditional to chance.
"""

from dataclasses import dataclass

LANGUAGES = {
    "zh": "Simplified Chinese (Mandarin, as written in mainland China)",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "es": "Spanish (neutral international Spanish)",
}

ENGINES = ("claude-code", "anthropic-api")
DEFAULT_ENGINE = "claude-code"
DEFAULT_MODEL = "claude-opus-5-5"


@dataclass(frozen=True)
class TranslationConfig:
    languages: tuple
    engine: str = DEFAULT_ENGINE
    model: str = DEFAULT_MODEL


def normalize_translations(raw):
    """Parse the ``translations:`` key; ``None`` when the book doesn't translate."""
    from ..config import ProjectLayoutError

    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProjectLayoutError(
            "translations: must be a mapping (e.g. translations:\\n  languages: [zh, de])")
    languages = raw.get("languages") or []
    if isinstance(languages, str):
        languages = [languages]
    if not languages:
        raise ProjectLayoutError(
            "translations: needs at least one entry under languages "
            f"(known: {', '.join(LANGUAGES)})")
    for code in languages:
        if code not in LANGUAGES:
            raise ProjectLayoutError(
                f"unknown translation language {code!r} "
                f"(known: {', '.join(LANGUAGES)})")
    engine = raw.get("engine") or DEFAULT_ENGINE
    if engine not in ENGINES:
        raise ProjectLayoutError(
            f"unknown translations engine {engine!r} (known: {', '.join(ENGINES)})")
    return TranslationConfig(
        languages=tuple(str(c) for c in languages),
        engine=engine,
        model=str(raw.get("model") or DEFAULT_MODEL),
    )
