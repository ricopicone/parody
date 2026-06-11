"""
API-based Jupytext to Markdown Converter with Execution

This script uses jupytext's Python API directly to convert Python files to notebooks,
then executes them and converts to markdown. This avoids CLI configuration issues
with jupyter_contrib_nbextensions and other problematic extensions.
"""

import os
import sys
import tempfile
import hashlib
import json
import shutil
from pathlib import Path
import argparse
from datetime import datetime
import time
import io
import contextlib
import traceback

# Auto-figure capture constants
AUTOFIG_HELPER_TAG = "remove_cell"
AUTOFIG_DISABLE_TAG = "no_autofig"
AUTOFIG_CAPTURE_SENTINEL = "# __AUTOFIG_CAPTURE__"

# Import required libraries
try:
    import jupytext
    import nbformat
    from nbconvert import MarkdownExporter
    from nbconvert.preprocessors import ExecutePreprocessor, TagRemovePreprocessor
    from traitlets.config import Config
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install: pip install jupytext nbconvert matplotlib")
    sys.exit(1)

# Import figure mover utility
try:
    from .figure_mover import move_figures_after_notebook_execution
    FIGURE_MOVER_AVAILABLE = True
except ImportError:
    FIGURE_MOVER_AVAILABLE = False
    print("Warning: figure_mover utility not available. Figure files will not be moved automatically.")


def calculate_file_hash(file_path):
    """Calculate SHA-256 hash of a file for dependency tracking."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def load_conversion_cache(cache_file):
    """Load conversion cache from JSON file."""
    if not cache_file.exists():
        return {}
    try:
        with open(cache_file, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_conversion_cache(cache_file, cache_data):
    """Save conversion cache to JSON file."""
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save conversion cache: {e}")


def needs_conversion(input_path, output_path, cache_data):
    """Check if conversion is needed based on file modification times and hashes."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    # If output doesn't exist, conversion is needed
    if not output_path.exists():
        return True

    # Calculate current hash of input file
    current_hash = calculate_file_hash(input_path)
    if not current_hash:
        return True

    # Check cache: if the input file hash matches what we cached when we
    # last converted, and the output file still exists, no conversion is
    # needed.  We intentionally do NOT check modification times here
    # because git reset --hard (used during deployment) resets mtimes
    # even when file content is unchanged, which would cause unnecessary
    # re-execution of expensive notebooks (e.g. those requiring torch).
    cache_key = str(input_path)
    if cache_key in cache_data:
        cached_info = cache_data[cache_key]
        if (cached_info.get('hash') == current_hash and
            cached_info.get('output_path') == str(output_path)):
            return False

    return True


