# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1963 / #1981 — the map node's label differs by app LANGUAGE, not version.

Two real dumps of the **same** app version 4.8.1 sit behind this file:

* ``fixtures/companion_parking/map_481.xml`` — contributed English dump,
  where the map carries ``content-desc="Google Map"``.
* The ten non-empty ``content-desc`` values a reporter pasted into #1981 from
  a German phone (Galaxy S10+, Android 12, phone and app both German), where
  the very same element reads ``Google Maps``.

Same version, two languages, two labels. The step's pattern was anchored on
``Google\\s*Map$``, so the plural form never matched and the walk stopped with
"nav step 'open_parking_marker' is not on the current screen" — which is what
the reporter saw while the marker was plainly on his screen.

The English half of every assertion below reads the fixture rather than a
transcription; only the German labels are typed out, because a comment is
where they came from.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import (
    parse_ui_dump,
    tap_point_for,
)

VW = PRESETS['volkswagen']
PARKING = next(n for n in VW.nav_reads if n.name == 'parking_position')
# Picked by action rather than by index, so inserting a step cannot silently
# point this file at a different one.
STEP = next(s for s in PARKING.path if s.action == 'open_parking_marker')

MAP_481 = parse_ui_dump(
    (Path(__file__).parent / 'fixtures' / 'companion_parking' / 'map_481.xml')
    .read_text(encoding='utf-8')
)
# The English dump's own map element: full screen, clickable. Measured, not
# assumed — the German tree below reuses this geometry so that the label is
# the only thing that differs between the two cases.
MAP_NODE = next(n for n in MAP_481 if n.content_desc == 'Google Map')

# Verbatim from #1981. Ten values, in the order the reporter listed them.
GERMAN_LABELS = (
    'Google Maps',
    'Karteneinstellungen',
    'Fahrzeugstandort',
    'Ihr Standort',
    'Bottom sheet collapsed',
    'Schnellfilter',
    'Fahrzeug Tab',
    'Karte Tab',
    'Volkswagen entdecken Tab',
    'Profil Tab',
)


def _channel() -> CompanionChannel:
    return CompanionChannel(object(), VW, time_fn=lambda: 0)


def _german_tree():
    """His labels on nodes that are otherwise shaped like the English ones."""
    return [replace(MAP_NODE, content_desc=label) for label in GERMAN_LABELS]


def test_the_two_dumps_really_are_the_same_app_version():
    # The premise of this whole file. If the fixture is ever replaced by one
    # from another version, this test says so instead of the file quietly
    # testing something else.
    sources = (Path(__file__).parent / 'fixtures' / 'companion_parking'
               / 'sources.json').read_text(encoding='utf-8')
    assert '"4.8.1"' in sources


def test_english_dump_resolves_the_map_and_taps_inside_it():
    node = _channel()._step_node(MAP_481, STEP)
    assert node is MAP_NODE
    point = tap_point_for(node, STEP.tap_fraction)
    left, top, right, bottom = MAP_NODE.bounds
    assert point == (
        int(left + (right - left) * STEP.tap_fraction[0]),
        int(top + (bottom - top) * STEP.tap_fraction[1]),
    )
    # Inside the map's own box, which is the whole point of the fraction.
    assert left < point[0] < right and top < point[1] < bottom


def test_german_label_resolves_the_same_element():
    """The label is the only variable: same tree, plural form."""
    tree = [replace(n, content_desc='Google Maps')
            if n is MAP_NODE else n for n in MAP_481]
    node = _channel()._step_node(tree, STEP)
    assert node is not None, "'Google Maps' did not match the map element"
    assert node.bounds == MAP_NODE.bounds
    assert tap_point_for(node, STEP.tap_fraction) == tap_point_for(
        MAP_NODE, STEP.tap_fraction
    )


def test_his_full_german_label_set_matches_exactly_one_element():
    tree = _german_tree()
    node = _channel()._step_node(tree, STEP)
    assert node is not None and node.content_desc == 'Google Maps'
    matched = [n for n in tree
               if _channel()._step_node([n], STEP) is not None]
    assert [n.content_desc for n in matched] == ['Google Maps']


