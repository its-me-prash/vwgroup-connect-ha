"""Run a live, read-only EU Data Act portal login check.

Set ``VAG_EMAIL`` and ``VAG_PASSWORD`` in the environment before running.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import aiohttp

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    _safe_url,
)

_LOGGER_NAME = "custom_components.vag_connect.cariad.auth._eu_data_act"
_HTTP_LOGGER_NAME = f"{_LOGGER_NAME}.http"


def _http_trace_config() -> aiohttp.TraceConfig:
    trace = aiohttp.TraceConfig()
    logger = logging.getLogger(_HTTP_LOGGER_NAME)

    def log_response(method: str, url: object, response: aiohttp.ClientResponse) -> None:
        logger.debug(
            "HTTP %s %s -> %d content-type=%s content-length=%s",
            method,
            _safe_url(str(url)),
            response.status,
            response.headers.get("Content-Type", "unknown"),
            response.content_length,
        )

    async def on_request_end(session, trace_context, params) -> None:
        log_response(params.method, params.url, params.response)

    async def on_request_redirect(session, trace_context, params) -> None:
        log_response(params.method, params.url, params.response)

    trace.on_request_end.append(on_request_end)
    trace.on_request_redirect.append(on_request_redirect)
    return trace


async def _run(
    email: str,
    password: str,
    brand: str,
    country: str,
    language: str,
    http_trace: bool,
) -> None:
    trace_configs = [_http_trace_config()] if http_trace else []
    async with aiohttp.ClientSession(trace_configs=trace_configs) as session:
        portal = EUDataActConnector(
            session,
            brand=brand,
            country=country,
            language=language,
        )
        await portal.login(email, password)
        vins = await portal.list_vehicle_vins()

    if vins:
        suffixes = ", ".join(f"...{vin[-4:]}" for vin in vins)
        print(f"Portal login and vehicle-list request succeeded ({len(vins)} vehicle(s)).")
        print(f"Vehicles: {suffixes}")
    else:
        print("Portal login succeeded, but the portal returned no vehicles.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check a real, read-only EU Data Act portal login."
    )
    parser.add_argument("--brand", default="volkswagen")
    parser.add_argument("--country", default="de")
    parser.add_argument("--language", default="de")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable sanitized debug logs for the EU Data Act connector.",
    )
    parser.add_argument(
        "--http-trace",
        action="store_true",
        help="Log status and safe metadata for each HTTP response (not its body).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    if args.debug:
        logging.getLogger(_LOGGER_NAME).setLevel(logging.DEBUG)
    if args.http_trace:
        logging.getLogger(_HTTP_LOGGER_NAME).setLevel(logging.DEBUG)

    email = os.environ.get("VAG_EMAIL", "").strip()
    password = os.environ.get("VAG_PASSWORD", "")
    missing = [
        name
        for name, value in (("VAG_EMAIL", email), ("VAG_PASSWORD", password))
        if not value
    ]
    if missing:
        parser.error(f"set required environment variable(s): {', '.join(missing)}")

    asyncio.run(
        _run(
            email,
            password,
            args.brand,
            args.country,
            args.language,
            args.http_trace,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
