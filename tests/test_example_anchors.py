"""Example anchors must reach a schema-v1 artifact.

Anchor extraction only added `example` to its class map under with_hashes,
and with_hashes = schema_version >= 2 (build.py). A v1 notebook therefore
carried no example anchors, so a consumer had nothing to number.
"""

from parody.writers.artifact import extract_anchor_ids

MD = """
::: {.example #exa:rotations}
Compute the rotation.
:::

::: {.definition #def:screw}
A screw axis.
:::
"""


def _types(anchors):
    return {a["id"]: a["type"] for a in anchors}


def test_example_anchor_found_without_hashes():
    types = _types(extract_anchor_ids(MD, with_hashes=False))
    assert types.get("exa:rotations") == "example"


def test_definition_anchor_still_found():
    types = _types(extract_anchor_ids(MD, with_hashes=False))
    assert types.get("def:screw") == "definition"


def test_example_anchor_still_found_with_hashes():
    types = _types(extract_anchor_ids(MD, with_hashes=True))
    assert types.get("exa:rotations") == "example"


def test_an_explicit_id_prefix_is_what_resolves_in_v1():
    """`exa:` joins the id-prefix map, which applies in every schema version.

    The div-class scan is v2-only, so a hash-only example (::: {.example h="c4"})
    still yields no anchor in v1 — authored blocks carry an explicit #exa: id.
    """
    hash_only = extract_anchor_ids('::: {.example h="c4"}\nBody.\n:::',
                                   with_hashes=False)
    assert not [a for a in hash_only if a["type"] == "example"]
    with_id = extract_anchor_ids('::: {.example #exa:kept}\nBody.\n:::',
                                 with_hashes=False)
    assert _types(with_id)["exa:kept"] == "example"


def test_existing_v1_types_are_unchanged():
    """Adding `exa` must not disturb the prefixes already resolving in v1."""
    md = ("::: {.exercise #exe:one}\nDo it.\n:::\n\n"
          "::: {.theorem #thm:t}\nT.\n:::")
    types = _types(extract_anchor_ids(md, with_hashes=False))
    assert types["exe:one"] == "exercise"
    assert types["thm:t"] == "theorem"
