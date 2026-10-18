# Translate Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `parody translate` command that translates every published section of a book into the configured languages through Claude, checks each translation mechanically, and writes it into `translations/<lang>/<chapter>/<section>.md` in the book repo. Re-running it only translates chunks whose English changed.

**Architecture:** This is subsystem 1 of 5 in the spec. The later ones are the twin-page proof, the full twin and side-by-side PDFs, the read-along pane, and web paragraph translations. All of them read the files this step writes.

A section is split at the source level into *chunks*: top-level, blank-line-separated runs that never break a fence, a div or display maths. Chunk identity is a hash of the English chunk text. A translation file stores, in English order, each translated chunk under the hash of the English it was made from. Aligning the English hashes against the stored hashes classifies each chunk as `current`, `stale` or `missing`. Only stale and missing chunks go to the engine.

A preservation checker parses English and translation with pandoc in one call each and compares per-chunk facts: maths, blanks, key terms, refs, ids, code and blocks. It gates every write.

**Tech Stack:** Python ≥3.11, pypandoc (bundled pandoc 3.6.1), PyYAML, difflib, subprocess (Claude Code headless `claude -p`), optional `anthropic` SDK, pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-translations-design.md`. Read it; this plan implements its "The translate step (parody)" and "Translation files (book repo)" sections and decisions D1, D7–D10, D12, D13.

## Global Constraints

- Languages and their prompt names, verbatim:
  - `zh`: "Simplified Chinese (Mandarin, as written in mainland China)"
  - `ko`: "Korean"
  - `de`: "German"
  - `fr`: "French"
  - `es`: "Spanish (neutral international Spanish)"
- Default engine `claude-code`, default model `claude-opus-5-5`.
- The `claude-code` engine must run with `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` removed from the child environment, and must never pass `--bare`.
- Drafts are never translated. Eligibility is `resolve_section_draft(frontmatter.get("draft"), chapter.draft)` from `parody/writers/artifact.py`, unchanged.
- Nothing is committed by the command. Files are written to the working tree only.
- A chunk translation that fails the preservation check is never written. A previously written translation of that chunk is kept as it was.
- Edition-aware books (`project.editions` non-empty) are refused with a clear error. The spec's scope is the ricopic.one notes, which have no editions.
- The checker parses with the web path's reader format, exactly: `markdown-smart-markdown_in_html_blocks+raw_tex+tex_math_dollars+grid_tables` (from `parody/writers/artifact.py`).
- Version bump to `0.61.0` updates `pyproject.toml` **and** `uv.lock` in the same commit.

## Review Focus

1. **Fences and blank lines.** A blank line inside a `$$…$$` display, a `:::` fenced div, a code fence, or an indented footnote continuation must not split a chunk. *Pinned in Task 2.*
2. **A mid-section edit.** Inserting one paragraph, editing one and deleting one must leave every other chunk's translation byte-identical, and send only the new and edited chunks to the engine. *Pinned in Tasks 2 and 6.*
3. **Malformed engine output.** A missing chunk marker, an extra chunk, a code-fence wrapper, or chatter before the first marker must be retried. If it never comes back right, it must never be written. *Pinned in Tasks 4 and 6.*
4. **An `ANTHROPIC_API_KEY` in the environment.** It would silently bill the API instead of the subscription. *Pinned in Task 5.*
5. **Re-running after an interruption.** A second run with nothing changed makes zero engine calls. A run interrupted after some sections resumes with the rest. *Pinned in Task 6.*

---

## File Structure

```
parody/translate/
  __init__.py      re-exports translate_project, project_status
  languages.py     LANGUAGES table, TranslationConfig, normalize_translations()
  chunks.py        split_frontmatter, split_chunks, chunk_hash, align_chunks
  store.py         TranslationFile (read/write), translation_path, glossary load/save
  check.py         chunk_facts (one pandoc call), compare_facts, add_keyword_glosses
  prompt.py        system_prompt(), request(), parse_response()
  engines.py       Engine protocol, ClaudeCodeEngine, AnthropicAPIEngine, make_engine
  run.py           section enumeration, status, translate_section, translate_project
