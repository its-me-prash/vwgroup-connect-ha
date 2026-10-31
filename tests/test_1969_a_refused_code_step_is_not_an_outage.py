"""#1969 (@Ra72xx) — a 4xx at the e-mail-code step must not promise it will pass.

He got, every time:

    Website authproxy: the site answered 400 while checking the e-mail code —
    this is a server-side failure, not your code or your password

and a dialog saying *"VW backend temporarily unavailable … wait 5-15 minutes …
do NOT reconfigure"*. The verdict is right and #1843 decided it deliberately:
the code is only sent AFTER the password has been accepted, so neither the
password nor the code can be the cause of an HTTP error. **The remedy was
wrong.** Waiting clears a 5xx. It does not clear a refusal, and his repeated.

Two things are fixed and both are pinned here:

1. the raise site parsed the site's own error text one branch earlier and then
   **threw it away** on a 4xx, leaving a bare number — the single piece of
   evidence that would say why;
2. a 4xx now gets its own error key, so the "temporarily unavailable" wording
   stays with the statuses it is true for.

And it had to be fixed in **both** flows: the setup path and the options/reauth
path have separate handlers, reported separately by two different people in
#1843. A guard on one is the gap it is meant to close.
"""
from __future__ import annotations

import glob
import io
import json

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    AuthProxyUnavailableError,
)
from custom_components.vag_connect.config_flow import _map_error

_KEY = "authproxy_refused"


class TestTheExceptionCarriesWhatWasThrownAway:
    def test_the_status_is_available_to_the_caller(self) -> None:
        err = AuthProxyUnavailableError("x", status=400, reason="whatever")
        assert err.status == 400

    def test_the_sites_own_reason_is_kept(self) -> None:
        err = AuthProxyUnavailableError("x", status=400, reason="code expired")
        assert err.reason == "code expired"

    def test_it_is_still_constructible_from_a_message_alone(self) -> None:
        """Control: every other call site passes only a message."""
        err = AuthProxyUnavailableError("just a message")
        assert str(err) == "just a message"
        assert err.status is None and err.reason is None


class TestTheRaiseSiteKeepsTheReason:
    """Measured on the source of the OTP branch, over the AST of the call.

    Checked structurally rather than by substring, because the explanatory
    comment beside it names ``status`` and ``reason`` too — a presence check by
    text would pass with the keywords deleted.
    """

    def test_the_raise_passes_status_and_reason(self) -> None:
        import ast
        import inspect
        import textwrap

        from custom_components.vag_connect.cariad.auth import _website_authproxy

        src = textwrap.dedent(inspect.getsource(_website_authproxy))
        tree = ast.parse(src)
        found: list[set[str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            fn = node.exc.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name != "AuthProxyUnavailableError":
                continue
            kws = {kw.arg for kw in node.exc.keywords if kw.arg}
            if kws:
                found.append(kws)
        assert found, "no AuthProxyUnavailableError raise passes any keyword"
        assert any({"status", "reason"} <= k for k in found), (
            f"the OTP branch must pass both status and reason; found {found}"
        )


class TestBothFlowsSplitTheVerdict:
    """The setup handler and the options/reauth handler, over the AST."""

    @pytest.mark.parametrize(
        "module",
        ["custom_components.vag_connect.config_flow",
         "custom_components.vag_connect._vwde_reauth"],
    )
    def test_a_4xx_raises_the_refused_key(self, module: str) -> None:
        import ast
        import importlib
        import inspect
        import textwrap

        mod = importlib.import_module(module)
        tree = ast.parse(textwrap.dedent(inspect.getsource(mod)))
        handlers = [
            h
            for h in ast.walk(tree)
            if isinstance(h, ast.ExceptHandler)
            and "AuthProxyUnavailableError" in ast.dump(h.type or ast.Pass())
        ]
        assert handlers, f"{module}: no handler for AuthProxyUnavailableError"
        raised = {
            a.value
            for h in handlers
            for n in ast.walk(h)
            if isinstance(n, ast.Call)
            for a in n.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        }
        assert _KEY in raised, (
            f"{module} still sends every status to one verdict; raised={raised}"
        )
        assert "upstream_unavailable" in raised, (
            f"{module} lost the 5xx path, which was correct; raised={raised}"
        )


class TestTheKeyActuallyReachesTheUser:
    def test_the_allowlist_passes_it_through(self) -> None:
        """A key missing from _map_error becomes 'cannot_connect' in silence."""
        assert _map_error(_KEY) == _KEY

    def test_the_control_still_maps(self) -> None:
        assert _map_error("upstream_unavailable") == "upstream_unavailable"

    def test_an_unknown_key_still_falls_back(self) -> None:
        """Positive control for the test above: the allowlist is a real gate."""
        assert _map_error("something_invented") == "cannot_connect"

    @pytest.mark.parametrize(
        "path",
        ["custom_components/vag_connect/strings.json"]
        + sorted(glob.glob("custom_components/vag_connect/translations/*.json")),
    )
    def test_the_text_exists_in_every_language(self, path: str) -> None:
        """House convention: a config error key is present in all 13 files."""
        d = json.loads(io.open(path, encoding="utf-8").read())
        text = d["config"]["error"].get(_KEY)
        assert text, f"{path} has no {_KEY}"
        assert len(text) > 60, f"{path}: {_KEY} is too short to be the message"

    def test_the_wording_does_not_promise_it_passes(self) -> None:
        """The whole point: this key must not repeat the 'wait' advice."""
        d = json.loads(
            io.open("custom_components/vag_connect/strings.json", encoding="utf-8").read()
        )
        text = d["config"]["error"][_KEY].lower()
        for promise in ("temporarily unavailable", "wait 5", "try again later"):
            assert promise not in text, f"{_KEY} still promises: {promise!r}"
        assert "not your code" in text and "not your password" in text, (
            "it must keep #1843's verdict: neither the code nor the password"
        )

    def test_the_german_text_is_german_and_uses_real_umlauts(self) -> None:
        d = json.loads(
            io.open("custom_components/vag_connect/translations/de.json", encoding="utf-8").read()
        )
        text = d["config"]["error"][_KEY]
        assert "Passwort" in text, "de.json carries the English sentence"
        assert "Serverstörung" in text, (
            "the German word is Serverstörung; a dropped syllable shipped once"
        )
        for bad in ("Stoerung", "aelter", "ueber ", "oeffn"):
            assert bad not in text, f"ASCII umlaut substitute in de.json: {bad}"
