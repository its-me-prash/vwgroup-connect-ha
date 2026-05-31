# STYLE.md

How we write commits, PRs, CHANGELOG entries, and issue comments in this repo.

## Why a style guide

After a few iterations our output started reading as AI-generated: multi-paragraph commit bodies, "Summary / Test plan" headings on every PR, em-dashes everywhere, bilingual EN/DE blocks in the same artifact. Top-tier maintainers in the same niche write much shorter and don't use any of that. This file codifies the patterns we match.

## Commits

- Subject only. ~50-72 chars. No trailing period.
- Format: `Component: short imperative` for feature/fix commits. Example: `Audi: drop x-assertion header from token request`. Sub-scope in parens when narrowing: `Sensor (TIMESTAMP): parse ISO strings to tz-aware datetime`.
- Prefix `chore:` / `docs:` / `fix:` only for non-feature changes (deps, formatting, doc-only).
- Suffix `(BC)` when breaking.
- No body in 90% of cases. If you need context, write a PR description instead.
- No `Co-Authored-By: Claude ...` trailers. Strip them from every commit.

## PR descriptions

- Open with `fixes #N` or `closes #N` on its own line. Lowercase. Plain text, no markdown link.
- Then 1-2 short paragraphs of prose explaining what changed and why.
- Optional: 3-6 bullet points for concrete code-level changes if it helps the reviewer.
- Code fences only for actual multi-line code or shell output. Inline `code` (single backticks) for paths, identifiers, env vars.
- No headings unless the PR has 3+ genuinely distinct sections worth navigating. Default = no headings.
- No `## Summary` / `## Test plan` boilerplate.
- No screenshots in routine PRs.
- No tables.
- No emoji.
- No GitHub admonition blocks (`> [!NOTE]`, `> [!WARNING]`).
- For drafts or uncertain work, end with a one-line caveat. Examples: `Untested against live accounts.` / `Draft, does not unblock VW EU login.`

Example:

```
fixes #319

VW backend started rejecting requests carrying the dummy `x-assertion="0"`
value some time around 2026-05-27. Drop the three assertion headers from
the Audi token request to bring it back in line with what the official
myAudi app sends.

- `_cariad_token_headers` default flipped to the 5-header set
  (Content-Type, Accept, Accept-Charset, User-Agent, x-qmauth)
- 8-header superset preserved behind `include_assertion=True` for
  future debugging
```

## CHANGELOG

- Keep-a-Changelog format. `### Added` / `### Changed` / `### Fixed` / `### Security` / `### Dependencies`.
- One line per entry. 5-15 words.
- Imperative, no period. Example: `Fix duplicate device registry entries on reload`.
- Reference issue / PR in parens at end: `(#319)` or `(#319, thanks @moltke69)`.
- No nested bullets.
- No emoji in entries.
- No "Migration guide" subsection unless there is a real breaking change with action required.
- No marketing copy. No "What's new" framing.

Example release:

```
## [2.6.1] - 2026-05-31

### Fixed
- Audi login: drop x-assertion header trio rejected by VW backend (#319)
```

## Issue comments

- Default to 1 sentence. Add a second only for a concrete fact (PR ref, alternative, workaround).
- Use bare `#1234` references, not markdown links. GitHub renders them.
- `/cc @maintainer` only when you genuinely need their input.
- Say no with reasoning plus alternative: `We won't do X because Y. Instead we have Z.`
- Ask for more info bluntly: `Can you paste the log line that fires?` / `Did you try a full HA restart, not just integration reload?`
- No apologetic openers. No `Thanks for the detailed report!` boilerplate. Earn it.
- No emoji.
- No GitHub admonitions.
- Don't paste full stack traces. Link to logs or quote 3-5 lines.

## Language

- English primary across commits, PRs, CHANGELOG.
- Switch to German only when replying to a German-speaking user in a German thread.
- No bilingual EN/DE blocks inside the same artifact.

## Em-dashes

Don't use them. Use period, comma, colon, or `...` for hedging.

## AI-tells to avoid

These patterns mark output as AI-generated. Don't ship them.

1. Em-dashes anywhere.
2. `## Summary` / `## Test plan` / `## How` / `## Why` headings on routine PRs.
3. `Co-Authored-By: Claude ...` commit trailers.
4. `Generated with Claude Code` sign-offs in PR bodies.
5. `> [!NOTE]` / `> [!WARNING]` admonition blocks.
6. Multi-paragraph commit bodies with sub-headers like `Critical Bug Fixes:`, `Result:`, `Affected Files:`.
7. Bilingual EN/DE blocks in the same commit / PR / CHANGELOG entry.
8. `TL;DR` / `Cross-project` / `Strategic posture` / `Affected users` framing in issue comments.
9. Bullet lists with 5+ items in short issue comments.
10. Markdown-linked issue refs `[#123](https://github.com/.../issues/123)`. Use bare `#123`.
11. Apologetic / hedging openers ("Apologies for the confusion", "It seems that perhaps...").
12. Triple-fenced code blocks for single inline identifiers.

## References

- evcc AGENTS.md: https://github.com/evcc-io/evcc/blob/master/AGENTS.md
- Keep a Changelog: https://keepachangelog.com/en/1.0.0/