parody/config.py   Project.translations (set from normalize_translations)
parody/cli.py      cmd_translate + parser
tests/test_translate_config.py, test_translate_chunks.py, test_translate_store.py,
tests/test_translate_check.py, test_translate_prompt.py, test_translate_engines.py,
tests/test_translate_run.py
```

---

### Task 1: Config and languages

**Files:**
- Create: `parody/translate/__init__.py` (empty for now), `parody/translate/languages.py`
- Modify: `parody/config.py`: add a `translations` field to `Project`, and set it in `load_project` for the parody layout
- Test: `tests/test_translate_config.py`

**Interfaces:**
- Produces:
  - `LANGUAGES: dict[str, str]` (code → prompt name; the Global Constraints values).
  - `@dataclass(frozen=True) TranslationConfig(languages: tuple[str, ...], engine: str, model: str)`.
  - `normalize_translations(raw: dict | None) -> TranslationConfig | None`.
  - `Project.translations: TranslationConfig | None` (default `None`; legacy layout always `None`).

- [ ] **Step 1: Write the failing tests**

```python
from parody.translate.languages import LANGUAGES, normalize_translations
from parody.config import ProjectLayoutError, load_project

def test_absent_key_means_no_translations():
    assert normalize_translations(None) is None

def test_defaults():
    cfg = normalize_translations({"languages": ["zh", "de"]})
    assert cfg.languages == ("zh", "de")
    assert cfg.engine == "claude-code"
    assert cfg.model == "claude-opus-5-5"

def test_unknown_language_is_rejected():
    with pytest.raises(ProjectLayoutError, match="unknown translation language 'xx'"):
        normalize_translations({"languages": ["xx"]})

def test_unknown_engine_is_rejected():
    with pytest.raises(ProjectLayoutError, match="engine"):
        normalize_translations({"languages": ["zh"], "engine": "deepl"})

def test_empty_languages_is_rejected():
    with pytest.raises(ProjectLayoutError, match="languages"):
        normalize_translations({"languages": []})

def test_prompt_names():
    assert LANGUAGES["zh"] == "Simplified Chinese (Mandarin, as written in mainland China)"
    assert set(LANGUAGES) == {"zh", "ko", "de", "fr", "es"}

def test_load_project_reads_the_key(tmp_path):
    (tmp_path / "parody.yaml").write_text(
        "title: T\nslug: t\nchapters: []\ntranslations:\n  languages: [ko]\n")
    assert load_project(tmp_path).translations.languages == ("ko",)
```

- [ ] **Step 2: Run them, expect FAIL** (`ModuleNotFoundError: parody.translate`)

Run: `uv run pytest tests/test_translate_config.py -q`

- [ ] **Step 3: Implement `languages.py` and wire `Project.translations`**

`normalize_translations` accepts `languages` as a list of codes, and `engine ∈ {"claude-code", "anthropic-api"}`. It raises `ProjectLayoutError`, imported from `parody.config` inside the function to avoid an import cycle. In `config.py`, add `translations: object = None` to `Project` and pass `translations=normalize_translations(meta.get("translations"))` in the parody branch of `load_project`. Follow the `normalize_editions` pattern.

- [ ] **Step 4: Run them, expect PASS**

- [ ] **Step 5: Commit** `feat(translate): translations: config key and language table`

---

### Task 2: Chunks and alignment

**Files:**
- Create: `parody/translate/chunks.py`
- Test: `tests/test_translate_chunks.py`

**Interfaces:**
- Produces:
  - `split_frontmatter(raw: str) -> tuple[dict, str]`: front matter dict (`{}` if none) and the body after it.
  - `split_chunks(body: str) -> list[str]`: each chunk stripped of surrounding blank lines; never empty.
  - `chunk_hash(text: str) -> str`: `hashlib.sha256(text.strip().encode()).hexdigest()[:12]`.
  - `align_chunks(english: list[str], stored: list[str]) -> list[tuple[int, int | None, str]]`. Arguments are hash lists. Returns one tuple per English index: `(en_index, stored_index_or_None, status)` with status in `{"current", "stale", "missing"}`.

**Splitting rule** (the decision a test cannot fully pin):

Walk the lines and track four pieces of state:

- **Code fence.** A line starting with ``` or `~~~` opens a fence. The fence closes on a line starting with the same character repeated at least as many times.
- **Div depth.** A line matching `^:{3,}\s*\S` (outside code) opens a fenced div and increments the depth. A line matching `^:{3,}\s*$` decrements it.
- **Display maths.** Each `$$` occurrence on a line (outside code) toggles the display-maths flag.
- **Blank lines.** A blank line ends a chunk only when all three conditions hold:
  - the line is outside a code fence, at div depth 0, and outside display maths;
  - the next non-blank line is not indented by ≥4 spaces or a tab, since that would continue a footnote or list item;
  - the next non-blank line exists.

