import pytest

from app.utils import parse_json_response


class TestParseJsonResponse:
    def test_plain_json_object(self):
        assert parse_json_response('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}

    def test_fenced_json(self):
        raw = '```json\n{"a": 1}\n```'
        assert parse_json_response(raw) == {"a": 1}

    def test_fenced_without_language(self):
        raw = '```\n{"a": 1}\n```'
        assert parse_json_response(raw) == {"a": 1}

    def test_prose_with_embedded_object(self):
        raw = 'Here is the plan:\n{"tasks": [1, 2]}\nHope this helps!'
        assert parse_json_response(raw) == {"tasks": [1, 2]}

    def test_whitespace_is_trimmed(self):
        assert parse_json_response('   \n{"k":1}\n   ') == {"k": 1}

    def test_nested_braces(self):
        raw = '{"outer": {"inner": 42}}'
        assert parse_json_response(raw) == {"outer": {"inner": 42}}

    # --- rejection cases ---

    def test_bare_list_rejected(self):
        with pytest.raises(ValueError, match="expected object"):
            parse_json_response("[1, 2, 3]")

    def test_bare_string_rejected(self):
        with pytest.raises(ValueError, match="expected object"):
            parse_json_response('"just a string"')

    def test_bare_number_rejected(self):
        with pytest.raises(ValueError, match="expected object"):
            parse_json_response("42")

    def test_bare_null_rejected(self):
        with pytest.raises(ValueError, match="expected object"):
            parse_json_response("null")

    def test_gibberish_raises(self):
        with pytest.raises(ValueError):
            parse_json_response("just some prose without any JSON at all")

    def test_malformed_json_raises(self):
        # Has braces but unclosed string → inner json.loads fails.
        with pytest.raises(ValueError):
            parse_json_response('Some intro {"a": "unclosed')
