# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resource table variants and the direct/Bridge extraction contract."""
from __future__ import annotations

import base64
import gzip
import struct

import pytest
from hypothesis import given, strategies as st

from custom_components.vag_connect.companion.resources import extract_battery_strings
from custom_components.vag_connect.companion.transport import NetworkAdbTransport

KEY = "acc_vehicle_tab_range_tile_value_petrol_level"


def pool(text, utf8):
    if utf8:
        raw = text.encode("utf-8")

        def length(n):
            return bytes([n]) if n < 128 else bytes([0x80 | (n >> 8), n & 255])

        raw = length(len(text)) + length(len(raw)) + raw + b"\0"
    else:
        raw = struct.pack("<H", len(text)) + text.encode("utf-16le") + b"\0\0"
    raw += bytes(-len(raw) % 4)
    return struct.pack("<HHIIIIII", 1, 28, 32 + len(raw), 1, 0, 0x100 if utf8 else 0, 32, 0) + bytes(4) + raw


def table(text="Fuel level: %s per cent", utf8=True, flags=0):
    # Minimal standard Android resource table, with ONE independently named
    # string entry; no proprietary APK/binary fixture is distributed.
    global_pool, type_pool, key_pool = pool(text, utf8), pool("string", utf8), pool(KEY, utf8)
    offsets = struct.pack("<I", 0)  # offset zero also encodes sparse index 0
    entry = struct.pack("<HHIHBBI", 8, 0, 0, 8, 0, 3, 0)
    resource_type = struct.pack("<HHIBBHII", 0x201, 48, 68, 1, flags, 0, 1, 52) + struct.pack("<I", 28) + bytes(24) + offsets + entry
    package = bytearray(288)
    size = len(package) + len(type_pool) + len(key_pool) + len(resource_type)
    struct.pack_into("<HHII", package, 0, 0x200, 288, size, 0x7f)
    struct.pack_into("<I", package, 268, 288)
    struct.pack_into("<I", package, 276, 288 + len(type_pool))
    body = global_pool + package + type_pool + key_pool + resource_type
    return struct.pack("<HHII", 2, 12, 12 + len(body), 1) + body


@pytest.mark.parametrize("utf8", [True, False])
@pytest.mark.parametrize("flags", [0, 1, 2])
def test_resource_table_encodings_and_offset_formats(utf8, flags):
    label = "É" * 80 + " %s"
    assert extract_battery_strings(table(label, utf8, flags)) == {KEY: {label}}


@given(st.binary(max_size=1024))
def test_arbitrary_resource_bytes_never_raise(data):
    assert isinstance(extract_battery_strings(data), dict)


@pytest.mark.asyncio
async def test_transport_reads_language_splits_and_skips_native_density_splits():
    class Transport(NetworkAdbTransport):
        def __init__(self):
            super().__init__("unused", 5555, "unused")
            self.commands = []

        async def shell(self, cmd, timeout_s=10.0):
            self.commands.append(cmd)
            if cmd.startswith("pm path"):
                return "\n".join("package:/data/app/app/" + p for p in (
                    "base.apk", "split_config.fr.apk", "split_config.arm64_v8a.apk", "split_config.xxhdpi.apk"))
            label = "Texte %s" if "split_config.fr" in cmd else "Fuel level: %s per cent"
            return base64.b64encode(gzip.compress(table(label))).decode()

    transport = Transport()
    assert await transport.battery_strings("com.volkswagen.weconnect") == {
        KEY: {"Fuel level: %s per cent", "Texte %s"}}
    assert len(transport.commands) == 3


@pytest.mark.asyncio
async def test_missing_decoder_commands_do_not_produce_labels():
    class Transport(NetworkAdbTransport):
        async def shell(self, cmd, timeout_s=10.0):
            return "package:/data/app/app/base.apk" if cmd.startswith("pm path") else "unzip: not found"

    transport = Transport("unused", 5555, "unused")
    assert await transport.battery_strings("com.volkswagen.weconnect") == {}
