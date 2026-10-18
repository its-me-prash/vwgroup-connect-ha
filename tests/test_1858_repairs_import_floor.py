# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1858 — a type-only import took the whole integration down on older HA.

``repairs.py`` imported ``RepairsFlowResult`` at module level. The name only
exists from HA 2026.9, and HA loads the repairs platform as soon as the
integration sets up, so on anything older the import raised and the whole
integration failed to set up — with a traceback naming *repairs*, which sends
people looking at their repair issues instead of at their HA version. Meanwhile
``hacs.json`` advertised ``2024.4.0``, so HACS offered the update to exactly
the installations it would break.

Every use of the name is a ``-> RepairsFlowResult`` return annotation, so it
belongs under ``TYPE_CHECKING``. That needs ``from __future__ import
annotations`` as well: HA before 2026.10 runs Python 3.13, which evaluates
annotations eagerly at function definition, so the import alone would only
trade the ImportError for a NameError. Python 3.14 defers them (PEP 649) and
would not need the future import — which is exactly why a test that only runs
on 3.14 has to check for it explicitly rather than rely on the module importing
cleanly here.
"""
from __future__ import annotations

import ast
import asyncio
import importlib
import json
import logging
import pathlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_REPAIRS = _ROOT / "custom_components" / "vag_connect" / "repairs.py"
_MODULE = "custom_components.vag_connect.repairs"


def _tree() -> ast.Module:
    return ast.parse(_REPAIRS.read_text(encoding="utf-8"))


def test_the_type_only_name_is_not_imported_at_runtime() -> None:
    """Walked as a tree, not grepped: a string search for the import line also
    matches the one inside the ``TYPE_CHECKING`` block, so it passes whether
    the import is guarded or not — which is the whole question.
    """
    tree = _tree()

    guarded: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_guard = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not is_guard:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.ImportFrom):
                guarded.extend(a.name for a in sub.names)

    runtime: list[str] = []
    for node in tree.body:  # module level only — nested is either guarded or local
        if isinstance(node, ast.ImportFrom):
            runtime.extend(a.name for a in node.names)

    assert "RepairsFlowResult" in guarded, (
        "RepairsFlowResult must be imported under TYPE_CHECKING"
    )
    assert "RepairsFlowResult" not in runtime, (
        "RepairsFlowResult is imported at runtime again — that is #1858"
    )
    # The class itself IS needed at runtime: it is subclassed.
    assert "RepairsFlow" in runtime


def test_future_annotations_is_present() -> None:
    """Without it, Python 3.13 — every HA before 2026.10 — evaluates the return
    annotations at function definition and raises NameError instead. This test
    cannot catch that by importing, because the interpreter running it defers
    annotations anyway, so it checks for the declaration itself.
    """
    tree = _tree()
    futures = [
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "__future__"
        for alias in node.names
    ]
    assert "annotations" in futures

    # And it must come before the other imports, or it is a SyntaxError.
    first_import = next(
        i
        for i, node in enumerate(tree.body)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )
    assert (
        isinstance(tree.body[first_import], ast.ImportFrom)
        and tree.body[first_import].module == "__future__"
    )


def test_the_module_still_imports_when_ha_lacks_the_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reported failure, reproduced.

    An HA without ``RepairsFlowResult`` is simulated by taking the attribute
    off the real module — ``from X import Y`` is an attribute lookup, so this
    is the same ImportError an older HA raises. Against the shipped code this
    test fails; it is the only one here that exercises the actual breakage
    rather than the shape of the source.
    """
    import homeassistant.components.repairs as ha_repairs

    assert hasattr(ha_repairs, "RepairsFlowResult"), (
        "the installed HA does not have the name at all — this test would "
        "pass vacuously"
    )
    monkeypatch.delattr(ha_repairs, "RepairsFlowResult")

    original = sys.modules.get(_MODULE)
    parent = sys.modules.get("custom_components.vag_connect")
    sys.modules.pop(_MODULE, None)
    try:
        fresh = importlib.import_module(_MODULE)
        assert fresh.RepairsFlow is ha_repairs.RepairsFlow
        assert not hasattr(fresh, "RepairsFlowResult")
    finally:
        # Put the original object back so no later test picks up a second copy
        # of these classes.
        if original is not None:
            sys.modules[_MODULE] = original
            if parent is not None:
                parent.repairs = original
        else:
            sys.modules.pop(_MODULE, None)