**Alignment:** Run `difflib.SequenceMatcher(a=stored, b=english, autojunk=False).get_opcodes()` and map each opcode:

- `equal` → `current`, paired index for index.
- `replace` → pair positionally as `stale` for the overlapping length. Leftover English entries are `missing`, and leftover stored entries are dropped.
- `insert` → `missing`.
- `delete` → nothing.

- [ ] **Step 1: Write the failing tests**

```python
from parody.translate.chunks import align_chunks, chunk_hash, split_chunks, split_frontmatter

def test_frontmatter():
    meta, body = split_frontmatter("---\ntitle: V\nhash: o5\n---\n\n# V\n")
    assert meta == {"title": "V", "hash": "o5"}
    assert body.strip() == "# V"

def test_paragraphs_split_on_blank_lines():
    assert split_chunks("A\nb.\n\nC.\n\n\nD.") == ["A\nb.", "C.", "D."]

def test_display_math_with_blank_line_is_one_chunk():
    body = "Text: $$\\begin{aligned}\na &= b\n\nc &= d\\end{aligned}$$\nafter.\n\nNext."
    assert split_chunks(body) == [body.split("\n\nNext.")[0], "Next."]

def test_fenced_div_with_blank_lines_is_one_chunk():
    body = "::: definition\n\nFor $v$.\n\n$$x$$\n\n:::\n\nAfter."
    assert split_chunks(body) == ["::: definition\n\nFor $v$.\n\n$$x$$\n\n:::", "After."]

def test_nested_divs():
    body = "::: a\n\n::: b\n\nx\n\n:::\n\n:::\n\ny"
    assert split_chunks(body)[1] == "y"

def test_code_fence_with_blank_lines_and_colons_is_one_chunk():
    body = "```python\nx = 1\n\n::: not a div\n```\n\nz"
    assert split_chunks(body) == ["```python\nx = 1\n\n::: not a div\n```", "z"]

def test_footnote_continuation_stays_with_its_definition():
    body = "[^3]: Alternatively, we could\n\n    solve for all four.\n\nNice!"
    assert split_chunks(body) == ["[^3]: Alternatively, we could\n\n    solve for all four.", "Nice!"]

def test_hash_ignores_surrounding_whitespace():
    assert chunk_hash("abc\n") == chunk_hash("abc") and len(chunk_hash("abc")) == 12

def test_align_insert_edit_delete():
    stored = ["h1", "h2", "h3", "h4"]
    english = ["h1", "NEW", "h2", "h3x", "h5"]   # inserted NEW, edited h3, h4->h5 replaced
    got = align_chunks(english, stored)
    assert got[0] == (0, 0, "current")
    assert got[1] == (1, None, "missing")
    assert got[2] == (2, 1, "current")
    assert got[3][2] == "stale" and got[4][2] in {"stale", "missing"}

def test_align_deleted_chunk_is_dropped():
    assert align_chunks(["h1", "h3"], ["h1", "h2", "h3"]) == [(0, 0, "current"), (1, 2, "current")]
```

- [ ] **Step 2: Run, expect FAIL.** Run: `uv run pytest tests/test_translate_chunks.py -q`
- [ ] **Step 3: Implement `chunks.py`**
- [ ] **Step 4: Run, expect PASS.** Also run `split_chunks` on every `chapters/*/*.md` of `~/electronics-primer/electronics-parody` in a throwaway one-liner. Confirm no chunk ends inside an open `$$` (an even count of `$$` per chunk) or an open `:::`.
- [ ] **Step 5: Commit** `feat(translate): split sections into chunks and align them by hash`

---

### Task 3: Translation file and glossary store

**Files:**
- Create: `parody/translate/store.py`
- Test: `tests/test_translate_store.py`

