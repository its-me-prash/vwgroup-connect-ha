# Release process

> Single canonical release procedure. Follow this for every tag.

Last updated: 2026-04-26 — current version: v1.8.0

---

## When to release

Release whenever a coherent, atomic batch of changes is on `main` and CI is
green. There is no fixed cadence. The session-based roadmap
([`docs/ROADMAP.md`](docs/ROADMAP.md)) maps each upcoming session to a
target version.

### The rolling window — a hard cap of two

**At most two tagged releases in any rolling seven-day window, and pre-releases
count.** Five betas plus a stable in one week is six, not one.

The cap exists for the people on the other end: every tag is an update prompt in
everyone's Home Assistant, and a project that ships daily trains its users to
ignore them — which is exactly when a release that genuinely matters gets skipped.

Count it from the live release list rather than from memory, because betas are easy
to forget:

```bash
gh release list --limit 30 --json tagName,publishedAt,isPrerelease
```

Everything published within the last seven days counts, boundary included: at
exactly the seven-day mark the old release is still inside, so freedom starts after
it, not at it.

**Overriding it is allowed and must be written down.** A release that escapes a
live outage can be worth the cost — v4.12.0 went out two days early because the
portal was refusing logins and no published version survived it. When you override,
record in the release commit or the issue which rule you set aside, what the harm
was, who was affected by name, and that the decision was taken knowingly. An
undocumented override is indistinguishable from not having checked.

---

## Daily: `[Unreleased]` block

Every commit that touches `custom_components/` needs an entry in the
`[Unreleased]` block of `CHANGELOG.md`. The `changelog_check.yml`
workflow enforces this.

```markdown
## [Unreleased]

### Added | Changed | Fixed | Removed
- short description of the change
```

### Add the entry with the script, not with a block rewrite

```bash
python scripts/add_changelog_entry.py --section fixed --text-file entry.md
python scripts/add_changelog_entry.py --section added --dry-run --text "- **…**"
```

`add_changelog_entry.py` inserts one entry at the end of its section and
touches nothing else — it refuses to write if a single existing line would be
removed or altered. That matters because of how the block is *usually* edited:
rewriting the whole `[Unreleased]` block makes git see one large change on each
branch instead of two small additions in different places, so two branches
overlap and resolving the conflict means one side's entries go with it. Twice in
one day that nearly cost an entry — once a duplicated `### Behoben / Fixed`
heading left by a merge, once main's whole `### Hinzugefügt / Added` section
dropped by a side-pick. Inserting per section merges cleanly in that case
(measured); the same section still conflicts, but over two lines whose union is
obviously both.

`check_changelog_structure.py` is the net under it. In `changelog_check.yml` it
runs two checks on every pull request that touches `CHANGELOG.md`: no conflict
marker anywhere, and no duplicate section heading inside `[Unreleased]` —
counted by what a heading *means*, so `### Fixed` beside `### Behoben / Fixed`
is one section twice and not two sections. Three of the last 80 revisions of
this file on main really were in that state.

```bash
python scripts/check_changelog_structure.py            # what CI runs
```

A third check — *no entry that was in the baseline has vanished* — exists
behind `--base` / `--baseline-file` and is deliberately **not** in CI. Measured
against this file's own history, each commit against its real parent, it would
have refused five of the last 80 revisions and **none of the five had lost
anything**: every one was an entry whose bold title had been rewritten, one of
them by inserting an issue number into the title, which is exactly what this
document asks for. Over the same window it caught zero real losses, while the
duplicate-heading check caught three with no false alarm. The cause is
structural: 516 of the 819 entries cite no issue number, so they are keyed by
their title and a reword is indistinguishable from a deletion. A required check
that refuses legitimate work and has never caught damage gets a `--skip` added
to it and then protects nothing.

So run it deliberately, which means after resolving a changelog conflict:

```bash
python scripts/check_changelog_structure.py --base origin/main
```

Know both of its blind spots before you trust it. An entry whose issue number
is also cited by another entry can be deleted without it reporting anything —
322 of 985 entries today, 6 of the 12 in the Unreleased block. And it will
accuse you of deleting an entry you only reworded; in the Unreleased block that
is one entry of thirteen today, since the other twelve cite an issue. It is a
second pair of eyes, not a guarantee. The guarantee is that
`add_changelog_entry.py` never rewrites the block.

Neither script checks section order or vocabulary, on purpose: this file has
used 31 distinct headings and keeps past entries as written.

### While a release is being cut, check where in-flight entries landed

An open release pull request renames `[Unreleased]` to the new version and adds
a fresh empty `[Unreleased]` above it. A feature branch that appends to
`[Unreleased]` does **not** textually overlap that rename, so git merges the two
without stopping — and the appended entry lands under the **released** version,
while the fresh `[Unreleased]` stays empty.

