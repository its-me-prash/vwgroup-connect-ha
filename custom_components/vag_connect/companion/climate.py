# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Volkswagen Air Conditioning sheet: state and commands for the companion channel.

Builds on the channel's walk, overlay, version and rate-limit machinery; this
module only knows the one sheet behind the overview's ``climateTile``.

What the app does, from the installed 4.3.2 APK and the #968 captures:

* ``cta_start`` / ``cta_stop`` is one button whose resource-id flips while air
  conditioning OR window heating runs. The sheet dismisses itself once the app
  has had its start/stop request accepted.
* The Mk8 toggles (``air_conditioning_toggle`` / ``window_heating_toggle``) and
  the mode picker (``clima_air_conditioning_pick`` → "Select mode") only choose
  WHAT Start starts. Changing them sends nothing to the car.
* The temperature dial is a pager of 15.5 (LO) … 30.0 (HI) °C in 0.5 steps;
  the app has no Fahrenheit dial (ClimaSettingsMapper sends "celsius").
  Tapping a neighbouring number scrolls one step; the app sends the new target
  to the car 1 s after the dial stops (debounced), idle or running, and on
  close. So a temperature change costs one car request of its own: the taps
  go out in one batch inside the debounce, and the dial is read back once.
  In the window-heating mode the dial is drawn but disabled.
* Labels are matched against the installed app's own translations
  (``resources.py``); the German/English patterns are only the fallback when
  the tables cannot be read.

The sheet has no Save (4.6.4 review): Start applies the selected mode and the
dial's temperature. So the mode and temperature are held in HA and applied by
``start`` itself, right before it presses Start; changing them alone never
opens the app.

Every step is read back from the screen before the next one, and a command
never confirms anything the app did not show. A tap is not a vehicle result:
the next poll supplies the real state.
"""
from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Callable

from .presets import app_version_covered, app_version_listed
from .resources import (
    DATA_UNAVAILABLE,
    StringResources,
    climate_function_state,
    climate_mode_is_window_heating,
    CLIMA_DEGREE,
    dial_labels,
    find_app_alert,
)
from .screen import UiNode, _rid_matches, find_node_for, find_rate_limit_banner, has_anchor
from .transport import CompanionTransportError

if TYPE_CHECKING:
    from .channel import CompanionChannel

# Commands are mapped against these builds only (4.6.4: the same sheet ids in
# the 4.6.4 dumps; not yet sent to a car on 4.6.4). Reads keep the preset's own
# version set; a tap on another build's sheet is not assumed to be safe.
CLIMATE_APP_VERSIONS: tuple[str, ...] = ("4.6.4", "4.3.2")

DIAL_MIN_C = 15.5  # rendered "LO"
DIAL_MAX_C = 30.0  # rendered "HI"
DIAL_STEP_C = 0.5
# LO to HI: the most steps one change can take.
_DIAL_MAX_STEPS = round((DIAL_MAX_C - DIAL_MIN_C) / DIAL_STEP_C)
_DIAL_NUMBER_RE = re.compile(r"-?\d{1,3}(?:[.,]\d)?")
# The app debounces dial changes by 1000 ms before it sends them.
_DIAL_FLUSH_S = 1.2
# Steps one drag covers: about 41 % of the dial's width each, so two fit with
# room to spare on the captured phones.
_DRAG_STEPS = 2
# Gestures (car requests) one temperature change may take.
_DIAL_MAX_GESTURES = 2
# The step width must look like the captured dials' (about 0.41 of the width).
_DIAL_PAGE_MIN, _DIAL_PAGE_MAX = 0.25, 0.6
# Distance kept from the dial's edges when a drag starts.
_DRAG_MARGIN = 0.05
# Drag speed: well below the pager's 400 dp/s fling threshold on any density.
_DRAG_MAX_PX_S = 350
_DRAG_MIN_MS = 1000
# Dumps spent waiting for the screen a tap should produce. A dump already takes
# about a second on ADB, so these poll back to back rather than sleeping.
_SCREEN_TRIES = 5
_OUTCOME_TRIES = 12
# Values the climate sheet supplies; a command drops only these from the cache.
_CLIMATE_KEYS = (
    "climatisation_active", "climatisation_state", "window_heating_front",
    "climate_remaining_time_min",
)


@dataclass
class ClimaSheet:
    """What the Air Conditioning sheet shows right now."""

    start: UiNode | None = None
    stop: UiNode | None = None
    dial: UiNode | None = None
    ac_toggle: UiNode | None = None
    wh_toggle: UiNode | None = None
    pick: UiNode | None = None
    pick_title: str = ""

    @property
    def present(self) -> bool:
        return self.dial is not None and (self.start is not None or self.stop is not None)

    @property
    def running(self) -> bool:
        return self.stop is not None


_LIMIT_REASON = (
    "the car refused the request: its daily request budget is used up (the app "
    "says too many requests were sent to the vehicle). Start the car to reset it; "
    "commands are paused until then, or until you press Reset companion connection"
)


def _find(nodes: list[UiNode], rid: str, *, checkable: bool = False) -> UiNode | None:
    return next(
        (
            n for n in nodes
            if _rid_matches(n.resource_id, rid) and (n.checkable or not checkable)
        ),
        None,
    )


def _inside(node: UiNode, box: tuple[int, int, int, int]) -> bool:
    if node.bounds is None:
        return False
    left, top, right, bottom = box
    n_left, n_top, n_right, n_bottom = node.bounds
    return left <= n_left <= n_right <= right and top <= n_top <= n_bottom <= bottom


def read_sheet(nodes: list[UiNode]) -> ClimaSheet:
    """Locate the sheet's controls by resource-id; nothing here depends on language."""
    sheet = ClimaSheet(
        start=_find(nodes, "cta_start"),
        stop=_find(nodes, "cta_stop"),
        dial=_find(nodes, "clima_compose_view"),
        ac_toggle=_find(nodes, "air_conditioning_toggle", checkable=True),
        wh_toggle=_find(nodes, "window_heating_toggle", checkable=True),
        pick=_find(nodes, "clima_air_conditioning_pick"),
    )
    if sheet.pick is not None and sheet.pick.bounds is not None:
        title = next(
            (
                n for n in nodes
                if _rid_matches(n.resource_id, "title") and _inside(n, sheet.pick.bounds)
            ),
            None,
        )
        sheet.pick_title = title.text if title is not None else ""
    return sheet


