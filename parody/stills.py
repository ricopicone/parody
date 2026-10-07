"""A still frame of an animated figure, for print.

The web plays a GIF; LaTeX cannot include one. LuaLaTeX has no GIF driver, so
``\\includegraphics{door-frames.gif}`` fails, and because latexmk runs in force
mode the PDF still builds, leaving an empty space above the caption. No
warning fires either, because the path DID resolve.

print.lua therefore hands every animated or video src to this module, which
writes one frame as a PNG into the build's conversion cache. It is the same
cache the svg→pdf conversion uses. print.lua calls it as a subprocess::

    python -m parody.stills <src> <out.png> [<still>]

``<still>`` picks the frame, and comes from the figure's ``still=`` attribute:

    first   (default) the first frame
    last    the last frame
    N       frame N, counting from 0
    0.5     a fraction of the way through (0 ≤ f ≤ 1)

Pillow, which matplotlib already depends on, reads GIF, WebP and APNG. A video
(.mp4, .webm, …) falls back to ffmpeg, then ImageMagick. Exit status 0 means
``<out.png>`` exists. Anything else means there is no still, and print.lua
reports the figure as unresolved.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def frame_index(still: str | None, n_frames: int) -> int:
    """The 0-based frame ``still`` names, clamped into ``[0, n_frames)``."""
    last = max(n_frames - 1, 0)
    spec = (still or "first").strip().lower()
    if spec in ("", "first"):
        return 0
    if spec == "last":
        return last
    try:
        if "." in spec:
            frac = float(spec)
            if not 0.0 <= frac <= 1.0:
                raise ValueError(spec)
            return min(round(frac * last), last)
        return min(max(int(spec), 0), last)
    except ValueError:
        raise ValueError(
            f"still={still!r}: expected first, last, a frame number, "
            "or a fraction between 0 and 1") from None


def _with_pillow(src: Path, out: Path, still: str | None) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(src) as im:
            n = getattr(im, "n_frames", 1)
            im.seek(frame_index(still, n))
            # convert: a GIF frame is palette-mode, and its transparency would
            # otherwise come through as whatever the palette's index maps to
            im.convert("RGBA").save(out, "PNG")
        return True
    except ValueError:
        raise
    except Exception:
        return False


def _with_ffmpeg(src: Path, out: Path, still: str | None) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    spec = (still or "first").strip().lower()
    if spec in ("", "first"):
        select = []
    elif spec == "last":
        select = ["-sseof", "-0.1"]
    elif "." in spec:
        # a fraction needs the duration, which only ffprobe knows
        return False
    else:
        select = None
    args = [ffmpeg, "-y", "-loglevel", "error"]
    if select is not None:
        args += select + ["-i", str(src)]
    else:
        args += ["-i", str(src), "-vf", f"select=eq(n\\,{int(spec)})"]
    args += ["-frames:v", "1", str(out)]
    return subprocess.run(args, capture_output=True).returncode == 0 and out.exists()


def _with_magick(src: Path, out: Path, still: str | None) -> bool:
    magick = shutil.which("magick")
    if not magick:
        return False
    spec = (still or "first").strip().lower()
    if spec in ("", "first"):
        idx = "0"
    elif spec == "last":
        idx = "-1"
    elif "." in spec:
        return False
    else:
        idx = str(int(spec))
    result = subprocess.run([magick, f"{src}[{idx}]", str(out)], capture_output=True)
    return result.returncode == 0 and out.exists()


def extract_still(src: Path, out: Path, still: str | None = None) -> bool:
    """Write one frame of ``src`` to ``out`` (PNG). True if it worked.

    The extraction is skipped when ``out`` is already newer than ``src``, so a
    rebuild costs one stat and nothing more. A changed animation does get a
    fresh still.
    """
    src, out = Path(src), Path(out)
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return True
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.png")
    for extract in (_with_pillow, _with_ffmpeg, _with_magick):
        tmp.unlink(missing_ok=True)
        if extract(src, tmp, still) and tmp.exists():
            tmp.replace(out)
            return True
    tmp.unlink(missing_ok=True)
    return False


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("usage: python -m parody.stills <src> <out.png> [<still>]",
              file=sys.stderr)
        return 2
    src, out = Path(argv[0]), Path(argv[1])
    still = argv[2] if len(argv) == 3 else None
    if not src.is_file():
        return 1
    try:
        return 0 if extract_still(src, out, still) else 1
    except ValueError as exc:
        print(f"⚠️  {exc} ({src})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
