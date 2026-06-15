"""JSON artifact writer.

Ported verbatim from homepage-django teaching/scripts/convert_notebook_md_to_json.py
(Phase 1 of the seed plan). Golden tests assert semantic identity with the
ancestor's committed notebooks_data/*.json; keep changes here parity-safe.
"""

import os
import sys
import yaml
import json
import pypandoc
from pathlib import Path
import subprocess
import re
import shutil
from datetime import datetime, timezone

from .. import __version__

# Artifact schema version; homepage-django's import_notebooks validates against
# this. Bump only with a matching importer change (see its NOTEBOOKS_SPLIT_PLAN.md).
SCHEMA_VERSION = 1

def get_source_commit(path):
    """Git commit hash of the repo containing the notebook sources, if any."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path, capture_output=True, text=True, timeout=10,
        ).stdout.strip() or None
    except Exception:
        return None

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def convert_jupytext_files_in_directory(directory):
    """
    Convert all jupytext Python files in a directory to markdown with execution.
    """
    from ..readers.jupytext_converter_api import convert_directory_with_api_execution

    directory = Path(directory)

    # Use cache file in the directory
    cache_file = directory / '.jupytext_cache.json'

    results = convert_directory_with_api_execution(
        directory,
        recursive=True,
        timeout=300,  # 5 minute timeout
        cache_file=cache_file,
        force=False
    )

    if results['failed_files']:
        failed = ", ".join(str(f) for f in results['failed_files'])
        raise RuntimeError(f"jupytext conversion failed for: {failed}")

    return results['converted_files'] + results['cached_files']

def is_jupytext_file(file_path):
    """
    Check if a Python file is in jupytext format by looking for cell markers.
    """
    from ..readers.jupytext_converter_api import is_jupytext_file as check_jupytext
    return check_jupytext(file_path) is not None

def convert_jupytext_to_markdown(input_path, output_path):
    """
    Convert a jupytext Python file to markdown with execution.
    """
    from ..readers.jupytext_converter_api import convert_jupytext_with_api_execution

    try:
        success, result_path, was_cached = convert_jupytext_with_api_execution(
            input_path, output_path, timeout=300
        )

        if success:
            status = "⚡ Cached" if was_cached else "✓ Converted"
            print(f"{status} jupytext file: {input_path} → {result_path}")
            return True
        else:
            print(f"⚠️  Could not convert jupytext file {input_path}")
            return False

    except Exception as e:
        print(f"⚠️  Error converting jupytext file {input_path}: {e}")
        return False

def clean_markdown_output(md_path):
    """
    Clean up the markdown output from nbconvert.
    Note: This is now handled by the execution-based converter.
    """
    # This function is kept for backward compatibility but the actual
    # cleaning is now done in jupytext_converter_api.py
    pass

def extract_download_code_paths(markdown_content):
    """
    Extract paths from .link-code or .download-code fenced code blocks.
    Example: ```{.download-code path="file.py"}
    Returns a list of paths (strings).
    """
    paths = []
    pattern = re.compile(r"```\{[^}]*\.(?:link-code|download-code)[^}]*\}")
    for match in pattern.finditer(markdown_content):
        header = match.group(0)
        path_match = re.search(r"path\s*=\s*['\"]([^'\"]+)['\"]", header)
        if path_match:
            paths.append(path_match.group(1))
    return paths

def get_section_download_paths(chapter_dir, section_slug):
    section_path = chapter_dir / f"{section_slug}.md"
    with open(section_path, "r", encoding="utf-8") as f:
        raw = f.read()

    if raw.startswith("---"):
        _, _, content = raw.split("---", 2)
    else:
        content = raw

    return extract_download_code_paths(content)

def copy_selected_code_files_to_media(notebook_dir, notebook_slug, requested_files, media_root=None):
    """
    Copy only the code files referenced by .link-code/.download-code blocks.
    requested_files is a set of (chapter_slug, relative_path) tuples.
    Returns the number of files copied.

    media_root: directory containing the media/ tree. In the ancestor this was
    the Django project root; in parody it is a caller-supplied output location.
    When None, no files are copied (the JSON artifact does not depend on this
    side effect).
    """
    if media_root is None:
        return 0
    notebook_dir = Path(notebook_dir)
    media_notebooks_dir = Path(media_root) / "media" / "notebooks" / notebook_slug

    files_copied = 0
    for chapter_slug, rel_path in sorted(requested_files):
        # Absolute media-hierarchy paths point at shared assets that already
        # live in the served media tree; there is nothing to copy from the
        # source tree (the lua filter passes the href through unchanged).
        if rel_path.startswith(("notebooks/", "media/")):
            continue
        chapter_dir = notebook_dir / chapter_slug
        src_path = chapter_dir / rel_path
        if not src_path.exists():
            fallback_path = Path(rel_path)
            if fallback_path.exists():
                src_path = fallback_path
            else:
                print(f"  ⚠️  Skipping missing code file: {rel_path}")
                continue

        dest_path = media_notebooks_dir / chapter_slug / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)
        files_copied += 1
        print(f"  📄 Copied {rel_path} → media/notebooks/{notebook_slug}/{chapter_slug}/")

    return files_copied

