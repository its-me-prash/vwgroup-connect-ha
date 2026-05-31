# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.2.0 PR #2 — safe_get defensive dot-path accessor.

Closes the bug-class that hit:
- VW HA #922 (``'NoneType' object is not subscriptable``)
- pycupra #76 (``self.attrs.get('mycar')['engines']['primary']`` crash)
- audi #686 (PPE schema rotation crash)

"D'oh!"  — Homer Simpson, every time ``resp['a']['b']`` crashes
"""

from __future__ import annotations


from custom_components.vag_connect.cariad._util import safe_get


class TestSafeGetBasic:
    """Bazinga-level pedantry: every documented path-shape returns sanely."""

    def test_empty_path_returns_data(self) -> None:
        assert safe_get({"a": 1}, "") == {"a": 1}

    def test_single_key(self) -> None:
        assert safe_get({"a": 1}, "a") == 1

    def test_dotted_path(self) -> None:
        assert safe_get({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_missing_key_returns_default(self) -> None:
        assert safe_get({"a": 1}, "b") is None
        assert safe_get({"a": 1}, "b", default="fallback") == "fallback"

    def test_missing_intermediate_key(self) -> None:
        assert safe_get({"a": {"b": 1}}, "a.x.c") is None
        assert safe_get({"a": {"b": 1}}, "a.x.c", default=0) == 0


class TestSafeGetListIndex:
    """The bracket-index syntax — what saves us from MY26 rotations."""

    def test_pure_list_index(self) -> None:
        assert safe_get({"l": ["a", "b", "c"]}, "l[1]") == "b"

    def test_list_index_then_key(self) -> None:
        data = {"doors": [{"name": "front"}, {"name": "rear"}]}
        assert safe_get(data, "doors[0].name") == "front"
        assert safe_get(data, "doors[1].name") == "rear"

    def test_nested_list_then_key(self) -> None:
        data = {"l": [{"status": [{"value": "open"}]}]}
        assert safe_get(data, "l[0].status[0].value") == "open"

    def test_out_of_range_returns_default(self) -> None:
        assert safe_get({"l": ["a"]}, "l[5]") is None
        assert safe_get({"l": ["a"]}, "l[5]", default="x") == "x"

    def test_negative_index(self) -> None:
        # Python negative indexing supported
        assert safe_get({"l": ["a", "b", "c"]}, "l[-1]") == "c"

    def test_negative_out_of_range_returns_default(self) -> None:
        assert safe_get({"l": ["a"]}, "l[-5]") is None


class TestSafeGetDefensive:
    """The crash scenarios competitors hit. We mustn't crash."""

    def test_none_input(self) -> None:
        assert safe_get(None, "a.b.c") is None
        assert safe_get(None, "a.b.c", default="fb") == "fb"

    def test_scalar_input(self) -> None:
        assert safe_get(42, "a") is None
        assert safe_get("hello", "a") is None

    def test_list_to_dict_traversal(self) -> None:
        # Trying to dict-access a list mid-path → default
        assert safe_get({"l": ["str"]}, "l.foo") is None

    def test_dict_with_list_index_pattern(self) -> None:
        # Trying to int-index a dict → default
        assert safe_get({"d": {"k": "v"}}, "d[0]") is None

    def test_my26_rotation_simulation(self) -> None:
        """The exact MY26 schema-rotation pattern that hit pycupra #76:
        backend silently flipped doors.status from list to dict.
        Pre-v2.2.0: would have crashed. Now: returns default."""
        # Old shape (works)
        old = {"doors": [{"status": [{"value": "open"}]}]}
        assert safe_get(old, "doors[0].status[0].value") == "open"
        # New MY26 shape (status is now a dict, not a list)
        new = {"doors": [{"status": {"value": "open"}}]}
        assert safe_get(new, "doors[0].status[0].value") is None
        # And the empty-list case (also seen in the wild)
        empty = {"doors": [{"status": []}]}
        assert safe_get(empty, "doors[0].status[0].value") is None


class TestSafeGetMalformedPath:
    """Don't crash on weird path strings either."""

    def test_invalid_bracket_returns_default(self) -> None:
        assert safe_get({"a": [1]}, "a[abc]") is None

    def test_unclosed_bracket(self) -> None:
        # "a[0" doesn't end with "]" → treated as regular key → not found
        assert safe_get({"a": [1]}, "a[0") is None
