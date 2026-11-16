"""#2135 — the EU Data Act portal moved to ``eu-data-act.vwgroup-datahub.com``.

On 2026-11-16 the old host ``eu-data-act.drivesomethinggreater.com`` started
answering every path with a permanent redirect to the new one, and the login
chain landed there. The redirect allowlist refused it, so every brand on the
portal fallback failed to set up with "invalid credentials".

The legacy ``_data_act_portal`` strategy checked the callback with a substring
test on the old domain; it now matches the parsed host against both domains.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth import _data_act_portal, _data_act_scraper
from custom_components.vag_connect.cariad.auth._data_act_portal import _is_portal_url


def test_every_portal_base_is_the_new_host() -> None:
    assert _data_act_portal._PORTAL_BASE == "https://eu-data-act.vwgroup-datahub.com"
    assert _data_act_scraper._PORTAL_BASE == "https://eu-data-act.vwgroup-datahub.com"
    assert _data_act_portal._PORTAL_OIDC_REDIRECT_URI.startswith(
        "https://eu-data-act.vwgroup-datahub.com/"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://eu-data-act.vwgroup-datahub.com/login?code=x&state=y",
        "https://EU-Data-Act.VWGroup-DataHub.com/services/callbacklogin",
        "https://eu-data-act.drivesomethinggreater.com/login?code=x",
    ],
)
def test_portal_callbacks_on_either_domain_are_accepted(url: str) -> None:
    assert _is_portal_url(url) is True


@pytest.mark.parametrize(
    ("name", "url"),
    [
        ("none", None),
        ("empty", ""),
        ("identity provider", "https://identity.vwgroup.io/signin-service/v1/x"),
        (
            "portal only in the query",
            "https://identity.vwgroup.io/oidc/v1/authorize"
            "?redirect_uri=https://eu-data-act.vwgroup-datahub.com/login",
        ),
        ("lookalike suffix", "https://eu-data-act.vwgroup-datahub.com.evil.tld/login"),
        ("lookalike registrable domain", "https://evilvwgroup-datahub.com/login"),
        ("legacy lookalike", "https://notdrivesomethinggreater.com/login"),
    ],
)
def test_everything_else_is_not_a_portal_callback(name: str, url: str | None) -> None:
    assert _is_portal_url(url) is False, name