def _post_process_html_for_anchors(html):
    """
    Post-process HTML to convert {#prefix:id} patterns to proper HTML id attributes.
    Handles equations, tables, and other elements that need IDs.
    """
    # For equations: add id attribute to span wrapper
    # Pattern: {#eq:label} after closing bracket or }
    html = re.sub(
        r'\{#eq:([A-Za-z0-9_-]+)\}',
        lambda m: f'<span id="eq:{m.group(1)}"></span>',
        html
    )

    # For tables: add id to the table element if not present
    # Pattern: {#tbl:label} - find preceding table and add id to it
    def add_table_id(html_content, tbl_id, match_start):
        """Helper to add id to table tag"""
        # Find the table opening tag before this position
        table_start = html_content.rfind('<table', 0, match_start)
        if table_start != -1:
            # Find the end of the opening tag
            tag_end = html_content.find('>', table_start)
            if tag_end != -1 and f'id="tbl:{tbl_id}"' not in html_content[table_start:tag_end+1]:
                # Insert id into the table tag
                new_table_tag = html_content[table_start:tag_end].replace('<table', f'<table id="tbl:{tbl_id}"', 1)
                html_new = html_content[:table_start] + new_table_tag + html_content[tag_end:]
                return html_new
        return html_content

    # Process all {#tbl:id} patterns
    for match in re.finditer(r'\{#tbl:([A-Za-z0-9_-]+)\}', html):
        tbl_id = match.group(1)
        html = add_table_id(html, tbl_id, match.start())

    # Remove all remaining {#tbl:id} placeholders
    html = re.sub(r'\{#tbl:[A-Za-z0-9_-]+\}', '', html)

    return html

# Short-hash attribute on headings/divs: h=xx, h="xx", hash='xx' (meta/rtc
# style; the stable permalink/cross-ref/QR key, distinct from the anchor id).
_HASH_ATTR_RE = re.compile(r'''(?:^|\s)h(?:ash)?=(?:"([^"]*)"|'([^']*)'|([^\s}]+))''')


