"""
Notebook utilities for enhanced figure handling using engcom.show.

This module provides integration with the engcom package for enhanced figure
handling with captions, IDs, and format control while maintaining compatibility
with the existing pandoc filter system.
"""

import matplotlib.pyplot as plt
import os
import json
from pathlib import Path
import time
import uuid
from datetime import datetime

try:
    from engcom.show import show as engcom_show
    ENGCOM_AVAILABLE = True
except ImportError:
    ENGCOM_AVAILABLE = False


def show(fig=None, filename=None, caption='', label=None, figsize=None,
         format="svg", dpi=150, suppress_input=False, suppress_output=False,
         width=None, height=None):
    """
    Enhanced figure display function that uses engcom.show when available,
    with fallback to custom implementation.
    
    Args:
        fig: Figure handle. If None, uses plt.gcf().
        filename (str): Filename for the figure (passed to engcom.show).
        caption (str): Caption for the figure.
        label (str): Label/ID for figure referencing. 
        figsize (tuple): Figure size (passed to engcom.show).
        format (str): Output format - 'svg', 'png', 'pdf', etc. Default is 'svg'.
        dpi (int): DPI for raster formats. Default is 150.
        suppress_input (bool): Whether to suppress the input cell.
        suppress_output (bool): Whether to suppress the output cell.
        width (str): CSS width specification (e.g., "100%", "500px").
        height (str): CSS height specification (e.g., "400px").
    
    Returns:
        None (displays the figure)
    """

    if fig is None:
        fig = plt.gcf()

    # Generate metadata for our enhanced system
    metadata = _generate_figure_metadata(caption, label, format, width, height)

    # Save metadata for the pandoc filter to use
    _save_figure_metadata(metadata)

    # Add cell tags if needed
    if suppress_input or suppress_output:
        _add_cell_tags(suppress_input, suppress_output)

    # Use engcom.show if available, otherwise fallback to plt.show()
    if ENGCOM_AVAILABLE:
        # Set matplotlib format for engcom compatibility
        if format.lower() == 'svg':
            plt.rcParams['savefig.format'] = 'svg'
        elif format.lower() == 'png':
            plt.rcParams['savefig.format'] = 'png'
            plt.rcParams['savefig.dpi'] = dpi

        # Call engcom.show with the parameters it expects
        return engcom_show(fig, filename=filename, caption=caption,
                          label=label, figsize=figsize)
    else:
        # Fallback implementation
        print("Warning: engcom package not available. Using fallback implementation.")
        print("Consider installing with: pip install engcom")

        # Set format for matplotlib
        if format.lower() == 'svg':
            plt.rcParams['savefig.format'] = 'svg'
        elif format.lower() == 'png':
            plt.rcParams['savefig.format'] = 'png'
            plt.rcParams['savefig.dpi'] = dpi

        return plt.show()


def _generate_figure_metadata(caption, label, format, width, height):
    """Generate metadata for the figure."""

    # Generate default caption if none provided
    if not caption:
        caption = "Figure"

    # Generate default ID if none provided
    if not label:
        label = f"fig-{uuid.uuid4().hex[:8]}"

    metadata = {
        "caption": caption,
        "id": label,
        "format": format,
        "timestamp": datetime.now().isoformat(),
        "width": width,
        "height": height
    }

    return metadata


def _save_figure_metadata(metadata):
    """
    Save figure metadata to a file that the pandoc filter can read.
    The metadata will be associated with the next figure output.
    """

    # Try to determine the output directory from the current working directory
    cwd = Path.cwd()

    # Look for a pattern that indicates we're in a notebook directory
    if "notebooks-source" in str(cwd):
        # We're likely in a notebook source directory
        metadata_dir = cwd / "_figure_metadata"
    else:
        # Fallback to current directory
        metadata_dir = Path(".") / "_figure_metadata"

    metadata_dir.mkdir(exist_ok=True)

    # Use timestamp to create unique metadata file
    timestamp = str(int(time.time() * 1000000))  # microsecond precision
    metadata_file = metadata_dir / f"metadata_{timestamp}.json"

    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)


def _add_cell_tags(suppress_input, suppress_output):
    """
    Add cell tags to control visibility. This outputs special comments
    that the pandoc filter can detect.
    """

    tags = []
    if suppress_input:
        tags.append("hide-input")
    if suppress_output:
        tags.append("hide-output")

    if tags:
        # Print a comment that the filter can potentially detect
        print(f"<!-- CELL_TAGS: {','.join(tags)} -->")


def setup_matplotlib_defaults():
    """
    Set up matplotlib defaults for better-looking figures in notebooks.
    Call this at the beginning of notebooks for consistent styling.
    """

    plt.rcParams.update({
        'figure.figsize': (10, 6),
        'figure.dpi': 100,
        'savefig.dpi': 150,
        'savefig.format': 'svg',
        'font.size': 12,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 10,
        'figure.titlesize': 16,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.1
    })


def setup_engcom_integration():
    """
    Set up integration with engcom package.
    This function can be called to verify engcom is available and set up defaults.
    """

    if ENGCOM_AVAILABLE:
        print("✓ engcom package is available")
        print("  Enhanced figure functionality enabled")
        print("  Use show(fig, caption='...', label='...') for full features")
    else:
        print("⚠ engcom package not available")
        print("  Install with: pip install engcom")
        print("  Falling back to basic matplotlib functionality")

    # Set up matplotlib defaults regardless
    setup_matplotlib_defaults()

    return ENGCOM_AVAILABLE


def cleanup_metadata(directory=None, max_age_hours=1):
    """
    Clean up old figure metadata files.
    
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

        for metadata_file in metadata_dir.glob("metadata_*.json"):
            if metadata_file.stat().st_mtime < (current_time - max_age_seconds):
                try:
                    metadata_file.unlink()
                except OSError:
                    pass  # File might be in use, skip it


# Convenience functions that mirror engcom.show signature
def show_figure(fig=None, filename=None, caption='', label=None, figsize=None, **kwargs):
    """
    Convenience function that mirrors engcom.show signature exactly.
    Additional kwargs are passed to our enhanced show function.
    """
    return show(fig=fig, filename=filename, caption=caption,
                label=label, figsize=figsize, **kwargs)


# Legacy compatibility
def show_enhanced(*args, **kwargs):
    """Legacy compatibility function."""
    return show(*args, **kwargs)


# Quick setup function for notebooks
def quick_setup():
    """
    One-line setup for notebooks. Call this after importing.
    
    Example:
        from parody.utils.notebook_utils import quick_setup
        quick_setup()
    """

    success = setup_engcom_integration()

    if success:
        print("\n📊 Enhanced notebook functionality loaded!")
        print("Usage:")
        print("  from parody.utils.notebook_utils import show")
        print("  fig, ax = plt.subplots()")
        print("  ax.plot(x, y)")
        print("  show(fig, caption='My plot', label='my-plot-id')")
    else:
        print("\n📊 Basic notebook functionality loaded!")
        print("Usage:")
        print("  from parody.utils.notebook_utils import show")
        print("  plt.figure()")
        print("  plt.plot(x, y)")
        print("  show(caption='My plot', label='my-plot-id')")

    print("\nFeatures:")
    print("  ✓ SVG format by default for crisp graphics")
    print("  ✓ Figure captions and cross-referencing")
    print("  ✓ Cell visibility control")
    print("  ✓ Automatic figure numbering")


# Export main functions
__all__ = ['show', 'show_figure', 'setup_matplotlib_defaults',
           'setup_engcom_integration', 'quick_setup', 'cleanup_metadata']
