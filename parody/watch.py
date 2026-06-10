"""Rebuild on save — port of homepage-django's scripts/watch_notebooks.py.

Same triggers and debounce as the ancestor (.md/.yaml/.yml changes, editor
temp files ignored, jupytext execution skipped for fast saves), but rebuilds
in-process via build_project (+ optional preview) instead of shelling out to
Django management commands.

Requires the optional watchdog dependency: ``pip install parody[watch]``.
"""

import time
from pathlib import Path

DEBOUNCE_SECONDS = 1.0
WATCHED_SUFFIXES = {".md", ".yaml", ".yml"}


def should_ignore(path):
    name = Path(path).name
    return (
        name.startswith(".")
        or name.startswith("~")
        or name.endswith("~")
        or name.startswith("tmp")
        or name.startswith("metadata_")
    )


def is_relevant(path, root):
    path = Path(path)
    if path.suffix.lower() not in WATCHED_SUFFIXES:
        return False
    if should_ignore(path):
        return False
    try:
        path.resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


class ProjectRebuilder:
    """Debounced rebuild trigger; separated from watchdog for testability."""

    def __init__(self, root, rebuild, debounce_seconds=DEBOUNCE_SECONDS,
                 clock=time.monotonic):
        self.root = Path(root)
        self.rebuild = rebuild
        self.debounce = debounce_seconds
        self.clock = clock
        self.last_run = 0.0

    def handle_paths(self, paths):
        if not any(is_relevant(p, self.root) for p in paths if p):
            return False
        now = self.clock()
        if now - self.last_run < self.debounce:
            return False
        self.last_run = now
        try:
            self.rebuild()
        except Exception as e:
            print(f"❌ Rebuild failed: {e}")
        return True


def watch_project(project_dir, artifact_path, preview_dir=None, media_root=None,
                  bib_path=None, debounce_seconds=DEBOUNCE_SECONDS):
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        raise SystemExit(
            "parody watch requires watchdog: pip install 'parody[watch]'"
        )

    from .build import build_project
    from .config import load_project
    from .writers.preview import write_preview

    project_dir = Path(project_dir)

    def rebuild():
        print("🔁 Change detected, rebuilding (skip jupytext)...")
        artifact = build_project(
            project_dir, artifact_path, convert_jupytext=False, media_root=media_root,
        )
        if preview_dir:
            project = load_project(project_dir)
            write_preview(
                artifact, preview_dir,
                media_src=media_root or project_dir,
                bib_path=bib_path or project.bibliography,
            )
        print("✅ Rebuilt")

    rebuilder = ProjectRebuilder(project_dir, rebuild, debounce_seconds)

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            paths = [event.src_path, getattr(event, "dest_path", None)]
            rebuilder.handle_paths(paths)

    rebuild()  # initial build so the preview exists immediately

    observer = Observer()
    observer.schedule(Handler(), path=str(project_dir), recursive=True)
    print(f"👀 Watching {project_dir} for markdown/YAML changes... (Ctrl+C to stop)")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
