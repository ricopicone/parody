"""The prompt sent to the engine and the parsing of its answer (task #825)."""

import pytest

from parody.translate.prompt import ResponseError, parse_response, request, system_prompt


def test_system_prompt_names_language_and_lists_glossary():
    text = system_prompt("zh", {"voltage divider": "分压器"})
    assert "into Simplified Chinese (Mandarin, as written in mainland China)." in text
    assert "{LANGUAGE}" not in text
    assert "- voltage divider → 分压器" in text


def test_system_prompt_without_glossary_has_no_glossary_section():
    assert "established" not in system_prompt("de", {})


def test_request_has_markers_and_todo_line():
    text = request(["Voltage dividers", "# Voltage dividers", "Para."], [0, 2],
                   {1: "# Spannungsteiler"})
    assert "<english-section>\n<<<chunk 0>>>\nVoltage dividers\n<<<chunk 1>>>" in text
    assert "<existing-translation>\n<<<chunk 1>>>\n# Spannungsteiler\n</existing-translation>" in text
    assert text.rstrip().endswith("Translate these chunks: 0, 2")


def test_request_without_previous_has_no_existing_block():
    assert "<existing-translation>" not in request(["a"], [0], {})


def test_request_lists_problems_from_a_previous_attempt():
    text = request(["a", "b"], [1], {}, problems={1: ["blanks: 0 of 1"]})
    assert "Problems with your previous attempt:" in text
    assert "chunk 1: blanks: 0 of 1" in text


def test_parse_response_ok():
    got = parse_response("<<<chunk 2>>>\nZwei.\n\n<<<chunk 5>>>\nFünf\n\nmit Absatz.\n", [2, 5])
    assert got == {2: "Zwei.", 5: "Fünf\n\nmit Absatz."}


def test_parse_missing_chunk_raises():
    with pytest.raises(ResponseError, match="5"):
        parse_response("<<<chunk 2>>>\nZwei.", [2, 5])


def test_parse_extra_chunk_raises():
    with pytest.raises(ResponseError):
        parse_response("<<<chunk 2>>>\nZwei.\n<<<chunk 3>>>\nDrei.", [2])


def test_parse_duplicate_chunk_raises():
    with pytest.raises(ResponseError):
        parse_response("<<<chunk 2>>>\nZwei.\n<<<chunk 2>>>\nNochmal.", [2])


def test_parse_strips_code_fence_wrapper():
    assert parse_response("```markdown\n<<<chunk 1>>>\nEins.\n```", [1]) == {1: "Eins."}


def test_parse_rejects_chatter_before_first_marker():
    with pytest.raises(ResponseError):
        parse_response("Sure! Here is the translation:\n<<<chunk 2>>>\nZwei.", [2])


def test_parse_keeps_inner_code_fences():
    body = "```python\nx = 1\n```"
    assert parse_response(f"<<<chunk 1>>>\n{body}\n", [1]) == {1: body}


def test_system_prompt_translates_box_titles():
    text = system_prompt("de", {})
    assert 'title="…"' in text
    assert "translate the title" in text