def _attr_hash(attr_text):
    if not attr_text:
        return None
    m = _HASH_ATTR_RE.search(attr_text)
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def extract_anchor_ids(markdown_content, with_hashes=False):
    """
    Extract all {#id} patterns from markdown content with context.
    Returns a list of anchor objects with id, type, level (for headings), and title.

    Supports:
    - Headings: ## Title {#id}
    - Figures: ![caption](path){#fig:label}
    - Tables: Table: caption {#tbl:label}
    - Equations: $$ ... $$ {#eq:label}
    - Definitions: ::: {.definition #def:label}
    - Comments: ::: {.comment #cmt:label}
    - Theorems: ::: {.theorem #thm:label}

    with_hashes (schema v2): also match headings/divs that carry extra
    attributes (id-first divs, ``h=xx`` short hashes, ``.example`` divs) and
    attach a "hash" key to anchors that declare one; HTML-commented content
    is skipped (commented-out headings created phantom anchors whose hashes
    collided with the live ones). Schema-v1 extraction is deliberately
    untouched: it is pinned by golden parity with the ancestor.
    """
    if with_hashes:
        markdown_content = re.sub(r"<!--.*?-->", "", markdown_content,
                                  flags=re.S)
    anchors = []

    # Pattern for headings with IDs: ## Title {#id}
    if with_hashes:
        heading_pattern = r'^(#{1,6})\s+(.+?)\s+\{#([A-Za-z0-9_:-]+)((?:\s[^}]*)?)\}\s*$'
    else:
        heading_pattern = r'^(#{1,6})\s+(.+?)\s+\{#([A-Za-z0-9_-]+)\}\s*$'

    # Pattern for typed anchors: {#prefix:label} or {#prefix-label}
    # (figures, tables, equations, definitions, comments, theorems, exercises)
    # Allow attributes like width, height after the label
    typed_pattern = r'\{#(fig|tbl|eq|def|cmt|thm|exe)([:\-])([A-Za-z0-9_-]+)([^}]*)\}'

    # Pattern for div environments: ::: {.type ... #id ...}
    # Captures the environment type (definition/comment/theorem/exercise) and the ID
    # Handles both: {.definition #id ...} and {.definition title="..." #id ...}
    div_pattern = r':::[ \t]+\{\.(definition|comment|theorem|exercise)\s+[^}]*?#([A-Za-z0-9_:-]+)[^}]*?\}'

    # Pattern for standalone IDs without type prefix
    standalone_pattern = r'\{#([A-Za-z0-9_-]+)\}'

    lines = markdown_content.split('\n')
    found_ids = set()

    # Extract headings with IDs
    for line in lines:
        heading_match = re.match(heading_pattern, line)
        if heading_match:
            level = len(heading_match.group(1))  # Count # symbols
            title = heading_match.group(2).strip()
            anchor_id = heading_match.group(3)

            if anchor_id not in found_ids:
                anchor = {
                    'id': anchor_id,
                    'type': 'heading',
                    'level': level,
                    'title': title
                }
                if with_hashes:
                    h = _attr_hash(heading_match.group(4))
                    if h:
                        anchor['hash'] = h
                anchors.append(anchor)
                found_ids.add(anchor_id)

    # Extract typed anchors (figures, tables, equations, definitions, comments, theorems)
    for match in re.finditer(typed_pattern, markdown_content):
        prefix = match.group(1)  # fig, tbl, eq, def, cmt, or thm
        sep = match.group(2)     # ':' or '-'
        anchor_label = match.group(3)

        # Preserve the prefix + separator for all typed anchors
        anchor_id = f"{prefix}{sep}{anchor_label}"

        if anchor_id not in found_ids:
            type_map = {
                'fig': 'figure',
                'tbl': 'table',
                'eq': 'equation',
                'def': 'definition',
                'cmt': 'comment',
                'thm': 'theorem',
                'exe': 'exercise'
            }
            anchor = {
                'id': anchor_id,
                'type': type_map.get(prefix, 'anchor'),
                'level': None,
                'title': None
            }
            if with_hashes:
                h = _attr_hash(match.group(4))
                if h:
                    anchor['hash'] = h
            anchors.append(anchor)
            found_ids.add(anchor_id)

    # Extract div environment anchors: ::: {.definition #id}
    # v2 parses the attribute block instead of pattern-matching it, so
    # id-first divs (::: {#chortle .exercise h="x"}) and .example divs are
    # found and their hashes captured.
    class_type_map = {
        'definition': 'definition',
        'comment': 'comment',
        'theorem': 'theorem',
    }
    if with_hashes:
        class_type_map = dict(class_type_map, exercise='exercise',
                              example='example')
        div_matches = []
        for m in re.finditer(r'^:{3,}\s*\{([^}]*)\}', markdown_content,
                             flags=re.MULTILINE):
            attr_text = m.group(1)
            idm = re.search(r'#([A-Za-z0-9_:-]+)', attr_text)
            env_class = next(
                (c for c in re.findall(r'\.([A-Za-z0-9_-]+)', attr_text)
                 if c in class_type_map), None)
            if idm and env_class:
                div_matches.append((env_class, idm.group(1),
                                    _attr_hash(attr_text)))
    else:
        div_matches = [(m.group(1), m.group(2), None)
                       for m in re.finditer(div_pattern, markdown_content)]

    for env_class, full_id, div_hash in div_matches:
        anchor_id = full_id
        anchor_type = class_type_map.get(env_class, 'anchor')

        # Allow optional colon-prefixed IDs to override type, but keep the full id intact
        if ':' in full_id:
            prefix, _ = full_id.split(':', 1)
            type_map = {
                'def': 'definition',
                'cmt': 'comment',
                'thm': 'theorem',
                'exe': 'exercise'
            }
            anchor_type = type_map.get(prefix, anchor_type)

        if anchor_id not in found_ids:
            anchor = {
                'id': anchor_id,
                'type': anchor_type,
                'level': None,
                'title': None
            }
            if div_hash:
                anchor['hash'] = div_hash
            anchors.append(anchor)
            found_ids.add(anchor_id)

    # Also find standalone IDs (not on headings, not typed) as generic anchors
    for match in re.finditer(standalone_pattern, markdown_content):
        anchor_id = match.group(1)

        # Skip if already found as heading or typed anchor
        if anchor_id in found_ids:
            continue

        # Check if this is part of a heading (already handled)
        is_heading = False
        for line in lines:
            if anchor_id in line and re.match(heading_pattern, line):
                is_heading = True
                break

        if not is_heading:
            anchors.append({
                'id': anchor_id,
                'type': 'anchor',  # Generic anchor
                'level': None,
                'title': None
            })
            found_ids.add(anchor_id)

    return anchors