def dial_value(raw: str, resources: StringResources | None = None) -> float | None:
    """One dial label: "21.5", "22", "LO" (15.5) or "HI" (30.0), translated."""
    text = raw.strip()
    low, high = dial_labels(resources or {})
    if text.casefold() in low:
        return DIAL_MIN_C
    if text.casefold() in high:
        return DIAL_MAX_C
    if not _DIAL_NUMBER_RE.fullmatch(text):
        return None
    return float(text.replace(",", "."))


def read_dial(
    nodes: list[UiNode], resources: StringResources | None = None,
) -> tuple[float | None, UiNode | None, UiNode | None]:
    """(centre value, left neighbour, right neighbour) of the temperature dial.

    The dial draws up to three bare labels in a row. The setting is the one
    nearest the container's centre; its neighbours are one 0.5 step away.
    """
    dial = _find(nodes, "clima_compose_view")
    if dial is None or dial.bounds is None:
        return None, None, None
    left, _top, right, _bottom = dial.bounds
    centre_x = (left + right) / 2
    labels = sorted(
        (
            n for n in nodes
            if n.text and n.bounds and _inside(n, dial.bounds)
            and dial_value(n.text, resources) is not None
        ),
        key=lambda n: (n.bounds[0] + n.bounds[2]) / 2,  # type: ignore[index]
    )
    if not labels:
        return None, None, None
    centre = min(labels, key=lambda n: abs((n.bounds[0] + n.bounds[2]) / 2 - centre_x))  # type: ignore[index]
    i = labels.index(centre)
    lower = labels[i - 1] if i > 0 else None
    higher = labels[i + 1] if i + 1 < len(labels) else None
    return dial_value(centre.text, resources), lower, higher


def dial_is_celsius(nodes: list[UiNode], resources: StringResources | None = None) -> bool:
    """True when every label on the dial is one the app's °C dial draws.

    That is a number on the 15.5-30.0 grid, the LO/HI labels
    (``clima_temperature_low`` / ``_high``) or the degree sign
    (``unit_degree_sign``). The app has no Fahrenheit key, so anything else
    means a dial this integration does not know, and it is never walked.
    """
    dial = _find(nodes, "clima_compose_view")
    if dial is None or dial.bounds is None:
        return False
    degree = {
        label.strip().casefold()
        for label in (resources or {}).get(CLIMA_DEGREE, ()) if label.strip()
    } | {"°"}
    values = 0
    for node in nodes:
        text = node.text.strip() if node.text else ""
        if not text or not _inside(node, dial.bounds):
            continue
        if text.casefold() in degree:
            continue
        value = dial_value(text, resources)
        if (
            value is None or not DIAL_MIN_C <= value <= DIAL_MAX_C
            or value / DIAL_STEP_C != round(value / DIAL_STEP_C)
        ):
            return False
        values += 1
    return values > 0