Reproduced in a throwaway repository: the merge is clean,
`check_changelog_structure.py` exits 0, and nothing in CI reports it. The file
is structurally valid; only the placement is wrong. Nothing is lost, but the
entry ships inside a version that did not contain the change and is then
missing from the next release's notes.

This predates `.gitattributes` and is not caused by the union merge driver —
measured with and without it, the outcome is identical, because there is no
conflict for a merge driver to resolve.

So, while a release pull request is open:

1. prefer not to update feature branches onto `main`; wait until the release
   has merged;
2. if you must, re-read the `[Unreleased]` block afterwards and move anything
   that slid into the released version back up;
3. after the release merges, check `[Unreleased]` once before pushing anything
   else.

The `--base` entry-loss check does not catch this either — it asks whether an
entry *vanished*, and this entry is still there, under the wrong heading.

## Language convention (v2.4.1+ — EN-primary, switched 2026-05-23)

CHANGELOG entries + release notes + GH release titles use **English as
the primary language**, with German callouts where the original
context was DACH-specific (Facebook-group threads, German tester
names, brand-specific German terminology like "Standheizung",
"S-PIN", "Konfigurator").

**Why the switch from DE-primary (v1.12.3 → v2.4.0)**: the project's
new "VW Group Connect" identity + growing international audience
(VW North America landed in v2.3.0, more brands coming) make
English-primary more inclusive. The DACH community's voice stays
visible via inline German callouts in the entries themselves.