@pytest.mark.parametrize('labels', [
    [n.content_desc for n in MAP_481 if n.content_desc],
    list(GERMAN_LABELS),
])
def test_both_real_label_sets_contain_the_element(labels):
    # Guards against a future pattern that happens to pass one language only.
    tree = [replace(MAP_NODE, content_desc=label) for label in labels]
    assert _channel()._step_node(tree, STEP) is not None


@pytest.mark.parametrize('label', [
    'Google Maps Timeline',   # the anchor must still bite after widening
    'Open Google Maps',
    'Maps',
    'Map',
    'Karteneinstellungen',    # contains "Karte", is not the map
    'Map settings',
    'Karte Tab',
])
def test_neighbouring_labels_do_not_match(label):
    tree = [replace(MAP_NODE, content_desc=label)]
    assert _channel()._step_node(tree, STEP) is None


@pytest.mark.parametrize('labels', [
    [n.content_desc for n in MAP_481 if n.content_desc],
    list(GERMAN_LABELS),
])
def test_without_the_map_element_the_walk_stops(labels):
    # #1963's failure mode is the CORRECT behaviour when the element is truly
    # absent: stop rather than tap blind. Widening the pattern must not turn
    # that into a tap on some other node.
    tree = [replace(MAP_NODE, content_desc=label) for label in labels
            if label not in ('Google Map', 'Google Maps')]
    node = _channel()._step_node(tree, STEP)
    assert node is None or tap_point_for(node, STEP.tap_fraction) is None


def test_an_unavailable_map_element_is_not_a_tap_target():
    for change in ({'enabled': False}, {'bounds': (0, 0, 0, 0)}):
        tree = [replace(MAP_NODE, content_desc='Google Maps', **change)]
        node = _channel()._step_node(tree, STEP)
        assert node is None or tap_point_for(node, STEP.tap_fraction) in (
            None, (0, 0)
        )


def test_the_space_has_always_been_optional():
    """``Googlemaps`` matches, and that is inherited, not introduced.

    The pattern has used ``\\s*`` rather than ``\\s+`` since the step was
    written, so ``Googlemap`` matched before this fix too. Writing it down
    because it failed a negative control of mine: the control encoded an
    assumption I had not measured, and the measurement said the code was
    right and the control was wrong.
    """
    tree = [replace(MAP_NODE, content_desc='Googlemaps')]
    assert _channel()._step_node(tree, STEP) is not None


def test_the_fix_admits_exactly_two_more_labels():
    """Pins the blast radius: one real label, one harmless side effect."""
    import re
    before = r"^(?:Google\s*Map|Google\s*Karte)$"
    after = STEP.content_desc_re
    candidates = [
        'Google Map', 'Google Maps', 'Googlemap', 'Googlemaps',
        'Google Karte', 'GoogleKarte', 'Google Maps Timeline', 'Maps',
        'Map', 'Map settings', 'Karteneinstellungen', 'Karte Tab',
        'Open Google Maps', 'Google', 'maps',
        *[n.content_desc for n in MAP_481 if n.content_desc],
        *GERMAN_LABELS,
    ]
    gained = sorted({
        c for c in candidates
        if re.search(after, c, re.I) and not re.search(before, c, re.I)
    })
    assert gained == ['Google Maps', 'Googlemaps']
    # And nothing was lost — every label the old pattern accepted still works.
    lost = [c for c in candidates
            if re.search(before, c, re.I) and not re.search(after, c, re.I)]
    assert lost == []


# ---------------------------------------------------------------------------
# #968 — a THIRD real spelling, and it is not a whitespace variant.
#
# @Odatas attached a full dump set to #968 on 2026-10-23, fifteen days before
# the #1981 dump was asked for. Measured from that archive on 2026-11-07: his
# map screen carries `Google-Karte`, with a HYPHEN. The pattern's `\s*` matches
# whitespace only, so the #1963 fix does not help him.
#
# Nine of his ten labels are identical to the #1981 set, character for
# character. The ONE that differs is the Google attribution. So the label
# varies between two German phones on the same app version 4.8.1 — which rules
# out both version and language as the whole story, and points at whatever
# renders that attribution rather than at the VW app's own translation.
#
# His dump is not added as a fixture here: it is his data, and the one fixture
# this repository holds was a deliberate contribution with a sources.json
# entry. These ten labels are what the measurement produced.
ODATAS_LABELS = (
    'Google-Karte',
    'Karteneinstellungen',
    'Fahrzeugstandort',
    'Ihr Standort',
    'Bottom sheet collapsed',
    'Schnellfilter',
    'Fahrzeug Tab',
    'Karte Tab',
    'Volkswagen entdecken Tab',
    'Profil Tab',
)

