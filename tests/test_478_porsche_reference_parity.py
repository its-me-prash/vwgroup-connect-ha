# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v4.7.8 — Porsche login 1:1 with the reference client (settle delay + plain
library User-Agent), the lifecycle fixes around it (dead refresh token → reauth,
solved-captcha hand-over hygiene, "session expired" repair that finally clears),
and the Scout/merge corrections shipped in the same release.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad import _channel_merge as merge_mod
from custom_components.vag_connect.cariad.api import porsche as api_mod
from custom_components.vag_connect.cariad.auth import porsche as auth_mod
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.const import CONF_BRAND
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_CC = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
_LANGS = ("cs", "da", "de", "en", "es", "fi", "fr", "it", "nb", "nl", "pl", "sv")


class _Resp:
    def __init__(self, status: int, location: str = "", text: str = "") -> None:
        self.status = status
        self.headers = {"Location": location} if location else {}
        self._text = text

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def text(self) -> str:
        return self._text


def _session(post_responses=None, get_responses=None) -> MagicMock:
    pit = iter(post_responses or [])
    git = iter(get_responses or [])
    s = MagicMock()
    s.post = MagicMock(side_effect=lambda *a, **kw: next(pit))
    s.get = MagicMock(side_effect=lambda *a, **kw: next(git))
    return s


# ── 1:1 with the reference client ─────────────────────────────────────────────

def test_settle_delay_matches_reference_client_verbatim() -> None:
    # CJNE/pyporscheconnectapi sleeps 2.5 s between the password POST and the
    # first resume hop. Pin the constant in SOURCE: the conftest zeroes the live
    # value for test speed, so the module attribute can't be asserted directly.
    src = Path(auth_mod.__file__).read_text(encoding="utf-8")
    assert "_POST_PASSWORD_SETTLE_S = 2.5" in src