def extract_exercise_solutions(content):
    """
    Extract exercise solutions from exercise-solution divs.
    Returns a tuple: (content_without_solutions, solutions_dict)
    where solutions_dict maps exercise IDs to their solution HTML and metadata.
    Each solution entry is a dict with 'content', 'title', and optionally other metadata.
    """
    import re

    solutions = {}

    # Pattern to match ::: {.exercise #id title="..." ...} ... ::: {.exercise-solution} ... ::: :::
    # This captures the entire exercise block including nested solution and title attribute.
    # The negative lookahead (?!::: \{\.exercise\s) prevents the match from crossing into
    # a subsequent exercise block when an exercise without a solution appears in between.
    exercise_pattern = r'(::: \{\.exercise\s+#(exe[:\-][A-Za-z0-9_-]+)([^}]*)\}(?:(?!::: \{\.exercise\s).)*?)(::: \{\.exercise-solution\})(.*?)(:::)(.*?)(:::)'

    def extract_solution(match):
        """Replace exercise-solution div with empty string and store solution."""
        before_solution = match.group(1)  # Everything before exercise-solution div
        exercise_id = match.group(2)      # Exercise ID (e.g., exe:reflex-agent)
        attributes = match.group(3)       # Attributes after ID (e.g., title="...")
        solution_content = match.group(5) # Content inside exercise-solution
        after_solution = match.group(7)   # Content after inner ::: but before outer :::

        # Extract title attribute if present
        title_match = re.search(r'title="([^"]+)"', attributes)
        title = title_match.group(1) if title_match else None

        # Store the solution content with metadata
        solutions[exercise_id] = {
            'content': solution_content.strip(),
            'title': title
        }

        # Return the exercise without the solution div
        return before_solution + after_solution + match.group(8)

    # Extract all solutions and remove them from content
    content_without_solutions = re.sub(exercise_pattern, extract_solution, content, flags=re.DOTALL)

    return content_without_solutions, solutions

def extract_exercise_problems(content):
    """
    Extract exercise problem-statement bodies from `::: {.exercise #exe:...}` divs.

    Intended to run on the output of `extract_exercise_solutions`, so any nested
    `::: {.exercise-solution}` div has already been removed; the body captured
    here is therefore just the problem statement.

    Returns a dict mapping exercise IDs to {'title': str|None, 'content': markdown_body}.
    """
    problems = {}
    lines = content.split('\n')

    opener_re = re.compile(
        r'^:::[ \t]+\{\.exercise\s+#(exe[:\-][A-Za-z0-9_-]+)([^}]*)\}[ \t]*$'
    )

    i = 0
    while i < len(lines):
        m = opener_re.match(lines[i])
        if not m:
            i += 1
            continue

        exercise_id = m.group(1)
        attributes = m.group(2)
        title_match = re.search(r'title="([^"]+)"', attributes)
        title = title_match.group(1) if title_match else None

        body_lines = []
        depth = 1
        j = i + 1
        while j < len(lines):
            stripped = lines[j].strip()
            if stripped == ':::':
                depth -= 1
                if depth == 0:
                    break
                body_lines.append(lines[j])
            elif stripped.startswith(':::') and '{' in stripped:
                depth += 1
                body_lines.append(lines[j])
            else:
                body_lines.append(lines[j])
            j += 1

        if depth == 0:
            problems[exercise_id] = {
                'title': title,
                'content': '\n'.join(body_lines).strip(),
            }
            i = j + 1
        else:
            # Unbalanced fence; skip past the opener and keep scanning.
            i += 1

    return problems


