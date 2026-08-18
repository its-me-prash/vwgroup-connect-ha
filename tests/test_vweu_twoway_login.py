# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way headless login — the window._IDK / signin-service page parsers.

The HTML snippets below are modelled on the REAL pages captured live from a VW
account 2026-08-18 (the ``loginIdentifier`` and ``codeConfirmation`` stages), so
these pin the regex parsers against the shapes VW actually serves for client
650d46ca ("Volkswagen OneApp").
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._device_grant import (
    VWEU_DAG_CLIENT_ID,
    VWEU_DAG_SCOPE,
)
from custom_components.vag_connect.cariad.auth._vweu_twoway_login import (
    VwEuTwoWayLogin,
    _extract_idk,
    _form_action,
    _hidden_inputs,
)

_CLIENT = "650d46ca-2475-4384-85c2-6af3bf3d52f1@apps_vw-dilab_com"

# ── loginIdentifier stage (fresh login) ──────────────────────────────────────
_IDENTIFIER_PAGE = (
    "<html><head><script>\n"
    "  window._IDK = {\n"
    '    templateModel: {"clientId":"' + _CLIENT + '","template":"loginIdentifier"},\n'
    '    csrf_token: "Q2GYHqXDofRiN8BMayz40mL6",\n'
    '    relayState: "daf06c6ba63eafd34d9c664b",\n'
    "    template: 'loginIdentifier',\n"
    "  };\n"
    "</script></head><body>\n"
    '  <form action="/signin-service/v1/' + _CLIENT + '/login/identifier" method="POST">\n'
    '    <input type="hidden" name="_csrf" value="Q2GYHqXDofRiN8BMayz40mL6"/>\n'
    '    <input type="hidden" name="relayState" value="daf06c6ba63eafd34d9c664b"/>\n'
    '    <input type="hidden" name="hmac" value="abc123"/>\n'
    "  </form></body></html>"
)

# ── codeConfirmation stage (approve the device) ──────────────────────────────
_CONFIRM_PAGE = (
    "<html><head><script>\n"
    "  window._IDK = {\n"
    '    templateModel: {"template":"codeConfirmation","userCode":"TMZB-CBSJ",'
    '"clientIdentityName":"Volkswagen OneApp"},\n'
    '    template: "codeConfirmation",\n'
    '    userId: "76b39a5c-63eb-4054-9271-f3aabbccddee",\n'
    '    clientIdentityName: "Volkswagen OneApp",\n'
    "  };\n"
    "</script></head><body>\n"
    '  <form action="/signin-service/v1/device/' + _CLIENT + "/TMZB-CBSJ?"
    'relayState=317b49&amp;user_id=76b39a5c&amp;hmac=4a1a7c" method="POST">\n'
    '    <input type="hidden" name="_csrf" value="LLnr6WHxSiSyQetrWVfCC64u"/>\n'
    '    <input type="hidden" name="client_identity_name" value="Volkswagen OneApp"/>\n'
    "  </form></body></html>"
)


def test_extract_idk_identifier_stage() -> None:
    f = _extract_idk(_IDENTIFIER_PAGE)
    assert f.get("template") == "loginIdentifier"
    assert f.get("csrf_token") == "Q2GYHqXDofRiN8BMayz40mL6"
    assert f.get("relayState") == "daf06c6ba63eafd34d9c664b"


def test_extract_idk_confirm_stage() -> None:
    f = _extract_idk(_CONFIRM_PAGE)
    assert f.get("template") == "codeConfirmation"
    assert f.get("clientIdentityName") == "Volkswagen OneApp"
    assert f.get("userId", "").startswith("76b39a5c")


def test_extract_idk_absent() -> None:
    assert _extract_idk("<html>no idk here</html>") == {}


def test_form_action_identifier() -> None:
    assert _form_action(_IDENTIFIER_PAGE) == (
        f"/signin-service/v1/{_CLIENT}/login/identifier"
    )


def test_form_action_confirm_carries_query_params() -> None:
    action = _form_action(_CONFIRM_PAGE)
    assert action is not None
    # &amp; is unescaped to & so the query params reach the POST target.
    assert action.startswith(f"/signin-service/v1/device/{_CLIENT}/TMZB-CBSJ?")
    assert "relayState=317b49" in action
    assert "&user_id=76b39a5c" in action
    assert "&hmac=4a1a7c" in action


def test_hidden_inputs_confirm_has_csrf_and_client_identity() -> None:
    hi = _hidden_inputs(_CONFIRM_PAGE)
    assert hi.get("_csrf") == "LLnr6WHxSiSyQetrWVfCC64u"
    assert hi.get("client_identity_name") == "Volkswagen OneApp"


def test_hidden_inputs_identifier() -> None:
    hi = _hidden_inputs(_IDENTIFIER_PAGE)
    assert set(hi) == {"_csrf", "relayState", "hmac"}


def test_login_client_defaults_to_650d46ca() -> None:
    lg = VwEuTwoWayLogin(None)
    assert lg._client_id == VWEU_DAG_CLIENT_ID
    assert lg._scope == VWEU_DAG_SCOPE
    assert lg._client_id.startswith("650d46ca")