def test_settle_delay_sits_between_password_post_and_resume(monkeypatch) -> None:
    monkeypatch.setattr(auth_mod, "_POST_PASSWORD_SETTLE_S", 0.123)
    events: list[tuple] = []

    async def fake_sleep(seconds):
        events.append(("sleep", seconds))

    async def fake_follow(self, location, referer, verifier=""):
        events.append(("follow", location))
        return "CODE"

    async def fake_exchange(self, code, verifier):
        events.append(("exchange", code))
        return "TOKENS"

    monkeypatch.setattr(auth_mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(auth_mod.PorscheAuth, "_follow_to_code", fake_follow)
    monkeypatch.setattr(auth_mod.PorscheAuth, "_exchange_code", fake_exchange)
    session = _session(
        get_responses=[_Resp(302, location="https://identity.porsche.com/u/login/identifier?state=S1")],
        post_responses=[
            _Resp(200),                                       # identifier accepted
            _Resp(302, location="/authorize/resume?state=S1"),  # password accepted
        ],
    )
    out = asyncio.run(auth_mod.PorscheAuth(session).authenticate("a@b.com", "pw"))
    assert out == "TOKENS"
    # order is the whole point: password POST → settle → resume chain → exchange
    assert events == [
        ("sleep", 0.123),
        ("follow", "/authorize/resume?state=S1"),
        ("exchange", "CODE"),
    ]


def test_settle_delay_is_not_paid_on_a_wrong_password(monkeypatch) -> None:
    events: list = []

    async def fake_sleep(seconds):
        events.append("sleep")

    monkeypatch.setattr(auth_mod.asyncio, "sleep", fake_sleep)
    session = _session(
        get_responses=[_Resp(302, location="https://identity.porsche.com/u/login/identifier?state=S1")],
        post_responses=[_Resp(200), _Resp(401)],
    )
    with pytest.raises(auth_mod.AuthenticationError):
        asyncio.run(auth_mod.PorscheAuth(session).authenticate("a@b.com", "pw"))
    assert events == []


@pytest.mark.parametrize("ua", [auth_mod._USER_AGENT, api_mod._USER_AGENT])
def test_user_agent_is_the_plain_library_identity(ua: str) -> None:
    # The reference client identifies itself as a library and has been stable
    # for years; borrowing a phone's identity buys nothing and reads as evasion.
    assert ua.startswith("vag-connect-ha/")
    assert "github.com/its-me-prash/vwgroup-connect-ha" in ua
    for impersonation in ("okhttp", "Android", "iPhone", "Mozilla", "Dalvik"):
        assert impersonation not in ua


def test_both_layers_carry_the_same_user_agent() -> None:
    assert auth_mod._USER_AGENT == api_mod._USER_AGENT


# ── lifecycle around the login ────────────────────────────────────────────────

def _coord_self(reason: str = "", *, pending: bool = True) -> SimpleNamespace:
    portal = SimpleNamespace(last_login_interaction="", last_no_data_reason=reason)
    client = SimpleNamespace(_eu_portal=portal, _supplementary_eu_portal=None)
    entry = SimpleNamespace(entry_id="e1", data={CONF_BRAND: "skoda"})
    return SimpleNamespace(
        _cariad_client=client, entry=entry, hass=MagicMock(),
        _portal_interaction_reason="",
        _data_act_session_expired_pending=pending,
    )


def test_session_expired_repair_is_remembered_when_raised() -> None:
    me = SimpleNamespace(
        hass=MagicMock(), entry=SimpleNamespace(entry_id="e1", data={CONF_BRAND: "skoda"}),
    )
    with patch("homeassistant.helpers.issue_registry.async_create_issue") as create:
        VagConnectCoordinator._raise_data_act_session_expired_repair(me)
    create.assert_called_once()
    assert "data_act_session_expired_e1" in str(create.call_args.args)
    assert me._data_act_session_expired_pending is True


def test_session_expired_repair_clears_once_data_flows_again() -> None:
    me = _coord_self("", pending=True)
    with patch("homeassistant.helpers.issue_registry.async_delete_issue") as delete, \
            patch("homeassistant.helpers.issue_registry.async_create_issue"):
        VagConnectCoordinator._update_data_act_no_data_repair(me)
    assert any("data_act_session_expired_e1" in str(c.args) for c in delete.call_args_list)
    assert me._data_act_session_expired_pending is False


def test_session_expired_repair_survives_a_no_data_poll() -> None:
    # the kickoff can raise it mid-cycle; the same cycle's empty dataset must
    # not erase it straight away
    me = _coord_self("empty", pending=True)
    with patch("homeassistant.helpers.issue_registry.async_delete_issue") as delete, \
            patch("homeassistant.helpers.issue_registry.async_create_issue"):
        VagConnectCoordinator._update_data_act_no_data_repair(me)
    assert not any("data_act_session_expired_e1" in str(c.args) for c in delete.call_args_list)
    assert me._data_act_session_expired_pending is True


def test_session_expired_repair_is_left_alone_when_never_raised() -> None:
    me = _coord_self("", pending=False)
    with patch("homeassistant.helpers.issue_registry.async_delete_issue") as delete, \
            patch("homeassistant.helpers.issue_registry.async_create_issue"):
        VagConnectCoordinator._update_data_act_no_data_repair(me)
    assert not any("data_act_session_expired_e1" in str(c.args) for c in delete.call_args_list)


def test_coordinator_source_carries_the_porsche_lifecycle_fixes() -> None:
    src = (_CC / "coordinator.py").read_text(encoding="utf-8")
    # M2 — every read failed auth → reauth instead of an endless interactive loop
    assert "every vehicle read failed authentication" in src
    # L1 — the solved-captcha hand-over is only promoted with a refresh token
    assert 'porsche_initial.get("refresh_token")' in src
    # L2 — and the hand-over key is stripped from entry.data afterwards
    assert 'k != "porsche_initial_tokens"' in src


# ── "everything is empty" made visible ────────────────────────────────────────

def _overview(measurements: list) -> dict:
    return {
        "modelName": "Taycan",
        "modelType": {"engine": "BEV", "year": 2021},
        "measurements": measurements,
    }


def _status(overview) -> VehicleData:
    client = api_mod.PorscheClient.__new__(api_mod.PorscheClient)
    client._get = AsyncMock(return_value=overview)  # type: ignore[method-assign]
    return asyncio.run(client.get_status("WP0X"))


def test_connect_contract_enabled_is_active() -> None:
    d = _status(_overview([{"key": "CONNECT_CONTRACT", "status": {"isEnabled": True}, "value": {}}]))
    assert d.connect_contract_active is True


def test_connect_contract_disabled_is_inactive() -> None:
    d = _status(_overview([{"key": "CONNECT_CONTRACT", "status": {"isEnabled": False}, "value": {}}]))
    assert d.connect_contract_active is False


def test_connect_contract_absent_is_unknown() -> None:
    d = _status(_overview([{"key": "BATTERY_LEVEL", "status": {"isEnabled": True}, "value": {}}]))
    assert d.connect_contract_active is None


def test_status_auth_failure_propagates_to_the_coordinator() -> None:
    # ``_request`` has already refreshed/retried/fallen back before raising
    # AuthenticationError — swallowing it left entities silently empty and the
    # interactive login re-running with no reauth prompt.
    client = api_mod.PorscheClient.__new__(api_mod.PorscheClient)
    client._get = AsyncMock(side_effect=api_mod.AuthenticationError("dead token"))  # type: ignore[method-assign]
    with pytest.raises(api_mod.AuthenticationError):
        asyncio.run(client.get_status("WP0X"))
    assert client.probe_outcomes["porsche_status"] == "AuthenticationError"


def test_status_failure_is_recorded_and_warned_once_per_vin(caplog) -> None:
    client = api_mod.PorscheClient.__new__(api_mod.PorscheClient)
    err = RuntimeError("boom")
    err.status = 403  # type: ignore[attr-defined]
    client._get = AsyncMock(side_effect=err)  # type: ignore[method-assign]
    with caplog.at_level("DEBUG"):
        asyncio.run(client.get_status("WP0ZZZ123456"))
        asyncio.run(client.get_status("WP0ZZZ123456"))
    assert client.probe_outcomes["porsche_status"] == "RuntimeError:403"
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "status read failed" in r.getMessage()]
    assert len(warnings) == 1
    assert "123456" in warnings[0].getMessage()      # masked tail only
    assert "WP0ZZZ123456" not in warnings[0].getMessage()