**Interfaces:**
- Consumes: `split_frontmatter` (Task 2).
- Produces:
  - `translation_path(project_dir: Path, language: str, chapter_slug: str, section_slug: str) -> Path` = `project_dir/"translations"/language/chapter_slug/f"{section_slug}.md"`.
  - `@dataclass TranslationFile(language: str, source: str, title: str | None, title_hash: str | None, chunks: list[tuple[str, str]], engine: str = "", model: str = "", updated: str = "")`. `chunks` holds `(source_hash, text)` pairs in English order.
  - `TranslationFile.read(path: Path) -> TranslationFile` (classmethod), `.write(path: Path) -> None` (creates parents; writes atomically via a temp file and `os.replace`).
  - `class TranslationFileError(Exception)`.
  - `glossary_path(project_dir, language) -> Path` = `…/translations/<lang>/glossary.yaml`.
  - `load_glossary(path) -> dict[str, str]` (`{}` if absent), `save_glossary(path, glossary)` (keys sorted, `allow_unicode=True`).

**File format** (exact; later subsystems parse it):

```
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

<!-- parody:chunk h=0b1c2d3e4f50 -->

在 [uy]{.hashref} 中…
```

A chunk's text is everything between its marker line and the next marker, or the end of the file, stripped. The front matter is written with `yaml.safe_dump(..., allow_unicode=True, sort_keys=False)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_round_trip`: write a file with a zh title, two chunks (one containing a blank line inside `$$`), and engine/model/updated. Read it back and require it to be equal.
  - `test_marker_regex_is_exact`: a chunk whose text contains `<!-- other comment -->` survives the round trip.
  - `test_malformed_marker_raises`: a body with text before the first marker raises `TranslationFileError`.
  - `test_glossary_round_trip_is_sorted_unicode`: save `{"voltage divider": "分压器", "current": "电流"}`. The file text contains `分压器` literally, and `current` sorts first.
  - `test_missing_glossary_is_empty`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `store.py`.** The marker regex is `^<!-- parody:chunk h=([0-9a-f]{12}) -->$`, multiline.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(translate): translation file format and glossary store`

---

### Task 4: Preservation check, key-term glosses, prompt protocol

**Files:**
- Create: `parody/translate/check.py`, `parody/translate/prompt.py`
- Test: `tests/test_translate_check.py`, `tests/test_translate_prompt.py`

**Interfaces:**
- Produces (check.py):
  - `CHECK_FROM = "markdown-smart-markdown_in_html_blocks+raw_tex+tex_math_dollars+grid_tables"`.
  - `@dataclass Facts(blocks: int, math: Counter, cloze: int, keywords: list[str], hashrefs: Counter, cites: Counter, notes: int, code: Counter, images: Counter, tables: int, ids: Counter, attrs: Counter, raw: Counter)`.
  - `chunk_facts(chunks: list[str]) -> list[Facts]`. It makes **one** pandoc call: the chunks are joined with `"\n\n<!-- parody:split -->\n\n"`, read with `CHECK_FROM` to JSON, and the top-level block list is split at `RawBlock("html", "<!-- parody:split -->")`. The walker then counts the following:
    - `Math` text;
    - `Span`s by class `cloze`, `keyword` and `hashref`, where `keywords` holds the stringified inner text in order and `hashrefs` the inner text;
    - `Cite` ids;
    - `Note`s;
    - `Code` and `CodeBlock` text;
    - `Image` targets;
    - `Table`s;
    - every non-empty identifier;
    - every key/value attribute except `en`;
    - `RawInline` and `RawBlock` text (other than the split marker).
  - `compare_facts(en: Facts, tr: Facts) -> list[str]`. It returns human-readable problems, empty if the chunk passes. Example: `"maths changed: missing $v_\\text{in}$"`, `"blanks: 2 of 3"`, `"key terms: 0 of 1"`, `"section links changed"`, `"paragraph count: 3 of 2"`.
  - `add_keyword_glosses(tr_chunk: str, en_keywords: list[str]) -> str`. In the *i*-th `{…}` attribute block that follows a `]` and contains the class `.keyword`, it inserts ` en="<en_keywords[i]>"`, with `"` replaced by `”`. If an `en=` is already present, or the count of keyword spans differs from `len(en_keywords)`, it returns the input unchanged.