#: The pattern before #1963, and the one #1963 shipped. Kept as literals so the
#: delta tests below state what each step added instead of re-deriving it.
_BEFORE_1963 = r"^(?:Google\s*Map|Google\s*Karte)$"
_AFTER_1963 = r"^(?:Google\s*Maps?|Google\s*Karte)$"


def test_odatas_label_resolves_the_map_element():
    """The hyphen form must match. RED before the fix, by one character class."""
    tree = [replace(MAP_NODE, content_desc='Google-Karte')]
    node = _channel()._step_node(tree, STEP)
    assert node is not None, "'Google-Karte' did not match the map element"
    assert tap_point_for(node, STEP.tap_fraction) == tap_point_for(
        MAP_NODE, STEP.tap_fraction
    )


def test_his_full_label_set_matches_exactly_one_element():
    tree = [replace(MAP_NODE, content_desc=label) for label in ODATAS_LABELS]
    matched = [n for n in tree
               if _channel()._step_node([n], STEP) is not None]
    assert [n.content_desc for n in matched] == ['Google-Karte']


def test_the_two_german_sets_differ_in_exactly_one_label():
    """The premise of this whole block, asserted rather than assumed.

    Both sets come from German phones on app 4.8.1. If a future edit makes
    them differ in more than the Google attribution, the reasoning above no
    longer holds and this test says so.
    """
    a, b = set(GERMAN_LABELS), set(ODATAS_LABELS)
    assert len(a) == len(b) == 10
    assert a - b == {'Google Maps'}
    assert b - a == {'Google-Karte'}


@pytest.mark.parametrize('labels', [
    [n.content_desc for n in MAP_481 if n.content_desc],
    list(GERMAN_LABELS),
    list(ODATAS_LABELS),
])
def test_all_three_real_label_sets_contain_the_element(labels):
    tree = [replace(MAP_NODE, content_desc=label) for label in labels]
    assert _channel()._step_node(tree, STEP) is not None


@pytest.mark.parametrize('label', [
    'Google-Karten-Einstellungen',   # the anchor must still bite
    'Googlemaps-Karte',
    'Google-',
    '-Karte',
    'Google - Karte Tab',
])
def test_hyphen_does_not_open_the_pattern_up(label):
    tree = [replace(MAP_NODE, content_desc=label)]
    assert _channel()._step_node(tree, STEP) is None


def test_each_step_added_only_what_it_was_for():
    """Two deltas, pinned separately, so neither step can be widened silently."""
    import re
    candidates = [
        'Google Map', 'Google Maps', 'Googlemap', 'Googlemaps',
        'Google Karte', 'GoogleKarte', 'Google-Karte', 'Google-Maps',
        'Google-Map', 'Google-karte', 'Googlekarte',
        'Google Maps Timeline', 'Open Google Maps', 'Maps', 'Map',
        'Map settings', 'Karteneinstellungen', 'Karte Tab',
        'Google-Karten-Einstellungen', 'Googlemaps-Karte',
        *[n.content_desc for n in MAP_481 if n.content_desc],
        *GERMAN_LABELS,
        *ODATAS_LABELS,
    ]

    def hits(pattern):
        return {c for c in candidates if re.search(pattern, c, re.I)}

    before, after_1963, now = (hits(_BEFORE_1963), hits(_AFTER_1963),
                               hits(STEP.content_desc_re))

    # #1963 added the plural, and `\s*` carried the spaceless form along.
    assert sorted(after_1963 - before) == ['Google Maps', 'Googlemaps']
    # #968 adds the hyphen, for every alternative the pattern already had.
    assert sorted(now - after_1963) == [
        'Google-Karte', 'Google-Map', 'Google-Maps', 'Google-karte',
    ]
    # Neither step lost anything.
    assert not before - after_1963
    assert not after_1963 - now
