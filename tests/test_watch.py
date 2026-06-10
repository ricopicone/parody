"""Watch: debounce and path-filtering logic (the watchdog loop itself is thin)."""

from parody.watch import ProjectRebuilder, is_relevant, should_ignore


def test_path_filters(tmp_path):
    root = tmp_path
    assert is_relevant(root / "chapters/ch/sec.md", root)
    assert is_relevant(root / "parody.yaml", root)
    assert not is_relevant(root / "chapters/ch/code.py", root)  # execution skipped on watch
    assert not is_relevant(root / "chapters/ch/.sec.md.swp", root)
    assert not is_relevant(root / "chapters/ch/sec.md~", root)
    assert not is_relevant("/elsewhere/sec.md", root)
    assert should_ignore("metadata_123.yaml")


def test_debounce(tmp_path):
    calls = []
    fake_now = [0.0]
    r = ProjectRebuilder(tmp_path, lambda: calls.append(1),
                         debounce_seconds=1.0, clock=lambda: fake_now[0])

    md = str(tmp_path / "a.md")
    fake_now[0] = 10.0
    assert r.handle_paths([md])
    assert r.handle_paths([md]) is False  # within debounce window
    fake_now[0] = 11.5
    assert r.handle_paths([md])
    assert len(calls) == 2


def test_irrelevant_paths_do_not_trigger(tmp_path):
    calls = []
    r = ProjectRebuilder(tmp_path, lambda: calls.append(1))
    assert r.handle_paths([str(tmp_path / "image.png"), None]) is False
    assert calls == []


def test_rebuild_errors_are_contained(tmp_path):
    def boom():
        raise RuntimeError("kaboom")

    r = ProjectRebuilder(tmp_path, boom)
    assert r.handle_paths([str(tmp_path / "a.md")])  # swallowed, not raised