# ── Scout corrections ─────────────────────────────────────────────────────────

def _map(points: list[dict]) -> VehicleData:
    fields = _walk_fields({"data": points})
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_fuel_shaped_short_term_consumption_gets_its_own_field() -> None:
    d = _map([{"dataFieldName": "shortTermAverageConsumption",
               "value": "5.2 l/100km", "key": "k"}])
    assert d.short_term_avg_fuel_consumption_l_100km == 5.2
    assert d.short_term_avg_electric_consumption_kwh_100km is None


def test_electric_short_term_consumption_stays_electric() -> None:
    d = _map([{"dataFieldName": "shortTermAverageConsumption",
               "value": "15.8 kWh/100km", "key": "k"}])
    assert d.short_term_avg_electric_consumption_kwh_100km == 15.8
    assert d.short_term_avg_fuel_consumption_l_100km is None


@pytest.mark.parametrize("code", ["14", "15"])
def test_scr_status_codes_are_not_engine_start_counts(code: str) -> None:
    d = _map([{"dataFieldName": "scr_number_of_engine_starts", "value": code, "key": "k"}])
    assert d.engine_starts_count is None


def test_scr_count_range_is_still_a_count() -> None:
    d = _map([{"dataFieldName": "scr_number_of_engine_starts", "value": "13", "key": "k"}])
    assert d.engine_starts_count == 13


def test_charge_report_soc_lands_on_its_own_field_not_battery_soc() -> None:
    d = _map([{"dataFieldName": "battery_state_report.soc_at_charge_start",
               "value": "63", "key": "k"}])
    assert d.battery_soc_charge_report == 63
    assert d.battery_soc is None


def test_alarm_reason_is_mapped_verbatim() -> None:
    # #1396 (CUPRA Raval) — anti-theft alarm reason enum, kept as-is
    d = _map([{"dataFieldName": "dwa_alarm_reason",
               "value": "ALARM_REASON_DRIVERSDOOROPEN", "key": "k"}])
    assert d.alarm_reason == "ALARM_REASON_DRIVERSDOOROPEN"
    assert d.alarm_active is None  # a reason is not an "active now" flag


