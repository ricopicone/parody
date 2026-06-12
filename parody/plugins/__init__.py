"""Parody plugins: opt-in machinery that books enable from parody.yaml.

A plugin activates when its config key is present in parody.yaml (no
separate plugin list). Each plugin module exposes
``make_transform(config, project_dir) -> callable(text) -> text``; the
transforms run on every section's markdown at read time in BOTH the
artifact and print pipelines, before pandoc sees it. Sources on disk stay
pristine.
"""

from importlib import import_module

# config key in parody.yaml -> module providing make_transform()
REGISTRY = {
    "versioning": "parody.plugins.versioning",
}


def content_transforms(project_meta, project_dir):
    """Build the active transform pipeline for a project."""
    transforms = []
    for key, modpath in REGISTRY.items():
        cfg = (project_meta or {}).get(key)
        if cfg:
            mod = import_module(modpath)
            transforms.append(mod.make_transform(cfg, project_dir))
    return transforms


def apply_transforms(text, transforms):
    for transform in transforms or ():
        text = transform(text)
    return text
