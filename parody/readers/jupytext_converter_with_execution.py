"""
Enhanced Jupytext to Markdown Converter with Execution and Dependency Tracking

This script converts Python files in jupytext percent or light formats to markdown,
but unlike the basic converter, it executes the code to capture outputs, plots, and
console responses. It also includes dependency tracking to avoid unnecessary conversions.
"""

import os
import sys
import subprocess
import tempfile
import hashlib
import json
import shutil
from pathlib import Path
import argparse
from datetime import datetime
import time


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
    """
    Check if conversion is needed based on file modification times and hashes.
    
    Args:
        input_path: Path to source .py file
        output_path: Path to target .md file
        cache_data: Conversion cache dictionary
    
    Returns:
        bool: True if conversion is needed
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # If output doesn't exist, conversion is needed
    if not output_path.exists():
        return True

    # Calculate current hash of input file
    current_hash = calculate_file_hash(input_path)
    if not current_hash:
        return True

    # Check cache
    cache_key = str(input_path)
    if cache_key in cache_data:
        cached_info = cache_data[cache_key]
        if (cached_info.get('hash') == current_hash and
            cached_info.get('output_path') == str(output_path)):
            # Check if output file is newer than input
            try:
                input_mtime = input_path.stat().st_mtime
                output_mtime = output_path.stat().st_mtime
                if output_mtime >= input_mtime:
                    return False
            except Exception:
                pass

    return True


def has_jupytext():
    """Check if jupytext is available in the environment."""
    try:
        result = subprocess.run(['jupytext', '--version'],
                              capture_output=True, text=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def has_jupyter():
    """Check if jupyter is available in the environment."""
    try:
        result = subprocess.run(['jupyter', '--version'],
                              capture_output=True, text=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def is_jupytext_file(file_path):
    """
    Check if a Python file is in jupytext format by looking for cell markers.
    Supports both percent format (# %%) and light format (# + style markers).
    """
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


def convert_py_to_notebook(py_file, notebook_file):
    """Convert Python file to Jupyter notebook using jupytext."""
    try:
        cmd = ['jupytext', '--to', 'notebook', '--output', str(notebook_file), str(py_file)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {py_file} to notebook: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False


def execute_notebook(notebook_file, executed_notebook_file, timeout=300):
    """Execute notebook and save the result with outputs."""
    try:
        cmd = [
            'jupyter', 'nbconvert',
            '--to', 'notebook',
            '--execute',
            '--output', str(executed_notebook_file.name),
            '--output-dir', str(executed_notebook_file.parent),
            '--ExecutePreprocessor.timeout=' + str(timeout),
            '--ExecutePreprocessor.allow_errors=True',
            str(notebook_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error executing notebook {notebook_file}: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False


def convert_notebook_to_markdown(notebook_file, markdown_file):
    """Convert executed notebook to markdown using nbconvert."""
    try:
        cmd = [
            'jupyter', 'nbconvert',
            '--to', 'markdown',
            '--output', str(markdown_file.name),
            '--output-dir', str(markdown_file.parent),
            str(notebook_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting notebook {notebook_file} to markdown: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False


def clean_markdown_output(md_path):
    """
    Clean up the markdown output from nbconvert to make it more suitable
    for inclusion in notebooks.
    """
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
        # nbconvert creates files like "filename_files/filename_X_Y.png"
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


def convert_jupytext_with_execution(input_path, output_path=None, timeout=300, cache_data=None):
    """
    Convert a jupytext Python file to markdown with code execution.
    
    Args:
        input_path: Path to the jupytext Python file
        output_path: Optional output path for markdown file. If None, uses same name with .md extension
        timeout: Timeout for code execution in seconds
        cache_data: Conversion cache dictionary for dependency tracking
    
    Returns:
        tuple: (success: bool, output_path: Path or None, was_cached: bool)
    """
    input_path = Path(input_path)

    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist")
        return False, None, False

    if not has_jupytext():
        print("Error: jupytext is not installed or not available in PATH")
        print("Install with: pip install jupytext")
        return False, None, False

    if not has_jupyter():
        print("Error: jupyter is not installed or not available in PATH")
        print("Install with: pip install jupyter nbconvert")
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

    # Create temporary directory for intermediate files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)

        # Step 1: Convert Python file to notebook
        temp_notebook = temp_dir / 'temp_notebook.ipynb'
        if not convert_py_to_notebook(input_path, temp_notebook):
            return False, None, False

        # Step 2: Execute the notebook
        executed_notebook = temp_dir / 'executed_notebook.ipynb'
        if not execute_notebook(temp_notebook, executed_notebook, timeout):
            print("Warning: Failed to execute notebook, using non-executed version")
            executed_notebook = temp_notebook

        # Step 3: Convert executed notebook to markdown
        temp_markdown = temp_dir / 'output.md'
        if not convert_notebook_to_markdown(executed_notebook, temp_markdown):
            return False, None, False

        # Step 4: Clean up the markdown and move to final location
        if clean_markdown_output(temp_markdown):
            shutil.move(str(temp_markdown), str(output_path))

            # Move any generated files (like images) to the output directory
            files_dir = temp_dir / 'output_files'
            if files_dir.exists():
                output_files_dir = output_path.parent / f"{output_path.stem}_files"
                if output_files_dir.exists():
                    shutil.rmtree(output_files_dir)
                shutil.move(str(files_dir), str(output_files_dir))
        else:
            return False, None, False

    # Update cache
    if cache_data is not None:
        file_hash = calculate_file_hash(input_path)
        cache_key = str(input_path)
        cache_data[cache_key] = {
            'hash': file_hash,
            'output_path': str(output_path),
            'timestamp': datetime.now().isoformat(),
            'format': format_type
        }

    print(f"✓ Executed and converted: {input_path} → {output_path} (format: {format_type})")
    return True, output_path, False


def convert_directory_with_execution(input_dir, output_dir=None, recursive=True, timeout=300,
                                   cache_file=None, force=False):
    """
    Convert all jupytext Python files in a directory to markdown with execution.
    
    Args:
        input_dir: Directory containing Python files
        output_dir: Output directory for markdown files. If None, outputs alongside source files
        recursive: Whether to search subdirectories
        timeout: Timeout for code execution in seconds  
        cache_file: Path to cache file for dependency tracking
        force: Force conversion even if cache says it's not needed
    
    Returns:
        dict: Results with converted_files, cached_files, and failed_files lists
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

    # Find all Python files
    pattern = '**/*.py' if recursive else '*.py'
    python_files = list(input_dir.glob(pattern))

    start_time = time.time()

    for py_file in python_files:
        if is_jupytext_file(py_file):
            if output_dir:
                # Maintain relative directory structure in output
                rel_path = py_file.relative_to(input_dir)
                output_path = Path(output_dir) / rel_path.with_suffix('.md')
            else:
                output_path = py_file.with_suffix('.md')

            success, result_path, was_cached = convert_jupytext_with_execution(
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
    parser = argparse.ArgumentParser(description='Convert jupytext Python files to markdown with execution')
    parser.add_argument('input', help='Input Python file or directory')
    parser.add_argument('-o', '--output', help='Output file or directory')
    parser.add_argument('-r', '--recursive', action='store_true',
                       help='Process directories recursively')
    parser.add_argument('--timeout', type=int, default=300,
                       help='Timeout for code execution in seconds (default: 300)')
    parser.add_argument('--cache-file', help='Path to conversion cache file')
    parser.add_argument('--force', action='store_true',
                       help='Force conversion even if cache says not needed')
    parser.add_argument('--clean', action='store_true',
                       help='Clean up markdown output (remove metadata, etc.)')

    args = parser.parse_args()

    input_path = Path(args.input)

    if input_path.is_file():
        # Convert single file
        success, result_path, was_cached = convert_jupytext_with_execution(
            input_path, args.output, args.timeout,
            {} if args.cache_file else None
        )
        if not success:
            sys.exit(1)
    elif input_path.is_dir():
        # Convert directory
        results = convert_directory_with_execution(
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
