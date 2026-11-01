"""The portal operator's login-redirect allowlist, ported from his reference.

In the service notice of 2026-10-06 the operator (@VWGroupDatahub) wrote:
"Maintainers of other integrations are encouraged to review and adopt the
relevant login-flow changes already implemented for EVCC and
ioBroker.vw-connect." He had implemented them there himself — all five commits
on the evcc pull request are his, including one that answers that project's code
review.

This module had the core of it already, from his own PR #1740: the chain stops
at ``/services/callbacklogin``, the Location header decides the next hop, there
is a redirect cap, and non-https is refused. What it did not have is the guard
his reference carries: **every login redirect must target the identity provider
or the portal, and nothing else.**

Why the gap mattered, measured before this was added:

* a 307/308 across a host boundary keeps method AND body by definition, and the
  body of the first hop is the username and password. The existing drop covers
  301/302/303 only, which is correct HTTP and was never the whole problem;
* the Referer was set on every hop including a cross-host one, so the previous
  URL — carrying ``code`` and ``state`` on an OIDC chain — reached the foreign
  host even though Authorization and Cookie were stripped;
* the foreign response's HTML went to the landing classifier, letting whoever
  controls that host steer the login verdict.

His Go version needs none of that bookkeeping: the standard library applies the
RFC rules, and ``CheckRedirect`` refuses a foreign hop *before* the request is
made. The allowlist closes all three here for the same reason — the request
never happens.

The tables below are his, case for case: ``TestIsUserPage`` from
``vehicle/vw/eudataact/api_test.go`` and the callback and host rows from
``TestLoginRedirects``. Ported rather than invented, because his table already
contains the lookalikes a hand-written one forgets.
"""
from __future__ import annotations

from typing import Any, Self

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    _is_login_host,
    _is_user_page,
    _valid_marketing_callback,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

_PORTAL = "https://eu-data-act.drivesomethinggreater.com"
_IDENTITY = "https://identity.vwgroup.io"
_CALLBACK = f"{_PORTAL}/services/callbacklogin"
_USER_PAGE = f"{_PORTAL}/content/euda/de/de/user.html"
_PORTAL_HOST = "eu-data-act.drivesomethinggreater.com"


# ── his TestIsUserPage table, verbatim ───────────────────────────────────────
@pytest.mark.parametrize(
    ("name", "uri", "want"),
    [
        ("German", f"{_PORTAL}/content/euda/de/de/user.html", True),
        ("English", f"{_PORTAL}/content/euda/gb/en/user.html", True),
        ("query", f"{_PORTAL}/content/euda/de/en/user.html?next=/error", True),
        ("fragment", f"{_PORTAL}/content/euda/fr/fr/user.html#profile", True),
        ("error page", f"{_PORTAL}/content/euda/de/de/error.html?next=user.html", False),
        ("other content", f"{_PORTAL}/content/other/de/de/user.html", False),
        ("lookalike prefix", f"{_PORTAL}/content/euda-other/de/de/user.html", False),
        ("lookalike filename", f"{_PORTAL}/content/euda/de/de/notuser.html", False),
        ("extra segment", f"{_PORTAL}/content/euda/de/de/user.html/extra", False),
        ("trailing slash", f"{_PORTAL}/content/euda/de/de/user.html/", False),
        ("wrong host", "https://example.org/content/euda/de/de/user.html", False),
        ("lookalike host", f"{_PORTAL}.example.org/content/euda/de/de/user.html", False),
        ("HTTP", f"http://{_PORTAL_HOST}/content/euda/de/de/user.html", False),
        ("relative", "/content/euda/de/de/user.html", False),
    ],
)
def test_is_user_page(name: str, uri: str, want: bool) -> None:
    assert _is_user_page(uri) is want, name


# ── his callback rows from TestLoginRedirects ────────────────────────────────
@pytest.mark.parametrize(
    ("name", "url", "want"),
    [
        ("the real callback", f"{_IDENTITY}/oidc/v1/oauth/client/callback", True),
        ("the success variant", f"{_IDENTITY}/oidc/v1/oauth/client/callback/success", True),
        ("insecure callback", "http://example.org/callback", False),
        ("http callback", "http://identity.vwgroup.io/oidc/v1/oauth/client/callback", False),
        ("callback wrong path", f"{_IDENTITY}/unexpected/callback", False),
        ("foreign host, right path", "https://example.org/oidc/v1/oauth/client/callback", False),
        ("lookalike host", f"{_IDENTITY}.example.org/oidc/v1/oauth/client/callback", False),
        ("path prefix only", f"{_IDENTITY}/oidc/v1/oauth/client/callback/other", False),
        ("empty", "", False),
    ],
)
def test_valid_marketing_callback(name: str, url: str, want: bool) -> None:
    assert _valid_marketing_callback(url) is want, name


