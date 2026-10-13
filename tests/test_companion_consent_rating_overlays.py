# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""2026-10-07 — two VW app 4.6.4 pop-ups the companion clears on its own.

- The Google Maps consent on the Map tab (it blocks the parking read): agreed
  only during the opted-in parking walk. Other callers BACK out and stop.
- The rating prompt (thumbs down / thumbs up, no close button): closed with
  BACK, so the app is never rated.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.companion.channel import (
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import find_overlay, parse_ui_dump


def _node(text: str = "", desc: str = "", rid: str = "", bounds: str = "[0,0][10,10]",
          clickable: bool = False) -> str:
    return (
        f'<node index="0" text="{text}" resource-id="{rid}" class="android.view.View" '
        f'package="com.volkswagen.weconnect" content-desc="{desc}" checkable="false" '
        f'checked="false" clickable="{str(clickable).lower()}" enabled="true" '
        f'focusable="false" focused="false" scrollable="false" long-clickable="false" '
        f'password="false" selected="false" bounds="{bounds}" />'
    )


def _dump(*nodes: str) -> str:
    return '<?xml version="1.0"?><hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


# As seen live on 4.6.4 (2026-10-07), Map tab right after the update.
CONSENT = _dump(
    _node(rid="com.volkswagen.weconnect:id/google_maps_consent_fragment", bounds="[0,1028][1080,2064]"),
    _node(text="This app uses Google Maps", bounds="[53,1081][809,1158]"),
    _node(text="By using Google Maps, you give Volkswagen AG your consent to", bounds="[53,1200][1027,1728]"),
    _node(text="Agree", bounds="[485,1871][596,1922]"),
    _node(desc="Map Tab", rid="com.volkswagen.weconnect:id/cat_nav_map_tab_navigation",
          bounds="[360,2088][720,2193]", clickable=True),
)
CONSENT_NO_BUTTON = _dump(_node(text="This app uses Google Maps", bounds="[53,1081][809,1158]"))
# Layout dialog_app_rating_alert: title plus two icon-only buttons.
RATING = _dump(
    _node(text="How do you like the Volkswagen app? Give us your feedback.", rid="com.volkswagen.weconnect:id/title"),
    _node(rid="com.volkswagen.weconnect:id/cta_thumb_down", bounds="[60,900][520,1000]", clickable=True),
    _node(rid="com.volkswagen.weconnect:id/cta_thumb_up", bounds="[560,900][1020,1000]", clickable=True),
)
OVERVIEW = _dump(_node(desc="Climate control. On. Open details", clickable=True))


def _channel(*screens: str) -> tuple[CompanionChannel, MagicMock]:
    t = MagicMock()
    t.dump_ui = AsyncMock(side_effect=list(screens))
    t.tap = AsyncMock()
    t.key_back = AsyncMock()
    return CompanionChannel(t, PRESETS["volkswagen"], time_fn=lambda: 0.0), t


def test_both_pop_ups_are_recognised() -> None:
    vw = PRESETS["volkswagen"]
    assert find_overlay(parse_ui_dump(CONSENT), vw).name == "google_maps_consent"
    assert find_overlay(parse_ui_dump(RATING), vw).name == "app_rating"
    assert find_overlay(parse_ui_dump(OVERVIEW), vw) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("parking_on", [False, True])
async def test_read_never_agrees_to_consent_outside_parking_walk(parking_on) -> None:
    ch, t = _channel(CONSENT, OVERVIEW)
    ch.set_nav_opt_in("parking_position", parking_on)
    ch._refresh_version_gate = AsyncMock()
    t.foreground_app = AsyncMock()
    t.sleep_if_enabled = AsyncMock()
    t.force_stop_if_enabled = AsyncMock()
    assert await ch.read() == {}
    t.tap.assert_not_awaited()
    t.key_back.assert_awaited_once()


@pytest.mark.asyncio
async def test_command_backs_out_of_consent_and_refuses_with_parking_on() -> None:
    ch, t = _channel(CONSENT, OVERVIEW)
    ch.set_nav_opt_in("parking_position", True)
    ch._version_ok = True
    ch._live_app_version = "4.6.4"
    ch._refresh_version_gate = AsyncMock()
    t.foreground_app = AsyncMock()
    with pytest.raises(CompanionWriteBlocked, match="not tapping blind"):
        await ch.do_action("start_charging")
    t.tap.assert_not_awaited()
    t.key_back.assert_awaited_once()


@pytest.mark.asyncio
async def test_parking_walk_with_opt_in_agrees_then_reads_coordinates() -> None:
    ch, t = _channel(OVERVIEW)
    ch.set_nav_opt_in("parking_position", True)
    nav = next(n for n in PRESETS["volkswagen"].nav_reads if n.name == "parking_position")
    start = _dump(_node(
        desc="Map Tab", rid="com.volkswagen.weconnect:id/cat_nav_map_tab_navigation",
        bounds="[0,0][100,100]", clickable=True,
    ))
    find = _dump(_node(desc="Find vehicle", bounds="[0,100][100,200]", clickable=True))
    marker = _dump(_node(desc="Google Map", bounds="[0,200][100,400]", clickable=True))
    share = _dump(_node(text="Share", bounds="[0,400][100,500]", clickable=True))
    link = _dump(_node(text="https://www.google.com/maps?q=48.2,16.3"))
    t.dump_ui.side_effect = [start, find]
    ch._settle = AsyncMock(side_effect=[CONSENT, marker, share, link])
    ch._return_to_overview = AsyncMock()
    fields = {}
    await ch._read_nav_group([nav], fields)
    assert fields == {"latitude": 48.2, "longitude": 16.3}
    assert [c.args for c in t.tap.await_args_list] == [
        (50, 50), (540, 1896), (50, 150), (50, 286), (50, 450),
    ]
    t.key_back.assert_not_awaited()
    ch._return_to_overview.assert_awaited_once_with(4)


@pytest.mark.asyncio
@pytest.mark.parametrize("walk,parking_on", [(None, True), ("parking_position", False),
                                              ("climate_detail", True)])
async def test_consent_requires_both_parking_walk_and_opt_in(walk, parking_on) -> None:
    ch, t = _channel(CONSENT, OVERVIEW)
    ch.set_nav_opt_in("parking_position", parking_on)
    _nodes, cleared = await ch._dump_and_clear_overlays(agree_opt_in=walk)
    assert cleared is False
    t.tap.assert_not_awaited()
    t.key_back.assert_awaited_once()


@pytest.mark.asyncio
async def test_without_its_button_parking_consent_backs_out_and_stops() -> None:
    ch, t = _channel(CONSENT_NO_BUTTON, OVERVIEW)
    ch.set_nav_opt_in("parking_position", True)
    _nodes, cleared = await ch._dump_and_clear_overlays(agree_opt_in="parking_position")
    assert cleared is False
    t.key_back.assert_awaited_once()
    t.tap.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_rating_prompt_is_closed_with_back_never_rated() -> None:
    ch, t = _channel(RATING, OVERVIEW)
    _nodes, cleared = await ch._dump_and_clear_overlays()
    assert cleared is True
    t.key_back.assert_awaited_once()
    t.tap.assert_not_awaited()
