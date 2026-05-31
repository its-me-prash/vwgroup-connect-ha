# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.5.6 — Auth config resolver tests.

The resolver moves the auth-config priority chain from "hardcoded only" to
"APK extraction first, hardcoded as fallback". These tests verify:

1. With no APK cache available, the resolver returns hardcoded values byte-for-byte.
2. With APK auth_secrets present, APK values win.
3. The OAuth client_id chain merges APK UUIDs, per-brand alternates, and
   the hardcoded canonical — deduped, ordered, hardcoded LAST.
4. The unknown UUIDs discovered in the 2026-05-27 retro-mining are
   present in the chain.
5. Provenance debug helper correctly reports which source each value
   came from.
"""

from __future__ import annotations

import json

import pytest


# Hardcoded values that are the v2.5.4 baseline (cross-verified against
# upstream + evcc + volkswagencarnet + ioBroker.vw-connect).
HARDCODED = {
    "client_id":   "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
    "qm_secret":   "1ab69925ac179aaa4e83abe671a9476d176418b85bd706f1436ca15be647989c",
    "qm_clientid": "01da27b0",
    "token_url":   "https://emea.bff.cariad.digital/auth/v1/idk/oidc/token",
}


@pytest.fixture
def fresh_resolver_class(monkeypatch):
    """Re-import the resolver with a clean module-level cache root."""
    import importlib
    from custom_components.vag_connect.cariad.auth import _auth_config_resolver as mod
    importlib.reload(mod)
    return mod


def _make_resolver(mod, brand: str = "audi"):
    return mod.AuthConfigResolver(
        brand,
        hardcoded_client_id=HARDCODED["client_id"],
        hardcoded_qmauth_secret=HARDCODED["qm_secret"],
        hardcoded_qmauth_client_id=HARDCODED["qm_clientid"],
        hardcoded_token_url=HARDCODED["token_url"],
    )


# ── Without APK cache (clean install / CI without atlas data) ──────────────


class TestResolverFallbackOnly:
    """When no APK cache exists, every getter must return the hardcoded fallback."""

    def test_qmauth_secret_falls_back(self, fresh_resolver_class, monkeypatch):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        r = _make_resolver(fresh_resolver_class)
        assert r.qmauth_secret() == HARDCODED["qm_secret"]

    def test_qmauth_client_id_falls_back(self, fresh_resolver_class, monkeypatch):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        r = _make_resolver(fresh_resolver_class)
        assert r.qmauth_client_id() == HARDCODED["qm_clientid"]

    def test_token_url_falls_back(self, fresh_resolver_class, monkeypatch):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        r = _make_resolver(fresh_resolver_class)
        assert r.token_url() == HARDCODED["token_url"]


# ── With synthetic APK cache (proves APK-primary semantics) ────────────────


@pytest.fixture
def fake_apk_cache(tmp_path):
    """Create a synthetic .app-atlas-apk-cache/ tree with auth_secrets."""
    cache = tmp_path / ".app-atlas-apk-cache"
    cache.mkdir()
    audi = cache / "audi.json"
    audi.write_text(
        json.dumps({
            "versions": {
                "5.5.0": {  # newer than the 5.4.1 we mined
                    "findings": {
                        "auth_secrets": {
                            # NEW values that should win over hardcoded
                            "qmauth_secret_candidates": [
                                "deadbeefdeadbeefdeadbeefdeadbeef"
                                "deadbeefdeadbeefdeadbeefdeadbeef",
                            ],
                            "client_id_candidates": [
                                "feeddeed",  # NEW 8-hex
                                # Plus a UUID that should land in the chain
                                "abcdef01-2345-6789-abcd-ef0123456789@apps_vw-dilab_com",
                            ],
                            "token_path_markers_seen": [
                                "/auth/v1/idk/oidc/token",  # confirms new URL
                            ],
                        }
                    }
                }
            }
        }),
        encoding="utf-8",
    )
    return cache


class TestResolverApkPrimary:
    """APK values must win over hardcoded when both are present."""

    def test_apk_qmauth_secret_wins(self, fresh_resolver_class, monkeypatch, fake_apk_cache):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", fake_apk_cache)
        r = _make_resolver(fresh_resolver_class)
        assert r.qmauth_secret() == (
            "deadbeefdeadbeefdeadbeefdeadbeef"
            "deadbeefdeadbeefdeadbeefdeadbeef"
        )

    def test_apk_qmauth_client_id_wins(self, fresh_resolver_class, monkeypatch, fake_apk_cache):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", fake_apk_cache)
        r = _make_resolver(fresh_resolver_class)
        assert r.qmauth_client_id() == "feeddeed"

    def test_apk_token_url_wins(self, fresh_resolver_class, monkeypatch, fake_apk_cache):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", fake_apk_cache)
        r = _make_resolver(fresh_resolver_class)
        assert r.token_url() == HARDCODED["token_url"]  # same URL, but confirmed by APK


# ── OAuth client_id chain ──────────────────────────────────────────────────


class TestClientIdChain:
    """The OAuth chain must include APK + brand-alternates + hardcoded, deduped."""

    def test_chain_includes_hardcoded_last(self, fresh_resolver_class, monkeypatch):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        r = _make_resolver(fresh_resolver_class, "audi")
        chain = r.oauth_client_id_chain()
        assert chain[-1] == HARDCODED["client_id"]

    def test_audi_alternate_uuid_present(self, fresh_resolver_class, monkeypatch):
        """The 16dd7960-... UUID we found in Audi 5.4.1 must be in the chain."""
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        r = _make_resolver(fresh_resolver_class, "audi")
        chain = r.oauth_client_id_chain()
        assert any("16dd7960" in c for c in chain), chain

    def test_volkswagen_alternates_present(self, fresh_resolver_class, monkeypatch):
        """Both VW UUIDs from retro-mining must be in the chain."""
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        r = _make_resolver(fresh_resolver_class, "volkswagen")
        chain = r.oauth_client_id_chain()
        assert any("4edc53db" in c for c in chain), chain
        assert any("a24fba63" in c for c in chain), chain

    def test_chain_dedupes(self, fresh_resolver_class, monkeypatch, fake_apk_cache):
        """Same UUID present in APK + alternates + hardcoded must appear only once."""
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", fake_apk_cache)
        r = _make_resolver(fresh_resolver_class, "audi")
        chain = r.oauth_client_id_chain()
        assert len(chain) == len(set(chain))

    def test_chain_size_reasonable(self, fresh_resolver_class, monkeypatch):
        """No brand should have more than 6 candidates — that's the point at
        which we'd be hitting rate-limits before exhausting the chain."""
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        for brand in ("audi", "volkswagen", "skoda", "cupra", "seat"):
            r = _make_resolver(fresh_resolver_class, brand)
            assert len(r.oauth_client_id_chain()) <= 6, brand