class TestTheHostAllowlist:
    """``isLoginHost``: the identity provider or the portal, nothing else."""

    @pytest.mark.parametrize(
        "netloc",
        ["identity.vwgroup.io", "eu-data-act.drivesomethinggreater.com",
         "IDENTITY.VWGROUP.IO", "EU-Data-Act.DriveSomethingGreater.com"],
    )
    def test_the_two_real_hosts_in_any_case(self, netloc: str) -> None:
        assert _is_login_host(netloc) is True

    @pytest.mark.parametrize(
        ("name", "netloc"),
        [
            ("plain foreign", "example.org"),
            ("suffix lookalike", "identity.vwgroup.io.example.org"),
            ("prefix lookalike", "evil-identity.vwgroup.io.evil"),
            ("subdomain of the idp", "login.identity.vwgroup.io"),
            ("sibling vwgroup host", "other.vwgroup.io"),
            ("portal lookalike", "eu-data-act.drivesomethinggreater.com.evil.tld"),
            ("explicit port", "identity.vwgroup.io:443"),
            ("empty", ""),
        ],
    )
    def test_everything_else_is_refused(self, name: str, netloc: str) -> None:
        """``other.vwgroup.io`` and the explicit port are refused on purpose.

        The reference compares the whole Host with ``EqualFold``, so a sibling
        subdomain and a URL carrying ``:443`` are both a different Host there
        too. Matching it beats being clever: a widened rule here is exactly the
        kind of change that would have to be justified against a credential
        path, and nothing has asked for one.
        """
        assert _is_login_host(netloc) is False, name


# ── the walker refuses the hop rather than following it ──────────────────────
class _Response:
    def __init__(self, url: str, *, status: int,
                 headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return ""


class _ForeignRedirectSession:
    """First hop answers with a redirect to *location*; nothing else is served."""

    def __init__(self, location: str, status: int = 302) -> None:
        self._location = location
        self._status = status
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append(("POST", url, kwargs))
        return _Response(url, status=self._status,
                         headers={"Location": self._location})

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append(("GET", url, kwargs))
        raise AssertionError(f"the foreign host was contacted: {url}")


def _connector(session: Any) -> EUDataActConnector:
    c = EUDataActConnector.__new__(EUDataActConnector)
    c._session = session
    # __init__ is bypassed, so the fail-closed canary's fields are set here the
    # way __init__ sets them.
    c.refused_login_hosts = set()
    c.refused_login_host_count = 0
    return c


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_a_foreign_hop_is_refused_on_every_redirect_status(status: int) -> None:
    """307/308 are the ones that mattered: they keep method and body."""
    session = _ForeignRedirectSession("https://evil.example.org/cb?code=abc", status)
    with pytest.raises(AuthenticationError) as err:
        await _connector(session)._follow_login_redirects(
            "POST", f"{_IDENTITY}/signin-service/v1/login",
            headers={"User-Agent": "Mozilla/5.0"},
            data={"email": "u@example.org", "password": "s3cret"},
        )
    assert "unexpected host" in str(err.value)
    assert "evil.example.org" in str(err.value), "the refused host must be named"


@pytest.mark.asyncio
async def test_the_foreign_host_is_never_contacted() -> None:
    """The point of refusing instead of following without a body."""
    session = _ForeignRedirectSession("https://evil.example.org/cb", 307)
    with pytest.raises(AuthenticationError):
        await _connector(session)._follow_login_redirects(
            "POST", f"{_IDENTITY}/signin-service/v1/login",
            headers={}, data={"password": "s3cret"},
        )
    assert len(session.requests) == 1, "only the first hop may have been made"
    assert all("evil.example.org" not in url for _, url, _ in session.requests)


@pytest.mark.asyncio
async def test_the_credentials_never_leave_in_the_refused_direction() -> None:
    """The failure this closes, stated as a test: a 307 across a host boundary
    kept method and body, and the body is the password."""
    session = _ForeignRedirectSession("https://evil.example.org/cb", 307)
    with pytest.raises(AuthenticationError):
        await _connector(session)._follow_login_redirects(
            "POST", f"{_IDENTITY}/signin-service/v1/login",
            headers={}, data={"password": "s3cret-marker"},
        )
    sent = "".join(repr(kwargs) for _, _, kwargs in session.requests[1:])
    assert "s3cret-marker" not in sent, "the password reached a second hop"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [
    f"{_PORTAL}/login",
    f"{_IDENTITY}/oidc/v1/oauth/client/callback",
])
async def test_a_hop_inside_the_allowlist_is_still_followed(target: str) -> None:
    """Control: the guard must not break the flow it protects. Without this the
    allowlist could be inverted and the suite would still pass."""
    class _OneHop(_ForeignRedirectSession):
        def get(self, url: str, **kwargs: Any) -> _Response:
            self.requests.append(("GET", url, kwargs))
            return _Response(url, status=200)

    session = _OneHop(target)
    url, _html, status = await _connector(session)._follow_login_redirects(
        "POST", f"{_IDENTITY}/signin-service/v1/login", headers={}, data={"a": "b"},
    )
    assert status == 200
    assert url == target
    assert len(session.requests) == 2, "the allowed hop was not followed"


