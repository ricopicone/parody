"""Which sentence of the English sits on which page (task #825).

The twin build builds the English a second time with zero-node marks (see
``marks``) and reads back two side files:

- ``main.twin``: one row per (page, mark value), with the number of lines
  the value occupies on that page;
- ``main.twinctr``: every LaTeX counter's value at each mark.
"""

from pathlib import Path

from ..writers.latex import SHARED_PROFILE_DIR

TWINMARKS_SUPPORT = [SHARED_PROFILE_DIR / "parody-twinmarks.sty",
                     SHARED_PROFILE_DIR / "parody-twinmarks.lua"]
TWINMARKS_FLAG = "\\usepackage{parody-twinmarks}"


def read_rows(path):
    """``[(abspage, page number, value, lines)]`` from a ``.twin`` file."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(tuple(int(x) for x in line.split("\t")))
    return rows


def read_counters(path):
    """``{value: {counter: value}}`` from a ``.twinctr`` file; the first write wins.

    A mark inside measured material (a blank sized to its answer, say) is
    expanded more than once; the first expansion is the one in reading order.
    """
    counters = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        value, _, pairs = line.partition("|")
        value = int(value)
        if value in counters:
            continue
        counters[value] = {name: int(n) for name, _, n in
                           (p.partition("=") for p in pairs.split(",") if "=" in p)}
    return counters
