"""Parody plugins: opt-in machinery that books enable from parody.yaml.

A plugin activates when its config key is present in parody.yaml (no
separate plugin list). A plugin module may expose either (or both) hook:

- ``make_transform(config, project_dir) -> callable(text) -> text`` —
  per-section markdown rewrites that run at read time in BOTH the artifact
  and print pipelines, before pandoc sees it (e.g. versioning).
- ``make_artifact_hook(config, project_dir) -> callable(artifact) -> artifact``
  — a post-processor that augments the finished artifact dict, for plugins
  that contribute book-level metadata rather than rewriting prose (e.g.
  apocrypha). Print builds never call these.

Sources on disk stay pristine either way.
"""

from importlib import import_module

# config key in parody.yaml -> module providing make_transform() and/or
# make_artifact_hook()
REGISTRY = {
    "versioning": "parody.plugins.versioning",
    "apocrypha": "parody.plugins.apocrypha",
    "book": "parody.plugins.bookmeta",
}


def content_transforms(project_meta, project_dir):
    """Build the active per-section transform pipeline for a project."""
    transforms = []
    for key, modpath in REGISTRY.items():
        cfg = (project_meta or {}).get(key)
        if cfg:
            mod = import_module(modpath)
            if hasattr(mod, "make_transform"):
                transforms.append(mod.make_transform(cfg, project_dir))
    return transforms


def apply_transforms(text, transforms):
    for transform in transforms or ():
        text = transform(text)
    return text


def artifact_hooks(project_meta, project_dir):
    """Build the active artifact post-processors for a project."""
    hooks = []
    for key, modpath in REGISTRY.items():
        cfg = (project_meta or {}).get(key)
        if cfg:
            mod = import_module(modpath)
            if hasattr(mod, "make_artifact_hook"):
                hooks.append(mod.make_artifact_hook(cfg, project_dir))
    return hooks


def apply_artifact_hooks(artifact, hooks):
    for hook in hooks or ():
        artifact = hook(artifact)
    return artifact
