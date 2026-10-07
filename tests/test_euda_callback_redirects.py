from __future__ import annotations

from typing import Any, Self

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
)

_PORTAL = "https://eu-data-act.drivesomethinggreater.com"
_CALLBACK = f"{_PORTAL}/services/callbacklogin"
_AEM_CONTENT = f"{_PORTAL}/content/euda/de/de/user.html"


class _Response:
    def __init__(
        self,
        url: str,
        *,
        status: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return ""


class _RedirectSession:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append(("POST", url, kwargs))
        return _Response(
            url,
            status=302,
            headers={"Location": f"{_PORTAL}/login"},
        )

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append(("GET", url, kwargs))
        if url == f"{_PORTAL}/login":
            return _Response(
                url,
                status=302,
                headers={"Location": _CALLBACK},
            )
        if url == _CALLBACK:
            return _Response(
                url,
                status=302,
                headers={"Location": _AEM_CONTENT},
            )
        raise AssertionError(f"unexpected follow-up request: {url}")


@pytest.mark.asyncio
async def test_login_redirect_chain_stops_after_portal_callback() -> None:
    session = _RedirectSession()
    connector = EUDataActConnector(session)  # type: ignore[arg-type]

    landing, html, status = await connector._request_login_redirects(
        "POST",
        "https://identity.vwgroup.io/signin-service/v1/client/login/authenticate",
        headers={"User-Agent": "test"},
        data={"password": "not-logged"},
    )

    assert (landing, html, status) == (_CALLBACK, "", 302)
    assert [method for method, _, _ in session.requests] == ["POST", "GET", "GET"]
    assert [url for _, url, _ in session.requests][-1] == _CALLBACK
    assert all(not kwargs["allow_redirects"] for _, _, kwargs in session.requests)
    assert all(_AEM_CONTENT not in url for _, url, _ in session.requests)