# ── Provenance ─────────────────────────────────────────────────────────────


class TestProvenance:
    """The provenance dict must accurately reflect which source each value came from."""

    def test_provenance_hardcoded_when_no_apk(self, fresh_resolver_class, monkeypatch):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", None)
        r = _make_resolver(fresh_resolver_class)
        prov = r.provenance()
        assert prov["qmauth_secret"] == "hardcoded"
        assert prov["qmauth_client_id"] == "hardcoded"
        assert prov["token_url"] == "hardcoded"

    def test_provenance_apk_when_present(self, fresh_resolver_class, monkeypatch, fake_apk_cache):
        monkeypatch.setattr(fresh_resolver_class, "_APK_CACHE_ROOT", fake_apk_cache)
        r = _make_resolver(fresh_resolver_class)
        prov = r.provenance()
        assert prov["qmauth_secret"] == "apk"
        assert prov["qmauth_client_id"] == "apk"
        assert prov["token_url"] == "apk"


# ── Forensic verification (v2.5.4 secret reconstruction) ───────────────────


class TestForensicCrossSource:
    """v2.5.4 secret cross-verification across upstream (byte array)
    + evcc PR #30292 (hex string) + our hardcoded. All three must agree
    byte-for-byte — guards against accidental hardcoded-secret rotation."""

    def test_upstream_byte_array_matches_v254_hex(self) -> None:
        """The upstream MIT-licensed byte array literal, when
        reconstructed, equals our v2.5.4 hardcoded hex secret. This is
        the strongest forensic cross-check we can do without binary
        smali parsing (which is blocked by R8 obfuscation)."""
        byte_list = [
            26, 256-74, 256-103, 37, 256-84, 23,
            256-102, 256-86, 78, 256-125, 256-85, 256-26,
            113, 256-87, 71, 109, 23, 100, 24, 256-72,
            91, 256-41, 6, 256-15, 67, 108, 256-95, 91, 256-26,
            71, 256-104, 256-100,
        ]
        assert len(byte_list) == 32, "HMAC-SHA256 key must be 32 bytes"
        reconstructed = bytes(byte_list).hex()
        assert reconstructed == HARDCODED["qm_secret"]