class TestTheFailClosedCanary:
    """What makes a fail-closed login guard safe to ship.

    A silent fallback to the old permissive behaviour is deliberately NOT
    provided: whoever can trigger a foreign redirect would simply trigger the
    fallback, and a gate with a bypass is not a gate. What replaces it is
    visibility — a wrong host list shows up in diagnostics within one poll, with
    the host that was refused, instead of arriving as "login broken" later.
    """

    @pytest.mark.asyncio
    async def test_the_refusal_records_the_host_and_counts(self) -> None:
        c = _connector(_ForeignRedirectSession("https://Evil.Example.ORG/cb", 302))
        with pytest.raises(AuthenticationError):
            await c._follow_login_redirects(
                "POST", f"{_IDENTITY}/signin-service/v1/login", headers={}, data={},
            )
        assert c.refused_login_host_count == 1
        assert c.refused_login_hosts == {"evil.example.org"}, "host must be folded"

    @pytest.mark.asyncio
    async def test_the_url_is_never_recorded(self) -> None:
        """A refused login URL can carry ``code`` and ``state``. Only the host
        is safe to keep, and this is the test that keeps it that way."""
        c = _connector(_ForeignRedirectSession(
            "https://evil.example.org/cb?code=SECRET-CODE&state=SECRET-STATE", 307))
        with pytest.raises(AuthenticationError) as err:
            await c._follow_login_redirects(
                "POST", f"{_IDENTITY}/signin-service/v1/login", headers={}, data={},
            )
        blob = repr(sorted(c.refused_login_hosts)) + str(err.value)
        assert "SECRET-CODE" not in blob
        assert "SECRET-STATE" not in blob
        assert "code=" not in blob and "state=" not in blob
        assert "evil.example.org" in blob, "control: the host IS kept"

    @pytest.mark.asyncio
    async def test_the_same_host_twice_counts_twice_but_lists_once(self) -> None:
        c = _connector(_ForeignRedirectSession("https://evil.example.org/cb", 302))
        for _ in range(2):
            with pytest.raises(AuthenticationError):
                await c._follow_login_redirects(
                    "POST", f"{_IDENTITY}/signin-service/v1/login",
                    headers={}, data={},
                )
        assert c.refused_login_host_count == 2
        assert c.refused_login_hosts == {"evil.example.org"}

    @pytest.mark.asyncio
    async def test_the_warning_names_the_host(self, caplog) -> None:
        """A locked-out user has to find the remedy in their own log."""
        import logging

        c = _connector(_ForeignRedirectSession("https://moved.example.org/cb", 302))
        with caplog.at_level(logging.WARNING), pytest.raises(AuthenticationError):
            await c._follow_login_redirects(
                "POST", f"{_IDENTITY}/signin-service/v1/login", headers={}, data={},
            )
        assert "moved.example.org" in caplog.text
        assert "no credentials" in caplog.text, (
            "the message must say what did NOT happen, or a reporter assumes it did"
        )


class TestTheDiagnosticsReader:
    def test_a_clean_client_reports_zero(self) -> None:
        from custom_components.vag_connect.diagnostics import _refused_login_hosts

        c = _connector(_ForeignRedirectSession("https://x.example.org/"))
        assert _refused_login_hosts(c) == {"count": 0, "hosts": []}

    def test_a_refusal_shows_up(self) -> None:
        from custom_components.vag_connect.diagnostics import _refused_login_hosts

        c = _connector(_ForeignRedirectSession("https://x.example.org/"))
        c.refused_login_hosts = {"b.example.org", "a.example.org"}
        c.refused_login_host_count = 3
        assert _refused_login_hosts(c) == {
            "count": 3, "hosts": ["a.example.org", "b.example.org"],
        }

    def test_a_client_without_the_fields_returns_none(self) -> None:
        """Control: other brands' clients have no such counter, and the reader
        must stay quiet rather than inventing a zero for them."""
        from custom_components.vag_connect.diagnostics import _refused_login_hosts

        assert _refused_login_hosts(object()) is None