**Style guide**:
- Section title: `## [X.Y.Z] - YYYY-MM-DD — "EN Codename / DE Codename"`
  (EN first). No `v` before the number, ASCII hyphen before the date — the
  heading is machine-read, see [Heading format is
  machine-read](#heading-format-is-machine-read).
- Body: English-primary. Insert a German sentence/paragraph only when
  the original context was DACH-specific or when terminology has no
  clean English equivalent.
- Code/log strings stay as-is (already English by convention).
- Past entries (pre-v2.4.1) are preserved DE-primary for historical
  accuracy — never rewrite history.

## Changelog format (v2.4.1+ — two forms, one source)

**Corrected 2026-11-04.** What stood here told you to keep entries short
because "technical detail belongs in commit messages". That stopped being true
when the release notes were split out: `scripts/build_release_notes.py` reads
this file and *generates* the short form, and its own docstring says the
opposite of the old sentence — "CHANGELOG.md — unchanged, and still the long
form: what broke, why, how". Following the sentence that stood here strips the
detail out of the one place that keeps it, so the two documents now agree.

Every entry carries **both** forms, and nothing is written twice:

- The **bold title** is the short form. `build_release_notes.py` reads the
  titles out of a section and builds the GitHub Release body from them — one
  line per change, with its issue numbers and a thank-you. The title therefore
  has to stand on its own, because a reader of the release body sees nothing
  else of the entry. Write the issue number into the title; the builder moves
  it to the end of the line itself.
- The **paragraphs after the title** are the long form, and they belong here:
  what broke, why, and how it was measured. They are for whoever hits the same
  thing in six months, and they are deliberately *not* in the release body —
  v5.1.0 pasted a whole section in once and produced a body of 44 681
  characters over 653 lines, which Home Assistant shows in its update dialog.

Either way an entry opens with `- **`; that is what both parsers split on
(`build_release_notes.split_entries`, `check_changelog_structure.py`).

**Per-release structure** (skip empty sections):

```markdown
## [X.Y.Z] - YYYY-MM-DD — "Short codename"

### Fixed
- **Bold title that stands on its own (#NNN)** — then the long form as
  paragraphs: what broke, why, how it was measured.

### Added
- **Bold title for the new entity, sensor, service or capability (#NNN)** —
  paragraphs as above.

### Changed
- **Bold title (#NNN)** — the paragraphs say what changes for the user (new
  options, new automatic behaviour, new notifications).

### Notes
- Anything noteworthy that doesn't fit above (release-process
  changes, deprecation warnings, etc.)
```

### Heading format is machine-read

That `## [X.Y.Z]` line is parsed by three readers. Getting it wrong either
turns CI red or quietly degrades the published release, so the shape is not
cosmetic:

| Reader | What it looks for | With `## [vX.Y.Z]` instead |
|---|---|---|
| `ci.yml`, step *CHANGELOG.md enthält aktuelle Version* | `[` + the bare `manifest.json` version + `]` | **CI goes red** on every push and pull request |
| `release.yml`, step *Release-Notes generieren* | `## [X.Y.Z]` opening the section | the notes lose this version's section and fall back to a bare *see the CHANGELOG* link |
| `release.yml`, the version/date list in the same step | `## [X.Y.Z]`, optionally followed by `- YYYY-MM-DD` | this version drops out of the parsed list |

So:

- **No `v` before the number.** `## [4.13.0]`, never `## [v4.13.0]`. The `v`
  belongs on the git tag, not in the heading.
- **ASCII hyphen before the ISO date**, because the date is captured by
  `\s*-\s*`. An em dash there is not matched and the date is lost — not from
  this release's notes, which never print it, but from the **next** release's
  *Recent releases* pointer, which then lists this version with no date.
- **Punctuation after the date is free.** Everything following `]` is `[^\n]*`
  to the first reader and ignored by the others, so the codename can be set off
  with an em dash, quotes, or both.

The newest entry in [`CHANGELOG.md`](CHANGELOG.md) is the live example, and
step 2 below shows the same shape. Checking the heading against the parsers is
one command:

```bash
grep -nE '^## \[' CHANGELOG.md | head -3   # newest headings, exactly as parsed
```

**Do**:
- One line per fix / feature wherever possible
- For new architecture or behaviour the user will notice, write 1–3
  sentences explaining what they will see / can do differently
- Issue numbers in parentheses at the end: `(#281, #282)`
- Plain language — avoid project-internal jargon (`*_pending family`,
  `T1 audit`, brand-vererbung) in the user-facing changelog
- Credit the reporter: a short `Thanks @handle` next to their fix, plus
  an ack-comment on the closed issue **in the reporter's native
  language** (see below)

**Don't**:
- Cite reference implementations (`per matpoulin`, `mirroring
  CarConnectivity v0.6.3`) — that's commit-message territory
- List file paths, LoC counts, function/class names
- Document tier classifications, audit methodology, or migration
  rationale (those live in `docs/SCOUT_POLICY.md`, `MIGRATION.md`)
- Repeat the same info in a top quote-block AND a per-section bullet
- Use emoji unless explicitly requested

**Length sanity-check**: a PATCH release should fit on one screen
(20–40 lines). MINOR releases can be 40–80. MAJOR releases up to
100 lines but only if there's truly new user-facing behaviour to
explain. If the current draft is >100 lines, it's almost certainly
too detailed for a changelog.

## Ack-comment language (when closing an issue)

When responding to a reporter on a GitHub issue, **write in their
native language** when reasonably inferable from:

- the **Country** field of the issue template (`Germany` → DE,
  `Spain` → ES, `Italy` → IT, etc.)
- the language they wrote their issue in
- the language of related projects they linked to

Why: respect + reduces friction for non-English-speakers replying to
follow-ups. Most German reporters reply faster in German; Spanish
reporters appreciate Spanish; the few minutes of writing in their
language is well spent.

If unsure or no signal → default to English.

If two reporters in different languages share an issue (e.g. one
German + one French commenter), write a bilingual reply or use both
languages in clearly marked sections.

Technical terms (HACS, Home Assistant, OptionsFlow, HTTP 403) stay
as-is — they're proper nouns / API names.

Commit-message prefix conventions are listed in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Semver

We are now on **post-1.0.0 strict semver**:

| Change | Bump | Example |
|---|---|---|
| Bug fix only | PATCH | 1.8.0 → 1.8.1 |
| New feature, new entity, new brand, new endpoint | MINOR | 1.8.0 → 1.9.0 |
| Breaking change (removed entity, renamed config key, dropped HA version) | MAJOR | 1.x → 2.0.0 |

Pre-1.0.0 historical correction is documented at the top of
`CHANGELOG.md`. **Do not refer to it for new releases.**

---

## Step by step

### 1. Bump `manifest.json`

```jsonc
// custom_components/vag_connect/manifest.json
{
  "version": "1.9.0"   // bump per semver
}
```

### 2. Finalise `CHANGELOG.md`

Replace the `[Unreleased]` heading with the version + ISO date and add a
new empty `[Unreleased]` block above it.

```markdown
## [Unreleased]

## [1.9.0] - 2026-MM-DD

### Added
- Capability-aware entity creation (#56)
```

### 3. READMEs — nothing to mirror any more

This step used to say "mirror the release notes into all 8 READMEs" and update a
roadmap table marking the version `✅ Done`. Both halves are out of date:

- There is no roadmap table in the READMEs any longer, and no per-release version
  marker. The only version strings left are historical prose references (a
  CHANGELOG pointer, for example), which a release must not touch.
- There are **12** top-level READMEs, not 8: `README.md` plus eleven translations
  (`cs da de es fi fr it nb nl pl sv`). The other README files in the tree are
  internal and not user-facing.

So a normal release changes no README at all. If a release *does* add something the
READMEs should describe, all twelve are updated together under the i18n convention
above — never English alone.

### 4. Resolve the version placeholders in `docs/`

Some pages are written before the version they describe exists and carry a
forward-looking placeholder instead of a number. Nothing resolves these
automatically, so they ship verbatim unless this step catches them.

`docs/COMPANION.md` is the current one: its header table has an **Applies to**
row that reads *the first release after 4.13.0*. Replace it with the concrete
version in the release commit — a number is the convention everywhere else in
the repo. That page is the Companion's entry point: `README.md` routes readers
to it from three places, and `docs/COMPANION_AGENT.md`,
`docs/COMPANION_APP_MAP.md`, `docs/COMPANION_BATTERY.md` and
`docs/COMPANION_CLIMATE.md` all name it as the page to start from, so a stale
row there is the first thing a Companion user reads.

Sweep for the rest before committing. The sweep is scoped to the pages readers
see, so this document's own quote of that row does not show up as noise:

```bash
git grep -nE 'the (first|next) release after|\bTBD\b|X\.Y\.Z' -- docs/ README.md
```

### 5. Commit + push

```bash
git add custom_components/vag_connect/manifest.json CHANGELOG.md README*.md
git commit -m "chore: release 1.9.0"
git push origin main
```

### 6. Tag

```bash
git tag -a v1.9.0 -m "VW Group Connect v1.9.0"
git push origin v1.9.0
```

The `release.yml` workflow then automatically:

- builds `vag_connect.zip`
- generates release notes from the matching `CHANGELOG.md` section
- creates the GitHub Release attached to that tag
- HACS picks it up within ~6 hours

### 7. Notify users

If the release fixes user-reported bugs (issues with comments from
non-maintainer accounts), add a short comment on each affected issue
linking to the release page. **Address every commenter, not just the
issue author.**

---

## Pre-release checklist

```bash
python -m pytest tests/                                   # all green
python -m ruff check custom_components/ tests/            # 0 errors
python -m mypy custom_components/vag_connect/ \
  --ignore-missing-imports \
  --disallow-untyped-defs \
  --disallow-incomplete-defs \
  --warn-return-any                                       # 0 errors
python -m pytest tests/ \
  --cov=custom_components/vag_connect \
  --cov-fail-under=75                                     # gate value: see below

# The versions and the coverage gate CI pins. Read them, don't memorise them.
grep -nE 'python-version|ruff==|--cov-fail-under=' .github/workflows/ci.yml
```

**These are the gates worth running locally, not all of CI.**
`.github/workflows/ci.yml` has four jobs; the commands above cover four checks
from two of them. CI also runs, and this page deliberately does not duplicate:

| Also enforced by CI | Where |
|---|---|
| `manifest.json` carries every required field and a valid `iot_class` | `ci.yml`, *manifest.json validieren* |
| every `*.json` under `custom_components/` parses | `ci.yml`, *Alle JSON-Dateien validieren* |
| `CHANGELOG.md` contains the `manifest.json` version as `[X.Y.Z]` | `ci.yml`, *CHANGELOG.md enthält aktuelle Version* |
| Home Assistant **hassfest** | `ci.yml`, `hassfest` job |
| **HACS Validation** | `ci.yml`, `hacs` job |

Two things a green local run does not prove, both pinned in `ci.yml` and both
left out of this page on purpose so it cannot drift against them:

- **ruff version.** CI installs one exact release (`pip install ruff==…`). A
  different local ruff can disagree with it in either direction.
- **Python version.** CI sets one interpreter via `actions/setup-python`. A
  different local interpreter can pass code CI rejects, and the reverse.

The `grep` line above prints both, plus the coverage gate, straight from
`ci.yml`. `ci.yml` wins over anything written here.

A checklist that passes locally and fails in CI is worse than no checklist, and
this one has already cost a release cycle: it claimed to match CI exactly while
naming a narrower `ruff` target and a lower coverage figure than the real gate.

---

## Hotfix procedure

If a release breaks setup for users:

1. Open a `bug` issue describing the regression.
2. Fix on a short-lived branch.
3. Bump PATCH (e.g. 1.9.0 → 1.9.1).
4. Squash-merge to `main`.
5. Tag immediately.

Avoid amending or force-pushing to existing tags. Tags are immutable.

---

## Version history

Full history: [`CHANGELOG.md`](CHANGELOG.md)

| Version | Date | Type | Notes |
|---|---|---|---|
| 1.8.0 | 2026-04-26 | MINOR | Foundation Fix — 7 P0 audit findings + CUPRA flash |
| 1.7.0 | 2026-04-26 | MINOR | Škoda complete rewrite + car-friendly translations |
| 1.6.x | 2026-04-25 | MINOR | SEAT/CUPRA 9-endpoint expansion, Lock platform |
| 1.5.x | 2026-04-23/24 | PATCH chain | Multiple auth fixes (Škoda, CUPRA) |
| 1.0.0 | 2026-04-12 | MAJOR | First stable, 7 brands, HACS-ready |