def is_jupytext_file(file_path):
    """Check if a Python file is in jupytext format by looking for cell markers."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for percent format markers
        if '# %%' in content:
            return 'percent'

        # Check for light format markers
        if '# +' in content or '# -' in content:
            return 'light'

        # Check if it looks like light format (comments not adjacent to code)
        lines = content.split('\n')
        has_standalone_comments = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#') and not stripped.startswith('# +') and not stripped.startswith('# -'):
                # Check if this comment is standalone (not adjacent to code)
                next_line = lines[i + 1] if i + 1 < len(lines) else ''
                prev_line = lines[i - 1] if i - 1 >= 0 else ''

                if (next_line.strip() == '' or next_line.strip().startswith('#')) and \
                   (prev_line.strip() == '' or prev_line.strip().startswith('#')):
                    has_standalone_comments = True
                    break

        if has_standalone_comments:
            return 'light'

    except Exception as e:
        print(f"Error reading file {file_path}: {e}")

    return None


def convert_py_to_notebook_api(py_file):
    """Convert Python file to Jupyter notebook using jupytext API."""
    try:
        # Read the Python file and convert using jupytext API
        notebook = jupytext.read(py_file)
        return notebook
    except Exception as e:
        print(f"Error converting {py_file} to notebook using jupytext API: {e}")
        return None


def _cell_source(cell):
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return source


def _cell_has_tag(cell, tag):
    tags = cell.get("metadata", {}).get("tags", [])
    return tag in tags


def _cell_contains_engcom_show(source):
    return (
        "engcom.show" in source
        or "notebook_utils.show" in source
        or "teaching.utils.notebook_utils.show" in source
    )


def _inject_autofig_helpers(notebook, working_dir=None, fig_dir=None):
    """Inject auto-figure helper code as first cell.

    Args:
        notebook: The notebook object to modify
        working_dir: The working directory path to use for imports and file operations
        fig_dir: Where captures are saved. Defaults to the working dir; the
            converter passes <script_dir>/<stem>_files so figures land in
            their committed source-tree home (no post-hoc moving).
    """
    # Get the working directory - use provided path or fallback to os.getcwd()
    if working_dir:
        wd_code = f'_AUTOFIG_WORKING_DIR = r"{working_dir}"'
    else:
        wd_code = '_AUTOFIG_WORKING_DIR = os.getcwd()'
    wd_code += (f'\n_AUTOFIG_FIG_DIR = r"{fig_dir}"' if fig_dir
                else '\n_AUTOFIG_FIG_DIR = _AUTOFIG_WORKING_DIR')

    # Build helper code with working directory injected
    helper_code = ('''
# Auto-injected helpers for figure capture and matplotlib configuration
import os
import sys

# Get the working directory - this is where log file will be written and modules are located
''' + wd_code + '''

# Add current directory to sys.path so relative imports work
if _AUTOFIG_WORKING_DIR not in sys.path:
    sys.path.insert(0, _AUTOFIG_WORKING_DIR)

import matplotlib
# Use SVG backend for vector graphics (force=True to override inline backend)
try:
    matplotlib.use('SVG', force=True)
except:
    try:
        matplotlib.use('Agg', force=True)  # Fallback to Agg if SVG not available
    except:
        pass

import matplotlib.pyplot as plt

# Configure matplotlib to save as SVG
plt.rcParams['savefig.format'] = 'svg'

try:
    import json
    import time
    from pathlib import Path

    try:
        from IPython import get_ipython
    except Exception:
        get_ipython = None
except Exception:
    json = None
    time = None
    Path = None
    get_ipython = None

# Disable IPython's inline backend post_execute hook that closes figures
# after each cell. Without this, figures are closed before our appended
# capture code can save them.
try:
    _ip = get_ipython() if get_ipython else None
    if _ip is not None:
        from matplotlib_inline.backend_inline import flush_figures
        try:
            _ip.events.unregister('post_execute', flush_figures)
        except ValueError:
            pass
except Exception:
    pass

_AUTOFIG_LOG_PATH = os.path.join(_AUTOFIG_WORKING_DIR, '.autofig_log.jsonl') if Path else None
_AUTOFIG_PENDING = None
_AUTOFIG_ANIMATIONS = {}  # Store animations to prevent garbage collection
_AUTOFIG_GIF_COUNTER = {}  # Per-execution-count counter for sequential GIF naming

try:
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    _AUTOFIG_HAS_3D = True
except Exception:
    _AUTOFIG_HAS_3D = False

if _AUTOFIG_LOG_PATH and Path(_AUTOFIG_LOG_PATH).exists():
    try:
        Path(_AUTOFIG_LOG_PATH).unlink()
    except Exception:
        pass


def autofig(fig=None, caption=None, label=None, width=None, height=None,
            fmt=None, raster=None, dpi=150, filename=None, ext=None,
            figsize=None, **_compat):
    # Two modes:
    #   autofig(caption=..., label=...)      -> metadata for the figures the
    #       end-of-cell capture finds (classic pending mode)
    #   autofig(fig, caption=..., label=...) -> capture THAT figure now
    #       (drop-in for engcom.show; accepts its ext=/filename=/figsize=)
    global _AUTOFIG_PENDING
    _AUTOFIG_PENDING = {
        "caption": caption,
        "label": label,
        "width": width,
        "height": height,
        "format": fmt or ext,
        "raster": raster,
        "dpi": dpi,
        "filename": filename,
    }
    if fig is not None:
        if figsize is not None:
            try:
                fig.set_size_inches(*figsize)
            except Exception:
                pass
        _autofig_capture_one(fig)


def _autofig_capture_one(fig):
    """Capture a single explicit figure with the pending metadata."""
    global _AUTOFIG_PENDING
    meta = _AUTOFIG_PENDING or {}
    fmt = meta.get("format")
    if not fmt:
        fmt = "png" if (_autofig_is_3d(fig) or meta.get("raster")) else "svg"
    base = meta.get("filename")
    if not base and meta.get("label"):
        base = str(meta["label"])
        if base.startswith("fig:"):
            base = base[4:]
        base = "".join(c if (c.isalnum() or c in "-_") else "-" for c in base)
    if base:
        base = base.rsplit(".", 1)[0]
        filename = f"{base}.{fmt}"
    else:
        suffix = _autofig_execution_count() or "cell"
        filename = f"autofig-{suffix}-x.{fmt}"
    os.makedirs(_AUTOFIG_FIG_DIR, exist_ok=True)
    filepath = os.path.join(_AUTOFIG_FIG_DIR, filename)
    try:
        fig.savefig(filepath, format=fmt, dpi=meta.get("dpi", 150))
    except Exception:
        _AUTOFIG_PENDING = None
        return
    record = {
        "cell_index": None,
        "execution_count": _autofig_execution_count(),
        "filename": filename,
        "caption": meta.get("caption"),
        "label": meta.get("label"),
        "width": meta.get("width"),
        "height": meta.get("height"),
    }
    if _AUTOFIG_LOG_PATH and json:
        try:
            with Path(_AUTOFIG_LOG_PATH).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\\n")
        except Exception:
            pass
    _AUTOFIG_PENDING = None
    import matplotlib.pyplot as _plt
    try:
        _plt.close(fig)
    except Exception:
        pass


def _autofig_is_3d(fig):
    if fig is None:
        return False
    for ax in fig.axes:
        if getattr(ax, "name", "") == "3d" or ax.__class__.__name__ == "Axes3D":
            return True
    return False


def _autofig_execution_count():
    if get_ipython:
        try:
            return get_ipython().execution_count
        except Exception:
            return None
    return None


def _autofig_capture(cell_index=None):
    global _AUTOFIG_PENDING
    if plt is None:
        _AUTOFIG_PENDING = None
        return

    fig_nums = plt.get_fignums()
    if not fig_nums:
        _AUTOFIG_PENDING = None
        return

    for idx, num in enumerate(fig_nums, start=1):
        fig = plt.figure(num)
        meta = _AUTOFIG_PENDING or {}
        fmt = meta.get("format")
        if not fmt:
            if meta.get("raster"):
                fmt = "png"
            else:
                # 3D plots need PNG, 2D plots use SVG
                fmt = "png" if _autofig_is_3d(fig) else "svg"

        dpi = meta.get("dpi", 150)
        # Deterministic names when the author supplied one: filename= wins,
        # then label= (sanitized, fig: prefix dropped). Unnamed figures keep
        # the cell-index scheme (documented as unstable across cell moves).
        base = meta.get("filename")
        if not base and meta.get("label"):
            base = str(meta["label"])
            if base.startswith("fig:"):
                base = base[4:]
            base = "".join(c if (c.isalnum() or c in "-_") else "-" for c in base)
        if base:
            base = base.rsplit(".", 1)[0]
            filename = f"{base}.{fmt}" if idx == 1 else f"{base}-{idx}.{fmt}"
        else:
            suffix = cell_index if cell_index is not None else _autofig_execution_count() or "cell"
            filename = f"autofig-{suffix}-{idx}.{fmt}"
        os.makedirs(_AUTOFIG_FIG_DIR, exist_ok=True)
        filepath = os.path.join(_AUTOFIG_FIG_DIR, filename)

        try:
            fig.savefig(filepath, format=fmt, dpi=dpi)
        except Exception:
            continue

        record = {
            "cell_index": cell_index,
            "execution_count": _autofig_execution_count(),
            "filename": filename,
            "caption": meta.get("caption"),
            "label": meta.get("label"),
            "width": meta.get("width"),
            "height": meta.get("height"),
        }
        if _AUTOFIG_LOG_PATH and json:
            try:
                with Path(_AUTOFIG_LOG_PATH).open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\\n")
            except Exception:
                pass

    _AUTOFIG_PENDING = None

    # Close all figures after capture to prevent accumulation across cells
    plt.close('all')


# Replace plt.show() with a no-op so figures stay open until the
# appended _autofig_capture() code runs at the end of the same cell.
# Mark the wrapper so we can detect if it's been replaced.
_autofig_original_show = plt.show

def _autofig_show(*args, **kwargs):
    pass  # no-op: figures stay open for capture
_autofig_show._autofig_noop = True

plt.show = _autofig_show

# Register an IPython pre_run_cell event to re-apply the plt.show wrapper
# before every cell. This guards against libraries like engcom that reload
# matplotlib.pyplot and restore the original show() function.
def _autofig_pre_run_cell(*args, **kwargs):
    import matplotlib.pyplot as _mplt
    if not getattr(_mplt.show, '_autofig_noop', False):
        _mplt.show = _autofig_show

try:
    _ip = get_ipython() if get_ipython else None
    if _ip is not None:
        _ip.events.register('pre_run_cell', _autofig_pre_run_cell)
except Exception:
    pass


def autofig_gif(anim, caption=None, label=None, width=None, height=None, fps=5, loop=0, cell_index=None):
    # Save a matplotlib animation to GIF and register it for inclusion.
    if time is None or anim is None:
        return anim

    suffix = cell_index if cell_index is not None else _autofig_execution_count()
    # Sequential numbering per cell, matching SVG naming convention
    _AUTOFIG_GIF_COUNTER[suffix] = _AUTOFIG_GIF_COUNTER.get(suffix, 0) + 1
    gif_num = _AUTOFIG_GIF_COUNTER[suffix]
    filename = f"autofig-{suffix}-anim-{gif_num}.gif"
    
    # Save animation with full path
    saved = False
    try:
        from matplotlib.animation import PillowWriter
        filepath = os.path.join(_AUTOFIG_WORKING_DIR, filename)
        writer = PillowWriter(fps=fps)
        anim.save(filepath, writer=writer)
        saved = True
    except Exception:
        pass
    
    # Keep animation reference to prevent garbage collection
    _AUTOFIG_ANIMATIONS[filename] = anim
    
    # Log the entry if save was successful
    record = {
        "cell_index": cell_index,
        "execution_count": _autofig_execution_count(),
        "filename": filename if saved else None,
        "caption": caption,
        "label": label,
        "width": width,
        "height": height,
    }
    if _AUTOFIG_LOG_PATH and json and saved:
        try:
            with Path(_AUTOFIG_LOG_PATH).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\\n")
        except Exception:
            pass
    
    # Return animation to keep reference alive
    return anim
''').strip()

    helper_cell = nbformat.v4.new_code_cell(helper_code)
    # Don't tag with remove_cell - we want it to execute
    # We'll remove it manually after execution
    helper_cell.metadata["tags"] = ["autofig_helper"]

    notebook.cells.insert(0, helper_cell)
    return notebook


def _inject_autofig_capture_calls(notebook):
    """Append auto-figure capture code to the end of each code cell.
    
    By appending to the same cell (rather than creating a separate cell),
    figures are guaranteed to still be open when capture runs.
    The appended code is delimited by AUTOFIG_CAPTURE_SENTINEL so it
    can be stripped after execution.
    """
    for idx, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        if _cell_has_tag(cell, AUTOFIG_DISABLE_TAG) or _cell_has_tag(cell, AUTOFIG_HELPER_TAG):
            continue

        source = _cell_source(cell)
        if "_autofig_capture(" in source:
            continue
        if _cell_contains_engcom_show(source):
            continue

        # Skip if immediately followed by engcom.show() in the next code cell
        skip_capture = False
        for next_cell in notebook.cells[idx + 1:]:
            if next_cell.cell_type != "code":
                continue
            next_source = _cell_source(next_cell)
            if _cell_contains_engcom_show(next_source):
                skip_capture = True
            break

        if skip_capture:
            continue

        cell.metadata.setdefault("autofig_index", idx)

        # Append capture code to the end of the cell, delimited by sentinel.
        capture_snippet = (
            f"\n{AUTOFIG_CAPTURE_SENTINEL}\n"
            f"if '_autofig_capture' in dir():\n"
            f"    _autofig_capture(cell_index={idx})\n"
            f"elif '_autofig_capture' in globals():\n"
            f"    _autofig_capture(cell_index={idx})\n"
            f"import matplotlib.pyplot as _plt; _plt.close('all')\n"
        )
        cell.source = source + capture_snippet

    return notebook


def _strip_autofig_capture_code(notebook):
    """Remove the appended capture code from all cells after execution."""
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = _cell_source(cell)
        if AUTOFIG_CAPTURE_SENTINEL in source:
            cell.source = source[:source.index(AUTOFIG_CAPTURE_SENTINEL)].rstrip()
    return notebook


def _inject_autofig_markdown_cells(notebook, autofig_entries):
    entries_by_cell = {}
    entries_by_exec = {}
    for entry in autofig_entries:
        cell_index = entry.get("cell_index")
        exec_count = entry.get("execution_count")
        if cell_index is not None:
            entries_by_cell.setdefault(cell_index, []).append(entry)
        elif exec_count is not None:
            entries_by_exec.setdefault(exec_count, []).append(entry)

    new_cells = []
    for idx, cell in enumerate(notebook.cells):
        new_cells.append(cell)
        # Only match code cells — markdown cells should never get autofig images
        if cell.cell_type != "code":
            continue
        source_index = cell.get("metadata", {}).get("autofig_index")
        # Match by autofig_index metadata (preferred) — never fall back to raw idx
        # to avoid false matches when a markdown cell happens to sit at the same index.
        cell_entries = list(entries_by_cell.get(source_index, [])) if source_index is not None else []
        # Also include entries matched by execution_count (e.g. autofig_gif calls
        # which don't know their cell_index).
        if entries_by_exec:
            exec_count = cell.get("execution_count")
            if exec_count in entries_by_exec:
                cell_entries.extend(entries_by_exec[exec_count])

        if cell_entries:
            md_lines = []
            for entry in cell_entries:
                caption = entry.get("caption")
                label = entry.get("label")
                width = entry.get("width")
                height = entry.get("height")
                filename = entry.get("filename")
                if not filename:
                    continue

                # Build alt text from caption and/or label
                alt_parts = []
                if caption:
                    alt_parts.append(caption)
                if label:
                    alt_parts.append(label)
                alt = "|".join(alt_parts) if alt_parts else ""

                attrs = []
                if width:
                    attrs.append(f"width={width}")
                if height:
                    attrs.append(f"height={height}")
                attr_text = f"{{{' '.join(attrs)}}}" if attrs else ""
                md_lines.append(f"![{alt}]({filename}){attr_text}")

            if md_lines:
                md_cell = nbformat.v4.new_markdown_cell("\n\n".join(md_lines))
                new_cells.append(md_cell)

    notebook.cells = new_cells
    return notebook


def _strip_autofig_image_outputs(notebook, autofig_entries):
    entries_by_cell = {}
    entries_by_exec = {}
    for entry in autofig_entries:
        cell_index = entry.get("cell_index")
        if cell_index is not None:
            entries_by_cell.setdefault(cell_index, []).append(entry)
        exec_count = entry.get("execution_count")
        if exec_count is not None:
            entries_by_exec.setdefault(exec_count, []).append(entry)

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source_index = cell.get("metadata", {}).get("autofig_index")
        exec_count = cell.get("execution_count")
        has_entries = False
        if source_index is not None and source_index in entries_by_cell:
            has_entries = True
        if not has_entries and exec_count is not None and exec_count in entries_by_exec:
            has_entries = True
        if not has_entries:
            continue

        outputs = cell.get("outputs", [])
        if not outputs:
            continue
        filtered_outputs = []
        for output in outputs:
            data = output.get("data") if isinstance(output, dict) else None
            if not data:
                filtered_outputs.append(output)
                continue
            if any(key in data for key in ["image/png", "image/svg+xml", "image/gif"]):
                continue
            filtered_outputs.append(output)
        cell["outputs"] = filtered_outputs

    return notebook


def execute_notebook_api(notebook, timeout=300, cwd=None):
    """Execute notebook using nbconvert ExecutePreprocessor.

    The kernel is pinned to the running interpreter (sys.executable) rather
    than whatever a 'python3' kernelspec resolves to: ipykernel's default spec
    launches a bare `python` from PATH, so under `make`/CI the kernel could be
    a different interpreter than the one parody (and the notebook's
    dependencies) are installed in.
    """
    try:
        # Create ExecutePreprocessor with figure extraction
        from traitlets.config import Config as TraitletsConfig
        c = TraitletsConfig()
        c.ExecutePreprocessor.timeout = timeout
        c.ExecutePreprocessor.allow_errors = True
        c.ExecutePreprocessor.kernel_name = 'python3'
        c.ExecutePreprocessor.store_widget_state = False

        ep = ExecutePreprocessor(config=c)

        # Set working directory directly on preprocessor instance
        if cwd:
            ep.cwd = str(cwd)

        # Pin the kernel to the current interpreter.
        from jupyter_client.manager import KernelManager
        km = KernelManager(kernel_name='python3')
        try:
            km.kernel_spec.argv = [
                sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'
            ]
        except Exception:
            # No 'python3' kernelspec anywhere; build the spec from scratch.
            from jupyter_client.kernelspec import KernelSpec
            km._kernel_spec = KernelSpec(
                argv=[sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
                display_name='python3', language='python',
            )

        # Execute the notebook with proper working directory
        resources = {}
        executed_notebook, resources = ep.preprocess(notebook, resources, km=km)

        # allow_errors=True keeps execution going so we can report every
        # failing cell, but errors must not silently become content: the
        # ancestor pipeline baked tracebacks into served HTML.
        errors = []
        for cell in executed_notebook.cells:
            if cell.get('cell_type') != 'code':
                continue
            for out in cell.get('outputs', []):
                if out.get('output_type') == 'error':
                    errors.append(f"{out.get('ename', 'Error')}: {out.get('evalue', '')}")
        if errors:
            print(f"❌ {len(errors)} cell(s) raised during execution:")
            for err in errors[:5]:
                print(f"   {err}")
            return executed_notebook, False

        return executed_notebook, True

    except Exception as e:
        print(f"Warning: Failed to execute notebook: {e}")
        # Return original notebook if execution fails
        return notebook, False


def convert_notebook_to_markdown_api(notebook, output_path):
    """Convert notebook to markdown using nbconvert API."""
    try:
        # Configure cell tag removal
        c = Config()
        c.TagRemovePreprocessor.remove_cell_tags = ("remove_cell",)
        c.TagRemovePreprocessor.remove_input_tags = ("remove_input",)
        c.TagRemovePreprocessor.remove_all_outputs_tags = ("remove_output",)
        c.TagRemovePreprocessor.enabled = True

        # Configure the exporter for SVG figures where possible
        c.MarkdownExporter.preprocessors = [
            'nbconvert.preprocessors.TagRemovePreprocessor',
        ]

        # Create MarkdownExporter with tag removal preprocessor
        exporter = MarkdownExporter(config=c)
        exporter.register_preprocessor(TagRemovePreprocessor(config=c), True)

        # Convert to markdown
        body, resources = exporter.from_notebook_node(notebook)

        # Write markdown file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(body)

        # Handle any output files (like images)
        if 'outputs' in resources:
            output_files_dir = output_path.parent / f"{output_path.stem}_files"
            output_files_dir.mkdir(exist_ok=True)

            for filename, data in resources['outputs'].items():
                output_file_path = output_files_dir / filename
                if isinstance(data, str):
                    with open(output_file_path, 'w', encoding='utf-8') as f:
                        f.write(data)
                else:
                    with open(output_file_path, 'wb') as f:
                        f.write(data)

        return True

    except Exception as e:
        print(f"Error converting notebook to markdown: {e}")
        return False


def clean_markdown_output(md_path):
    """Clean up the markdown output."""
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Remove jupyter metadata block if present
        if content.startswith('---\n'):
            parts = content.split('---\n', 2)
            if len(parts) >= 3:
                content = parts[2]

        # Clean up cell separators and unnecessary newlines
        content = content.replace('\n\n\n\n', '\n\n')
        content = content.replace('\n\n\n', '\n\n')

        # Fix image paths to be relative
        import re
        content = re.sub(
            r'!\[([^\]]*)\]\(([^)]*_files/[^)]*)\)',
            r'![\1](\2)',
            content
        )

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(content.strip() + '\n')

        return True
    except Exception as e:
        print(f"Warning: Could not clean markdown output {md_path}: {e}")
        return False


def rewrite_markdown_image_paths(md_path, source_notebook_path):
    try:
        from .figure_mover import determine_destination_path
        source_notebook_path = Path(source_notebook_path)
        dest_path = determine_destination_path(source_notebook_path)
        media_rel = str(dest_path).replace("media/", "")

        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        import re
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        def repl(match):
            alt_text = match.group(1)
            path = match.group(2)
            if path.startswith('notebooks/') or path.startswith('media/'):
                return match.group(0)
            if re.match(r'^(output_[^/]+\.(png|svg|gif))$', path) or re.match(r'^(autofig-[^/]+\.(png|svg|gif))$', path):
                return f"![{alt_text}]({media_rel}/{path})"
            return match.group(0)

        updated = re.sub(pattern, repl, content)

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(updated)

        return True
    except Exception as e:
        print(f"Warning: Could not rewrite image paths in {md_path}: {e}")
        return False


def convert_jupytext_with_api_execution(input_path, output_path=None, timeout=300, cache_data=None):
    """
    Convert a jupytext Python file to markdown using Python APIs with execution.
    
    Args:
        input_path: Path to the jupytext Python file
        output_path: Optional output path for markdown file
        timeout: Timeout for code execution in seconds
        cache_data: Conversion cache dictionary for dependency tracking
    
    Returns:
        tuple: (success: bool, output_path: Path or None, was_cached: bool)
    """
    input_path = Path(input_path)

    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist")
        return False, None, False

    # Determine format
    format_type = is_jupytext_file(input_path)
    if not format_type:
        print(f"Warning: {input_path} does not appear to be a jupytext file")
        return False, None, False

    if output_path is None:
        output_path = input_path.with_suffix('.md')
    else:
        output_path = Path(output_path)

    # Check if conversion is needed
    if cache_data is not None:
        if not needs_conversion(input_path, output_path, cache_data):
            print(f"⚡ Cached: {input_path} → {output_path} (up to date)")
            return True, output_path, True

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Convert Python file to notebook using jupytext API
        notebook = convert_py_to_notebook_api(input_path)
        if notebook is None:
            return False, None, False

        # Determine working directory (where the notebook source file is)
        # Must resolve to absolute path for kernel working directory and autofig file operations
        script_dir = input_path.parent.resolve()

        # Step 1b: Inject auto-figure helpers and capture calls
        fig_dir = script_dir / f"{input_path.stem}_files"
        notebook = _inject_autofig_helpers(notebook, working_dir=str(script_dir),
                                           fig_dir=str(fig_dir))
        notebook = _inject_autofig_capture_calls(notebook)

        # Step 2: Execute the notebook using API (set working directory to script's directory)
        executed_notebook, execution_success = execute_notebook_api(notebook, timeout, cwd=script_dir)
        if not execution_success:
            # Do not write markdown from a failed execution: the ancestor
            # pipeline wrote tracebacks/missing outputs into content silently.
            print(f"❌ Execution failed; not writing {output_path}")
            return False, None, False

        # Step 2a: Strip injected capture code from cells and remove helper cell
        executed_notebook = _strip_autofig_capture_code(executed_notebook)
        executed_notebook.cells = [
            cell for cell in executed_notebook.cells
            if "autofig_helper" not in cell.get("metadata", {}).get("tags", [])
        ]

        # Step 2b: Inject markdown for auto-captured figures (if any)
        autofig_log = script_dir / ".autofig_log.jsonl"
        if autofig_log.exists():
            try:
                entries = []
                with autofig_log.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            continue
                if entries:
                    executed_notebook = _strip_autofig_image_outputs(executed_notebook, entries)
                    executed_notebook = _inject_autofig_markdown_cells(executed_notebook, entries)
            finally:
                try:
                    autofig_log.unlink()
                except Exception:
                    pass

        # Step 3: Convert notebook to markdown using API
        if not convert_notebook_to_markdown_api(executed_notebook, output_path):
            return False, None, False

        # Step 4: Clean up the markdown
        clean_markdown_output(output_path)
        # Image refs stay bare (e.g. "plot.svg"): the web filter prefixes
        # notebooks/<slug>/<chapter>/<stem>_files/ and the print filter
        # resolves against the source tree, so location-independent refs
        # survive repo moves. (Media-path rewriting retired with the mover.)

        # Step 5: Move any generated figure files to proper media directory
        if FIGURE_MOVER_AVAILABLE and execution_success:
            try:
                from .figure_mover import identify_figure_files, move_figures_to_media

                # Captures save straight into <stem>_files/ now; the mover
                # only sweeps LEGACY strays (e.g. engcom.show writing to the
                # kernel cwd). Top level only: *_files dirs are the
                # committed home of figures and must never be raided.
                figure_files = [
                    f for f in identify_figure_files(script_dir)
                    if f.parent == script_dir
                ]
                if figure_files:
                    results = move_figures_to_media(
                        source_notebook_path=input_path,
                        figure_files=figure_files,
                        media_root=Path(os.environ.get("PARODY_MEDIA_ROOT", Path.cwd())),
                        dry_run=False,
                    )
                    if results['moved_files']:
                        print(f"  📊 Moved {len(results['moved_files'])} legacy "
                              f"figure files to media directory")
            except Exception as e:
                print(f"Warning: Failed to move figure files: {e}")

    except Exception as e:
                print(f"Warning: Failed to move figure files: {e}")

    except Exception as e:
        print(f"Error during conversion: {e}")
        return False, None, False

    # Update cache
    if cache_data is not None:
        file_hash = calculate_file_hash(input_path)
        cache_key = str(input_path)
        cache_data[cache_key] = {
            'hash': file_hash,
            'output_path': str(output_path),
            'timestamp': datetime.now().isoformat(),
            'format': format_type,
            'executed': execution_success
        }

    status = "✓ Executed and converted" if execution_success else "✓ Converted (non-executed)"
    print(f"{status}: {input_path} → {output_path} (format: {format_type})")
    return True, output_path, False


def convert_directory_with_api_execution(input_dir, output_dir=None, recursive=True, timeout=300,
                                        cache_file=None, force=False):
    """
    Convert all jupytext Python files in a directory to markdown with API execution.
    """
    input_dir = Path(input_dir)
    results = {
        'converted_files': [],
        'cached_files': [],
        'failed_files': []
    }

    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory")
        return results

    # Load conversion cache
    cache_data = {}
    if cache_file:
        cache_file = Path(cache_file)
        if not force:
            cache_data = load_conversion_cache(cache_file)

    # Find all Python files. Never descend into hidden dirs (.venv, .git),
    # build output, vendored wheels, media trees, or tooling dirs — the
    # jupytext light-format heuristic is loose enough to match arbitrary
    # library code (it once tried to execute tornado from site-packages).
    EXCLUDED_DIRS = {"build", "dist", "vendor", "media", "scripts",
                     "node_modules", "__pycache__"}

    def _excluded(path):
        return any(
            part.startswith(".") or part in EXCLUDED_DIRS
            for part in path.relative_to(input_dir).parts[:-1]
        )

    pattern = '**/*.py' if recursive else '*.py'
    python_files = [f for f in input_dir.glob(pattern) if not _excluded(f)]

    start_time = time.time()

    for py_file in python_files:
        if is_jupytext_file(py_file):
            if output_dir:
                # Maintain relative directory structure in output
                rel_path = py_file.relative_to(input_dir)
                output_path = Path(output_dir) / rel_path.with_suffix('.md')
            else:
                output_path = py_file.with_suffix('.md')

            success, result_path, was_cached = convert_jupytext_with_api_execution(
                py_file, output_path, timeout, cache_data if not force else None
            )

            if success:
                if was_cached:
                    results['cached_files'].append(result_path)
                else:
                    results['converted_files'].append(result_path)
            else:
                results['failed_files'].append(py_file)

    # Save updated cache
    if cache_file and cache_data:
        save_conversion_cache(cache_file, cache_data)

    elapsed_time = time.time() - start_time

    total_files = len(results['converted_files']) + len(results['cached_files']) + len(results['failed_files'])
    converted_count = len(results['converted_files'])
    cached_count = len(results['cached_files'])
    failed_count = len(results['failed_files'])

    print("\nConversion Summary:")
    print(f"  Total files processed: {total_files}")
    print(f"  ✓ Converted: {converted_count}")
    print(f"  ⚡ Cached (up to date): {cached_count}")
    print(f"  ❌ Failed: {failed_count}")
    print(f"  ⏱️ Time elapsed: {elapsed_time:.1f}s")

    return results


def main():
    parser = argparse.ArgumentParser(description='Convert jupytext Python files to markdown with API execution')
    parser.add_argument('input', help='Input Python file or directory')
    parser.add_argument('-o', '--output', help='Output file or directory')
    parser.add_argument('-r', '--recursive', action='store_true',
                       help='Process directories recursively')
    parser.add_argument('--timeout', type=int, default=300,
                       help='Timeout for code execution in seconds (default: 300)')
    parser.add_argument('--cache-file', help='Path to conversion cache file')
    parser.add_argument('--force', action='store_true',
                       help='Force conversion even if cache says not needed')

    args = parser.parse_args()

    input_path = Path(args.input)

    if input_path.is_file():
        # Convert single file
        success, result_path, was_cached = convert_jupytext_with_api_execution(
            input_path, args.output, args.timeout,
            {} if args.cache_file else None
        )
        if not success:
            sys.exit(1)
    elif input_path.is_dir():
        # Convert directory
        results = convert_directory_with_api_execution(
            input_path, args.output, args.recursive, args.timeout,
            args.cache_file, args.force
        )
        if results['failed_files']:
            print("\nFailed files:")
            for failed_file in results['failed_files']:
                print(f"  ❌ {failed_file}")
            sys.exit(1)
    else:
        print(f"Error: {input_path} does not exist")
        sys.exit(1)


if __name__ == '__main__':
    main()
