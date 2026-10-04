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
* The temperature dial is a pager of 15.5 (LO) … 30.0 (HI) °C in 0.5 steps.
  Tapping a neighbouring number scrolls one step; the app sends the new target
  to the car 1 s after the dial stops (debounced), idle or running.

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

from .screen import UiNode, _rid_matches, find_node_for, has_anchor
from .transport import CompanionTransportError

if TYPE_CHECKING:
    from .channel import CompanionChannel

# Commands are mapped against this build only. Reads keep the preset's own
# version set; a tap on another build's sheet is not assumed to be safe.
CLIMATE_APP_VERSIONS: tuple[str, ...] = ("4.3.2",)

DIAL_MIN_C = 15.5  # rendered "LO"
DIAL_MAX_C = 30.0  # rendered "HI"
DIAL_STEP_C = 0.5
_DIAL_TEXT_RE = re.compile(r"-?\d{1,2}(?:[.,]\d)?|LO|HI", re.I)
# The app debounces dial changes by 1000 ms before it sends them.
_DIAL_FLUSH_S = 1.2
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


def dial_value(raw: str) -> float | None:
    """One dial label as °C: "21.5", "22", "LO" (15.5) or "HI" (30.0)."""
    text = raw.strip()
    if text.upper() == "LO":
        return DIAL_MIN_C
    if text.upper() == "HI":
        return DIAL_MAX_C
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def read_dial(
    nodes: list[UiNode],
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
            if n.text and n.bounds and _DIAL_TEXT_RE.fullmatch(n.text.strip())
            and _inside(n, dial.bounds) and dial_value(n.text) is not None
        ),
        key=lambda n: (n.bounds[0] + n.bounds[2]) / 2,  # type: ignore[index]
    )
    if not labels:
        return None, None, None
    centre = min(labels, key=lambda n: abs((n.bounds[0] + n.bounds[2]) / 2 - centre_x))  # type: ignore[index]
    i = labels.index(centre)
    lower = labels[i - 1] if i > 0 else None
    higher = labels[i + 1] if i + 1 < len(labels) else None
    return dial_value(centre.text), lower, higher


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

    async def start(self, *, window_heating_only: bool = False) -> None:
        async with self._on_sheet() as nodes:
            sheet = read_sheet(nodes)
            if sheet.running:
                # Already on: Start is not on screen, and Stop must not be
                # pressed for a start request. Nothing to send.
                return
            nodes = await self._select(nodes, window_heating_only)
            sheet = read_sheet(nodes)
            if sheet.start is None or not sheet.start.enabled or sheet.start.tap_point is None:
                raise self._blocked("the Start button is not available on the sheet")
            await self._tap_command(sheet.start)
            await self._await_outcome(expect_running=True)

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

    async def set_temperature(self, temp_c: float) -> float:
        """Step the dial to ``temp_c`` (snapped to the app's 0.5 grid) and read it back."""
        target = snap_temperature(temp_c)
        async with self._on_sheet() as nodes:
            current, lower, higher = read_dial(nodes)
            if current is None:
                raise self._blocked("could not read the temperature dial")
            if current == target:
                return target
            self._mark_write()
            for _ in range(int((DIAL_MAX_C - DIAL_MIN_C) / DIAL_STEP_C) + 1):
                neighbour = higher if target > current else lower
                if neighbour is None or neighbour.tap_point is None:
                    raise self._blocked("the next temperature step is not on the dial")
                await self._ch._t.tap(*neighbour.tap_point)
                before = current
                nodes = await self._screen(lambda n: read_dial(n)[0] not in (None, before))
                moved, lower, higher = read_dial(nodes)
                if moved is None or moved == current:
                    # Locked while running on cars that only take a target
                    # temperature at start (GetIsTemperatureControlDisabled).
                    raise self._blocked("the temperature dial did not move")
                current = moved
                if current == target:
                    break
            if current != target:
                raise self._blocked(f"the dial stopped at {current} °C, not {target} °C")
            # Keep the sheet open past the app's 1 s debounce so the app sends
            # the new target itself, then confirm the dial still shows it.
            await self._sleep(_DIAL_FLUSH_S)
            nodes, _cleared = await self._ch._dump_and_clear_overlays()
            final, _lower, _higher = read_dial(nodes)
            if final != target:
                raise self._blocked(f"the dial reads {final} °C after the change, not {target} °C")
            self._ch._nav_cache["target_temperature"] = target
            return target

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
        try:
            nodes, cleared = await self._ch._dump_and_clear_overlays()
            if not cleared:
                raise self._blocked("a nag screen is up and did not clear; not tapping blind")
            if not read_sheet(nodes).present:
                tile = find_node_for(nodes, nav.path[0])
                if tile is None or tile.tap_point is None:
                    raise self._blocked("the climate tile is not on the current screen")
                await self._ch._t.tap(*tile.tap_point)
                walked = 1
                nodes = await self._screen(lambda n: read_sheet(n).present)
                if not read_sheet(nodes).present:
                    raise self._blocked("could not open the Air Conditioning sheet")
            yield nodes
        except CompanionTransportError as err:
            raise self._blocked(str(err)) from err
        finally:
            if not self._home:
                # The picker adds a level; the app's own close control is used.
                await self._ch._return_to_overview(max(walked, 1) + 1)

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
        if not ch._version_ok or ch._live_app_version not in CLIMATE_APP_VERSIONS:
            raise self._blocked(
                f"climate commands are mapped for app {'/'.join(CLIMATE_APP_VERSIONS)} "
                f"only; the phone has {ch._live_app_version or 'an unknown version'}. "
                "Reads still work."
            )
        if ch._is_rate_limited():
            raise self._blocked("the channel is backed off after a rate limit; commands are paused")
        if ch._last_write_at is not None:
            since = ch._now() - ch._last_write_at
            if since < _WRITE_MIN_INTERVAL_S:
                raise self._blocked(
                    f"a command was sent {int(since)}s ago; the companion channel "
                    f"keeps at least {int(_WRITE_MIN_INTERVAL_S)}s between commands"
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
        from .presets import coerce  # noqa: PLC0415

        if not window_heating_only and coerce(
            "clima_mode_window_heating", sheet.pick_title
        ) is not True:
            # Air conditioning is the selected mode: tile, Start, done. The
            # picker opens only to switch to or from window heating alone.
            return nodes
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

    def _ac_running(self, nodes: list[UiNode], sheet: ClimaSheet) -> bool:
        """While running, is it air conditioning (not window heating alone)?"""
        from .presets import coerce  # noqa: PLC0415

        desc = _find(nodes, "air_conditioning_description")
        if desc is not None:
            return coerce("clima_function_state", desc.text) is True
        # Pick layout. The automatic-window-heating row is only drawn beside the
        # air conditioning mode; otherwise the row's title names the mode.
        if _find(nodes, "window_heating_title") is not None:
            return True
        return coerce("clima_mode_window_heating", sheet.pick_title) is not True

    async def _tap_command(self, node: UiNode) -> None:
        # Mark first so a transport failure after delivery still blocks a repeat.
        self._mark_write()
        # A tap is not readback: drop only the climate sheet's cached values,
        # so the overview tile (read on every poll) supplies the new state.
        # Nothing else is invalidated, so a command never triggers a walk of
        # every opted-in screen.
        for key in _CLIMATE_KEYS:
            self._ch._nav_cache.pop(key, None)
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
            raise self._blocked(
                "the app showed another screen after the tap (for example "
                "'air conditioning using battery?'); it is not confirmed "
                "automatically — answer it in the app"
            )
        raise self._blocked("the app did not confirm the request")

    def _mark_write(self) -> None:
        self._ch._last_write_at = self._ch._now()

    @staticmethod
    def _blocked(reason: str) -> Exception:
        from .channel import CompanionWriteBlocked  # noqa: PLC0415

        return CompanionWriteBlocked(reason)