- Produces (prompt.py):
  - `system_prompt(language: str, glossary: dict[str, str]) -> str`. It is the brief below with `{LANGUAGE}` replaced by `LANGUAGES[language]`. When `glossary` is non-empty, a final section follows: `Use these established {LANGUAGE} translations for these terms:` with one `- English → translation` line per entry.
  - `request(english: list[str], todo: list[int], previous: dict[int, str]) -> str`. `english[0]` is the title chunk when the section has a title. `previous` maps English index → the existing translation, for context.
  - `parse_response(text: str, todo: list[int]) -> dict[int, str]`. It raises `ResponseError` unless every index in `todo` appears exactly once and no other index appears. Text before the first marker is ignored only when it is whitespace. A wrapping ```` ``` ```` fence around the whole response is stripped first.
  - `class ResponseError(Exception)`.

**Request format** (exact):

```
<english-section>
<<<chunk 0>>>
Voltage dividers
<<<chunk 1>>>
# Voltage dividers {#lec:voltage_dividers h="o5"}
…
</english-section>

<existing-translation>
<<<chunk 1>>>
# 分压器 {#lec:voltage_dividers h="o5"}
…
</existing-translation>

Translate these chunks: 2, 5, 7
```

The `<existing-translation>` block is omitted when `previous` is empty.

**System prompt brief** (exact copy; it adapts the spec's trial prompt to the chunk protocol):

```
You are translating one section of an undergraduate engineering textbook from English into {LANGUAGE}.

Who reads this: international students whose English is still developing. They read your translation side by side with the English original while listening to an English audio narration, and glance at the translation when a passage in English is hard to follow. So the translation must be faithful to the English sentence by sentence (no summarising, no added explanation, nothing omitted), keep the same sentences in the same order, and read naturally and clearly, in the register of a good university textbook written in {LANGUAGE}. Keep the author's informal, encouraging tone. Use the standard technical terminology that {LANGUAGE}-language engineering courses actually use.

The section arrives split into numbered chunks, each starting with a line `<<<chunk N>>>`. Chunk 0, when present, is the section title as plain text. You may also get the existing translation of some chunks for context; keep your terminology consistent with it. Translate only the chunks you are asked for, and return each one starting with its own `<<<chunk N>>>` line, in order, with nothing before, between or after them.

The chunks are Pandoc Markdown with extensions. Translate the prose; preserve every piece of markup exactly:

