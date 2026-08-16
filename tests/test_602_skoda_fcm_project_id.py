# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#602 / v3.2.2 — Škoda FCM registration uses the project SLUG, not the number.

``firebase-messaging`` keys the FCM installation + registration URLs on
``project_id`` (``.../projects/{project_id}/installations``). The Firebase
project id is the SLUG ``myskoda-ng``; ``678067506455`` is the sender/project
*number*. Conflating them made every registration fail with "Unable to register
with fcm" (a Škoda tester's log). All four values are verbatim from the MySkoda
8.15.0 APK res/values/strings.xml.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.push import skoda_mqtt as sm


def test_project_id_is_the_slug_not_the_number():
    assert sm._FCM_PROJECT_ID == "myskoda-ng"
    # The classic conflation — guard so it can never be re-set to the number.
    assert sm._FCM_PROJECT_ID != sm._FCM_SENDER_ID
    assert not sm._FCM_PROJECT_ID.isdigit()


def test_other_fcm_values_match_the_live_apk():
    assert sm._FCM_SENDER_ID == "678067506455"
    assert sm._FCM_API_KEY == "AIzaSyBlJdDfVR6ltRhKpA87F3SmCe2hHqhyEd8"
    assert sm._FCM_APP_ID == "1:678067506455:android:4afca86c91d6d4c235bb52"
    assert sm._FCM_PACKAGE == "cz.skodaauto.myskoda"


def test_register_config_receives_project_id_first():
    # FcmRegisterConfig(project_id, app_id, api_key, messaging_sender_id) — the
    # first positional arg must be the slug, or the install URL 404s.
    from firebase_messaging import FcmRegisterConfig

    cfg = FcmRegisterConfig(
        sm._FCM_PROJECT_ID, sm._FCM_APP_ID, sm._FCM_API_KEY, sm._FCM_SENDER_ID
    )
    assert cfg.project_id == "myskoda-ng"
    assert cfg.messaging_sender_id == "678067506455"