def test_blank_alarm_reason_is_not_a_value() -> None:
    d = _map([{"dataFieldName": "dwa_alarm_reason", "value": "  ", "key": "k"}])
    assert d.alarm_reason is None


def test_raval_der_envelope_packet_is_consumed_not_invented() -> None:
    # #1396 — bare ``data`` leaf = base64 DER envelope (two timestamps); it is
    # consumed as metadata so the Scout stops re-reporting it, no sensor.
    fields = _walk_fields({"data": [
        {"dataFieldName": "data",
         "value": "oRiCARGFAt6bmw8yMDI2MDkxMDIwMTMwNlqeDzIwMjYwOTEwMjAwMzA2WpwBAA==",
         "key": "k"},
    ]})
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))
    assert d.alarm_reason is None
    # ``first()`` consumed it: no longer an unmapped (Scout-reported) field
    assert "data" not in d.raw_unmapped_fields


def test_unknown_leaf_still_surfaces_as_unmapped() -> None:
    # guard for the test above: an unrelated leaf DOES stay visible to the Scout
    fields = _walk_fields({"data": [
        {"dataFieldName": "some_new_leaf", "value": "1", "key": "k"},
    ]})
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))
    assert "some_new_leaf" in d.raw_unmapped_fields


# ── position: freshest fix wins ───────────────────────────────────────────────

def test_freshest_position_beats_merge_order() -> None:
    older = VehicleData(vin="X", latitude=1.0, longitude=1.0, heading=10,
                        position_captured_at="2026-09-11T10:00:00Z")
    newer = VehicleData(vin="X", latitude=2.0, longitude=2.0, heading=20,
                        position_captured_at="2026-09-11T10:30:00Z")
    merged = merge_mod.merge_channels([("eu_data_act", older), ("brand_native", newer)])
    assert (merged.latitude, merged.longitude, merged.heading) == (2.0, 2.0, 20)
    assert merged.position_captured_at == "2026-09-11T10:30:00Z"
    assert merged.field_sources["latitude"] == "brand_native"
    assert merged.field_sources["heading"] == "brand_native"


def test_primary_keeps_position_when_it_is_the_freshest() -> None:
    newer = VehicleData(vin="X", latitude=1.0, longitude=1.0,
                        position_captured_at="2026-09-11T10:30:00Z")
    older = VehicleData(vin="X", latitude=2.0, longitude=2.0,
                        position_captured_at="2026-09-11T10:00:00Z")
    merged = merge_mod.merge_channels([("eu_data_act", newer), ("brand_native", older)])
    assert merged.latitude == 1.0
    assert merged.field_sources["latitude"] == "eu_data_act"


def test_untimestamped_pin_cannot_beat_a_timestamped_fix() -> None:
    no_ts = VehicleData(vin="X", latitude=1.0, longitude=1.0)
    with_ts = VehicleData(vin="X", latitude=2.0, longitude=2.0,
                          position_captured_at="2026-09-11T10:00:00Z")
    merged = merge_mod.merge_channels([("eu_data_act", no_ts), ("brand_native", with_ts)])
    assert merged.latitude == 2.0
    assert merged.field_sources["latitude"] == "brand_native"


def test_unparseable_timestamp_is_skipped_not_fatal() -> None:
    bad = VehicleData(vin="X", latitude=1.0, longitude=1.0, position_captured_at="yesterday")
    good = VehicleData(vin="X", latitude=2.0, longitude=2.0,
                       position_captured_at="2026-09-11T10:00:00Z")
    merged = merge_mod.merge_channels([("eu_data_act", bad), ("brand_native", good)])
    assert merged.latitude == 2.0


def test_single_channel_position_is_untouched() -> None:
    only = VehicleData(vin="X", latitude=1.0, longitude=1.0,
                       position_captured_at="2026-09-11T10:00:00Z")
    merged = merge_mod.merge_channels([("eu_data_act", only)])
    assert merged.latitude == 1.0
    assert merged.field_sources["latitude"] == "eu_data_act"


# ── entities + strings ────────────────────────────────────────────────────────