- Math: everything between `$…$` and `$$…$$` stays byte-for-byte identical, including `\text{…}`, `\cloze{…}` and environment names. Do not translate inside math.
- Attributes and ids: keep `{#…}`, `{.…}`, `h="…"`, `width="…"` and the like exactly.
- `[xx]{.hashref}` spans: keep them exactly; do not translate their contents.
- Cross-references such as `[@fig:voltage_divider_demo]`: keep exactly, positioned where the grammar of {LANGUAGE} needs them.
- Images `![caption](path){…}`: translate the caption, keep the path and attributes.
- Code (inline `code` and fenced code blocks): keep exactly.
- Raw LaTeX commands outside math: keep exactly.
- Fenced divs (`::: name` … `:::`), block quotes (`>`), lists, tables, footnote markers (`[^3]`) and footnote definitions: keep the structure; translate the text.
- `[text]{.keyword}`: translate the term, keep the span wrapper and its attributes.
- `[text]{.cloze}`: these are fill-in-the-blank answers. Translate the text inside, keep the span wrapper, and keep exactly one cloze span for each one in the original. If the cloze holds only math, leave it unchanged. Rearrange the surrounding sentence as {LANGUAGE} grammar requires, but the blank must still stand for the same idea.
- References to equations such as `($*$)` and `($*$b)`: keep them.
- Keep the same paragraphs, list items and blocks, in the same order: one translated block for each English block.
```

- [ ] **Step 1: Write the failing tests** (check):
  - `test_identical_chunks_pass`: facts of the trial section `tests/translate_fixtures/voltage-dividers.md` against themselves give no problems. Copy the section from `~/electronics-primer/electronics-parody/chapters/fundamentals/voltage-dividers.md` into the fixture.
  - `test_one_space_in_maths_fails`: changing `\frac{R_2} {R_1+R_2}` to `\frac{R_2}{R_1+R_2}` in one chunk reports a maths problem *for that chunk index only*.
  - `test_dropped_cloze_fails` and `test_dropped_keyword_fails`.
  - `test_translated_hashref_fails`: `[uy]{.hashref}` → `[ui]{.hashref}`.
  - `test_dropped_figure_id_fails`: removing `{#fig:voltage_divider_demo …}`.
  - `test_extra_paragraph_fails`.
  - `test_en_attr_is_ignored`: adding `en="x"` to a keyword is not a problem.
  - `test_footnote_definition_chunk_has_no_blocks_but_note_is_counted`: on the fixture.
  - `test_add_keyword_glosses`: `"[分压器]{.keyword}是…"` with `["voltage divider"]` gives `"[分压器]{.keyword en=\"voltage divider\"}是…"`. A count mismatch returns the input unchanged.
- [ ] **Step 2: Write the failing tests** (prompt):
  - `test_system_prompt_names_language_and_lists_glossary`.
  - `test_request_has_markers_and_todo_line`.
  - `test_parse_response_ok`: two chunks back.
  - `test_parse_missing_chunk_raises`.
  - `test_parse_extra_chunk_raises`.
  - `test_parse_strips_code_fence_wrapper`.
  - `test_parse_rejects_chatter_before_first_marker`: `"Sure! Here…\n<<<chunk 2>>>…"` raises.
  - `test_parse_preserves_inner_blank_lines`.
- [ ] **Step 3: Run both test files, expect FAIL.**
- [ ] **Step 4: Implement `check.py` and `prompt.py`.** For `chunk_facts`, use `pypandoc.convert_text(text, "json", format=CHECK_FROM)` and walk the AST recursively over dicts and lists by `t`/`c`. Stringify a span's inner text by concatenating `Str` `c`, a space for `Space`/`SoftBreak`, and `$…$` for `Math`.
- [ ] **Step 5: Run, expect PASS.**
- [ ] **Step 6: Commit** `feat(translate): preservation check, key-term glosses and the chunk prompt protocol`

---

### Task 5: Engines

**Files:**
- Create: `parody/translate/engines.py`
- Modify: `pyproject.toml`: add the optional extra `translate-api = ["anthropic>=X"]`. Set X to the current 1.x minor, checked with `uv pip index versions anthropic` or PyPI's JSON. Do not guess.
- Test: `tests/test_translate_engines.py`

**Interfaces:**
- Produces:
  - `class Engine(Protocol): name: str; model: str; def complete(self, system: str, user: str) -> str`.
  - `class EngineError(Exception)`.
  - `ClaudeCodeEngine(model: str, executable: str = "claude", timeout: int = 3600)`. Its `complete` runs `subprocess.run` with `input=user`, `capture_output=True` and `text=True`.
    - argv, exact: `[executable, "-p", "--output-format", "json", "--model", model, "--tools", "", "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "", "--system-prompt", system]`.
    - env: `os.environ` minus `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.
    - It parses stdout as JSON. A non-zero exit, `is_error`, `subtype != "success"`, or unparseable stdout raises `EngineError` with the stderr/result text. Otherwise it returns `result`.
  - `AnthropicAPIEngine(model: str)`. It imports `anthropic` lazily and raises `EngineError("pip install 'parody[translate-api]'")` if the package is missing.
    - It uses `client.beta.messages.stream(model=model, max_tokens=64000, system=system, messages=[{"role": "user", "content": user}], betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"})` and `.get_final_message()`.
    - A `stop_reason` of `refusal` or `max_tokens` raises `EngineError`.
    - It returns the concatenated `text` blocks.
  - `make_engine(config: TranslationConfig) -> Engine`.

- [ ] **Step 1: Write the failing tests**, monkeypatching `subprocess.run`:
  - `test_claude_code_strips_api_key`: with `ANTHROPIC_API_KEY=sk-x` and `ANTHROPIC_AUTH_TOKEN=t` set, the captured `env` contains neither.
  - `test_claude_code_argv`: the captured argv equals the exact list above, and `"--bare" not in argv`.
  - `test_claude_code_returns_result`: stdout `{"type":"result","subtype":"success","is_error":false,"result":"<<<chunk 1>>>\nX"}` returns the result text.
  - `test_claude_code_error_raises`: `is_error: true`, a non-zero return code, and non-JSON stdout each raise `EngineError`.
  - `test_api_engine_missing_package_message`: monkeypatch `builtins.__import__` to fail for `anthropic`. The message mentions `parody[translate-api]`.
  - `test_make_engine`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `engines.py` and the extra.** Run `uv lock` so `uv.lock` records the extra.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(translate): claude-code and anthropic-api engines` (include `pyproject.toml` and `uv.lock`).

---

### Task 6: Orchestration and status

**Files:**
- Create: `parody/translate/run.py`; fill in `parody/translate/__init__.py`
- Test: `tests/test_translate_run.py` (uses a `FakeEngine`, and builds a small book in `tmp_path`)

**Interfaces:**
- Consumes: everything above; `resolve_section_draft` (`parody.writers.artifact`); `load_project` (`parody.config`).
- Produces:
  - `@dataclass SectionStatus(chapter: str, section: str, language: str, state: str, todo: int = 0, total: int = 0, problems: list[str] = field(default_factory=list))`. `state` ∈ `{"current", "stale", "missing", "draft", "translated", "partial", "failed", "no-source"}`.
  - `project_status(project, languages=None, sections=None) -> list[SectionStatus]`. It never calls an engine.
  - `translate_project(project, engine, languages=None, sections=None, jobs=1, retries=2, today=None, log=print) -> list[SectionStatus]`. `sections` holds `"chapter/section"` strings. The default `languages` is `project.translations.languages`.
  - `translate_section(project, chapter, section_slug, language, engine, glossary, retries=2, today=None) -> SectionStatus`.

**`translate_section` algorithm:**

1. Read the source `chapter.directory / f"{slug}.md"`; if it is absent, return `no-source`. Then `split_frontmatter` and `split_chunks`.
2. If `resolve_section_draft(meta.get("draft"), chapter.draft)` is true, return `draft` and touch nothing.
3. Build `english`. It is `[meta["title"]] + chunks` when the front matter has a `title`, else `chunks`; let `has_title` record which. Hash each entry.
4. Load the existing `TranslationFile`, if any. Its stored hashes are `[title_hash] + [h for h, _ in chunks]` when `has_title`; drop a `None` title_hash. Run `align_chunks`.
5. `todo` is every English index whose status is not `current`. If `todo` is empty, return `current` and do not call the engine. `previous` maps each English index to the stored text aligned to it, current or stale.
6. Call `engine.complete(system_prompt(language, relevant), request(english, todo, previous))`. `relevant` is the glossary entries whose English term occurs, case-insensitively, in the text of the todo chunks. Then `parse_response`.
7. Assemble the candidate list. Current chunks keep their stored text verbatim. For todo chunks, the translation is passed through `add_keyword_glosses(text, en_facts[i].keywords)`. Compute `chunk_facts` on the English chunks and on the candidate chunk list, excluding the title. Run `compare_facts` per todo index; the title only needs to be non-empty and single-line.
8. Retry the failing todo indices up to `retries` more times. The request carries an extra `Problems with your previous attempt:` block that lists the problems per chunk. A `ResponseError` or `EngineError` counts as a failure of every index in that call.
9. Write the file. The passing todo chunks are `(english_hash, text)`. Failing chunks that had a stale stored translation keep the stored `(old_hash, old_text)`. Failing chunks with nothing stored are left out. `updated = today or date.today().isoformat()`.
10. Add the passing keyword pairs to the glossary, without overwriting existing keys.
11. Return `translated` if everything passed, `partial` if some failed but something was written, and `failed` if nothing passed. `problems` carries the last problems.

**`translate_project`:**

- It raises `ProjectLayoutError` when `project.translations is None`, and when `project.editions` is non-empty.
- It groups work by language and runs languages concurrently with `ThreadPoolExecutor(max_workers=jobs)`. Sections within a language run sequentially, and each language loads and saves its own glossary.
- It logs one line per section: `✓ zh fundamentals/voltage-dividers (3 chunks)`, `· current`, or `✗ … — problems`.

- [ ] **Step 1: Write the failing tests.** `FakeEngine` records calls and answers each todo chunk by returning the English chunk unchanged, so maths and markup are preserved and the check passes. The tests:
  - `test_first_run_translates_everything_and_writes_file`: the file exists, its chunk hashes equal the English hashes, and the title is set.
  - `test_second_run_makes_no_engine_calls`: Review Focus 5.
  - `test_mid_section_edit_sends_only_changed_chunks`: insert one paragraph, edit one and delete one. Only the 2 changed indices are sent, and every other stored chunk's text is byte-identical to before. Review Focus 2.
  - `test_draft_section_is_skipped`: a section with `draft: true` in a released chapter is skipped, and a section with `draft: false` in a draft chapter is translated.
  - `test_failing_chunk_is_retried_then_not_written`: a `FakeEngine` that drops `$` maths in chunk 2 every time makes `retries + 1` calls, chunk 2 is absent from the file, the state is `partial`, and the problems mention maths.
  - `test_failing_stale_chunk_keeps_old_translation`.
  - `test_malformed_response_retries`: the first response has chatter before the first marker and the second is fine, so the state is `translated` after 2 calls. Review Focus 3.
  - `test_interrupted_run_resumes`: the engine raises on the second section and the first section's file exists. A rerun with a good engine translates only the second. Review Focus 5.
  - `test_keyword_gloss_and_glossary`: the translated keyword carries `en="voltage divider"`, and `glossary.yaml` has the pair.
  - `test_status_reports_stale_and_missing_without_engine`.
  - `test_editions_book_is_refused`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `run.py`;** have `__init__.py` re-export `translate_project` and `project_status`.
- [ ] **Step 4: Run, expect PASS;** then run the full suite: `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(translate): translate and status orchestration`

---

### Task 7: CLI, docs, release prep, and a real run

**Files:**
- Modify: `parody/cli.py`: add `cmd_translate` and a `translate` parser after `figures`
- Modify: `README.md`: a short "Translations" section with the `translations:` config and the command, including the `ANTHROPIC_API_KEY` warning
- Modify: `pyproject.toml` and `uv.lock`: version `0.61.0`
- Test: `tests/test_translate_run.py` (CLI cases)

**Interfaces:**
- `parody translate [project_dir] [--lang zh,ko] [--section CH/SEC ...] [--status] [--jobs N]`.
  - `project_dir` defaults to `"."`.
  - `--status` prints `project_status` grouped by language and makes no engine calls.
  - The exit code is `1` if any section is `failed` or `partial`, else `0`.
  - A book with no `translations:` key prints `error: parody.yaml has no translations: key` and exits `1`.

- [ ] **Step 1: Write the failing tests:**
  - `test_cli_status_needs_no_engine`: monkeypatch `make_engine` to raise if called. `main(["translate", str(book), "--status"])` returns 0, and the output lists `missing`.
  - `test_cli_without_key_errors`.
  - `test_cli_translate_uses_engine`: monkeypatch `make_engine` to return a `FakeEngine`. It returns 0 and writes files.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `cmd_translate`** following the `cmd_figures` pattern (lazy imports, `load_project`).
- [ ] **Step 4: Run the full suite, expect PASS.**
- [ ] **Step 5: Real run (verification, spends subscription tokens, ~1 section).** Copy `~/electronics-primer/electronics-parody` to the scratchpad. Do not write into the real book repo. Add `translations: {languages: [zh, de]}` to its `parody.yaml`. Then run `uv run parody translate <copy> --section fundamentals/voltage-dividers` with `ANTHROPIC_API_KEY` unset. The expected outcome:
  - both files are written;
  - `--status` reports them `current`;
  - a second run makes no calls (no `✓` lines);
  - editing one sentence in the English copy sends exactly one chunk;
  - reading the German file, it is fluent German with maths untouched.
- [ ] **Step 6: Commit** `0.61.0: parody translate writes checked translations into the book repo` (include `pyproject.toml`, `uv.lock`, `README.md`, `parody/cli.py`, tests).

---

## Later subsystems (separate plans, written after this one ships)

2. The twin-page proof on Electronics Primer chapter 1, in de and zh (the riskiest part).
3. The full twin and side-by-side PDFs, with the build report and their place in the release chain.
4. The parody-web read-along twin pane: synced scroll, the paragraph tint, mirrored blank reveals, and serving.
5. Web paragraph translations: build output, toggles and the whole-page switch.