def convert_solution_to_html(solution_markdown, chapter_dir):
    """Convert solution markdown content to HTML using pypandoc."""
    import tempfile

    filter_path = Path(__file__).parent.parent / "filters" / "filter.lua"

    # Create a temporary file for the solution content
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False,
                                     dir=chapter_dir) as temp_file:
        temp_file.write(solution_markdown)
        temp_file.flush()

        try:
            html = pypandoc.convert_file(
                temp_file.name, 'html+raw_tex',
                format='markdown-smart-markdown_in_html_blocks+raw_tex+tex_math_dollars+grid_tables',
                extra_args=[
                    f"--lua-filter={filter_path}",
                    "--wrap=none",
                    "--mathjax",
                ]
            )
        finally:
            import os
            try:
                os.unlink(temp_file.name)
            except:
                pass

    # Post-process HTML
    html = _post_process_html_for_anchors(html)
    return html

def load_section(chapter_dir, section_slug, with_hashes=False, transform=None):
    section_path = chapter_dir / f"{section_slug}.md"
    with open(section_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Separate YAML front matter and markdown content
    if raw.startswith("---"):
        _, frontmatter, content = raw.split("---", 2)
        meta = yaml.safe_load(frontmatter.strip())
    else:
        raise ValueError(f"Missing frontmatter in {section_path}")

    if transform is not None:
        content = transform(content)

    # Extract solutions before processing content
    content_without_solutions, solutions_markdown = extract_exercise_solutions(content)

    # Convert solution markdown to HTML
    solutions_html = {}
    for exercise_id, solution_data in solutions_markdown.items():
        # solution_data is now a dict with 'content' and 'title'
        solution_content_html = convert_solution_to_html(solution_data['content'], chapter_dir)
        solutions_html[exercise_id] = {
            'content': solution_content_html,
            'title': solution_data.get('title')
        }

    # Extract problem bodies (used by the exam print view). Runs on the
    # solution-stripped content so the captured body is the problem statement only.
    problems_markdown = extract_exercise_problems(content_without_solutions)
    problems_html = {}
    for exercise_id, problem_data in problems_markdown.items():
        problem_content_html = convert_solution_to_html(problem_data['content'], chapter_dir)
        problems_html[exercise_id] = {
            'content': problem_content_html,
            'title': problem_data.get('title'),
        }

    # Extract anchor IDs from the content (now without solutions)
    anchor_ids = extract_anchor_ids(content_without_solutions,
                                    with_hashes=with_hashes)

    # Section-level short hash (schema v2): front matter `hash:` key
    section_hash = None
    if with_hashes and meta.get('hash') is not None:
        section_hash = str(meta['hash'])

    # Add the section's frontmatter ID as a heading anchor for cross-referencing
    if 'id' in meta and meta['id']:
        section_id = str(meta['id'])  # Ensure ID is a string (YAML may parse numeric IDs as integers)
        # Only add if not already in anchors (avoid duplicates)
        if not any(a.get('id') == section_id for a in anchor_ids if isinstance(a, dict)):
            section_anchor = {
                'id': section_id,
                'type': 'heading',
                'level': 2,  # Section-level anchor (matches ## heading level)
                'title': meta.get('title', ''),
                'is_section': True  # Mark this as a section-level anchor, not an internal heading
            }
            if section_hash:
                section_anchor['hash'] = section_hash
            anchor_ids.insert(0, section_anchor)

    # Create a temporary file with the content to preserve directory context
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False,
                                     dir=chapter_dir) as temp_file:
        temp_file.write(content_without_solutions.strip())
        temp_file.flush()

        filter_path = Path(__file__).parent.parent / "filters" / "filter.lua"
        try:
            html = pypandoc.convert_file(temp_file.name, 'html+raw_tex',
                                       format='markdown-smart-markdown_in_html_blocks+raw_tex+tex_math_dollars+grid_tables',
                                       extra_args=[
                                           f"--lua-filter={filter_path}",
                                           "--wrap=none",
                                           "--mathjax",
                                       ])
        finally:
            # Clean up temporary file
            import os
            try:
                os.unlink(temp_file.name)
            except:
                pass

    # Post-process HTML to wrap equations and convert {#id} to id attributes
    html = _post_process_html_for_anchors(html)

    result = {
        "title": meta.get("title", ""),
        "slug": meta.get("slug", section_slug),
        "html": html,
        "anchors": anchor_ids
    }
    if section_hash:
        result["hash"] = section_hash

    # Add solutions if any were found
    if solutions_html:
        result["has_solutions"] = True
        result["solutions"] = solutions_html

    # Add problem bodies if any exercises were found (used by the exam print view).
    if problems_html:
        result["problems"] = problems_html

    # Schema v2: web-publication metadata (drives `parody preview --online-only`
    # for a partial public site, e.g. rtcbook.org). online_only marks a section
    # licensed for the public web subset; online_resources is per-section
    # web-only addenda authored in a sibling <slug>.online.md.
    if with_hashes:
        if meta.get("online_only") or _heading_is_online_only(
                content_without_solutions, section_hash):
            result["online_only"] = True
        online_resources = _load_online_resources(chapter_dir, section_slug)
        if online_resources:
            result["online_resources"] = online_resources

    return result