def snap_temperature(temp_c: float) -> float:
    """The dial position the app can actually show for a requested temperature."""
    snapped = round(float(temp_c) / DIAL_STEP_C) * DIAL_STEP_C
    return min(DIAL_MAX_C, max(DIAL_MIN_C, snapped))


class ClimateController:
    """Drive the Air Conditioning sheet for one channel.

    Serialised against polling by the caller (``CompanionClient``). Every public
    method opens the sheet itself and always walks back to the overview.
    """

    def __init__(
        self,
        channel: "CompanionChannel",
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._ch = channel
        self._sleep = sleep
        # True once a dump showed the overview, so the walk back can be skipped.
        self._home = False

    # -- public commands ------------------------------------------------------

    async def start(
        self, *, window_heating_only: bool = False, temp_c: float | None = None,
    ) -> None:
        """Start what HA asked for: set the mode and the dial, check, then Start.

        The sheet has no Save: Start sends the mode the picker shows and the
        temperature the dial shows. So both are set first (the dial only in the
        air conditioning mode; the app disables it for window heating alone),
        read back from the screen, and Start is pressed only when both match.
        ``temp_c`` None leaves the dial as it is. A running climate is left
        alone here; ``adjust`` moves its dial.
        """
        target = (
            snap_temperature(temp_c)
            if temp_c is not None and not window_heating_only else None
        )
        async with self._on_sheet() as nodes:
            sheet = read_sheet(nodes)
            if sheet.running:
                # Already on: Start is not on screen, and Stop must not be
                # pressed for a start request. Nothing to send; but say so when
                # what runs is not what was asked for.
                if self._ac_shown(nodes, sheet) == window_heating_only:
                    running = "air conditioning" if window_heating_only else "window heating"
                    raise self._blocked(
                        f"{running} is already running; nothing was sent. Stop it "
                        "first to start the other function"
                    )
                return
            nodes = await self._select(nodes, window_heating_only)
            mode_title = read_sheet(nodes).pick_title
            if target is not None:
                nodes = await self._apply_dial(nodes, target)
            self._check_ready(nodes, window_heating_only, mode_title, target)
            sheet = read_sheet(nodes)
            if sheet.start is None or not sheet.start.enabled or sheet.start.tap_point is None:
                raise self._blocked("the Start button is not available on the sheet")
            await self._tap_command(sheet.start)
            if target is not None:
                # Read back just before Start; the overview does not show the
                # dial, so the cached sheet value is updated here.
                self._ch._nav_cache["target_temperature"] = target
            await self._await_outcome(expect_running=True)

    async def adjust(self, temp_c: float) -> bool:
        """Move the dial of a running air conditioning to ``temp_c``.

        The app sends a dial change to the car by itself, so this costs one car
        request and needs no Start. True when the dial now shows the target;
        False when there was nothing to move: the climate is off, or runs as
        window heating alone (the app disables the dial). The held value then
        applies at the next Start.
        """
        target = snap_temperature(temp_c)
        async with self._on_sheet() as nodes:
            sheet = read_sheet(nodes)
            if not sheet.running or not self._ac_running(nodes, sheet):
                return False
            nodes = await self._apply_dial(nodes, target, starting=False)
            self._ch._nav_cache["target_temperature"] = target
            return True

    async def stop(self, *, window_heating_only: bool = False) -> None:
        async with self._on_sheet() as nodes:
            sheet = read_sheet(nodes)
            if not sheet.running:
                return
            if window_heating_only and self._ac_running(nodes, sheet):
                # The single Stop ends air conditioning too; a window-heating
                # stop must not silently switch the climate off.
                raise self._blocked(
                    "air conditioning is running with the window heating; the "
                    "app has one Stop for both, so stop the climate instead"
                )
            if sheet.stop is None or sheet.stop.tap_point is None:
                raise self._blocked("the Stop button is not available on the sheet")
            await self._tap_command(sheet.stop)
            await self._await_outcome(expect_running=False)

    @property
    def _strings(self) -> StringResources:
        return getattr(self._ch, "_app_strings", None) or {}

    # -- the sheet ------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def _on_sheet(self) -> AsyncIterator[list[UiNode]]:
        """Gate, open the sheet with one tap on the tile, and always come back."""
        await self._gate()
        nav = next(
            (n for n in self._ch.preset.nav_reads if n.name == "climate_detail"), None
        )
        if nav is None or not nav.path:
            raise self._blocked("the climate sheet path is not mapped")
        self._home = False
        walked = 0
        trips = self._ch._limit_trips
        try:
            nodes, cleared = await self._ch._dump_and_clear_overlays()
            if not cleared:
                raise self._blocked("a nag screen is up and did not clear; not tapping blind")
            # A refusal here has tapped nothing, so the finally block must not
            # navigate back (that would be an unneeded tap).
            self._home = True
            self._ch._require_limit_language(nodes)
            self._home = False
            if not read_sheet(nodes).present:
                tile = find_node_for(nodes, nav.path[0])
                if tile is None or tile.tap_point is None:
                    raise self._blocked("the climate tile is not on the current screen")
                await self._ch._t.tap(*tile.tap_point)
                walked = 1
                nodes = await self._screen(lambda n: read_sheet(n).present)
                if not read_sheet(nodes).present:
                    raise self._refused(nodes, "the Air Conditioning sheet")
            yield nodes
        except CompanionTransportError as err:
            raise self._blocked(str(err)) from err
        finally:
            if not self._home:
                # The picker adds a level; the app's own close control is used.
                await self._ch._return_to_overview(max(walked, 1) + 1)
        if self._ch._limit_trips != trips:
            # The limit alert arrived late and the walk back closed it: the
            # car refused the request after all.
            raise self._blocked(_LIMIT_REASON)

    async def _screen(self, done: Callable[[list[UiNode]], bool]) -> list[UiNode]:
        """Dump until the screen a tap should produce is there (bounded)."""
        nodes: list[UiNode] = []
        for _ in range(_SCREEN_TRIES):
            nodes, _cleared = await self._ch._dump_and_clear_overlays()
            if done(nodes):
                break
        return nodes

    async def _gate(self) -> None:
        """The channel's write gates, plus the climate-specific version map."""
        from .channel import _WRITE_MIN_INTERVAL_S  # noqa: PLC0415

        ch = self._ch
        if not ch.preset.writable:
            raise self._blocked("this brand's companion preset is read-only")
        try:
            if not ch._t.connected:
                await ch._t.connect()
            await ch._t.foreground_app(ch.preset.package)
            # Re-read on every command: an app update between polls must not
            # inherit the previous build's permission to tap.
            await ch._refresh_version_gate()
        except CompanionTransportError as err:
            raise self._blocked(str(err)) from err
        if not ch._version_ok or not app_version_covered(
            ch._live_app_version, CLIMATE_APP_VERSIONS
        ):
            raise self._blocked(
                f"climate commands are mapped for app {'/'.join(CLIMATE_APP_VERSIONS)}; "
                f"the phone has {ch._live_app_version or 'an unknown version'}. "
                "Reads still work."
            )
        # Rule 9: the dial is walked with geometry from the listed builds.
        if not app_version_listed(ch._live_app_version, CLIMATE_APP_VERSIONS):
            from .channel import CompanionAppVersionUnverified  # noqa: PLC0415

            raise CompanionAppVersionUnverified(ch._live_app_version)
        if ch._is_rate_limited():
            raise self._blocked("the channel is backed off after a rate limit; commands are paused")
        if ch._last_write_at is not None:
            since = ch._now() - ch._last_write_at
            if since < _WRITE_MIN_INTERVAL_S:
                raise self._blocked(
                    f"a command was sent {int(since)}s ago; the companion channel "
                    f"keeps at least {int(_WRITE_MIN_INTERVAL_S)}s between commands"
                )
        if ch._live_app_version not in CLIMATE_APP_VERSIONS:
            # Rule 9: the mode picker and the dial are walked with geometry from
            # the listed builds, so a newer one is refused before any tap.
            raise self._blocked(
                f"climate commands are mapped for app {'/'.join(CLIMATE_APP_VERSIONS)} "
                f"only; the phone has {ch._live_app_version}. Reads still work."
            )

    async def _select(self, nodes: list[UiNode], window_heating_only: bool) -> list[UiNode]:
        """Make Start start the requested function. Local choice only; nothing is sent."""
        sheet = read_sheet(nodes)
        if sheet.ac_toggle is not None or sheet.wh_toggle is not None:
            # Mk8 layout: two independent "what to start" switches.
            for toggle_rid, want in (
                ("air_conditioning_toggle", not window_heating_only),
                ("window_heating_toggle", window_heating_only),
            ):
                toggle = _find(nodes, toggle_rid, checkable=True)
                if toggle is None:
                    if want:
                        raise self._blocked(f"'{toggle_rid}' is not on the sheet")
                    continue
                if toggle.checked != want:
                    if toggle.tap_point is None:
                        raise self._blocked(f"'{toggle_rid}' cannot be tapped")
                    await self._ch._t.tap(*toggle.tap_point)
                    rid, wanted = toggle_rid, want
                    nodes = await self._screen(
                        lambda n: (t := _find(n, rid, checkable=True)) is not None
                        and t.checked == wanted
                    )
                    again = _find(nodes, toggle_rid, checkable=True)
                    if again is None or again.checked != want:
                        raise self._blocked(f"'{toggle_rid}' did not change")
            return nodes
        if sheet.pick is None:
            if window_heating_only:
                raise self._blocked("this car's sheet offers no window-heating-only mode")
            return nodes
        if not sheet.pick.enabled or not sheet.pick.clickable:
            # No chevron: the car has no selectable mode, so Start is AC.
            if window_heating_only:
                raise self._blocked("this car's sheet offers no window-heating-only mode")
            return nodes
        if not window_heating_only:
            shown = climate_mode_is_window_heating(sheet.pick_title, self._strings)
            if shown is False:
                # Air conditioning is the selected mode: tile, Start, done. The
                # picker opens only to switch to or from window heating alone.
                return nodes
            if shown is None:
                # An unrecognised title may be window heating alone: refuse
                # rather than start a function nobody asked for.
                raise self._blocked(
                    "the sheet's mode is not one this integration recognises; "
                    "Start was not pressed"
                )
        # "Select mode" lists exactly [Air conditioning, Window heating], in that
        # order (ClimaViewModel.onModeChangePressed). Choose by position and
        # verify by the chosen row's own title, so no translated word is needed.
        await self._ch._t.tap(*sheet.pick.tap_point)  # type: ignore[misc]
        picker = await self._screen(
            lambda n: len([r for r in n if r.checkable and r.clickable]) == 2
        )
        rows = [n for n in picker if n.checkable and n.clickable and n.tap_point]
        if len(rows) != 2 or read_sheet(picker).present:
            raise self._blocked("the mode picker did not show the two expected modes")
        row = rows[1 if window_heating_only else 0]
        row_title = next(
            (n.text for n in picker if n.text and row.bounds and _inside(n, row.bounds)), ""
        )
        if not row.checked:
            await self._ch._t.tap(*row.tap_point)  # type: ignore[misc]
            picker = await self._screen(lambda n: read_sheet(n).present)
        if not read_sheet(picker).present:
            # Already-selected row (or a picker that stays open): close it with
            # the app's own control, never Android BACK.
            up = next(
                (
                    n for spec in self._ch.preset.up_controls
                    for n in picker
                    if spec.resource_id and _rid_matches(n.resource_id, spec.resource_id)
                    and n.tap_point
                ),
                None,
            )
            if up is None:
                raise self._blocked("could not close the mode picker")
            await self._ch._t.tap(*up.tap_point)  # type: ignore[misc]
            picker = await self._screen(lambda n: read_sheet(n).present)
        sheet = read_sheet(picker)
        if not sheet.present or (row_title and sheet.pick_title != row_title):
            raise self._blocked("the requested mode is not selected on the sheet")
        return picker

    async def _apply_dial(
        self, nodes: list[UiNode], target: float, *, starting: bool = True,
    ) -> list[UiNode]:
        """Set the dial to ``target``; return the readback.

        ``starting`` False is a running air conditioning: there is no Start to
        check or press, and the dial change itself is the request.

        The dial is a snapping pager. A tap on a neighbouring label animates
        one step, and a touch during that animation stops it, so taps cannot
        be chained. The app sends the value the dial settles on, 1 s after it
        settles (and when the sheet closes), whether or not Start is pressed.
        So one step is one tap, and two steps are one slow drag that settles
        once; each gesture is one car request. A change needs at most
        ``_DIAL_MAX_GESTURES`` of them. Everything that could stop Start is
        checked before the first gesture, and the dial is read back after
        each one. A wrong reading is reported, never corrected: a correction
        would be another request, and Start would send a wrong value.
        """
        strings = self._strings
        current = read_dial(nodes, strings)[0]
        if current is None:
            raise self._blocked("could not read the temperature dial")
        if not dial_is_celsius(nodes, strings):
            # Maintainer rule 3: no dial walk without a known unit.
            raise self._blocked(
                f"the temperature dial shows labels outside the {DIAL_MIN_C:g}-"
                f"{DIAL_MAX_C:g} °C dial this integration knows; not changing it"
            )
        if current == target:
            return nodes
        self._dial_preflight(nodes, starting=starting)
        no_start = "; Start was not pressed" if starting else ""
        steps = round(abs(target - current) / DIAL_STEP_C)
        gestures = -(-steps // _DRAG_STEPS)
        if not 0 < steps <= _DIAL_MAX_STEPS or gestures > _DIAL_MAX_GESTURES:
            raise self._blocked(
                f"a change of {abs(target - current):g} °C needs {gestures} dial "
                f"moves, each one car request; at most "
                f"{_DIAL_MAX_GESTURES * _DRAG_STEPS * DIAL_STEP_C:g} °C at a time"
            )
        if steps > 1 and getattr(self._ch._t, "swipe", None) is None:
            raise self._blocked(
                "this connection cannot drag the dial, so a change of more than "
                f"{DIAL_STEP_C:g} °C is not possible here; not changing it"
            )
        self._mark_write()
        up = target > current
        value = current
        moves = 0
        while value != target:
            move = min(round(abs(target - value) / DIAL_STEP_C), _DRAG_STEPS)
            await self._move_dial(nodes, up=up, steps=move)
            moves += 1
            # Past the app's 1 s debounce, then read the dial once.
            await self._sleep(_DIAL_FLUSH_S)
            nodes, _cleared = await self._ch._dump_and_clear_overlays()
            if self._ch._limit_on_screen(nodes):
                self._ch._trip_rate_limit()
                raise self._blocked(_LIMIT_REASON)
            landed = read_dial(nodes, strings)[0]
            expected = value + (move if up else -move) * DIAL_STEP_C
            if landed != expected:
                sent = "this change" if moves == 1 else f"these {moves} changes"
                raise self._blocked(
                    f"the temperature dial landed at "
                    f"{'an unreadable value' if landed is None else f'{landed:g} °C'}, "
                    f"not {expected:g} °C{no_start}. The app sends the dial to the "
                    f"car on its own, so {sent} reached the car; it was not "
                    "corrected, as that would cost another request"
                )
            value = expected
        return nodes

    async def _move_dial(self, nodes: list[UiNode], *, up: bool, steps: int) -> None:
        """One gesture: a tap on the neighbouring label, or a drag of ``steps``.

        Every position comes from the dump. The labels at the dial's edges are
        clipped by the screen, so the step width is taken from the edges the
        screen does not clip: the left edges of the centre and right labels,
        or the right edges of the left and centre labels.
        """
        _current, lower, higher = read_dial(nodes, self._strings)
        neighbour = higher if up else lower
        if neighbour is None or neighbour.tap_point is None:
            raise self._blocked("the next temperature step is not on the dial")
        t = self._ch._t
        if steps == 1:
            await t.tap(*neighbour.tap_point)
            return
        dial = _find(nodes, "clima_compose_view")
        centre = self._dial_centre(nodes)
        if dial is None or dial.bounds is None or centre is None or centre.bounds is None:
            raise self._blocked("could not measure the temperature dial")
        left, _top, right, _bottom = dial.bounds
        width = right - left
        if higher is not None and higher.bounds is not None:
            page = higher.bounds[0] - centre.bounds[0]
        elif lower is not None and lower.bounds is not None:
            page = centre.bounds[2] - lower.bounds[2]
        else:
            page = 0
        if not _DIAL_PAGE_MIN * width <= page <= _DIAL_PAGE_MAX * width:
            raise self._blocked(
                "the temperature dial's steps are not where this integration "
                "expects them; not changing it"
            )
        margin = int(width * _DRAG_MARGIN)
        distance = steps * page
        if distance > width - 2 * margin:
            raise self._blocked("the dial is too narrow to drag that far; not changing it")
        y = (centre.bounds[1] + centre.bounds[3]) // 2
        # Higher values sit to the right: they come to the centre when the
        # dial is dragged to the left.
        x1 = right - margin if up else left + margin
        x2 = x1 - distance if up else x1 + distance
        # Slow enough that the pager snaps to the nearest step instead of
        # flinging past it.
        duration_ms = max(_DRAG_MIN_MS, int(distance * 1000 / _DRAG_MAX_PX_S))
        await t.swipe(x1, y, x2, y, duration_ms)

    def _dial_centre(self, nodes: list[UiNode]) -> UiNode | None:
        """The label of the dial's current value (nearest the dial's centre)."""
        dial = _find(nodes, "clima_compose_view")
        if dial is None or dial.bounds is None:
            return None
        mid = (dial.bounds[0] + dial.bounds[2]) / 2
        labels = [
            n for n in nodes
            if n.text and n.bounds and _inside(n, dial.bounds)
            and dial_value(n.text, self._strings) is not None
        ]
        return min(
            labels, key=lambda n: abs((n.bounds[0] + n.bounds[2]) / 2 - mid),  # type: ignore[index]
            default=None,
        )

    def _dial_preflight(self, nodes: list[UiNode], *, starting: bool = True) -> None:
        """Refuse before the first dial tap unless Start will follow it.

        A dial change reaches the car whether or not Start is pressed, so
        every reason Start could be refused is checked first: the mode, the
        Start button and a request limit (the app build is pinned by ``_gate``).
        A running air conditioning (``starting`` False) has no Start to check;
        only the request limit applies.
        """
        if not starting:
            self._limit_preflight(nodes)
            return
        sheet = read_sheet(nodes)
        if sheet.ac_toggle is not None or sheet.wh_toggle is not None:
            mode_ok = (
                sheet.ac_toggle is not None and sheet.ac_toggle.checked
                and not (sheet.wh_toggle is not None and sheet.wh_toggle.checked)
            )
        elif sheet.pick is not None and sheet.pick.enabled and sheet.pick.clickable:
            mode_ok = climate_mode_is_window_heating(sheet.pick_title, self._strings) is False
        else:
            mode_ok = True  # no selectable mode: Start is air conditioning
        if not mode_ok:
            raise self._blocked(
                "the sheet's mode is not recognised as air conditioning; the "
                "temperature was not changed and Start was not pressed"
            )
        if sheet.start is None or not sheet.start.enabled or sheet.start.tap_point is None:
            raise self._blocked(
                "the Start button is not available on the sheet; the temperature "
                "was not changed"
            )
        self._limit_preflight(nodes)

    def _limit_preflight(self, nodes: list[UiNode]) -> None:
        ch = self._ch
        if ch._is_rate_limited():
            raise self._blocked("the channel is backed off after a rate limit; commands are paused")
        if ch._limit_on_screen(nodes):
            ch._trip_rate_limit()
            raise self._blocked(_LIMIT_REASON)

    def _check_ready(
        self,
        nodes: list[UiNode],
        window_heating_only: bool,
        mode_title: str,
        target: float | None,
    ) -> None:
        """Read the mode and the dial back; refuse Start on any difference."""
        sheet = read_sheet(nodes)
        if not sheet.present:
            raise self._blocked(
                "the Air Conditioning sheet closed before Start; Start was not pressed"
            )
        wanted = "window heating only" if window_heating_only else "air conditioning"
        wrong: list[str] = []
        if sheet.ac_toggle is not None or sheet.wh_toggle is not None:
            ac_on = sheet.ac_toggle is not None and sheet.ac_toggle.checked
            wh_on = sheet.wh_toggle is not None and sheet.wh_toggle.checked
            if ac_on == window_heating_only or wh_on != window_heating_only:
                wrong.append(f"a mode other than {wanted}")
        elif sheet.pick is not None:
            # _select verified the title against the chosen row; it must not
            # have changed since, and a recognised title must name the mode.
            # Air conditioning needs a recognised title: an unknown one may be
            # window heating alone.
            shown = climate_mode_is_window_heating(sheet.pick_title, self._strings)
            if sheet.pick_title != mode_title or (
                shown != window_heating_only
                and (shown is not None or not window_heating_only)
            ):
                wrong.append(f"a mode other than {wanted}")
        if target is not None:
            dial = read_dial(nodes, self._strings)[0]
            if dial != target:
                wrong.append(
                    f"{'no temperature' if dial is None else f'{dial:g} °C'}, "
                    f"not {target:g} °C"
                )
        if wrong:
            raise self._blocked(
                f"the sheet shows {' and '.join(wrong)} after setting it; "
                "Start was not pressed"
            )

    def _ac_shown(self, nodes: list[UiNode], sheet: ClimaSheet) -> bool | None:
        """While running: True for air conditioning, False for window heating
        alone, None when the sheet does not say."""
        desc = _find(nodes, "air_conditioning_description")
        if desc is not None:
            return climate_function_state(desc.text, self._strings)
        if _find(nodes, "window_heating_title") is not None:
            return True
        shown = climate_mode_is_window_heating(sheet.pick_title, self._strings)
        return None if shown is None else not shown

    def _ac_running(self, nodes: list[UiNode], sheet: ClimaSheet) -> bool:
        """While running, is it air conditioning (not window heating alone)?"""
        desc = _find(nodes, "air_conditioning_description")
        if desc is not None:
            return climate_function_state(desc.text, self._strings) is True
        # Pick layout. The automatic-window-heating row is only drawn beside the
        # air conditioning mode; otherwise the row's title names the mode.
        if _find(nodes, "window_heating_title") is not None:
            return True
        return climate_mode_is_window_heating(sheet.pick_title, self._strings) is not True

    async def _tap_command(self, node: UiNode) -> None:
        # Mark first so a transport failure after delivery still blocks a repeat.
        self._mark_write()
        # A tap is not readback: drop only the climate sheet's cached values,
        # so the overview tile (read on every poll) supplies the new state.
        # The readback refresh re-reads the climate sheet only (when opted in),
        # like a charge command, so it never walks every opted-in screen.
        for key in _CLIMATE_KEYS:
            self._ch._nav_cache.pop(key, None)
        self._ch._nav_only.add("climate_detail")
        await self._ch._t.tap(*node.tap_point)  # type: ignore[misc]

    async def _await_outcome(self, *, expect_running: bool) -> None:
        """Wait for the app to accept the request: it closes the sheet itself.

        A sheet that flips its CTA also counts. Anything else (the off-grid
        "air conditioning using battery?" question, an error) is left for the
        user: we never confirm a dialog that changes a vehicle setting.
        """
        nodes: list[UiNode] = []
        for _ in range(_OUTCOME_TRIES):
            nodes, _cleared = await self._ch._dump_and_clear_overlays()
            if has_anchor(nodes, self._ch.preset):
                self._home = True
                return
            sheet = read_sheet(nodes)
            if sheet.present and sheet.running == expect_running:
                return
            # Neither yet: the sheet is still animating closed, or the request
            # is in flight. Dump again; a dump itself takes about a second.
        if not read_sheet(nodes).present:
            raise self._refused(nodes, "a confirmation; it is not answered automatically")
        raise self._blocked("the app did not confirm the request")

    def _refused(self, nodes: list[UiNode], instead_of: str) -> Exception:
        """Say what kind of screen the app showed; pause on a request limit.

        When the car's daily request budget is used up, the app answers a tap
        with an alert ("Too many requests sent to the vehicle") instead of the
        screen. Repeating the tap cannot help until the car is started.
        """
        ch = self._ch
        on_screen = getattr(ch, "_limit_on_screen", None)
        limited = (
            on_screen(nodes) if callable(on_screen)
            else find_rate_limit_banner(nodes, ch.preset) is not None
        )
        if limited:
            ch._trip_rate_limit()
            return self._blocked(_LIMIT_REASON)
        # Never the screen's own text: it can carry places and notifications.
        if find_app_alert(nodes, self._strings):
            return self._blocked(f"the app showed its {DATA_UNAVAILABLE} alert instead of {instead_of}")
        if any(n.text.strip() or n.content_desc.strip() for n in nodes):
            return self._blocked(f"the app showed an unrecognised screen instead of {instead_of}")
        return self._blocked(f"the app did not show {instead_of}")

    def _mark_write(self) -> None:
        # Through the channel, so the wall-clock time is persisted too.
        self._ch._stamp_write()

    @staticmethod
    def _blocked(reason: str) -> Exception:
        from .channel import CompanionWriteBlocked  # noqa: PLC0415

        return CompanionWriteBlocked(reason)
