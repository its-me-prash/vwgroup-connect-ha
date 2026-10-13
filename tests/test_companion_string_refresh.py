"""Resource refresh failures and the missing-table command quarantine."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.relay_transport import AgentRelayTransport
from custom_components.vag_connect.companion.transport import CompanionTransportError


class Phone:
    connected = True
    version = '4.6.4'
    paths = ('/data/app/test/base.apk',)

    async def current_app_version(self, package):
        return self.version

    async def app_resource_paths(self, package):
        return self.paths

    async def foreground_app(self, package):
        pass


def channel(phone):
    return CompanionChannel(phone, PRESETS['volkswagen'], time_fn=lambda: 10000)


@pytest.mark.asyncio
async def test_failed_getter_preserves_previous_table():
    phone = Phone()
    phone.battery_strings = AsyncMock(side_effect=CompanionTransportError('failed'))
    ch = channel(phone)
    ch._app_strings = {'alert_daily_power_budget_title': {'Budget exhausted'}}
    await ch._refresh_version_gate()
    assert ch._app_strings == {'alert_daily_power_budget_title': {'Budget exhausted'}}


@pytest.mark.asyncio
async def test_fetch_only_on_version_or_split_change():
    phone = Phone()
    phone.battery_strings = AsyncMock(return_value={'key': {'label'}})
    ch = channel(phone)
    await ch._refresh_version_gate()
    ch._now = lambda: 20000
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 1
    phone.paths += ('/data/app/test/split_config.fr.apk',)
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 2
    phone.version = '4.6.5'
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['start_charging', 'sync_vehicle'])
async def test_relay_unknown_language_refuses_without_taps(action):
    broker = AsyncMock()
    broker.online = True
    async def command(verb, *args, **kwargs):
        if verb == 'app_version':
            return '4.6.4'
        if verb == 'dump_ui':
            # The overview (its anchor is up), in a language the fallback
            # does not cover: refused there, before any tap.
            return (
                '<hierarchy><node resource-id="rangeTile" bounds="[53,808][508,1254]" />'
                '<node resource-id="vwd_title" text="Recharge" /></hierarchy>'
            )
        assert verb in ('foreground', 'is_foreground')
    broker.command.side_effect = command
    phone = AgentRelayTransport(broker)
    phone._device = True
    ch = channel(phone)
    with pytest.raises(HomeAssistantError) as exc:
        await ch._command_gate(action, probe=action == 'sync_vehicle')
    assert exc.value.translation_key == 'companion_limit_language_unavailable'


@pytest.mark.asyncio
async def test_failed_fetch_reconnects_and_screen_read_continues():
    phone = Phone()
    phone.connect = AsyncMock(side_effect=lambda: setattr(phone, 'connected', True))
    async def broken_getter(package):
        phone.connected = False
        raise CompanionTransportError('shell failed')
    phone.battery_strings = AsyncMock(side_effect=broken_getter)
    phone.dump_ui = AsyncMock(return_value=(
        '<hierarchy><node resource-id="rangeTile" bounds="[53,808][508,1254]" />'
        '<node text="Recharge" /></hierarchy>'
    ))
    ch = channel(phone)
    assert isinstance(await ch.read(), dict)
    phone.connect.assert_awaited_once()
    phone.dump_ui.assert_awaited_once()
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 1


@pytest.mark.asyncio
async def test_empty_fetch_keeps_previous_table():
    phone = Phone()
    phone.battery_strings = AsyncMock(return_value={})
    ch = channel(phone)
    ch._app_strings = {'alert_daily_power_budget_title': {'Budget exhausted'}}
    await ch._refresh_version_gate()
    assert ch._app_strings['alert_daily_power_budget_title'] == {'Budget exhausted'}


@pytest.mark.parametrize('label', ['Recharge', 'Laden', 'Carga', ''])
def test_unknown_or_ambiguous_labels_refuse(label):
    from custom_components.vag_connect.companion.screen import parse_ui_dump
    with pytest.raises(HomeAssistantError):
        channel(Phone())._require_limit_language(parse_ui_dump(
            f'<hierarchy><node resource-id="vwd_title" text="{label}" /></hierarchy>'
        ))


@pytest.mark.parametrize('label', ['Charging', 'Klimatisierung', 'Climatización'])
def test_supported_label_allows_fallback(label):
    from custom_components.vag_connect.companion.screen import parse_ui_dump
    channel(Phone())._require_limit_language(parse_ui_dump(
        f'<hierarchy><node resource-id="vwd_title" text="{label}" /></hierarchy>'
    ))


@pytest.mark.asyncio
async def test_climate_refuses_unknown_language_before_tile_tap():
    from custom_components.vag_connect.companion.climate import ClimateController
    phone = Phone()
    phone.battery_strings = AsyncMock(return_value={})
    phone.dump_ui = AsyncMock(return_value='<hierarchy><node resource-id="vwd_title" text="Recharge" /></hierarchy>')
    phone.tap = AsyncMock()
    ch = channel(phone)
    with pytest.raises(HomeAssistantError):
        await ClimateController(ch).start()
    phone.tap.assert_not_awaited()


def _foreign_nodes():
    from custom_components.vag_connect.companion.screen import parse_ui_dump
    return parse_ui_dump('<hierarchy><node resource-id="vwd_title" text="Recharge" /></hierarchy>')


@pytest.mark.asyncio
async def test_stale_table_after_new_split_failure_does_not_authorise_writes():
    phone = Phone()
    phone.battery_strings = AsyncMock(return_value={'key': {'label'}})
    ch = channel(phone)
    await ch._refresh_version_gate()
    ch._require_limit_language(_foreign_nodes())  # current table: allowed
    phone.paths += ('/data/app/test/split_config.fr.apk',)
    phone.battery_strings = AsyncMock(side_effect=CompanionTransportError('failed'))
    await ch._refresh_version_gate()
    assert ch._app_strings == {'key': {'label'}}  # still serves reads
    with pytest.raises(HomeAssistantError):
        ch._require_limit_language(_foreign_nodes())


@pytest.mark.asyncio
async def test_failed_extraction_retries_with_backoff():
    phone = Phone()
    phone.battery_strings = AsyncMock(side_effect=CompanionTransportError('failed'))
    ch = channel(phone)
    clock = [1000.0]
    ch._now = lambda: clock[0]
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 1
    clock[0] += 899
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 1  # inside the 15 min backoff
    clock[0] += 2
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 2
    clock[0] += 3599
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 2  # second backoff is 1 h
    clock[0] += 2
    phone.battery_strings = AsyncMock(return_value={'key': {'label'}})
    await ch._refresh_version_gate()
    assert ch._strings_current()
    await ch._refresh_version_gate()
    assert phone.battery_strings.await_count == 1  # success: no further fetches