_ONLINE_HEADING_RE = re.compile(
    r'^#{1,6}\s+.*\{[^}]*\.online-only[^}]*\}\s*$', re.M)


def _heading_is_online_only(content, section_hash=None):
    """True if the section is marked `.online-only` (meta's marker for sections
    published to the web but not the print book). Prefers the heading carrying
    the section's own hash (robust when generated content, e.g. the parts-list
    catalog, is injected ahead of it); falls back to the leading heading."""
    if section_hash:
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("#") and ".online-only" in s and (
                    f'h="{section_hash}"' in s or f'h={section_hash}' in s):
                return True
    for line in content.lstrip().splitlines():
        s = line.strip()
        if not s or s.startswith("<!--"):
            continue
        if s.startswith("#"):
            return bool(_ONLINE_HEADING_RE.match(s))
        # stop at the first non-heading content block
        return False
    return False


def _load_online_resources(chapter_dir, section_slug):
    """Render a sibling <slug>.online.md (per-section web-only addenda) to HTML.
    Returns None when absent or a placeholder ('No online resources')."""
    path = chapter_dir / f"{section_slug}.online.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        try:
            _, _fm, text = text.split("---", 2)
        except ValueError:
            pass
    text = text.strip()
    if not text or text.lower().rstrip(".") == "no online resources":
        return None
    return convert_solution_to_html(text, chapter_dir)

def convert_notebook(notebook_dir, output_path, convert_jupytext=True, media_root=None):
    notebook_dir = Path(notebook_dir)
    if media_root is not None:
        # Execution-time figure moves read this env var (the figure mover sits
        # several layers below and ancestor code resolved against cwd).
        os.environ["PARODY_MEDIA_ROOT"] = str(Path(media_root).resolve())
    meta = load_yaml(notebook_dir / "__meta.yaml")
    notebook_slug = notebook_dir.name

    if convert_jupytext:
        # First, convert any jupytext files in the notebook directory
        print(f"Converting jupytext files in {notebook_dir}...")
        converted_files = convert_jupytext_files_in_directory(notebook_dir)
        if converted_files:
            print(f"✓ Converted {len(converted_files)} jupytext files")

    output = {
        "schema_version": SCHEMA_VERSION,
        "generator": f"parody {__version__}",
        "source_commit": get_source_commit(notebook_dir),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": meta.get("title", ""),
        "author": meta.get("author", []),
        "description": meta.get("description", ""),
        "acronym": meta.get("acronym", ""),
        "cover_image": meta.get("cover_image", ""),
        "pdf_file": meta.get("pdf_file", ""),
        "chapters": []
    }

    requested_code_files = set()

    for chapter_slug in meta.get("chapter_slugs", []):
        chapter_yaml = load_yaml(notebook_dir / f"_chapter_{chapter_slug}.yaml")
        chapter_dir = notebook_dir / f"chapter_{chapter_slug}"

        if convert_jupytext:
            # Convert jupytext files in this chapter directory
            chapter_converted = convert_jupytext_files_in_directory(chapter_dir)
            if chapter_converted:
                print(f"✓ Converted {len(chapter_converted)} jupytext files in chapter {chapter_slug}")

        chapter_data = {
            "title": chapter_yaml.get("title", ""),
            "slug": chapter_slug,
            "sections": []
        }
        for section_slug in chapter_yaml.get("section_slugs", []):
            for path in get_section_download_paths(chapter_dir, section_slug):
                requested_code_files.add((chapter_dir.name, path))
            section_data = load_section(chapter_dir, section_slug)
            chapter_data["sections"].append(section_data)

        output["chapters"].append(chapter_data)

    # Copy only requested code files to media directory
    if requested_code_files:
        print("Copying requested code files to media...")
        files_copied = copy_selected_code_files_to_media(
            notebook_dir,
            notebook_slug,
            requested_code_files,
            media_root=media_root
        )
        if files_copied > 0:
            print(f"✓ Copied {files_copied} code files to media/notebooks/{notebook_slug}/")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Notebook JSON written to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_notebook_md_to_json.py <input_dir> <output_json>")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_json = sys.argv[2]

    convert_notebook(input_dir, output_json)