def test_hacs_declares_a_floor_that_was_measured_not_guessed() -> None:
    """The second half of #1858: the manifest has to stop promising versions
    the code does not run on.

    Two constraints are known, both verified rather than read off a changelog:

    * HA 2026.2 introduced the ALPN-bucketed ``util.ssl.client_context`` the
      volkswagen.de HTTP/2 channel now asks for by name.
    * HA 2026.6.0 is where ``RepairsFlowResult`` starts being exported —
      @thomascombe measured it absent on 2026.4.3 and 2026.5.0 and present
      after upgrading.

    The floor is the HIGHER of the two even though the TYPE_CHECKING guard
    means the code itself would run on 2026.2: nobody has audited every other
    HA API this integration touches for introduction dates, and 2026.6.0 is a
    version a real installation was seen working on. Under-declaring is how
    #1858 reached users in the first place; over-declaring only costs a few
    old installations an update offer.
    """
    cfg = json.loads((_ROOT / "hacs.json").read_text(encoding="utf-8"))
    floor = cfg["homeassistant"]
    major, minor = (int(p) for p in floor.split(".")[:2])
    assert (major, minor) >= (2026, 6), (
        f"hacs.json promises {floor}; RepairsFlowResult is only exported from "
        "2026.6.0, which is also the version the reporter measured working"
    )

    # And the lower constraint has to be true of the import we rely on.
    from homeassistant.util.ssl import SSL_ALPN_HTTP11_HTTP2, client_context

    assert SSL_ALPN_HTTP11_HTTP2 == ("http/1.1", "h2")
    assert client_context is not None


# ── the triage line @thomascombe had to add by hand ─────────────────────────
def _real_import_error() -> ImportError:
    """A genuine ``from X import Y`` failure, not a hand-built stand-in.

    ``name_from`` is set by the interpreter and cannot be passed to the
    constructor, and ``path`` matters to the privacy test below, so the only
    faithful way to get the real shape is to provoke one. Removing the
    attribute reproduces what an older core looks like to ``from ... import``.
    """
    import homeassistant.components.repairs as ha_repairs

    saved = ha_repairs.RepairsFlowResult
    try:
        del ha_repairs.RepairsFlowResult
        try:
            from homeassistant.components.repairs import (  # noqa: F401
                RepairsFlowResult,
            )
        except ImportError as exc:
            return exc
        raise AssertionError("expected an ImportError")
    finally:
        ha_repairs.RepairsFlowResult = saved


def _coordinator():
    """The async_setup harness, mirroring TestCoordinatorAsyncSetup._coord."""
    import threading

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.hass.loop.call_soon_threadsafe = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.data = {
        "brand": "volkswagen",
        "username": "u@t.de",
        "password": "pw",
        "spin": "",
        "scan_interval": 5,
    }
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = None
    coord._started = False
    coord._was_available = True
    coord.vehicles = {}
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    return coord


def _run_setup_with(err: BaseException, caplog: pytest.LogCaptureFixture) -> str:
    """Drive the catch-all branch of async_setup and return everything logged."""
    from custom_components.vag_connect.cariad.api.factory import (
        CariadClientFactory,
    )

    coord = _coordinator()
    client = MagicMock()
    client.authenticate = AsyncMock(side_effect=err)
    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect.coordinator"),
        patch.object(CariadClientFactory, "create", return_value=client),
        patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        assert asyncio.run(coord.async_setup()) is False
    return "\n".join(r.getMessage() for r in caplog.records)


def test_an_import_error_now_says_which_import_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """@thomascombe's actual request. "setup failed: ImportError" was the whole
    message, so he patched a local log in to learn the module and the symbol.
    Both are plain names; logging them turns this into a one-line diagnosis.
    """
    err = _real_import_error()
    assert err.name == "homeassistant.components.repairs"
    assert getattr(err, "name_from", None) == "RepairsFlowResult"

    logged = _run_setup_with(err, caplog)

    assert "ImportError" in logged
    assert "homeassistant.components.repairs" in logged, (
        "the failing module is still not in the log"
    )
    assert "RepairsFlowResult" in logged, "the missing symbol is still not named"


def test_the_setup_error_never_logs_the_path_or_the_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The half that must not regress, and the reason the message is withheld
    at all (#1355).

    Two distinct leaks are checked, because the triage detail added above is
    exactly the kind of line someone later "improves" by reaching for
    ``err.path`` or ``str(err)``:

    * ``ImportError.path`` is the module's filesystem path. Measured on this
      machine it reads ``...\\Users\\<account>\\...\\site-packages\\...`` —
      the account name of whoever runs Home Assistant, in a line people paste
      into public issues.
    * ``str(err)`` on the OAuth callback path is
      ``weconnect://authenticated#access_token=<JWT>&code=<JWT>``, and those
      JWTs decode to the user's e-mail and a live token.
    """
    err = _real_import_error()
    assert err.path, "the probe produced no path, so this test proves nothing"
    logged = _run_setup_with(err, caplog)
    assert err.path not in logged, "the module path leaked into the log"
    # The account segment on its own, in case the path is ever shortened.
    for segment in pathlib.Path(err.path).parts:
        if segment.lower() in {"users", "home"}:
            continue
        if segment and segment in logged and len(segment) > 3:
            # Only the package names below site-packages may legitimately
            # appear, and only because they are also the module name.
            assert segment in err.name.split("."), (
                f"path segment {segment!r} leaked into the log"
            )

    caplog.clear()
    token = "eyJhbGciOiJIUzI1NiJ9.ZmFrZS1wYXlsb2Fk.c2lnbmF0dXJl"
    oauth = ValueError(
        f"weconnect://authenticated#access_token={token}&code={token}"
    )
    logged = _run_setup_with(oauth, caplog)
    assert "ValueError" in logged
    assert token not in logged, "an OAuth token leaked into the log (#1355)"
    assert "weconnect://" not in logged