def test_sensor_source_gates_engine_starts_to_combustion_and_relaxes_trip_gate() -> None:
    src = (_CC / "sensor.py").read_text(encoding="utf-8")
    assert 'key="short_term_avg_fuel_consumption_l_100km"' in src
    assert 'key="battery_soc_charge_report"' in src
    # the trip-statistics capability gate only hides sensors WITHOUT a value
    assert "and vehicle.get(desc.data_key) is None" in src
    # engine starts on combustion cars only
    i = src.index('key="engine_starts_count"')
    assert 'condition="combustion"' in src[i:i + 900]


def test_binary_sensor_source_has_connect_contract_diagnostic() -> None:
    src = (_CC / "binary_sensor.py").read_text(encoding="utf-8")
    i = src.index('key="connect_contract_active"')
    assert "EntityCategory.DIAGNOSTIC" in src[i:i + 600]


@pytest.mark.parametrize("lang", _LANGS)
def test_new_entity_names_exist_in_every_language(lang: str) -> None:
    d = json.loads((_CC / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
    assert d["entity"]["sensor"]["short_term_avg_fuel_consumption_l_100km"]["name"]
    assert d["entity"]["sensor"]["battery_soc_charge_report"]["name"]
    assert d["entity"]["sensor"]["alarm_reason"]["name"]
    assert d["entity"]["binary_sensor"]["connect_contract_active"]["name"]
    assert d["options"]["error"]["terms_and_conditions"]


@pytest.mark.parametrize("lang", _LANGS)
def test_captcha_copy_is_honest_about_where_the_answer_goes(lang: str) -> None:
    d = json.loads((_CC / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
    desc = d["config"]["step"]["porsche_captcha"]["description"]
    assert "{captcha_img}" in desc and "{report_url}" in desc
    assert "never leaves" not in desc.lower()
    assert "Porsche" in desc


def test_strings_json_matches_en_translation() -> None:
    s = json.loads((_CC / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((_CC / "translations" / "en.json").read_text(encoding="utf-8"))
    for kind, key in (("sensor", "short_term_avg_fuel_consumption_l_100km"),
                      ("sensor", "battery_soc_charge_report"),
                      ("binary_sensor", "connect_contract_active")):
        assert s["entity"][kind][key] == en["entity"][kind][key]
    assert (s["config"]["step"]["porsche_captcha"]["description"]
            == en["config"]["step"]["porsche_captcha"]["description"])


# ── pre-push review fixes ─────────────────────────────────────────────────────

def test_refresh_endpoint_hiccup_is_not_a_dead_token() -> None:
    from custom_components.vag_connect.cariad.exceptions import APIError
    session = _session(post_responses=[_Resp(503, text='{"error":"temporarily_unavailable"}')])
    with pytest.raises(APIError):
        asyncio.run(auth_mod.PorscheAuth(session).refresh("R"))


@pytest.mark.parametrize("resp", [
    _Resp(401), _Resp(403), _Resp(400, text='{"error":"invalid_grant"}'),
])
def test_refresh_rejections_mean_expired(resp: _Resp) -> None:
    from custom_components.vag_connect.cariad.exceptions import TokenExpiredError
    session = _session(post_responses=[resp])
    with pytest.raises(TokenExpiredError):
        asyncio.run(auth_mod.PorscheAuth(session).refresh("R"))


def test_concurrent_refreshes_coalesce_into_one() -> None:
    from custom_components.vag_connect.cariad.models import TokenSet
    client = api_mod.PorscheClient.__new__(api_mod.PorscheClient)
    client._tokens = TokenSet(access_token="A", refresh_token="R", id_token="")
    client._refresh_lock = None
    client._refresh_history = []
    client.on_tokens_changed = None
    client._auth = MagicMock()
    client._auth.refresh = AsyncMock(
        return_value=TokenSet(access_token="B", refresh_token="R2", id_token=""),
    )

    async def run() -> None:
        await asyncio.gather(*[client._refresh(stale_access_token="A") for _ in range(3)])

    asyncio.run(run())
    assert client._auth.refresh.await_count == 1        # three cars, one refresh
    assert client._tokens.access_token == "B"
    assert len(client._refresh_history) == 1            # one budget slot used


def test_refresh_without_stale_hint_still_refreshes() -> None:
    from custom_components.vag_connect.cariad.models import TokenSet
    client = api_mod.PorscheClient.__new__(api_mod.PorscheClient)
    client._tokens = TokenSet(access_token="A", refresh_token="R", id_token="")
    client._refresh_lock = None
    client._refresh_history = []
    client.on_tokens_changed = None
    client._auth = MagicMock()
    client._auth.refresh = AsyncMock(
        return_value=TokenSet(access_token="B", refresh_token="R", id_token=""),
    )
    asyncio.run(client._refresh())
    assert client._auth.refresh.await_count == 1


def _porsche_coord(brand: str = "porsche") -> SimpleNamespace:
    return SimpleNamespace(entry=SimpleNamespace(data={CONF_BRAND: brand}))


def test_porsche_auth_dead_needs_two_consecutive_polls() -> None:
    me = _porsche_coord()
    dead = [api_mod.AuthenticationError("x"), api_mod.AuthenticationError("y")]
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1", "V2"], dead) is False
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1", "V2"], dead) is True


def test_porsche_auth_dead_resets_on_any_success() -> None:
    me = _porsche_coord()
    dead = [api_mod.AuthenticationError("x")]
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1"], dead) is False
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1"], [VehicleData(vin="V1")]) is False
    assert me._porsche_auth_fail_polls == 0
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1"], dead) is False  # counts from 1 again


def test_porsche_auth_dead_ignores_non_auth_and_partial_failures() -> None:
    me = _porsche_coord()
    mixed = [api_mod.AuthenticationError("x"), RuntimeError("net")]
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1", "V2"], mixed) is False
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1", "V2"], mixed) is False


def test_porsche_auth_dead_is_brand_gated() -> None:
    me = _porsche_coord("skoda")
    dead = [api_mod.AuthenticationError("x")]
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1"], dead) is False
    assert VagConnectCoordinator._porsche_auth_dead(me, ["V1"], dead) is False


def test_direct_body_wall_names_the_screen() -> None:
    session = _session(
        get_responses=[_Resp(302, location="https://identity.porsche.com/u/login/identifier?state=S1")],
        post_responses=[
            _Resp(200),
            _Resp(200, text="<html><title>My Porsche consent</title><body>agree</body></html>"),
        ],
    )
    auth = auth_mod.PorscheAuth(session)
    with pytest.raises(auth_mod.PorscheLoginWallError) as ei:
        asyncio.run(auth.authenticate("a@b.com", "pw"))
    assert ei.value.screen.startswith("identity.porsche.com/")
    assert ei.value.marker                      # secret-free page marker present
    for secret in ("S1", "a@b.com", "pw"):
        assert secret not in ei.value.screen and secret not in ei.value.marker


def test_wall_screen_is_reset_per_attempt(monkeypatch) -> None:
    async def fake_follow(self, location, referer, verifier=""):
        return "CODE"

    async def fake_exchange(self, code, verifier):
        return "TOKENS"

    monkeypatch.setattr(auth_mod.PorscheAuth, "_follow_to_code", fake_follow)
    monkeypatch.setattr(auth_mod.PorscheAuth, "_exchange_code", fake_exchange)
    session = _session(
        get_responses=[_Resp(302, location="https://identity.porsche.com/u/login/identifier?state=S1")],
        post_responses=[_Resp(200), _Resp(302, location="/authorize/resume?state=S1")],
    )
    auth = auth_mod.PorscheAuth(session)
    auth._last_wall_screen, auth._last_wall_marker = "stale.host/old", "old marker"
    assert asyncio.run(auth.authenticate("a@b.com", "pw")) == "TOKENS"
    assert (auth._last_wall_screen, auth._last_wall_marker) == ("", "")


def test_coordinator_strips_the_token_handover_unconditionally() -> None:
    src = (_CC / "coordinator.py").read_text(encoding="utf-8")
    i = src.index('if "porsche_initial_tokens" in self.entry.data:')
    # the strip sits OUTSIDE the "promote only when the store is empty" block
    assert "porsche_initial.get(\"refresh_token\")" in src[:i]
    assert 'k != "porsche_initial_tokens"' in src[i:i + 400]
