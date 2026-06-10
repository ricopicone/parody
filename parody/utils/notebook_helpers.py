"""
Simplified notebook helpers for direct engcom usage.

This module provides minimal utility functions to support the use of engcom
directly in Python notebooks, with focus on maintenance and setup helpers.
"""

import os
import time
from pathlib import Path


def cleanup_metadata(directory=None, max_age_hours=1):
    """
    Clean up old figure metadata files that may accumulate during development.

    Args:
        directory: Directory to clean up. If None, uses current directory.
        max_age_hours: Maximum age in hours before files are deleted.
    """

    if directory is None:
        directory = Path.cwd()
    else:
        directory = Path(directory)

    metadata_dir = directory / "_figure_metadata"

    if metadata_dir.exists():
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        cleaned_count = 0
        for metadata_file in metadata_dir.glob("metadata_*.json"):
            if metadata_file.stat().st_mtime < (current_time - max_age_seconds):
                try:
                    metadata_file.unlink()
                    cleaned_count += 1
                except OSError:
                    pass  # File might be in use, skip it

        if cleaned_count > 0:
            print(f"✓ Cleaned up {cleaned_count} old metadata files")
        else:
            print("✓ No old metadata files to clean up")


def check_engcom_installation():
    """
    Check if engcom is properly installed and available.

    Returns:
        bool: True if engcom is available, False otherwise
    """
    try:
        import engcom
        print("✓ engcom package is available")
        return True
    except ImportError:
        print("⚠ engcom package not found")
        print("Install with: pip install engcom")
        return False


def setup_matplotlib_for_engcom():
    """
    Set up matplotlib defaults that work well with engcom.
    Call this in your hidden setup cell.
    """
    try:
        import matplotlib.pyplot as plt

        plt.rcParams.update({
            'figure.figsize': (10, 6),
            'figure.dpi': 100,
            'savefig.dpi': 150,
            'savefig.format': 'svg',
            'savefig.bbox': 'tight',
            'savefig.pad_inches': 0.1,
            'font.size': 12,
            'axes.titlesize': 14,
            'axes.labelsize': 12,
            'xtick.labelsize': 10,
            'ytick.labelsize': 10,
            'legend.fontsize': 10,
            'figure.titlesize': 16,
            'axes.grid': True,
            'grid.alpha': 0.3
        })

        print("✓ Matplotlib configured for engcom")

    except ImportError:
        print("⚠ Matplotlib not available")


def notebook_setup():
    """
    Complete setup function to call in a hidden cell at the start of notebooks.

    This function:
    - Checks for engcom installation
    - Sets up matplotlib defaults
    - Provides usage instructions
    """
    print("🚀 Notebook Setup")
    print("=" * 20)

    engcom_ok = check_engcom_installation()
    setup_matplotlib_for_engcom()

    if engcom_ok:
        print("\n📖 Usage Pattern:")
        print("# %% tags=[\"remove_cell\"]")
        print("import engcom")
        print("import matplotlib.pyplot as plt")
        print("import numpy as np")
        print("")
        print("# %% (students see this)")
        print("fig, ax = plt.subplots()")
        print("ax.plot(x, y)")
        print("")
        print("# %% tags=[\"remove_input\"]")
        print("engcom.show(fig, caption='Description', label='fig-id')")
        print("")
        print("✅ Ready to use engcom!")
    else:
        print("\n❌ Please install engcom first: pip install engcom")


def demo_cell_visibility():
    """
    Demonstrate the cell visibility control patterns.
    """
    print("📝 Cell Visibility Control")
    print("=" * 30)
    print("Use these nbconvert cell tags to control cell visibility:")
    print("")
    print("1. Remove entire cells (imports, setup):")
    print("   # %% tags=[\"remove_cell\"]")
    print("   import engcom")
    print("")
    print("2. Remove input, show output (figure display):")
    print("   # %% tags=[\"remove_input\"]")
    print("   engcom.show(fig, caption='...', label='...')")
    print("")
    print("3. Normal cells (students see everything):")
    print("   # %%")
    print("   fig, ax = plt.subplots()")
    print("   ax.plot(x, y)")
    print("")
    print("The nbconvert TagRemovePreprocessor will:")
    print("✓ Remove cells marked with remove_cell")
    print("✓ Remove input but show output for remove_input")
    print("✓ Show everything else normally")


def validate_notebook_structure(file_path):
    """
    Validate that a notebook follows the expected structure for engcom usage.

    Args:
        file_path: Path to the Python file to validate

    Returns:
        dict: Validation results with suggestions
    """

    if not Path(file_path).exists():
        return {"valid": False, "error": "File not found"}

    with open(file_path, 'r') as f:
        content = f.read()

    results = {
        "valid": True,
        "warnings": [],
        "suggestions": [],
        "stats": {}
    }

    # Check for engcom import
    has_engcom_import = "import engcom" in content or "from engcom" in content
    if not has_engcom_import:
        results["warnings"].append("No engcom import found")
        results["suggestions"].append("Add 'import engcom' in a hidden cell")

    # Count cell types
    hide_cell_count = content.count("remove_cell")
    hide_input_count = content.count("remove_input")
    normal_cell_count = content.count("# %%") - hide_cell_count - hide_input_count
    engcom_show_count = content.count("engcom.show.show")

    results["stats"] = {
        "hide_cells": hide_cell_count,
        "hide_input_cells": hide_input_count,
        "normal_cells": normal_cell_count,
        "engcom_calls": engcom_show_count
    }

    # Suggestions
    if engcom_show_count > 0 and hide_input_count == 0:
        results["suggestions"].append("Consider hiding engcom.show() calls with '# %% tags=[\"remove_input\"]'")

    if has_engcom_import and hide_cell_count == 0:
        results["suggestions"].append("Consider hiding imports with '# %% tags=[\"remove_cell\"]'")

    return results


# Export main functions
__all__ = [
    'cleanup_metadata',
    'check_engcom_installation',
    'setup_matplotlib_for_engcom',
    'notebook_setup',
    'demo_cell_visibility',
    'validate_notebook_structure'
]
