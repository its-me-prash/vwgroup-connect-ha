# Changelog

All notable changes are documented here. / Alle wesentlichen Änderungen werden hier dokumentiert.

Format: [Keep a Changelog 1.0.0](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning 2.0.0](https://semver.org/)

> ❤️ **Support this project:** VW Group Connect is a one-person effort kept alive against constant Volkswagen backend changes. If it's useful to you, please consider sponsoring continued maintenance — **[github.com/sponsors/its-me-prash](https://github.com/sponsors/its-me-prash)**. Every issue report, diagnostic, translation, code contribution and real-car test helps too; contributors are credited in **[CONTRIBUTORS.md](CONTRIBUTORS.md)**. Thank you 🙏

> 📖 **Bi-lingual convention (v1.12.3 → v2.4.0 — DE-primary)**: section-titles were **DE / EN** joined by ` / ` and body content was German-only. Past entries are preserved as-is for historical accuracy.
>
> 📖 **Bi-lingual convention (v2.4.1+ — EN-primary, switched 2026-05-23)**: section-titles are now **EN / DE** joined by ` / `, body content is **English-primary** with German callouts where the original context was DACH-specific (Facebook-group threads, German tester names, brand-specific German terminology). The project's GitHub audience + the new "VW Group Connect" branding both lean international — English-primary makes the changelog readable for non-DACH users while keeping the DACH community's voice visible. Ask in an issue if you need a particular entry translated.

## Semver-Regeln für dieses Projekt (pre-1.0.0)

> **Historisch — nicht für neue Releases.** Das Projekt ist seit v1.0.0 auf
> strikter Semver; maßgeblich ist die Tabelle in `RELEASE_PROCESS.md`, wo ein
> Breaking Change MAJOR ist und nicht MINOR. Die Tabelle hier beschreibt nur,
> wie die Versionen vor v1.0.0 vergeben wurden.

| Was | Version | Beispiel |
|---|---|---|
| Breaking Change, Architekturwechsel | `0.MINOR.0` | 0.10.0 → 0.11.0 |
| Neue Features, neue Sensoren/Services | `0.MINOR.0` | 0.10.0 → 0.11.0 |
| Bugfix, kleine Enhancement | `0.MINOR.PATCH` | 0.11.0 → 0.11.1 |
| Ab v1.0.0 | Standard `MAJOR.MINOR.PATCH` | 1.0.0 → 1.1.0 |

> **Hinweis:** Die Versionen 0.9.0–0.14.0 wurden am 2026-04-11/12 mit falschen
> Semver-Typen vergeben. Retroaktive Korrektur:
> `0.9.0→0.8.1`, `0.10.0→0.8.2`, `0.11.0→0.9.0`,
> `0.12.0→0.10.0`, `0.13.0→0.10.1`, `0.14.0→0.11.0`
>
> **v1.19.1 historischer Hinweis (2026-05-07 Audit):** v1.19.1 hat
> einen neuen Sensor `requests_remaining_today` eingeführt — nach
> strikter Semver-Regel wäre das MINOR (`v1.20.0`) gewesen, nicht
> PATCH. Wurde als PATCH released für HACS-Continuity (User-Side
> kein Breaking Change). Tag bleibt v1.19.1; nachfolgende Releases
> v1.20.0+ zählen ab v1.19.4 → v1.20.0 als legitime MINOR-Bumps.
> Lessons-learned dokumentiert für v1.20.2+ Audit-Disziplin.

---

> 💡 **Für Entwickler / Contributors:** Die technischen Detail-Notes stehen
> in den Commit-Messages und Pull-Request-Bodies des jeweiligen Release — mit
> jeder geänderten Datei, jeder Issue-Referenz und der Methodik dahinter.

## [Unreleased]

### Behoben / Fixed

- **An auth repair card named the brand but never the account, so a two-car
  owner could not tell which entry it was about (#923, @kalwados).** Six of the
  cards print the account in parentheses — `auth_failed`, `two_factor_required`,
  `email_two_factor_required`, `terms_and_conditions`, `marketing_consent`,
  `too_many_requests` — and all six were handed an empty string, which rendered
  as "Your Volkswagen account ()". Four of them are the fixable reasons, so the
  card with the Repair button was in that set. The slot now carries the masked
  account id (`p***@***.de` — the shape the diagnostics download reduces an
  address to, because these cards get screenshotted into public issues),
  falling back to the entry title and then to "this entry".

  The reason it survived review: the frontend only checks that a placeholder
  *key* exists, so an empty *value* renders cleanly and errors nowhere, and the
  call site supplies both keys, which reads as complete. The new test drives
  the real function and demands a non-empty value for every placeholder in the
  copy that will actually be rendered, with a positive control that the copy
  really uses the slot and a guard that a newly added card printing the account
  cannot go unexercised.

  Inventory while here: of the 34 repair cards only `stale_data`,
  `historical_timeout` and `supplementary_reauth` name the vehicle, and only
  the first two are keyed per vehicle at all. The remaining 31 are per entry,
  so the account is the field that identifies them — which is what made the
  empty value cost something rather than merely look untidy.

- **The product itself promised that tokens were redacted, and that promise is
  what put the files into public issues (#923, #1968).** Three texts ask for a
  diagnostics file and all three overstated what the redaction did: the Vehicle
  Data Scout repair card said "everything is redacted automatically" and named
  **tokens** among what is stripped; the `test_cohort` option said "no VIN, GPS,
  tokens or email is ever included"; and the bug-report template said sensitive
  data had been auto-redacted since v1.8.x, listing neither cookies nor tokens.
  From mid-June until 5.2.1 none of that was true of the three credential keys.

  Both in-product strings are now scoped to 5.2.1 across **all 13 language
  files**. The edit is deliberately mechanical: only the clause in front of the
  colon that introduces the list was replaced, so each language keeps its own
  wording for the list itself and no prose was invented in a language that
  cannot be reviewed here. English and German additionally say what an older
  version did **not** redact. The bug-report template now names 5.2.1 as the
  floor, separates session cookies and account tokens from the fields that have
  been redacted since v1.8.x, and links #1968; its mandatory privacy checkbox
  no longer asks the reporter to strip tokens out of an opaque cookie jar by
  hand, which is not something anyone can do.

  The guard against a relapse anchors on the colon and on the identifiers that
  are spelled the same everywhere (VIN, GPS, token) rather than on vocabulary,
  so one test covers every language; a positive control fails if that anchor
  ever stops finding the two sentences, because an anchor that finds nothing
  would otherwise let the module pass while checking nothing — which is the
  shape of the review failure that allowed the original wording to stand.

- **Whether this portal ever throttles *us* is now in the diagnostics
  download, instead of being taken on faith (#1969).** Its rate limits are
  known only from someone else measuring their own traffic against the same
  portal — per-endpoint ceilings, a refill of roughly one request every two
  seconds, a short explicit `Retry-After`. Honouring that cooldown was the
  right change; pacing our polls against those numbers would not have been,
  because nothing had ever observed the mechanism on our own requests. A rate
  limit taken on faith is how a poll loop gets tuned against a figure that does
  not apply to it.

  Three values are recorded and exported as `portal_throttle`, so one user's
  file answers it: a count of zero means it has never happened to us; a count
  above zero with no seconds means we are throttled and told nothing, so any
  cap has to be guessed; a count above zero with a number says the mechanism
  applies and whether the 30-second cap is the right one. Recorded on **every**
  429, including the second one within a call and the over-cap case — those are
  precisely the observations that say the pacing is wrong, and precisely the
  ones a "record it only when we act on it" version would throw away.

  The fields are public on the connector on purpose: the download reads
  attributes off that object by name, so a leading underscore would have made
  this a field nobody can see. `_last_soft_status` right above it claims in its
  own comment to be "surfaced as diagnostic sensors" and is in fact read
  nowhere outside its module — measured, not assumed, and left alone rather
  than repeated.

- **A 404 on vehicle enumeration was reported as a dead session (#1964,
  @Hollywoodchaos).** He diagnosed it himself and proved it from outside the
  integration: logged into the portal in a browser with the same account, its
  own "Veículos associados" section fails with a technical error, so the 404 we
  received was the truth about the portal and not about his login. We turned it
  into the session-expired repair card, which told him to fix the one thing
  that was working.

  The cause is that a 404 on this portal means different things on different
  endpoints and one rule was applied to all of them. On the metadata endpoint
  it means "there is no such data request" — #1932 decided that deliberately
  and pinned it with a test — and that stays exactly as it was. On enumeration
  it means the portal cannot list the account's cars, which is an upstream
  problem, so that call now declares 404 and 410 as such and gets the same
  treatment the 5xx family already had. The rule lives at the call site that
  knows which endpoint it is talking to; nothing is implied for any other.

  **An existing test asserted the old behaviour, and its expectation is what
  changed.** #465 pinned "404/410 on enumeration raises an authentication
  error" with the reasoning *"404/410 means the data request is not
  provisioned"* — the metadata endpoint's meaning, borrowed onto enumeration
  because enumeration was a convenient way to drive the shared helper. The
  caller is what settles it: an authentication error out of enumeration makes
  `vw_eu` **replay the stored password**, enumerate again and then raise
  `PortalSessionExpiredError`. That is the exact sequence #465 itself exists to
  prevent, quoted in its own docstring for the 5xx case; it fixed the outage
  family and left 404 behind on the borrowed premise. The expectation was
  changed only after reading that caller, and the test now carries the
  reasoning instead of the conclusion — plus a sibling that fails if anyone
  "simplifies" this by adding 404 to the global outage set, which would
  silently reverse #1932.

- **A refused e-mail-code step promised that waiting would fix it (#1969,
  @Ra72xx).** His volkswagen.de login failed after the code with HTTP 400,
  repeatedly, and the dialog said "VW backend temporarily unavailable … wait
  5–15 minutes … do NOT reconfigure". The verdict was right and #1843 decided
  it on purpose: the code is only sent **after** the password is accepted, so
  neither can be the cause of an HTTP error. The remedy was wrong. Waiting
  clears a 5xx; it does not clear a refusal, and his repeated every time.

  A 4xx now has its own error text that keeps #1843's verdict — not your code,
  not your password — and drops the promise that it passes on its own. Fixed in
  **both** flows, because the setup path and the options/reauth path have
  separate handlers and were reported separately by two different people;
  fixing one would have left half the users waiting for nothing.

  And the part that was worse: the raise site **parsed the site's own error
  text one branch earlier and then threw it away** on a 4xx, leaving a bare
  number. The single piece of evidence that would say *why* VW refused was
  read and discarded. It is now carried on the exception and in the message.

  Known gap, stated rather than hidden: the new error text is written in
  English and German. The other eleven language files carry the English
  sentence so that key parity holds, and they want a translation pass.

  **And the first version of that text promised something it cannot keep.** It
  said "the exact reason the site gave is in the log next to this message".
  Measured afterwards: the parser behind that promise recognises exactly one
  page format — a body carrying the literal `templateModel` with JSON holding
  a truthy error — with no regex, no HTML parsing and no marker lists. An
  Auth0 JSON body, an Auth0 error page, an nginx/WAF 400 and an empty body all
  yield nothing, and the e-mail-code step is the Auth0 universal-login flow,
  where that word does not appear at all. So in exactly the case the sentence
  was written for, there is no reason in the log either.
  
  The text now says what is actually known — the status, and that it is
  neither the code nor the password — states plainly that the site usually
  gives no reason we can read on this step, and asks for the three things that
  do help. A test drives the real parser against those four bodies and fails
  if anyone restores the promise before the parser can keep it, which is the
  right order.

- **The portal tells us how long to wait when it throttles us, and we ignored
  it (#1969).** It answers a burst with 429 and a short explicit
  ``Retry-After``; 429 was deliberately kept out of the retriable set ("one
  quiet skip, no backoff-retry"), which is the right refusal to hammer a server
  and the wrong answer to one that has just named its own cooldown. The poll
  was simply lost — soft returned no-data, hard reported an outage — and on a
  multi-vehicle account the newest dataset was never reached, because the list
  endpoint is called once per VIN and the coordinator reads the VINs
  concurrently.

  A parseable cooldown inside a 30-second cap is now waited out and the request
  repeated, at most once per call, so a server that keeps throttling cannot
  hold a poll open. A missing, zero, over-cap or HTTP-date value leaves the old
  behaviour untouched. The parsing moved to ``cariad/_util`` because two
  channels needed it and only the app backend had it (#1850); its staticmethod
  on the base client stays, delegating, since a test pins that shape for a
  stale-value reason that still applies.

- **A dotted field name walked past every name-based redaction rule (#923).**
  Found by generalising the same way, and it is the wider of the two: each rule
  in the scrubber that keys off a name tested exact equality on the whole key,
  while EU Data Act field names **are** dotted — the dictionary's own count is
  3206 of 7990 — and an *unmapped* portal field lands verbatim in
  `raw_unmapped_fields`, which the download emits. Measured with one marker per
  key: `latitude`, `access_token` and `user_id` were handled, while
  `parking_position.latitude`, `vehicle.parking.longitude`,
  `settings.access_token`, `auth.tokens.refresh_token` and `vehicle.user_id`
  all came through in the clear.

  What hid it: the value-**pattern** rules were never affected. `profile.email`
  masked correctly, so the file read as redacted. The name rules now match the
  last dotted segment as well, which is the conservative direction — a dotted
  name whose leaf is registered carries the same kind of data as the bare one.
  The full dotted spelling is kept as the output key, so triage still sees
  which field was redacted, and a harmless dotted field such as
  `odometer.total_km` stays readable.

  The guard walks **every** name in all three sets and requires the dotted form
  to be handled too, so a name registered later is covered without anyone
  remembering this. Reverting the fix turns 48 of its 68 cases red, each one
  naming the field it would have leaked.

  It had to be fixed in **both** scrubbers. `_scrub_raw` has its own key logic
  and the same blindness: after `_scrub` was corrected it still returned four
  of the five dotted spellings in the clear, so a guard on the half that
  happened to be measured first would have gone green over a leak. Widening
  that guard to sweep both functions then caught a third hole immediately, in
  the new fix itself — `location_lat` and `location_lon` live only in the GPS
  set, which `_scrub_raw` never consulted. That is the argument for a guard
  that walks the sets instead of a list of examples: it found a gap introduced
  minutes earlier.

  This is the second time in one issue that a redaction looked complete because
  it was checked against itself. Both guards added since derive their
  expectation from somewhere else: one from the key names in `const.py`, this
  one from the redaction sets themselves.

- **A charging profile's coordinates reached the diagnostics download in the
  clear — the place the car habitually charges (#923).** Generalising from the
  cookie-jar defect found a second gap of exactly the same shape, and this one
  had been shipping. `coordinator.py` flattens each Škoda / SEAT / CUPRA
  charging profile into `{"name", "location_lat", "location_lon", …}`, while
  the GPS branch in `diagnostics.py` only ever matched the spellings
  `latitude` and `longitude`. So the coordinates of the profile's location —
  home, for most people — went into the download at two decimals, roughly a
  kilometre, in **both** the default and the opt-in mode, although that
  module's stated contract is privacy-by-default removal. The owner's own
  label for the place went with them, even though the project had already
  registered the sibling `charging_location_N_name` on the argument that such
  a label is the owner's word for a place.

  `location_lat` and `location_lon` now go through the same branch as
  `latitude` and `longitude`: removed by default, rounded to one decimal only
  on the existing opt-in. `active_charging_profile_name` is registered, and
  the per-profile label is masked by a container-aware step, because a global
  `name` rule would redact every brand, device and entity name in the file.
  Everything triage actually uses — target SoC, current limit, the counts —
  is kept, and an absent coordinate or label still stays visibly empty rather
  than becoming a fake redaction.

  Measured, not reasoned: a profile in the production shape through the real
  scrubber returned both coordinates and the label unchanged, with a positive
  control confirming that bare `latitude` *was* being removed, so the branch
  worked and the names were the gap. The guard against the next one derives
  the set of coordinate key names from the **source** and fails if any is in
  neither redaction set — it names `location_lat` and `location_lon` when the
  fix is reverted, so it would have caught this before release. A list checked
  against itself always looks complete; this is the second time that cost
  something in this issue.

  **If you have already attached a diagnostics file:** unlike the credential
  keys, there is nothing to rotate here. The coordinates are approximate, and
  deleting the comment is the only thing that helps — see #1968 for why that
  does not remove the uploaded file.

- **The push gate reported a permanent stop as if it were transient, so the
  Audi/VW push toggle looked like it was still starting up (#1941,
  @philf90).** He switched on *Audi/VW push updates*, confirmed
  `enable_push_audi_vw: true` in diagnostics, and got one line per setup:
  "Push setup skipped: no user_id captured by the brand client". It reads as
  *not captured yet*, and the comment above the gate said as much — next
  refresh re-tries. For his brand it never resolves: neither `VWEUClient` nor
  `AudiClient` assigns `user_id` or `_user_id` anywhere, so the gate bails on
  every setup, for both of the two brands that toggle names. It was logged at
  debug, so without debug logging on there was nothing to see at all.

  The two cases are now told apart. A client with no user-id slot at all is a
  permanent condition: it says so once per entry, at warning level, names the
  brand, states that it will not resolve on its own, and points at #1941. A
  client that has the slot and has not filled it keeps the debug line, with
  wording that now actually says it re-tries.

  **Not fixed here, deliberately.** The VW EU client does hold that value under
  another name — `_mbb_user_id()` decodes the `sub` claim of the id_token, and
  the authproxy path carries `mbb_user_id`. Widening the gate to accept it
  would make the toggle reachable, but the Audi/VW push manager ships with an
  unverified subscription body by its own docstring, so that step belongs with
  a tester on a real car rather than inside a logging fix. The same shape was
  #602 for Škoda, which is what the comment at this gate has described since.

- **`SECURITY.md` carried the same overstatement, and a supported-versions
  table five minor lines out of date (#923, #1968).** It named `4.7.x` as the
  supported line and said passwords, S-PINs, usernames and GPS "are never
  exposed in diagnostics exports". The table now reads `5.2.x`, and the two
  redaction bullets say how the redaction actually works — by key name,
  recursively, so a value is safe only once its key or a key above it is
  registered — which is the property that made the gap possible and the
  property that also meant the two nested token dicts were covered while the
  cookie jar was not. Measured, not assumed: reconstructing the pre-5.2.1
  scrubber and running it over the shapes the code writes leaves the cookie
  value in the clear and all six token values redacted. The file also now says
  how a problem gets published once it is fixed; until now it only said how to
  report one privately.

  `docs/TRIAGE.md` carried the same absolute in the heading of its "Redact
  before you paste" section — "Diagnostics redact the sensitive fields for
  you" — and in the step that tells a reporter where to click. Both now name
  5.2.1 as the floor, and the section explains the key-name matching, because
  that mechanism is also the limit a reader needs in order to recognise an
  unmasked credential if one ever shows up again.

## [5.2.1] - 2026-10-30 — The file we asked you for / Die Datei, um die wir gebeten haben

### Behoben / Fixed

- **Three credential keys reached the diagnostics download unredacted, the
  volkswagen.de session cookies among them (#923).** The file this integration
  asks you to attach to a public issue could carry `website_cookies` — the vw.de
  cookie jar that keeps you signed in — plus the per-VIN MBB command tokens and,
  if you use it, the Tibber account's tokens. All three are stored on the config
  entry, which the download emits as `config`, and a cookie or a token is an
  opaque string, so none of the pattern-based redactions matched one.

  **If you have attached a diagnostics file from a volkswagen.de-login entry to
  a public issue, sign out of volkswagen.de and back in.** That invalidates the
  jar in the file. There is no sign that anyone has used one — the problem is
  that the file was readable by anyone.

  It was missed the way long allow-lists are missed. The redaction list already
  carried both *sibling* jars — the supplementary vw.de slot and the VW-EU
  two-way one — and its own comment states that "the vw.de cookie list carries
  the auth0 / auth0-mf SSO session tokens". Checked against itself the list
  looked complete. The same had happened to the token maps: Companion, VW-EU
  two-way and Škoda were registered, MBB and Tibber were not. So the new test
  does not read the list. It derives what ought to be redacted from the key
  names in `const.py`, which is the only thing that exists at the moment someone
  adds a key, and fails when one is unhandled. Two keys are exempt with a
  written reason: a boolean opt-in that only looks like a password, and the
  Škoda key map, which has its own masker so the enrolment count survives.

- **"No data-request yet" was printed at people whose data request was active
  (#1850).** Reported by @indigomejor, who paired the line with its timestamps:
  the portal said it once at 12:03, four `dataset listing unavailable (HTTP 404)`
  lines followed, and his request had never gone away.

  The line now says what the portal actually answered — `(the portal answered
  HTTP 404)` — and adds that this answer does not always mean the request is
  missing, so if you already have one you should leave it alone. The advice for
  someone who genuinely has no request is unchanged, deliberately: a 404 *is*
  the portal saying "no such request", which #1932 decided and pinned with a
  test, and that is the one case where there is something to do. Replacing the
  advice on the strength of one report would have reversed that decision
  silently.

  Also fixed behind it: the status being reported is now cleared *before* the
  metadata read rather than after it. It is only written when a read fails
  softly, so a successful read left the previous poll's status in place — naming
  that would have attributed an old 404 to a healthy poll.

- **A dataset whose JSON root is not an object was read as "no data this poll",
  silently.** Nothing in a log distinguished that from an empty delivery. The
  shape has never been seen — every export file in this repository has an object
  at its root, and the "flat list of objects" in #1950 is the `Data` array
  inside one — so this deliberately does not start handling it: inventing
  handling for a payload nobody has delivered is how untested branches are born.
  It now warns, naming the root's type and how many top-level items it had, and
  nothing else: not the file name, which can carry a VIN, and not a single
  value.

- **The one-time historical export told you to enable a continuous data
  request (#1850).** It reaches the same "no active request" branch through its own
  metadata path, where that is the wrong control to point at: there is nothing
  continuous to enable for a one-time export. Named as a loose end when the
  rest of that message was corrected, and closed here rather than left as a
  known-wrong sentence.

## [5.2.0] - 2026-10-30 — As of when? / Seit wann gilt das?

### Behoben / Fixed

- **The Charging Port sensor could fail to be created at all, with "Error
  adding entity" in the log instead of an unavailable sensor (#1739).** Reported
  by @awood-ops on 5.1.3.

  That sensor is an enum: it declares exactly two permitted states, and Home
  Assistant does not degrade an out-of-vocabulary state to "unavailable" — it
  refuses to add the entity at all. His traceback showed the state arriving as
  `DISCONNECTED` against options spelled in lower case.

  **Three mistakes lined up, and the first diagnosis caught the least important
  one.** The normaliser was guarded by `isinstance(value, str)`, so it inspected
  only values that were already the type it trusted. That was real but it was not
  his bug: an upper-case string passes that guard and comes out folded correctly.

  The one that broke his car is that on his path the normaliser never ran at all.
  It lived only in the enrichment step, which runs on a poll that parsed vehicle
  data — and his failure was at setup, before any poll. On startup the integration
  restores the last-known-good snapshot so entities show recorded values instead
  of sitting unknown, and that restore hands the stored data straight to the
  platforms without enriching it. Since the vehicle cache has never had its
  version bumped, a snapshot written before a normaliser existed is still loaded
  verbatim today. Third, the normaliser covered one field while there are five
  enum sensors, every one of them exposed the same way.

  Normalisation now reads each enum sensor's permitted states from the sensor
  descriptors themselves and runs on both paths, so a sixth enum sensor is
  covered without anyone remembering a second list. A value that is not in its
  options becomes unavailable rather than a guess. Five mutations of the new code
  were each caught by a dedicated test, including one that moves the call after
  the snapshot is published — which would read as a fix and do nothing.

  @awood-ops read his own traceback and named the case mismatch before I did,
  after I had already published the wrong explanation.

- **A log line promised that a car refused by the legacy gateway would be
  retried after twelve hours, which for many setups never happens (#584).**
  Found in a log @Mjukes posted while asking how to opt in: the line was in his
  log, the observation was mine. The first published version of this entry said
  he had pointed it out and "reasonably expected a retry", which he never said —
  corrected here rather than quietly, since it put words in a reporter's mouth.

  The twelve hours are real — they are the cooldown on the denial — but the
  same denial also records a "no legacy enrolment" verdict, held in memory for
  as long as Home Assistant keeps the entry loaded, and since a
  change in early September the periodic check skips a car carrying that verdict
  outright when the entry reads through another channel. On such an entry the
  cooldown expiring changes nothing. On an entry whose primary channel *is* the
  legacy one, the read does come back. Both shapes exist, so no single number
  was ever true for everyone.

  The line no longer names a duration. It now says that the periodic check does
  not ask again while the verdict stands, and that a restart, a reload or a
  command attempt does — which is accurate for both shapes. The explanatory
  comment above the constant and the debug line for repeat hits made the same
  promise and were corrected with it. Anyone searching their logs for
  `Not retried for 12 h` will no longer find it; `operationList` and
  `gw.error.authentication` are unchanged.

- **A repair card from a car you no longer own could keep your full VIN, and
  put it in the diagnostics file you attach to a public issue (#923).** Found by
  @skornehl, who spotted it in his own export and stripped it out by hand before
  posting — twice, on two separate exports.

  A repair's id lands verbatim in Home Assistant's own config-entry
  diagnostics, where this integration's VIN redaction never sees it. That was
  fixed twice before, for `historical_timeout` (#1768) and for `stale_data`
  (#1626): new cards carry a masked VIN, and the legacy raw-VIN id is deleted
  when that same card is next raised or cleared. For `stale_data` the clear runs
  on every poll, so the cleanup was judged unnecessary — a sweep for it "would
  be dead code", and a test pinned that decision.

  **It is only dead code while the car still polls.** His second vehicle is sold
  and disabled. Its card was raised on 14 September carrying the raw VIN; the
  vehicle never polls again, so the clear never runs, so the id survived two
  releases. Two further holes had the same shape: the sweep took a list of VINs,
  and a sold car is in no list the code can build, and the call sat inside the
  cache-restore branch, so an entry with no cached snapshot never swept at all.

  The sweep now walks the integration's own issue registry and deletes any id
  ending in something VIN-shaped, on every setup, needing neither a VIN list nor
  a list of card families — so a family added later that forgets to mask is
  covered too. It matches the real VIN alphabet (ISO 3779 has no I, O or Q), so
  a 17-character tail that is not a VIN is left alone, and a masked id is never
  touched: that card may be showing a live warning. Nothing here changes what a
  card says or when it appears.

### Hinzugefügt / Added

- **The closure and lock sensors now say when the car captured them (#1950).**
  Asked for by @Adcad1970, who read the source first and corrected the premise
  this was going to be built on — see the entry below. Per-value freshness
  (`data_captured_at`, `freshness_source`) has been on numeric sensors since
  v4.7.11, but doors, locks, windows, boot and bonnet carried no capture time at
  all. On a portal-fed car those states are carried forward between snapshots,
  so a door state captured six hours ago rendered identically to one captured a
  minute ago — sitting right beside a battery reading that did show its age. A
  dashboard can now say "doors closed as of 15:36".

  The method moved onto the shared entity base instead of being copied into the
  binary-sensor platform, so **no platform file was touched** to gain it and
  every platform fed by the portal answers the question the same way. The
  existing gate does the limiting by itself: a live-read channel is already
  current at poll time, and a description without a data key has nothing to
  stamp, so neither gets an attribute. One caveat worth stating plainly: the
  stamp belongs to **that one field**. The newest capture in a snapshot is not
  every value's capture time, and that confusion is exactly what this closes.

- **The door, boot and bonnet locks now say when the car captured them (#1950).**
  Asked for by @Adcad1970, who then sent the shape of two real deliveries and read
  it correctly himself: every lock entry in his export carries its own
  `timestampUtc`, and the parser never dropped them. They were being lost one step
  later. Recording a capture time is opt-in per call site in the mapper, and no
  lock or closure site had ever asked for it — so those sensors reported
  `freshness_source: "dataset"` even though their own entry in the file was
  stamped. They now carry `data_captured_at` and `"point"`.

  **The door-lock sensor is an aggregate, and its stamp is the OLDEST reporting
  door's.** "All doors locked" is only as trustworthy as its stalest member: if one
  door's reading was captured two days ago, the verdict is two days old however
  fresh the other three are, and taking the freshest member would advertise a
  confidence the verdict does not have. If any reporting door carries no stamp at
  all, the verdict stays unstamped rather than borrowing a sibling's time — the
  sensor then reads "dataset" exactly as before, instead of a wrong "point". Boot
  and bonnet come from single fields and need no such choice.

  Nothing here depends on position in the file. His two deliveries, generated 44
  minutes apart, listed the same six locks in different places, so a result that
  moved with the order would have been wrong on at least one of them. The stamp is
  also recorded inside the branch that assigns the value, so an unsupported or
  invalid reading (0 or 1) records nothing and a verdict that came from another
  channel keeps its own provenance.

  One place it cannot appear: the `lock.door_lock` entity. That one has no data key
  — it reads the merged value directly — so the freshness attributes do not apply
  to it. The capture time is on the door-lock, boot-lock and bonnet-lock binary
  sensors.

### Geändert / Changed

- **Ready for Home Assistant 2026.11 before it reaches you (#1965).** The
  scheduled beta watch — not a user — found our own checks failing against
  2026.11.0b0, in three different ways that are worth separating.

  **The real change:** `ClimateEntity` got the native-unit treatment sensors
  have had for years. `temperature_unit`, `current_temperature` and
  `target_temperature` became deprecated aliases for `native_*` names, with
  removal announced for 2027.11. We are **deliberately not migrating yet**: the
  native names do not exist before 2026.11 — measured absent on 2026.10.1 — and
  this integration still supports 2026.6, so switching would break the climate
  entity on every installation that has not taken the update. For a custom
  integration the deprecation only logs a warning, so the entity keeps working
  on 2026.11 either way. A test now fails the moment the supported floor
  reaches 2026.11 and the old names are still there, so the migration happens
  on a trigger rather than on someone remembering.

  **A dependency that is not ours:** `httpx` is not part of Home Assistant's
  dependency set, so on an environment without it the HTTP/2 channel's three
  string returns are seen as untyped. They are now annotated, which is a
  statement of fact rather than a silencer.

  **And one false alarm, worth naming as such:** Home Assistant flipped the
  order inside its ALPN constant to prefer HTTP/2 — if anything an improvement
  for the volkswagen.de channel. Nothing of ours reads that order; a test of
  ours had pinned it, and so turned a cosmetic upstream change into a red
  build. It now compares the contents.

  No behaviour changes for anyone on any version.

- **A code comment called `last_seen_at` a delivery clock, which it is not
  (#1950, #1917).** @Adcad1970 found the contradiction in the source:
  `_capture_age_s` said `last_seen_at` "says when the delivery was last SEEN",
  while `compute_connection_state` and the EU Data Act mapper both document it
  as a capture time. The mapper is right. Every writer of that field takes a
  capture stamp and none takes a poll or wall clock — a test now measures that
  across the package rather than asserting it in prose.

  What made it the wrong anchor for the staleness verdict in #1917 is *which*
  capture it is: the freshest stamp known for the car, from any channel,
  advance-only, which can be hours newer than the values actually surfaced. So
  the verdict had been anchored on a real capture time, just not on the capture
  time of the data it was judging. The 5.1.3 fix stands unchanged; only its
  explanation was wrong. That wording had already travelled beyond the comment,
  which is the reason it is corrected here rather than quietly.

- **Code comments described the dataset-level capture time as a "~15-min"
  floor, which is not what it is (#1950).** It is the newest *car-captured*
  stamp in an export, and that is no duration at all: #1688 is this repo's
  standing case of a car whose own capture field sat five days behind every
  data point beside it. The 15 minutes is the portal's publish cadence, and
  even that holds only while the car keeps having wake events — a parked car's
  export repeats the last one.

  Nothing computed from it changed, and the parser's own docstring was always
  right; the shorthand that distant places used to refer to it was not. The
  same framing had spread to two further comments about merge order — a
  position pin and the static service data — so five comments were corrected,
  not three. It is corrected in public rather than quietly because the phrase
  had already been published: the 4.4.0 note further down still says "the
  portal's up-to-15-minute-old snapshot" about exactly these door and lock
  states. Shipped release notes are left as they were said.

  One finding worth passing on if you read the freshness attributes:
  `freshness_source: "dataset"` does **not** mean the value inherited a floor.
  It means only that no per-point capture time was *recorded* for that
  attribute — recording is opt-in in the mapper and few attributes ask for it —
  so a lock sensor can report "dataset" even though its own entry in the file
  did carry a timestamp. Either way that attribute carries no age, so nothing
  about it can be read as "roughly 15 minutes old".

  A test now pins what the comments assert and refuses a comment that prices a
  portal value at 15 minutes again. It also pins something that was found by
  measuring rather than by reading: a capture marker standing in the same list
  as a value is **taken as** that value's capture time, while the payload-wide
  floor is withheld. Two things are worth stating about that, because neither
  was: it is an inference from POSITION, and VW reorders the list between
  deliveries (#465, and @Adcad1970 measured the lock entries moving between two
  files on 30 Oct), so it is not the same thing as an entry carrying its own
  timestamp. And this repo cannot say which shape is more common — the only
  real export files in it are four from one CUPRA Born (#1195), all with
  markers, while marker-free exports whose every entry carries its own stamp
  are attested by #1688 and #1950 and by no fixture at all. Those two routes
  look identical in a single-marker file, which is how the wrong wording
  survived. One older test of the "newest wins" rule fed its input in
  ascending order only, so a "last one in the array wins" implementation would
  have passed it; it now feeds both orders.

## [5.1.3] - 2026-10-28 — No verdict without the evidence / Kein Urteil ohne Beleg

### Behoben / Fixed

- **An existing entry could not finish setting itself up, and the message
  blamed the account (#1947).** Reported on v5.1.2 by @mortenmoulder, @RichardPitt and
  @hausamsee, all on CUPRA, and diagnosed correctly in a single comment by
  @nijaobscvra666. The portal sign-in that v5.1.2 repaired succeeds, the read
  channel arms, a cached vehicle is restored — and setup then gives up every
  160 seconds with "No vehicles found for this account. The login itself
  worked", on accounts whose car is plainly visible in the portal.

  Nothing was wrong with those accounts, and nothing was wrong with the v5.1.2
  fix. These entries hold persisted tokens with no recorded strategy, which is
  why setup skips the fresh login; the token refresh is then refused, and such a
  refusal has been classified as *transient* since 2026-09-01, deliberately, so
  that a network hiccup would stop bouncing people to a password prompt. The
  fallback ladder that exists for exactly this situation — do the login that was
  skipped, and if that is refused as well, enumerate through the EU Data Act
  portal — was built thirteen days **before** that reclassification and only
  ever caught the other class. So the refusal walked past both rungs untouched,
  and the generic "no vehicles" wording is simply what the entry point reports
  when setup gives up without a reason of its own. It was never about vehicles.

  Both rungs now take both classes, **at setup only**. The poll loop keeps
  treating a refused refresh as transient, because there the entry has a
  last-known-good snapshot to stay alive on while the hiccup passes; setup has
  no snapshot, so "transient" meant retrying the same dead token file forever
  with nothing able to change the outcome. @hausamsee asked for precisely the
  outcome this produces — carry on with the channel that authenticated — and his
  car is the case the second rung now serves. The workaround people found,
  removing the entry and adding it again, worked only because it wipes the
  stored token file; it is no longer needed, and it cost everyone who used it
  their entity history.

- **A single stopped clock could switch the stale-data indicator off
  completely.** Found by auditing the fix above before it shipped, so it was
  never released — it is written down because the shape is worth knowing.

  The corrected verdict takes the newest of up to seventy per-field capture
  stamps. "Newest" is the smallest age, and a stamp dated in the **future**
  has a negative age, so it won outright: one car reporting a clock six hours
  ahead answered "six hours in the future" and the indicator read *not stale*
  on a feed that had been frozen for four days. Sixty-nine correct stamps
  silenced by one broken one.

  The verdict now judges on the stamps that are not in the future. Only when
  **every** stamp is future-dated does the negative answer stand, which keeps
  the deliberate behaviour from [#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465):
  a car whose clock runs ahead raises no repair card, because then there is
  nothing sane to prefer over it.
  ([#1917](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1917))

- **A parked car on a dongle is not a frozen feed, and no longer reports as
  one.** Also caught before shipping.

  The first version of the fix above consulted `data_captured_at` as a second
  source. That field is written in exactly one place — the KWP2000 dongle —
  and that client documents it as refreshing "only when the car is driven / on
  ignition". So the fix silently gave the dongle channel a staleness verdict it
  had never had, and every dongle car parked longer than three days would have
  reported its data as outdated. Correct arithmetic, wrong question: the
  indicator exists to say the feed broke, not that the owner took the train.

  The dongle's "Datenstand" is no longer part of that decision. It is still
  shown as the per-sensor *Data captured at* attribute, where it answers the
  question it can answer.
  ([#1917](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1917))

- **The indicator that tells you a reading is old was reading the wrong
  clock — and the capture time was sitting in the same snapshot all along.**

  @tdrieshof measured it on an Audi Q6 e-tron (PPE, Belgium, portal-only): the
  car was at **38 %**, Home Assistant showed **56 %**, and nothing in the
  interface suggested the number was two days old. His diagnostic is what made
  it checkable: the anchor the code read was about **22 hours** old while the
  car's own capture, quoted in his own log, was about **47 hours** old.

  A second report that looked identical turned out not to be this fault, and
  that belongs here rather than in a footnote: a Q4 whose charge target read 80
  against a setting of 50 looked exactly like a frozen feed, and the owner then
  checked the portal archives himself and found the source data genuinely wrong
  — readings four hours old against a fifteen-minute cadence, and a charging
  speed of 660 km/h held for three hours. That is VW's data being wrong, not
  ours being stale, and #1917 says so explicitly. It is named here because the
  symptom is the same and the cause is not, which is the whole difficulty with
  this class of bug.

  The staleness verdict asked "how long since `last_seen_at`", and
  `last_seen_at` says when the **delivery** was last seen. A channel refreshes
  that stamp even when every value inside the delivery is old, so the age came
  out as minutes no matter how stale the data was. The function's own docstring
  called that field "the car's own data was captured", which is the whole bug
  in one sentence.

  What makes this one unusual: nothing had to be collected. `field_captured_ts`
  — a per-field record of when the car captured each value — was already in the
  snapshot, already feeding the per-sensor *Data captured at* attribute, and
  already flipping that sensor's freshness label from "dataset" to "point". The
  per-sensor attributes knew the capture time while the verdict did not. The
  verdict now looks at it, preferring the **newest** capture (the question is
  whether the car recorded anything recently), then the dongle's own
  *Datenstand*, then the delivery sighting as before — so a channel that
  records no capture time behaves exactly as it did.

  A carried-forward field keeps its original capture stamp, which is the point:
  if every field is carried forward, every stamp is old, the newest is old, and
  the verdict fires.

  **What this does not fix, so nobody updates expecting it.** Two things:

  1. **The bar is 72 hours.** With the anchor corrected, @tdrieshof's two-day-old
     data is now *measured* correctly — 47 hours against the 22 the old
     anchor reported — and
     still sits under that bar, so his indicator stays off. While the anchor was
     wrong the bar never mattered, because the age was always minutes; fixing
     the anchor is what makes the threshold a live question for the first time.
     Three days is a long time for a feed that normally arrives every fifteen
     minutes. Lowering it means more cards on more cars, so it is a decision
     rather than a fix and it is not made here.
  2. **The 40 carried-forward fields still have no age limit of their own.**
     Only position has one, at 24 hours. This fixes the global verdict — "did
     the car capture anything recently" — so a wholly frozen feed is flagged. A
     single field freezing while others keep moving is a per-field problem and
     is still open.

  Pinned by 18 tests against seven mutations, including one that restores the
  old anchor. Why no test caught it before, measured rather than assumed: of
  the ten test files covering this area, not one set an old capture next to a
  fresh delivery, and both tests that call the age helper directly pass it a
  delivery sighting and nothing else. The function was covered only on its
  fallback path.
  ([#1917](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1917),
  [#1364](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1364))

- **The "raise your update interval" card could latch on for good and
  recommend a bigger number every time — and v5.1.2 is what made that
  possible.** This one is ours, introduced four hours after release, so it is
  stated plainly rather than buried.

  @clipse2004's CUPRA Formentor
  ([#1942](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1942)):
  he raised the interval, the card came back with a higher number, he raised it
  again, and so on. The escalation looked like repeated storms. It was not —
  the recommended value is derived from the *current* interval, so **one** flag
  that never clears produces 40 → 55 → 60 all by itself.

  The flag has exactly one setter and five clearers. The #1918 fix in v5.1.2
  added an early return so a bearer-less cookie session stops paying for a
  re-login that cannot work — correct in itself, but it sits *before* the
  budget check and before all five of those clearers. So: a client trips the
  budget while it still holds a real bearer (the flag goes up, rightly), the
  native plane then answers with the attestation wall *in the same session*,
  the portal fallback is armed, and from that moment every refresh leaves
  through the early return. Nothing can clear the flag again for the life of
  the client, and the card is raised on every poll with no storm behind it.
  That is the one state in which the advice is pure noise: a cookie session
  spends no refresh budget at all, so raising the interval cannot change
  anything.

  The branch now clears the flag on its way out. That is a measurement rather
  than an assumption — it returns precisely *because* it will not spend a slot.
  An account-lock flag is deliberately **not** cleared alongside it: nothing on
  that path checked whether the account is locked, and inventing an all-clear is
  the mistake this release is otherwise about.

  **That alone was not enough, and the reason is worth writing down.** Clearing
  it only on the next refresh assumes a next refresh happens. The data path asks
  for one only on a **401** — and the native block that sends a SEAT or CUPRA car
  to this fallback is a **403**. So on exactly the car the fallback exists for,
  nothing came back to run the clear and the card stayed raised until a restart.
  The flag is therefore now also dropped at the moment either read-only fallback
  is armed, which is the moment a storm becomes impossible. The evidence for
  that gap was already in this repository, in a test written days earlier that
  pins "a 403 does not recover"; it simply had not been connected to this fix.

  Why the #1918 tests could not see it: every one of them starts from a client
  built moments earlier, where the flag has never been anything but False.
  Asserting it is still False proves nothing about a flag that was True. Pinned
  now by the sequence itself, against six mutations — the first of which is a
  straight revert to the v5.1.2 code.

- **A locked car reported its doors unlocked, because the boot was counted as a
  door.** Found on the EU Data Act portal path and fixed there first; the entry
  below it covers the four other places the same mistake turned out to be live,
  North America included.

  There the tailgate's lock state was folded
  into the per-door `doors_locked` aggregation, where any unlocked member makes
  the whole verdict *unlocked*. So an unlocked boot on an otherwise locked car
  reported the doors as unlocked.

  @Adcad1970's Audi A6 e-tron is where it surfaced
  ([#1950](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1950)):
  "Doors Locked" and "Trunk Locked" moved together — identical timestamps,
  identical values — for hours while the car stayed locked.

  The direction he could not see is the worse one. On a delivery carrying *only*
  the tailgate's lock state, which this portal does send, the door verdict was
  decided entirely by the boot — and a locked boot then asserted **doors
  locked** on no door evidence at all. Measured before and after the change: a
  tailgate-locked-only payload went from a fabricated *locked* to *unknown*, and
  four locked doors plus an unlocked boot went from a wrong *unlocked* to
  *locked*. Only the boot's **lock** state was ever involved; an *open* boot
  never touched the door verdict, in either direction, and that boundary is now
  pinned too.

  The file already guarded against this exact hazard in the other dialect — the
  bare `locked` field is read under a dotted spelling precisely so the trunk
  state cannot mis-set `doors_locked` — and the historical `door_info.*` path
  has always aggregated doors alone, sending the boot lock to `trunk_locked`
  separately. Only the enum path got it wrong. The door verdict now comes from
  door fields; a tailgate-only payload leaves it unknown rather than stating
  something no field reported.

  Two consequences worth knowing, because they are not all upside. On a car
  whose portal delivery only ever carries the tailgate's lock state,
  `doors_locked` is now *unknown* instead of wrong — so the named `locked` and
  `unlocked` triggers cannot fire on it (an edge needs a real value on both
  sides), the `is_locked` condition answers "not locked" for unknown, and on a
  fresh install the "Doors Locked" sensor may not be created at all while
  hide-empty is on. In exchange, leaving the field empty finally lets the
  historical export path and the cross-channel gap-fill supply it — the old code
  occupied the field with the boot's value and blocked both.

  Why the existing portal tests never caught this is worth recording, because
  the obvious guess is wrong. It is not that they all supplied door fields
  alongside the tailgate: two of them feed a tailgate-only lock payload, which
  is exactly the broken shape. They passed because **not one of them asserted**
  `doors_locked` on it. The tests sat directly on the defect and said nothing.
  A field can be exercised by several tests and pinned by none — it is pinned
  now, against eight separate mutations.

- **The same mistake was live in four more places, and one of them was six
  brands wide.** After the fix above, the integration was swept for the pattern
  "a closure that is not a door decides whether the doors are shut". Every hit
  below was measured on the real parsers, not reasoned about, and each one broke
  the same two ways: it inverted the verdict against the real doors, and on a
  delivery carrying no door at all it fabricated a verdict from a single
  non-door member.

  **North America** (`doorStatus` and `exteriorStatus.doorLockStatus`): the boot
  and the bonnet rode in the list that decides both *Doors Open* and *Doors
  Locked*. Four locked doors plus an unlocked boot read as **unlocked**; worse,
  a locked boot on a delivery with no door fields at all reported the doors
  **locked** on no door evidence whatsoever. Both now come from door fields
  only.

  **Volkswagen EU — which Audi, Bentley, Lamborghini, VW Commercial and Audi NA
  all inherit unchanged**: the bonnet and the boot sat in the door aggregate and
  the roof sat in the window aggregate, so four closed doors plus an open bonnet
  reported an open door, and an open roof reported an open window.

  The part that makes this more than a tidy-up: **neither `hood_open` nor
  `sunroof_open` was ever written anywhere in that file**, and North America had
  no roof mapping at all. So the bonnet's and the roof's only effect on your
  system was to corrupt an aggregate they did not belong to. They now populate
  *Hood Open* and *Sunroof Open* — entities that already existed, already had
  names, and had simply never received a value on those channels.

  Kept deliberately: the per-closure *door* entities still include the boot and
  the bonnet. Those are intended — the translation table has named keys for both
  — so only the aggregate changed. The per-closure *window* entities lose their
  roof members, which is the opposite case: nothing ever translated `roofCover`
  or `sunRoofRear`, so they surfaced as window entities named after the raw
  backend key.

  The exclusions are deny-lists of known non-members, never allow-lists of door
  names. Those dict-iteration paths exist so a firmware-specific door id works
  without being enumerated anywhere, so an unrecognised spelling still counts as
  a door exactly as before — a fix that quietly dropped the next new door would
  be worse than the bug.

  One existing test had to change, and it is worth naming: it asserted that a
  raised bonnet plus an open boot meant "a door is open", on a fixture whose two
  side doors were both closed. It pinned the defect in place. 30 tests now cover
  the five sites, against 15 separate mutations.
  ([#1950](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1950))

- **"All closures secured" could say yes with the boot standing open.** It was
  deciding from at most three doors — the data dictionary documents a safe-state
  field for three of them and none at all for the front left — while the name
  promised every closure. Measured: three secured doors plus an open tailgate
  gave *secured*, with *Trunk Open* reading true on the same vehicle at the same
  moment.

  The arithmetic was widened to match the name rather than the name narrowed to
  match the arithmetic. It now also requires that nothing we can see is standing
  open, read from the boot's and the bonnet's **open** state — deliberately not
  from their own safe-state fields, which is the trap: v4.7.11 removed those two
  from this calculation after a live SEAT/CUPRA delivery reported the bonnet
  "unsafe" while a second field in the same dataset said it was closed. The
  dictionary documents no "safe" value for either of them, so that signal cannot
  carry a verdict. A test now pins that case so the widening cannot resurrect it.

  A closure we cannot see neither forces a *no* nor permits a *yes* on its own,
  so the claim is "every closure this delivery reported is secured". **This can
  change an automation's behaviour**: on a car that reports an open boot, an
  entity that used to read secured will now read unsecured — which is the point,
  but it is a value change rather than a cosmetic one.
  ([#1950](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1950))

- **Per-source connectivity sensors read "unavailable" for up to a whole poll
  interval after every restart.** The map those sensors are created from was
  computed on the poll path only, so after each setup and each reload they sat
  at *unavailable (restored)* until the next scheduled poll. For a diagnostic
  whose entire job is to say which sources a car is reaching, that reads as
  "this source is broken" rather than "not measured yet".

  @InfObject found it on a VW ID. Buzz
  ([#1954](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1954)) and
  brought the fix point with him: the computation is local-only — no await, no
  network — so there was never a reason to defer it to a poll. It now runs
  during setup as well, fail-soft, exactly as it does on the poll path.

  Two paths it does **not** reach, so nobody reads more into it than is there:
  a **companion (ADB) entry** skips that part of setup entirely — its first poll
  is immediate rather than an interval away, so the window is much shorter, but
  it is not zero — and a VIN whose setup read failed outright has nothing stored
  to put the value in.

- **A single "connection reset" on the dongle channel was offered to you as a
  defect worth filing.** The poll handler decides whether an error is
  self-healing — the car will be reachable again next poll — or something the
  Error Reporter should offer to file. Every branch of that decision inspected
  an `APIError`, which is the shape the shared request helper produces after it
  has retried a network failure and given up. Five of the fifteen channel
  clients do not go through that helper, and measuring what that actually means
  took two attempts:

  - the **dongle cloud** and **Skoda-official** convert nothing, so all four
    transient classes reach the handler raw and count as a defect — this is the
    gap that filed the issue;
  - **VW North America** converts three of the four into a backend-unavailable
    error the handler already understood, and leaks the fourth, a truncated
    response body;
  - **Porsche** retries and then raises the same tagged `APIError` the helper
    does, so it was already covered.

  An earlier version of this entry said a reset arrives raw on all five. It
  does not, and the correction is the same kind of care this release is about:
  the measurement that mattered was not "which clients inherit the helper" but
  "which ones let the exception through".

  That is what filed
  [#1959](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1959): one
  reset against the dongle cloud, on one car, over two days, on my own
  installation. Ordinary internet, presented as a bug. The cost is not that one
  issue — it is that noise in those reports teaches people to ignore the next
  one, and the next one may be real.

  The handler now recognises the transient network classes directly, and
  **imports that list from the request helper instead of restating it**, so the
  two cannot drift apart as one of them gains a class. The exclusion is by
  exception class only, never by which client raised it, so a genuine failure on
  the same channel is still reported.

  **What this does not change**, so nobody reads more into it. The Error
  Reporter has never filed anything on its own and still does not — it prepares
  a report and you decide whether to send it; this changes what it *offers*, not
  whether it asks. And a bare `OSError` is still reported: a connection reset
  reaches this point wrapped in an `aiohttp` class, while a bare one can just as
  easily be a local file or permission failure, which is worth knowing about.

## [5.1.2] - 2026-10-28 — Ten things it reported wrongly / Zehn Dinge, die es falsch gemeldet hat

### Behoben / Fixed

- **A readiness reading that never arrived was reported as the car being
  offline.** On the Volkswagen EU connector — which serves **Audi** as well —
  a missing field was collapsed into a definite *offline* instead of being
  left unknown. `None is True` is `False`, and that was the whole mechanism.

  @Mex-ai11's Audi A6 is where it surfaced
  ([#1851](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1851)):
  his entry reported *connection state: online* and *vehicle status: OFFLINE*
  at the same moment, on a feed that had been frozen since 12 October. On a
  feed that has stopped, the readiness field stops arriving with everything
  else — so the integration stated his car was offline while the official app
  showed it online. That contradiction is what sent him to re-authenticate and
  rebuild his entry twice, for nothing.

  The integration's own dataclass has said this must not happen since v2.0.1:
  *"Parser miss must NOT default to 'vehicle parked + offline'. Conditional
  automations like 'wake car when leaving driveway' relied on `is_online`
  being honest about its uncertainty."* The field is `bool | None` on purpose.
  Three of the four brand connectors check the type before assigning; this one
  did not.

  **A test was holding it in place**, which is the part worth saying out loud:
  `test_empty_payload_no_crash` asserted `is_online is False` on an empty
  payload — one line below asserting `battery_soc is None`, which gets the
  same question right. Changing that assertion is the point of the fix, not a
  casualty of it.

  Nothing downstream needed touching: the coordinator has treated the field as
  tri-state since #923 and reads only an explicit `False` as offline.

  Pinned by seven mutations. Two of the tests were wrong first, both in the
  same way and both caught by the mutation check rather than by review: one
  asserted a sentence appeared anywhere in `models.py`, where that phrase
  occurs three times, so deleting the one that governs this field passed on
  the other two; the other accepted **any** enclosing `isinstance` as a guard,
  and Škoda's assignment sits inside a type check on a different object, so
  removing its real guard passed as well. Proximity is not containment.
  ([#1921](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1921))

- **The "vehicle data hasn't refreshed" card now uses the name you gave the
  car.** @starwarsfan checked the previous fix on v5.1.1 and found it still
  wrong, in two ways, and he was right about both
  ([#1896](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1896)).

  **It ignored your rename.** The card was routed through the helper that
  builds a device name out of data — brand plus model, or brand plus the last
  six VIN characters — and that helper never consults Home Assistant's device
  registry. Renaming a device is an explicit statement about what the car is
  called, so a card that then calls it something else reintroduces the very
  "which car does this mean" problem it was built to solve. A name you set now
  wins over anything derived.

  **And on his car it fell through to the bare brand label**, `Audi (myAudi)`,
  which is what that helper returns when it has neither a model nor a VIN to
  work with. The VIN *was* known — it is what raised the card — but the call
  handed over the vehicle snapshot instead of the VIN, and on a snapshot that
  has gone thin the key is missing. The VIN is passed explicitly now, so the
  last-six fallback is always available.

  The registry lookup is wrapped: naming a car is a courtesy, the warning is
  the point, and a registry that cannot be read costs the nicer name rather
  than the card.

  **The previous close was wrong on its own terms**, and that is worth saying
  here rather than only in the thread. It described the design; his screenshot
  showed the implementation. The test that came with it asserted the card was
  named through the data helper — so it was pinning the defect, which is why
  nothing failed. That assertion now points at the corrected helper.

  Eight mutations, each breaking one part and asserting the named test catches
  it — including the two shapes of the original fault and a registry error
  being allowed to suppress the warning.
- **The service calendar showed nothing, on every brand, since it was built.**
  *Service due* and *Oil service due* have never rendered for anybody.
  @nijaobscvra666 reported it on a CUPRA Leon and did not stop at the symptom —
  he found the cause at the line, and he was right
  ([#1923](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1923)).

  The calendar's date parser accepted only strings, and **no writer in the
  integration produces a string for those two fields**. Every one of them —
  Škoda, SEAT/CUPRA, Volkswagen EU and the EU Data Act parser — stores an
  integer day count, because that is what the backends send and what the
  day-counter sensors read. So both events were dropped on every brand and
  both channels. The other seven events on that calendar were fine; their
  writers already convert at the source.

  It presented as an **empty** calendar rather than a missing one, which is
  why it survived so long: the setup gate only asks whether a service field is
  truthy, and a day count is, so the entity was created and then everything in
  it was discarded.

  The parser now takes day counts as well as dates, guards bools (`True` would
  have meant tomorrow) and rejects the sentinel integers backends ship inside
  error envelopes, where `-2147483648` would otherwise have become a calendar
  entry 5.8 million years in the past.

  **One decision worth recording, because it is invisible except for a few
  minutes around midnight.** Three places in the integration convert a day
  count to a date and all three anchor differently: `cariad/_util.py` on UTC
  midnight, the sensors on the machine's own zone, and the calendar on Home
  Assistant's configured zone. The calendar keeps its own, so it agrees with
  itself; making all three agree is a separate change with a wider blast
  radius.

  **Why this reached a reporter instead of a test**: the test that covers this
  fed the parser `"2026-12-01"` — a shape nothing in the integration produces.
  It was green, had always been green, and asserted a case that cannot occur.
  It now drives day counts, and the regression has its own tests alongside.

  Found in the same reading and not fixed here: the **HU/TÜV** entry on that
  calendar has no writer anywhere, so it can never fire
  ([#1925](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1925)).

- **The "data outdated" indicator never re-decided its verdict once a snapshot
  was republished.** On an entry whose feed had stopped, it kept reading
  *no* — indefinitely.

  **What this does not cover, so nobody updates expecting it to.** The verdict
  is computed from when the delivery was last seen, not from when the car
  actually captured the values inside it. A feed that keeps delivering on time
  while the payload is two days old therefore still reads as fresh, and
  @tdrieshof measured exactly that on an Audi Q6 e-tron: 56 % shown against 38 %
  in the car, with the indicator saying *no* and nothing in the interface
  suggesting the reading was old. That is a different hole in the same
  indicator, it is open, and it is the next piece of work rather than part of
  this one. His measurement also killed a heuristic I had been relying on —
  the values do move, because an old curve is being replayed late, so movement
  is not evidence of freshness
  ([#1917](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1917))
  ([#1920](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1920)).

  The verdict was decided in one place, during enrichment, and enrichment only
  runs on a poll that actually brought data back. Five separate paths
  republish the previous snapshot when a poll brings nothing — a failed poll,
  an empty one, a parse failure, an unexpected result shape, and a setup read
  that returned nothing — and every one of them carried the old verdict along
  with the old data. It also reached the on-disk store, because only keys
  beginning with an underscore are stripped before saving, so a restart read
  back a verdict the new session had never computed.

  Put together: a *not outdated* verdict decided while the data was still
  fresh could be saved, restored, and held through every empty read
  afterwards. @Mex-ai11's entry (#1851) served a nine-day-old snapshot while
  reporting itself fine, and the indicator meant to catch exactly that said
  nothing.

  The verdict is now re-decided wherever a snapshot is republished, including
  on load. That needs no fresh poll — the capture stamp is carried forward, so
  the age is knowable and the answer is true *now* rather than true when the
  data was last read.

  **One exemption deliberately does not apply here.** A stamp that reads old
  while the readings underneath it keep changing is not a frozen feed, and
  that case is excused during enrichment. On a republish nothing has changed
  by definition, so carrying the exemption across would answer "is this stale"
  with "it was not, last time".

  Eight mutations, each breaking one part. Two of the tests were wrong first
  and the mutation check is what said so — one accepted any mention of the
  re-decide anywhere in the enclosing function, and that function is 934 lines
  long with two such calls in it, so deleting the one being tested passed on
  the other.

- **A repair card could still be carrying your full VIN, and the fix that was
  supposed to clear it never ran.** If you have ever shared a diagnostics file
  from this integration publicly, this one is worth reading.

  A Home Assistant repair's internal id goes verbatim into Home Assistant's own
  config-entry diagnostics — a place this integration's VIN redaction never
  sees, as the code has said in a comment since the problem was first found.
  One card built its id from the unmasked VIN. That was fixed for **new** cards
  in v4.12.0, and the changelog said any older card "is cleared on upgrade so
  nothing lingers".

  **It was not.** The deletion sat inside the raising and clearing of that same
  card, so it only ran when the card was next raised or cleared — and for an
  export that has already timed out, neither ever happens again. The card
  raised before the upgrade simply stayed, through every version since.

  This is not a theory: someone running a version two releases past that "fix"
  attached a diagnostics file to a public issue, and it still carried the full
  seventeen characters.

  There is now a one-shot sweep at startup that deletes those ids for every car
  the entry knows. It is deliberately limited to the one card with the gap —
  its sibling clears itself on the next poll, so sweeping that one too would be
  code that never does anything, and a test says so rather than a comment.

  **What this does not do:** it cannot reach a file you have already uploaded
  somewhere. If you have shared a diagnostics file publicly, replacing it is
  still the only thing that removes what is already out there.

  The v4.12.0 entry above now carries a correction, because a changelog that
  tells people their data was cleaned when it was not is worse than one that
  says nothing.
  ([#1768](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1768))

- **A VW outage was reported as your data request being missing — and that
  advice made people delete working requests.** On 2026-10-22 Volkswagen let
  the EU Data Act portal's TLS certificate expire at 23:59:59 UTC. From
  midnight the portal could not be reached at all; it was measured still
  expired at 07:11 UTC and valid again by 08:25 UTC. Through all of it, every
  poll reported:

  > no data-request yet — enable the continuous data request for this car

  That was the opposite of the truth. The requests were alive and still
  producing files. People deleted theirs on the strength of that sentence and
  had to recreate them — and a new request only covers datasets from its
  creation onwards, so the gap does not come back.

  The mechanism: a read that fails in transport never gets an HTTP status, and
  the portal connector recorded nothing else. An expired certificate and a
  clean "404, no such request" both arrived as "no answer", so the code took
  the single branch it had. The same hole sat one step further on, where an
  unreachable dataset listing was filed as `empty` — "the portal answered and
  had nothing for us", which is not what happened either.

  A portal that cannot be reached is now reported as a **portal outage**, with
  the failure class named in the log and the advice stated plainly: your data
  request was **not** checked, so leave it alone. A portal that *answers* and
  names no request keeps the advice that helps, and that half is tested just as
  hard — a fix that turned a genuine "not set up yet" into a false outage would
  be the same bug facing the other way.

  From the other end of the same blind spot: when a sign-in strategy failed,
  the log named the exception class but dropped the HTTP status, so
  `UpstreamUnavailableError (message redacted)` was everything you had to tell
  a VW 5xx from a fault on your own side. A status code is not a secret and is
  now logged alongside the class; the message stays redacted, because that is
  what can carry a token.

  The notice shown when sign-in hits VW's device-attestation wall carried the
  same false certainty, in English and all eleven translations: the portal
  *"did not work for **this account**: check that data sharing is enabled for
  your car"*. The code never established that — at that point it knows only
  that the fallback returned nothing. Both reporters went through consent
  settings that were already correct, and one filed the wording itself as the
  bug. It now says what is known and gives the one check that tells the two
  causes apart: open the portal in a browser. If it loads, check your consent.
  If it does not, the portal is down and nothing on your side needs changing.

  Reported by @RaAdNe and @mathiasolofsson87. The certificate timings, the
  recovery steps and the "do not delete your data request" warning were
  measured and written up by @nijaobscvra666 while the outage was still on, and
  @scoma24 had asked for the missing status after having to produce a debug
  capture by hand.
  ([#1932](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1932),
  [#1933](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1933),
  [#1915](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1915))

- **A refusal the integration had already explained was still logged as "cause
  unknown", one line above the explanation.** @panther7's log had both halves
  side by side and they disagreed:

  > `command_unlock(***) classified as unknown`
  > `command_unlock(***) failed: … the car's gateway accepted your S-PIN and
  > then refused this integration's client identity for commands. This is not
  > your password, your S-PIN or your subscription — all three checked out.`

  The sentence was right; it comes from the code that read the gateway's
  answer. The classification beside it was wrong. The gateway's refusal is
  wrapped in an error type that carries no response body, and the classifier
  gave up on anything shaped like that before looking at what the error
  actually held — while the code that raised it had worked the cause out four
  lines earlier and kept only the prose.

  Both measured refusals now carry their cause as well as their wording, so
  the two lines agree. **Be clear about what this buys:** the log stops
  contradicting itself. Nothing in the integration reads these recorded
  reasons, so by itself this changes no behaviour, and the refusal it describes
  is still the car's answer — for @panther7 there is nothing to fix at his end.

  **What it deliberately does not do, which took longer to decide than the
  fix.** The obvious home for "the gateway refused our client identity" was the
  existing device-attestation reason, whose description reads almost like the
  message above. That reason is also one of three that mark a control
  unavailable for twenty-four hours. Using it would have taken his Lock button
  offline for a day in order to correct a log line, on a car whose controls are
  visible today. So the measured cause gets a reason of its own that records it
  and touches nothing, and whether a structurally refused command *should*
  disappear from the dashboard is left as the separate question it is.

  The reason list itself said the opposite of the code on this point — three
  reasons were documented as leaving the entity alone while in fact marking it
  unavailable, with nothing logged to say why — so it now states which ones
  change what you see. That documentation error is what nearly produced the
  regression above, and correcting it is probably worth more than the fix it
  accompanies.
  ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **A sign-in that could not possibly work was paying for itself out of an
  hourly budget, and the retries that mattered were then refused.** If your car
  is on the read-only EU Data Act portal fallback, the integration holds a
  placeholder instead of a real token, because the portal is a session rather
  than a token. Anything that still tried to read the manufacturer's own backend
  got turned away, and every one of those refusals triggered a fresh sign-in
  that landed straight back on the same fallback and changed nothing.

  There is a deliberate cap of three sign-ins per hour, because hammering a
  brand account gets it locked. A single poll made three of those reads, so one
  poll spent the entire hour's allowance on sign-ins that could not succeed.
  Fourteen minutes later the retries that would have fetched real data were
  refused for lack of allowance, and because neither of those reads remembers a
  failure, it repeated on every poll for as long as the fallback was live.

  @georghaberkorn68-ctrl measured it: two consecutive polls, the three retries
  in between, and the budget message that follows them. His own reading of the
  capture was right on every point.

  A fallback with nothing to refresh is now skipped instead of being charged
  for, on both the reading and the command allowance, and it says so once per
  episode rather than on every read. **What changes for you:** nothing about
  your data — the portal reads were never affected — but the retry after a
  missed reading now has the allowance it needs. One honest trade: the
  accidental side effect of those futile sign-ins was that they re-tried the
  manufacturer's backend a few times an hour, so if it started working again
  you would be back on it within the hour. That retry now happens when Home
  Assistant restarts or you reload the entry, which is the right place for it —
  the alternative is a password sign-in every hour, forever, against an account
  whose own backend may be closed for good.

  The sister channel that reads the manufacturer's website had the identical
  shape and is fixed with it. Two things this deliberately does **not** do: the
  three pointless reads are still sent each poll, and the separate flaw that
  let two simultaneous refusals both be charged is now unreachable here rather
  than repaired. Both are written up for their own fix.
  ([#1918](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1918))

- **SEAT and CUPRA could not sign in to the EU Data Act portal from 26 October,
  and the dialog told everyone their password was wrong.** The portal replaced
  its sign-in page with one that asks for the e-mail address and the password
  together instead of on two pages. The integration only knew the older layout
  and stopped as soon as it did not recognise what it was given — so the
  password was never even sent.

  Because the other sign-in route is refused for those two brands at the same
  moment, **both** ways in failed, and the repair dialog settled on *"e-mail
  address or password incorrect"*. That sentence was never established by
  anything. At least three people re-checked credentials that were correct the
  whole time, and one reported a working portal login, a live data request and
  files arriving every fifteen minutes while the integration insisted the
  password was wrong. Twelve reporters in three countries over two days, on
  Born, Tavascan, Leon ST, Raval, Formentor and Mii electric.

  Both layouts are now read. A page that asks for both at once gets both in one
  go; the older two-page sequence is unchanged, which is the half most of the
  test effort went into — a fix for two brands that broke the sign-in for every
  other would have been a worse outcome than the bug.

  The detection keys on **recognising a shape**, not on failing to recognise
  the old one: a page counts as the new layout only when it offers somewhere to
  type an address *and* somewhere to type a password. A page carrying a password
  box and nothing else is not posted credentials on the strength of it, and a
  page that is neither layout still fails loudly and still prints the field
  names it found — that list is what let the reporters identify the new page
  from the outside before anyone had read a line of code.

  One near-miss worth recording, because it was caught by deliberately breaking
  the fix rather than by review: the integration lifts a pre-filled address out
  of the page itself, so an **old** first page can carry an address field while
  still asking only for the address. Recognising the new layout from the
  address alone would have posted the password to a page that never asked for
  one.

  Reported by @revilo-1970, @georghaberkorn68-ctrl, @burratha, @Daftsios,
  @wilpatat, @nijaobscvra666, @peepprr, @Ryccou, @Jerjolmic, @lichti4,
  @tomasroud73 and @RichardPitt. @nijaobscvra666 named the function; @Ryccou
  worked out both halves unaided, including that the misleading message was a
  consequence rather than a cause; @peepprr established it was not CUPRA-only.
  ([#1947](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1947),
  [#1951](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1951),
  [#1953](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1953))
- **A recovery mechanism that never once ran has been removed, and the gap it
  was supposed to cover is now written down instead of pretended away.** Some
  sign-in paths leave a session that cannot renew itself: the credential simply
  expires after about two hours, and the only way back is to sign in again. In
  v2.8.0 a watchdog was added for exactly that — before each poll it checked
  whether every car had been failing and stale for more than twice the poll
  interval, and if so it signed in again quietly so nobody had to reload the
  integration by hand.

  Its very first check compared a session's label against a value that **no
  sign-in has ever written**. The label is a keyword into one of the sign-in
  flows, not something stamped on the resulting session, so the comparison
  could only ever be false. The watchdog returned immediately, for every
  account, on every poll, for as long as it existed. The same dead value also
  sat in a capability check, which quietly reported one capability short for
  those accounts.

  **Nothing changes for you**, and that is the point: nothing was happening.
  Removing it is behaviour-neutral, whereas repairing the check would have
  switched on a never-executed mechanism in a patch release — and it called the
  sign-in directly, outside the hourly limit that exists to stop an account
  being locked, so switching it on safely is a larger job than the bug is worth.
  A safety net that is believed and absent is worse than one that is known to be
  absent: two people read this code this week and both took it for working.

  The condition it was built for is real and is **not** fully covered by what
  remains — a failed read does trigger a fresh sign-in, but an expired
  credential does not always come back as the kind of failure that triggers it.
  That is now tracked on its own rather than left to a mechanism that was not
  doing it.

  Removing rather than repairing it was checked against the field before it was
  decided, not after. A read-only look at four comparable projects found **no
  proactive staleness watchdog in any of them** — no timers at all, and every
  sign-in reached either lazily, from a failing request, or from the setup
  dialog. The one proactive thing anywhere in the field guards a session that
  *can* be renewed, and its own history is the warning: it was added, then
  needed a sign-in fallback bolted on because rolling alone did not stop the
  session dying, and then needed a fix because a dead session kept it polling
  and sent the owner a fresh challenge message on every tick. That is the shape
  ours would have had.

  What replaced it is what was already there, and it is now tested end to end
  rather than assumed: a failing read drives exactly one sign-in and one retry,
  billed to the same hourly limit as everything else, and a failure that
  survives that does not loop. None of the four projects has such a test —
  theirs stub either the client or the very function under test.

  The reason this survived is that two reasonable halves were never checked
  against each other: something writes these labels, something else branches on
  them, and nothing asserted that the two sets meet. A test now pins that
  pairing for every label rather than keeping a list of the known-good ones —
  a list would have to be maintained by whoever forgot to pair them in the
  first place.

  Found while measuring an unrelated budget problem on the same kind of
  session, which is where the uncapped sign-in path and the dead gate both
  turned up.
  ([#1918](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1918))

## [5.1.1] - 2026-10-21 — Sensors that fill, names that fit / Sensoren, die sich füllen, Namen, die passen

### Geändert / Changed

- **Removed a constructor argument that looked like multi-brand support and
  did nothing.** While answering @bzykcar's question in
  [#1805](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1805) —
  whether any sign-in path is left that would reach the manufacturer channel
  for an Audi — the volkswagen.de connector turned out to accept a `brand`
  argument, and the runtime passed each entry's *real* brand into it. The value
  was stored on the instance and never read again, by anything. The connector
  is volkswagen.de in every path it has, so an Audi routed through it would
  have signed in to the Volkswagen site successfully, and anyone treating the
  argument as an Audi lever would have watched that work and believed it.

  A missing parameter is a question you have to answer; a dead one is an answer
  you can believe. Both it and a second never-read copy of the session object
  beside it are gone. Supporting another brand here needs a real
  implementation, and it will come back with one.

  No behaviour changes for any existing entry: every call site already received
  the Volkswagen site regardless of what it passed.

- **CHANGELOG.md merges resolve themselves now.** Landing seven pull requests
  on 2026-10-20 took **thirteen** CHANGELOG conflict resolutions, every one of
  them identical: both sides had appended one entry at the same place and "keep
  both" was always right. There was not a single code conflict in the batch —
  three of the seven touched the same files and their changes sat 26 to 39
  lines apart. All the friction came from one file.

  A one-line `.gitattributes` (`CHANGELOG.md merge=union`) resolves that shape
  with no markers and no human. It is only safe because of a property the
  repository already had: `add_changelog_entry.py` is insert-only, so the two
  sides of such a merge are additions in the same place rather than competing
  edits — and a test now says that out loud, so the driver cannot outlive its
  own justification.

  Reproduced both ways rather than assumed: without the driver the two appends
  conflict; with it the merge is clean, both entries survive, and the new one
  sits under `[Unreleased]` where it belongs. The test asserts the conflicting
  direction too, because a fixture that does not reproduce the problem proves
  nothing about the fix.

  One hazard is documented rather than fixed, and it is **not** caused by this
  change: while a release pull request is open it renames `[Unreleased]` to the
  new version, a feature branch appending to `[Unreleased]` does not overlap
  that rename, so git merges the two without stopping and the entry lands under
  the released version. Measured with and without the union driver — identical
  both times, because there is no conflict for a driver to resolve. It predates
  this file; `RELEASE_PROCESS.md` now says what to check and when.
  ([#1908](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1908))

- **Release notes are one line per change again, with the long form one click
  away.** v5.1.0's release body was **44 681 characters over 654 lines**,
  because the release workflow pasted the version's entire section of this file
  into it verbatim. That body is what Home Assistant shows in its update
  dialog and what HACS shows in the store listing, so the part a reader needs
  first — what changed, and does it affect me — sat under paragraphs of
  measurement and reasoning. Rebuilt through the new path, that same v5.1.0
  body is **6 222 characters over 99 lines**, of which the change list itself
  is 4 029 — the rest is the header, the diff link and the install notes the
  body always carried. The first number published here was wrong: it was
  measured on a different section and before the empty-bullet fix, and a
  line-by-line audit of the generated output is what caught it.

  Nothing here gets shorter and nothing is written twice. Every entry already
  opens with a bold title, and that title *is* the short form, so the builder
  reads the titles out rather than asking anyone to maintain a second list that
  would drift out of step with this one. Each line carries the entry's issue
  and pull request numbers and the people who reported or fixed it, and the
  body links this file at the release's own tag — not at `main`, so notes
  opened in six months still lead to what that version said.

  The long form stays the long form on purpose. It is written out in full for
  whoever is debugging the same thing later, and so that a summary of a release
  can be made from the reasoning rather than from the headline.

  Three defects were found by auditing the generated output line against line
  against the entries it came from, which is the check that the tests did not
  replace. A reference to a **Discussion** was emitted as a bare `#1415`, and
  GitHub numbers Discussions separately — so the one line whose subject is a
  discussion linked to *issue* 1415, somebody else's. Those are now explicit
  links. A cited precedent could be listed in front of the change itself
  (`#1313 #1679 #1843`), so the first number a reader saw belonged to a closed
  issue from months earlier; where an entry says which reference is its own,
  that one now comes first, and where it does not, 12 of 16 entries already
  list theirs first and nothing is reordered on a guess. And one line counted
  its three reporters without naming any of them.

  Pinned by eighteen mutations, each breaking one part and asserting the named
  test catches it. Two of those mutations were wrong before they were right,
  and both failures are the kind worth recording: one replaced the fix with a
  *different correct* implementation and so reported an unearned pass, and an
  earlier harness run died between mutating and restoring, left the mutation in
  the tree, and the next run hashed that file as the original — restoring the
  tree *to* the defect while reporting success. The harness now gates on a
  green baseline before it mutates anything and restores in a `finally`.
  ([#1912](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1912))

### Behoben / Fixed

- **An EV whose EU Data Act feed reports only the pack's energy content is
  recognised as having a battery again (#1902).** @keylogicjohan's ID.7 sends
  `REPORT_TYPE_ENERGY_CONTENTS` with the available and maximal kWh, but no SoC,
  electric range, charging state or pack voltage. None of the drivetrain tests
  could fire, so `has_battery` stayed false and every electric entity was
  skipped, including the available-energy and capacity sensors whose values
  were there. A capacity of 5 kWh or more now counts as evidence of a drive
  battery, the same way a pack above 60 V does since #1661: it sets
  `has_battery` only and leaves the EV-versus-hybrid verdict to SoC and range.
  5 kWh is far above a 48 V mild-hybrid pack and below the smallest plug-in
  hybrid pack. Thanks @keylogicjohan for the diagnostics and the analysis.

- **The "vehicle data hasn't refreshed" warning now says which car, and stops
  sending everyone to volkswagen.de.** @starwarsfan runs an Audi Q4 e-tron and a
  Škoda on one setup and got a card titled with the masked VIN alone —
  `***022149` — which is recognisable only to someone who has gone and looked it
  up. The warning told him something was wrong without telling him what. It now
  names the vehicle the way the device page names it, through the same helper so
  the two cannot drift apart, and falls back to the masked VIN when there is no
  label, exactly as before.

  The text was worse than the title. It told him to open **volkswagen.de** — he
  has an Audi and a Škoda, and that instruction was wrong twice over: the wrong
  site for a non-Volkswagen owner, and the wrong place even for a Volkswagen,
  because a lapsed EU Data Act feed is fixed in the portal rather than on
  volkswagen.de. His own reason for writing in is why that matters more than a
  typo would: he did not want to touch a setup that was working. A card that
  misdirects is a card that gets someone to break something that works.

  The opening sentence also named the EU Data Act as one of exactly two possible
  causes. This warning fires for **any** car whose own capture stamp has aged
  past the threshold, including one read over a brand channel, where that cause
  cannot apply at all. The opener is source-neutral now, and two short paragraphs
  say what to do in each case: check the continuous request in the portal if the
  car is read that way — and leave a working one alone — or, on a brand channel,
  nothing to re-add, the car simply has not reported. All twelve languages
  ([#1896](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1896)).

- **The Scout's "official spec field" column stopped being empty for 2857 of
  the catalogue's fields.** @GiuseppeAlbano's report
  ([#1895](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1895))
  listed one new Audi field with a dash where the official name belongs — and
  that field is in the shipped catalogue twice, with a description. The lookup
  reduced a dotted path to its last segment, on the assumption that a dot only
  ever separates the container from the field name. 3206 of the 7990 field
  names contain dots of their own: every `viwi_*` resource carries its
  interface version, and the charging families are spelled as nested paths. His
  field was looked up as `0_get_notifications`, which matches nothing. Only 349
  of those 3206 resolved.

  A quieter half came with it: `01_msp_elli.msp_elli_ocpi_cdr.currency`
  resolved to the generic `currency` field — a different field with a different
  unit and description — so a sensor auto-created from raw discovery could be
  named and united from the wrong entry. Specific spellings are now tried
  before general ones, and each index is consulted with the whole key rather
  than only the tail.

  Measured across every name, every prefixed name and every UUID in the
  catalogue (21226 keys): 5714 that resolved to nothing now resolve, 698 now
  resolve to their own exact entry instead of a generic one, and nothing that
  resolved before stopped resolving.
- **The FAQ now says where the vanished last-trip sensors went.**
  @fschulte2812 ([#1437](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1437))
  went thirteen days unanswered on a thread whose settled conclusion — "VW
  dropped the short-term cluster, there is nothing to fix" — was true of the EU
  Data Act portal and too broad as a general answer. The volkswagen.de channel
  had carried those figures since v4.11.0, and the parser for it was already
  owed when two reporters were told to stop looking. Nothing in the README or
  the FAQ mentioned any of it, so anyone with the same symptom found the thread,
  read the old conclusion and stopped.

  There is a FAQ entry now: which five sensors are affected, why they emptied,
  the three steps to get them back, and — because "add the channel" is not a
  complete restoration — a table of what it does **not** bring back
  (recuperation average, zero-emission distance, range gained while charging).
  It also points Audi owners at their own, different fault instead of sending
  them through a sign-in that cannot help them.

  A stale instruction is worse than none, so a test checks that what the entry
  claims is still true of the code: the sensor keys are read out of the
  document and matched against the real ones, the brand list against the
  channel's gate, and the `source: vw.de website` attribute against the label
  the code generates. If any of them moves, the entry gets corrected instead of
  quietly misleading the next reader.
- **An unmappable field stops asking three different people to file it, and
  dismissing the Scout card now sticks.** `eu_data_act.jobStatus` raised the
  user-facing Scout repair three times — on @Dirk-fs's Volkswagen
  ([#1831](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1831)), on
  @permyr's ID.7 Tourer GTX
  ([#1838](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1838)) and
  on @sssfamilientermine-wq's CUPRA Tavascan
  ([#1861](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1861)).
  The field is genuinely unmapped: the shipped catalogue has no entry for it at
  all. It is now kept out of the repair while staying fully visible in
  diagnostics — the samples (`JOBSTATUS_FLASHING`, `JOBSTATUS_DONE`) could be
  portal export-job plumbing or a software-flash job running on the car, and
  suppressing the data would close that question instead of answering it.

  Two faults turned up while doing it. The skip list was matched
  case-sensitively against a lower-case set, so adding the field as it is
  spelled by anyone would have skipped nothing while the list looked like it
  covered it. And the card was **deleted** whenever every finding was skipped,
  which is not the same as having no findings: Home Assistant stores a
  dismissal on the issue entry and deleting the entry discards it, so a field
  that kept reappearing kept raising a fresh, un-ignored card at someone who
  had already said no. Nothing-found still deletes the stale card; all-skipped
  now leaves it alone.
- **Plugged in and drawing nothing is no longer reported as charging.**
  @plainmad ([#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968))
  runs a Golf GTE Mk8 whose energy provider smart-controls the session, and
  captured the screen for the case nobody had: plugged in, charger supplying no
  power. The app says *"Charging status. Battery charge level: 86 per cent.
  Charging station shows current status"*, and we answered **charging** — as we
  did for *"Battery 86 % • Check charging station"* and for the button
  *"Start charging. Check charging status"*.

  The rule ended in a bare-verb search: the word "Charging" (or "Lädt" /
  "Wird geladen") anywhere in the label meant yes, with a list of explicit
  not-charging phrasings in front of it. That list cannot be completed — app
  4.3.2 needed one entry, 4.6.4 needs another, and "Start charging" was never
  covered at all.

  It now reads the state where the state is. Every dump we hold has one
  grammar, *"Charging status. … N per cent. `<STATE>`"* plus a compact tile
  whose state follows the separator, and the extracted clause decides. The bare
  verb counts only as a complete clause — which is the whole distinction,
  because the ID.3 on 4.3.2 writes the state as the bare word on a car that
  really is charging. Wording we do not recognise returns unknown rather than
  guessing, so the previous reading is left alone instead of being replaced by
  a confident wrong one.

  Measured over all seventeen battery fixtures: every label with a recorded
  expectation now comes out right, against four wrong before, and about twenty
  settings-screen labels ("Charging up to (50-100%)", "Reduced AC charging
  current") stop reading as charging. His dump is committed as a fixture, with
  his attribution.
- **The test-cohort share prompt no longer goes to entries that cannot produce
  a capture, and a probe that fails now says so.** @bzykcar
  ([#1805](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1805))
  enabled the opt-in cohort on a portal-only Audi, to help, and reported that
  `probe_outcomes` stayed empty. He was right, and two faults made it read that
  way.

  The prompt was gated on `hasattr(client, "command_captures")` — an attribute
  created unconditionally in the base client's `__init__`, so it was true for
  every brand and every auth strategy. The gate tested that a Python attribute
  existed, not that a channel was reachable. The capture it asks for is written
  inside the command confirm-poll, so an entry with no command path can never
  produce one; he was asked to share something that could not exist. It now
  consults `is_structural_read_only()`, this project's own answer to whether an
  entry can send a command. A working Audi with no volkswagen.de channel still
  gets the prompt, which is what that gate was added for, and SEAT/CUPRA keep
  theirs through the locale-capture flag.

  Separately, the three opt-in probes (position, state of health, range
  measurements) caught every exception, wrote one debug line and recorded
  nothing — so a probe that ran and was refused left `probe_outcomes` exactly as
  empty as one that never attempted anything. Each now records
  `error:<ExceptionType>` under its own key, the exception type only and never
  the message, which can carry a host or a path. The core read twenty lines
  below them already did this, which made their silence an inconsistency rather
  than a design choice.
- **The e-mail code step no longer tells you your password is wrong.**
  @kalwados added the volkswagen.de read channel, received the code by e-mail,
  typed it, and was told *"Login failed; your username or password are wrong"* —
  at a step he had only reached **because** his password was right. The code is
  sent only after the credential check passes; the password is the one thing
  that cannot be the problem there. He tried several times, gave up, signed in
  on volkswagen.de in a browser, and only then could he add the channel.

  A refused code now says the code was refused, in all 13 languages, and says
  outright that the password is not the issue — on both the flow he used and
  the setup flow a first-time install goes through, which had the same two
  routes to the same wrong verdict and was found while tracing this one. And an HTTP error from the site
  while the code is being checked is no longer reported as a bad code at all —
  that is the site failing, and asking for a new code against a server that is
  down cannot help. The sibling path at the password step was hardened for
  exactly this in [#1313](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1313)
  and [#1679](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1679)
  ("only a genuine 401 keeps the credential verdict"); the code step never was.
  ([#1843](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1843))

- **The charge-timer sensors and the charging calendar are no longer off by
  your UTC offset.** @keylogicjohan
  ([#1903](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1903))
  runs an ID.7 in Sweden, where the EU Data Act feed reported
  `next_charge_timer_start_at = 2026-10-20T18:28:00Z` for a session his charger
  logged as starting `18:28:00+02:00`. The wall-clock reading was right and the
  `Z` was wrong, so everything downstream ran two hours late.

  Fixed narrowly, and his own cross-check is why that was possible: he verified
  that the *other* timestamps in the same feed are genuinely UTC — `last_seen_at`
  against `instrument_cluster_time` — so this is two fields that are naive local
  time wearing a UTC suffix, not a feed-wide offset needing the car's timezone.
  The thirteen other timestamps in that module are untouched.

  Stripping the suffix would not have been enough: every timestamp consumer here
  reads a naive value as UTC, so the same two-hour error would have reappeared
  one layer down. The reading is re-stamped with the local zone instead. The
  limitation, stated rather than hidden: for a car in a different timezone from
  the Home Assistant instance this is wrong by the difference between them, and
  the feed carries nothing that would let us do better.
- **The Vehicle Status sensor was blank on every portal-fed car, of every
  brand.** @theblarney1 reported it permanently unknown on a portal-fed CUPRA
  Tavascan
  ([discussion #1415](https://github.com/its-me-prash/vwgroup-connect-ha/discussions/1415)),
  and the public diagnosis at the time was wrong in all three of its
  specifics: the sensor does not have one writer but two, the one that governs
  his car is a channel-agnostic derivation in the coordinator rather than the
  403-walled CUPRA call, and there is no engine-running gate in it.

  The real cause is wider. That derivation stamps OFFLINE / DRIVING / CHARGING
  / PARKED, and its PARKED branch required `is_online` to be `True` — a field
  the EU Data Act portal writes **zero** times. So on any portal-fed car
  `is_online` is unknown, no branch could fire, and the sensor stayed blank
  regardless of brand: Volkswagen and Audi as much as CUPRA and SEAT.

  It now reads PARKED when the feed affirmatively says the car is neither
  driving nor charging — both of which the portal does send. The checks are
  `is False` rather than falsy tests, so a car that reported nothing at all
  still yields unknown instead of a fabricated state; that case has its own
  test beside the #923 guarantee it belongs with. One pre-existing test was
  amended rather than deleted: its subject (unknown online is not OFFLINE)
  still holds and is still asserted.
- **Two diagnostics that described a setup the user no longer had.**
  @indigomejor ([#1850](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1850))
  found both while measuring v5.1.0.

  His portal-less entry logged *"3 polls with no fresh snapshot — standing down
  from the 60s drop-retry"* while his measured cadence stayed at 621-643 s
  against a 600 s interval, so nothing ever stood down: the counting block sat
  *before* the gate that asks whether a portal is armed. The number was true
  and the action it described never happened. Not purely cosmetic, which is how
  he reported it — the streak also kept climbing while the portal was off, so
  arming it later began with the retry budget already spent and the fast retry
  never got its first poll. Counting and logging are now gated on the same two
  conditions the scheduler uses; the anchor itself is still tracked
  unconditionally, because letting it go stale would spend the budget one poll
  after saving it.

  And his diagnostics kept reporting `skoda_official: disabled by source mode
  (mysmob_only)` after he had switched mode and the channel had been armed. The
  cause is a missing *write*, not a missing clear: the steady-state
  already-enrolled path runs on every poll and was the only arming path that
  recorded no label, so whichever label was written last stood for the life of
  the client. A clear would have been the wrong instrument — the failure labels
  added in #1901 exist so a probe that ran and was refused can be told apart
  from one that never ran, and a clear takes those with it.

- **An EV that sends no state of charge no longer gets an empty Battery level
  sensor.** Follow-up to
  [#1902](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1902):
  @keylogicjohan's ID.7 sends the pack's energy content and no state of charge,
  so once the drivetrain fix taught the integration to recognise it as electric,
  its electric entities appeared — and **Battery level** appeared with them,
  permanently empty, because the field it reads is one his feed never sends.

  `battery_soc` was the odd one out of its own family: `electric_range_km`,
  `battery_available_kwh` and `battery_cap_kwh` were all already in the set of
  keys whose entity is not created until the field is actually present, and it
  was not. It is now.

  Safe for every other EV, and the dynamic spawner is why: it re-evaluates on
  every poll and tracks what it has already added, so a sensor gated this way
  still appears the moment its value arrives. A normal EV gets Battery level on
  the first poll that carries a state of charge and keeps it; a restored
  snapshot carries the value forward, so an existing entry has it at setup.
  @bercedev deliberately left this out of the drivetrain fix rather than
  widening a ten-line change into a design argument, which was the right call.

- **A new setup no longer freezes six characters of your VIN into an entity
  id.** @benbrummer
  ([#1801](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1801))
  confirmed the volkswagen.de channel works on his Commercial Vehicles T6.1 and
  reported, alongside it, an entity whose id embeds part of his VIN while its
  friendly name reads correctly.

  Both halves were components behaving as designed: Home Assistant derives an
  `entity_id` once, from the device name at the moment the entity is first
  created, and never touches it again, while the friendly name is recomputed
  from live data on every update. So whichever entity spawns **first** fixes
  that id forever — and the one that spawned first was the push event entity,
  the only platform that needs no data to exist. At that moment there is no
  model name, so the device name falls back to `{Brand} {VIN[-6:]}`.

  The event entity now waits for there to have *been* a poll — not for any
  particular field, which would change what the event stream is for — so it
  appears one poll later with the model name known. The VIN fallback itself
  stays: on an account with two cars and no model data yet, those six
  characters are the only thing telling the devices apart. Existing entity ids
  are unaffected and can be renamed in the entity settings.

- **A release could publish with no change list at all, on a green run.**
  Found while cutting this release, in the path added by the notes split
  earlier in it. If a tag is pushed before `CHANGELOG.md`'s `[Unreleased]`
  heading has been renamed to the version, the notes builder refuses, the
  workflow catches the refusal and publishes the release with only a link —
  and that is the body Home Assistant shows in its update dialog and HACS in
  the store listing. The run stayed green and the only trace was a warning in
  a log nobody reads, so everyone would have seen an empty-looking release
  with nothing saying why. Tags are immutable, so it would have been found
  late or not at all.

  The release still publishes, deliberately: failing earlier would leave a
  public tag with no release and no `vag_connect.zip`, which is worse than a
  thin page. What changed is that the degraded path can no longer pass for a
  normal one. The body now states that it is incomplete, in both languages,
  and a final step turns the run red **after** the release and the asset
  exist — so nothing is lost and nothing is silent. The step also prints how
  to repair it without touching the tag.

  The same axis as the rest of this release, turned on its own release path:
  can the reader tell a failure from a success? Verified by extracting the
  workflow's own code and running it on both paths rather than by asserting
  about it — and the first version of the test that pins the red run survived
  a mutation, because `release.yml` carries a second `exit 1` in an unrelated
  step. That assertion is scoped to its own step now.
  ([#1916](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1916))


## [5.1.0] - 2026-10-20 — Saying what actually happened / Sagen, was wirklich passiert ist

### Hinzugefügt / Added

- **Six more readings from the EU Data Act feed: climate humidity and power
  draw, two battery states, the battery's own warning field, and the outside
  temperature sensor's health.** @Massen88's ID.4 Pro reported all six, and the
  report is what made them usable rather than merely visible: the official
  dictionary this integration ships already lists all six, but with **no unit
  and no type** — the car supplied the units VW left out (`Unit_PerCent`,
  `Unit_Watt`). Two of the new readings are real measurements, the humidity at
  the climate sensor and what heating and cooling are drawing in watts, which on
  an electric car is range you can watch. The other four are states, and all six
  arrive as diagnostics, switched off by default, on the portal cars whose feed
  carries them.

  Two were traps worth describing, because both are documented by VW's own
  catalogue and neither is obvious from the name. The battery's
  "charging active" signal **latches**: it stays active after the ignition goes
  on until the standstill flag clears, so it reads active while the car is
  merely switched on. It is therefore published as a raw signal and deliberately
  never becomes the charging state your automations use — that still comes from
  the brand channels. And the leaf whose name reads like an outside temperature
  is the outside temperature sensor's *fault status*; it is published as a
  status, and it is genuinely useful, because it says whether the outside
  temperature this integration already shows you can be trusted.

  The humidity reading is named after its source rather than a place: the
  catalogue says only "measured relative humidity", and while the signal's
  prefix and its sensor module both point at a cabin sensor, nothing available
  here proves cabin against intake air. It is kept separate from the existing
  outside-humidity reading, which comes off a different channel entirely, so a
  car reporting both will settle it ([#1863](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1863)).

- **Volkswagen Companion (ADB): VW app 4.8.1 support.** The Companion's reads
  and controls work again on VW app 4.8.1; departure time and Repeat edits need
  a direct ADB connection, and weekday changes stay in the app. Developed and
  checked on a Tiguan eHybrid in
  [gszigethy/vwgroup-connect-ha](https://github.com/gszigethy/vwgroup-connect-ha)
  (gszigethy/vwgroup-connect-ha#112, gszigethy/vwgroup-connect-ha#113,
  gszigethy/vwgroup-connect-ha#115): each read was compared with the app, and
  each control was sent once to the car through this code, read back and put
  back. Thanks @gszigethy.
  - **Commands on 4.8.1:** charging start/stop, the charge target, climate
    start/stop, the temperature dial, window heating alone, climate at unlock,
    automatic window heating, the climate zones, *Synchronise now*, and the
    departure timers (on/off, time and Repeat). 4.8.1 is listed per command
    after its own live test, not in the preset's read list, so app builds
    between 4.6.4 and 4.8.1, which nobody has checked, keep their reads and
    stay without commands.
  - **Departure timer editor on 4.8.1.** The app rebuilt the timer page; its
    time picker is hidden from `uiautomator` and its day buttons show no
    state. A 6 kB helper (`companion/a11y/`, Java source and build steps
    included, SHA-256 pinned) is pushed over ADB for the edit and removed
    afterwards. It reads the hidden wheels and sets them with their own
    accessibility action, so the time is checked before Save. A change of
    weekdays cannot be checked before Save on this page, so it is refused
    there (change the days in the app). The ADB Bridge add-on and the agent
    relay cannot run the helper and refuse the edit before changing anything
    on the page.
  - **Last long-haul trip:** five new Companion-only sensors (distance,
    duration, average speed, fuel and electric consumption) from the Driving
    data card 4.8.1 added. They appear only on Companion entries once the card
    was read, and are not mapped to any cloud or EU Data Act field.

### Geändert / Changed

- **The volkswagen.de HTTP/2 channel now uses Home Assistant's own SSL context
  instead of a private one.** When that channel was built, handing httpx a
  shared context was genuinely dangerous: httpx sets the ALPN protocols on
  whatever context it is given, so a context shared with the rest of Home
  Assistant made every *other* integration's connections try HTTP/2 and die
  with a garbled status line. @eurojojo hit exactly that, and it surfaced as a
  bogus "invalid credentials" on an unrelated login — the worst possible
  symptom, because it sends people hunting for a password problem they do not
  have ([#1679](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1679)). This integration therefore built its own
  context, in a background thread, because loading the certificate bundle
  blocks. Home Assistant 2026.2 fixed the problem at its root: it keeps a
  separate context per protocol set, so the HTTP/2 one it hands out is a
  different object from the HTTP/1.1 one everything else uses, and it builds
  them all up front. Asking for that one removes the private context, the
  background thread and the lock around it, and puts this channel on the
  sanctioned route. Nothing changes for cars. Which context gets handed over
  is now pinned by a test that checks the object itself, rather than one that
  checked how it was built.

- **The read-only volkswagen.de channel can now be added to a Volkswagen
  Commercial Vehicles entry.** @benbrummer could not add it to a T6.1, and when
  I went looking for the reason I expected to find one. The whole restriction
  was a single equality check at the top of the sign-in step, comparing the
  entry's brand against one exact string. Nothing downstream of it is
  brand-specific: the connector identifies itself to the site as `volkswagen`
  either way, because that names *volkswagen.de* rather than our brand list.
  And the two brands are already treated as one thing where it matters most —
  Commercial Vehicles uses the same We Connect app, and its EU Data Act
  configuration is the Volkswagen one with a different state name. His own
  report said the same from the outside: identical entity count and identical
  values whether the van is set up as Volkswagen EU or as Commercial Vehicles.

  What is still not established is whether volkswagen.de serves a Commercial
  VIN once the sign-in is allowed to start. That is a question about VW's site,
  and the gate was the thing preventing anyone from asking it; the channel is
  read-only, so the cost of being wrong is a failed sign-in the owner sees at
  once rather than anything silent. If Commercial VINs turn out not to be
  served, the gate comes back — this time with a reason attached to it. Every
  other brand is still refused, the abort text is unchanged so its twelve
  translations stay accurate, and a test checks that the commercial client
  really does inherit the arming method, because a widened gate that handed
  someone a channel which is stored, shown as configured and never armed would
  be a worse outcome than the refusal it replaces
  ([#1801](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1801)).

### Behoben / Fixed

- **When the manufacturer says "too many requests, wait N seconds", the
  integration now waits instead of asking three more times.** A throttled
  request was retried after 5, 10 and 20 seconds before the account-level pause
  engaged — three further requests at the exact moment the backend had said to
  stop — and the `Retry-After` header it sends with that refusal was not read on
  this path at all, so the pause that followed was a flat 30 minutes rather than
  the time actually asked for, which can be wrong in either direction. With the
  header present there is nothing left to find out by asking again: the retries
  are skipped and the client holds for what was requested, with a floor so a
  one-second value cannot become a loop and a ceiling at the half hour this
  kind of refusal already held for, so no header can stall things for longer
  than they could be stalled before. A backend asking for more than that is
  not waited out in full on purpose: resuming after half an hour now sends one
  request rather than four, and if that one is refused the refusal is honoured
  in turn. A refusal that carries no
  such instruction behaves exactly as before, because that one can still be a
  momentary burst.

  Two smaller things in the same place. The remaining-request-budget headers
  were being discarded on precisely the two responses that are *about* the
  budget, so someone sending diagnostics after a lockout could not show us
  their quota; they are now kept. And the pause is logged with the number that
  produced it.

  @indigomejor found this in his own lockout log and said what was wrong with
  it, after the first half of this issue was already fixed: the lockout came
  back at a *lower* request rate with no second client on the account, which
  ruled out the explanation everyone including me was leaning on and pointed
  here instead ([#1850](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1850)).

- **A portal feed that has stopped no longer overrides your polling interval.**
  For a car with the EU Data Act portal armed, the integration aligns its next
  poll to the portal's own delivery cadence — a snapshot a minute late is worth
  catching a minute later rather than a whole interval later. That retry had no
  limit, so on a feed that had stopped delivering it fired on every poll: the
  expected drop stayed permanently overdue and the cadence stuck at the
  three-minute lower bound for as long as the outage lasted, whatever interval
  you had configured. The retry now gets a budget of three polls, after which
  your configured interval applies again, and the first snapshot that actually
  lands restores the alignment. @indigomejor measured this on an Octavia:
  ten minutes configured, a flat 3.4-minute cadence across three days, roughly
  seventeen polls an hour, ending in a rate-limit lockout — and raising the
  interval could not help, because the interval was only ever the upper bound
  ([#1850](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1850)).

- **The volkswagen.de sign-in works again on accounts that get an e-mail
  code.** The advertising opt-in VW put in front of the login was already being
  declined, but only on the two paths that reach it before the code is
  entered. On an account that uses a code, that is never the case: the sign-in
  stops at the challenge page to collect the code, and the opt-in appears only
  after it is submitted — so for exactly the people reporting this, the fix in
  5.0.0 could not run. Entering a correct code ended with "login did not
  complete" and asking for a new one could not help, because the next one
  landed on the same page. The code step now declines the opt-in as the other
  two do, and it does so before judging the landing, which also covers the
  opt-in being served with an error status. @nuggie found the cause on 5.0.0
  and posted the log line that proves it — a sign-in chain ending at
  `consent.vwgroup.io` after the code POST, which only exists to be read
  because the same report round added logging to that step. @Fishermanjb
  reported it first and supplied the original logs, and @Ra72xx hit it
  independently on a second account and confirmed the workaround of declining
  the opt-in once in a browser
  ([#1827](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1827)).

- **Setup no longer fails on Home Assistant versions before 2026.6.** Every
  release since 4.13.0 stopped during setup with `setup failed: ImportError
  (message redacted)` and then looped on "No vehicles found for this account",
  because the repair-notice module imported a name — `RepairsFlowResult` —
  that Home Assistant only began exporting in 2026.6. That name is used
  nowhere except in type annotations, so it is no longer imported while the
  integration runs. Two things made this far harder to diagnose than it needed
  to be, and both are fixed as well: `hacs.json` still advertised `2024.4.0`,
  so HACS offered the update to precisely the installations it would break (it
  now declares `2026.6.0`), and the setup error withheld everything but the
  exception class, so "ImportError" was the entire diagnosis. It now also names
  the module and the symbol that could not be imported. Those are plain names;
  the exception message and the module's file path stay withheld, because the
  message can carry an access token and the path carries the account name of
  whoever runs Home Assistant. @thomascombe diagnosed the whole chain on a
  Golf 8 GTE — down to the file, the line and the version boundary, having
  first added that missing log line locally himself — and confirmed the same
  release sets up after upgrading the core ([#1858](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1858)).


- **A Škoda account no longer gets rate-limited by this integration's own
  retrying.** @indigomejor measured an account-level lockout and handed over
  what it took to find the cause: roughly 176 requests an hour, an HTTP 429 and
  then a hard refusal that pauses the integration for two hours. The official
  Škoda channel kept calling after it had started failing, because the guard in
  front of it only reacted to an explicit rate-limit answer — a 5xx was
  invisible to it, so a channel that was down was asked again every cycle. It
  now stands back for 5, then 15, then 30 minutes per channel after repeated
  failures, and resets as soon as a call succeeds. The reactive rate-limit
  guard still runs first, so nothing that worked before changes. He also ruled
  out the duplicate GitHub suggested, on version, cause, remedy and repair
  state, before filing ([#1850](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1850)).
- **Porsche remote commands no longer report "API error 201" while working.**
  Every lock, unlock, climate and charging call surfaced an error in Home
  Assistant although the car carried the command out. Porsche answers
  "201 Created" for an accepted command, and this was the one brand client that
  did not count 201 as success. The error message was the smaller half: the
  failure happened before the response body was read, and that body is where
  the command's own id and its "accepted" verdict live — which this integration
  uses to check afterwards whether the car really did take the command. So a
  command Porsche went on to reject looked exactly like one it performed.
  @tp9csmv79n-code found the cause and verified the fix before filing
  ([#1853](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1853)).
- **The "EU Data Act portal session expired" repair no longer opens after every restart.**
  The session had not expired. Since each entry got its own portal cookie jar (#1793), the
  startup check for the continuous data request, and the one-time export, still went out on
  Home Assistant's shared session. After a restart that session has no portal cookies, so
  the portal answered 401 and the repair asked you to sign in again, only for it to come
  back on the next restart. Both now use the entry's own portal session for cookie
  logins, including supplementary portals. Bearer-only device-grant entries skip the
  cookie-only kickoff and must create requests in the portal UI; manual request and
  export actions explain this requirement. An entry unloading during a data-request
  check or export no longer attempts a closed session or saves a retry timestamp
  that would delay provisioning after reload. Thanks @gszigethy.

- **The "Unknown user" notice now only says that when the login actually answered it.**
  `17eab6f9` (#1809) stopped the repair notice and the setup abort from calling a backend
  refusal "an MEB / ID-family car" — an Audi e-tron 55 quattro, a GE-platform car from 2019,
  had been told it was an ID.3/ID.4/Enyaq/Born/Q4. What replaced that claim was narrower and
  checkable: "the durable Car-Net login answered Unknown user for this car". The rule deciding
  when to say that was left exactly as it was, and on that rule the sentence reaches people
  whose login never answered it. A bare `invalid_grant` — the generic OAuth2 rejection, also
  produced by an audience mismatch (#464) and by a refused register — was read as the same
  verdict, and the entry's *other* write site flagged it on ANY mint failure at all, a 5xx or a
  timeout included. The one field that would have told the two apart, `error_description`,
  carries the actual "Unknown user" text, but the #1355 redaction dropped it before the setup
  flow ever saw it, so even a true claim could not have been substantiated. Measured live
  against an Audi e-tron 50 quattro, MY2022 — MLB-evo, not MEB: `HTTP 400`, `error=invalid_grant`,
  `error_description="Unknown user <account-uuid>"`. The description is now carried on the
  exception as an attribute (never in its message — it embeds an account UUID), and a new
  classifier decides on it: only a confirmed "Unknown user" keeps the Car-Net wording, and
  everything else — a 5xx, a timeout, an audience mismatch, an `unauthorized_client` — gets its
  own notice that says the cause is undetermined rather than guessing one. Ten of the twelve shipped languages still carried the pre-`17eab6f9` "this is an
  ID/MEB model" wording in this same notice and in the setup abort — `en` and `de` were fixed,
  the other ten were not caught by the translation-parity test because the keys still existed,
  just with the old text — so this PR carries the correction and the new notice to all of
  them. Setting up the EU Data Act portal with MBB commands no longer loses the portal when the
  command channel fails for any other reason: every mint failure now keeps the read-only
  portal entry with the reason recorded, a refusal already at register is classified like one
  at the token exchange, a Reconfigure no longer carries an earlier verdict into the next
  attempt, and the previous notice is taken down when the reason changes. Measured on, and the
  fix contributed by, @woifh's own Audi e-tron.

- **A sign-in Volkswagen has walled off no longer costs up to eight rejected attempts and a
  wrong explanation.** On VW EU and Audi the primary login reaches the very last step — right page,
  right POST, `authenticated`, authorization code in hand — and then the exchange of that code
  for a token is refused with `400 invalid assertion headers`. Nothing about the account is
  wrong, but the integration treated it as one more rejection to retry: it walked the whole
  `client_id × qmauth` candidate chain — **eight rejected sign-ins per login on VW EU** (four
  client ids × two qmauth secrets; the log in #1712 shows attempts #0–#6 moving on, then the
  last one failing) **and six on Audi** (three × two), and a refresh that fails falls back to a
  login — and ended on "all candidates exhausted" — a message that reads
  like a credentials problem, which is what sent people re-entering a password that was already
  correct. It now stops once every qmauth secret has drawn that answer (two attempts on either
  brand;
  one refused secret alone does not stop it, because the chain keeps the prior pair for VW
  re-rotations), and only for Audi and VW, the brands that sign those headers. This is the same
  wall as #1165 on VW North America, which has failed fast with its own honest error since
  July; the European side simply had no equivalent, so it now gets one — in the config flow,
  and also at setup and on re-login, where the read-only portal fallback used to hide it: if
  the portal fails too, the entry now stops with this reason and its own repair notice instead
  of "invalid credentials". (It already stopped there before rather than retrying, because
  "invalid credentials" is a hard setup reason too; what changes is what it tells you.) Why
  retrying cannot help was settled against the shipping app rather than assumed: myAudi 5.8.1 carries no
  `qmauth` symbol in any of its six DEX files or its native libraries, nor the HMAC secret the
  integration signs `x-qmauth` with, while it does carry the Play Integrity client
  (`StandardIntegrityManager`, `requestIntegrityToken`) and still sends `x-assertion`. The app
  has moved from the HMAC scheme to a Google-signed attestation bound to VW's package and
  signing certificate, which no open-source client can mint — so there is no candidate left for
  the chain to find. That also answers the question #1712 left open, and not in the hoped-for
  direction: the credentials have not merely rotated. What changes for you is honesty and cost,
  not access — the primary login stays blocked, vehicle data keeps flowing through the
  read-only EU Data Act portal where that works for your car, and where it does not, the
  integration now says so in every shipped language instead of blaming your password. Measured on an Audi e-tron 50 quattro, MY2022, and
  contributed by @woifh (#1712).

- **Signing in again with an e-mail address and a password now discards the
  expired sign-in it replaces.** On an entry first set up with the brand app's
  code sign-in, the old token was kept in two places and neither was replaced,
  so the reload spent a refresh attempt on a sign-in the manufacturer has
  retired before it got round to using the new password — and that wasted
  attempt counted towards the pause that protects the account from being
  rate-limited. The leftover was also still listed in the diagnostics
  afterwards, where it looked exactly like the cause of the failure that
  followed; @ratclma spotted it there and asked the right question about it.
  Entries that do have a password keep their stored tokens, because for Audi,
  Škoda, SEAT and CUPRA the same kind of token is the normal durable channel
  ([#1813](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1813)).

- **A "portal session expired" notice no longer survives the sign-in that fixed
  it.** The notice asks you to sign in again, and data arriving through the
  portal afterwards is the proof that you did — but clearing it also required a
  flag that only existed on the object which had raised it, and reloading the
  entry replaces that object while the notice itself persists. So anyone who
  reloaded, or whose entry was reloaded for them, kept being told their session
  had expired while their car was updating normally. The clear now rests on the
  evidence alone. Found by @Anoxym, who read the code and sent the sequence
  rather than the symptom ([#1867](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1867)).

- **A SEAT or CUPRA entry reading through the portal stops being nagged about an
  access path it no longer uses.** The notice about outdated app headers is
  cleared for a portal-served entry, and has been since 4.7.x — but only from
  inside the polling loop, so an entry whose poll does not complete kept the
  notice for as long as the entry existed. @georghaberkorn68-ctrl reported one
  standing at 535 since August, next to a car whose data was arriving fine. It
  is now also cleared when the entry starts up. An entry that is *not* reading
  through the portal keeps its notice, including across a restart: a real
  access problem should not blink out and come back
  ([#1866](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1866)).

- **When the SEAT/CUPRA user lookup fails, the log now says what happened.** It
  used to print one sentence with nothing in it, so a refused request, a
  forbidden one, a timeout and a malformed answer were indistinguishable — and
  @georghaberkorn68-ctrl spent a twelve-minute debug capture on a question that
  no log this code could produce was able to answer. The exception and, where
  there is one, the HTTP status are now named. Deliberately nothing else: that
  error object also holds the request address and the response body, which are
  the two things this line must never grow
  ([#1866](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1866)).

- **Diagnostics now name the portal field a value came from, not only the
  channel.** @Joassens reported a Passat GTE whose fuel level sat at exactly
  100 % across 467 km of driving while the tank went to half, killed his own
  "stale because I hadn't burned any fuel" theory with the odometer, and ended
  with the sentence this change exists for: *"I can't tell which from
  diagnostics, since they don't include the raw portal field."*

  He was right, and nothing in the file could have told him. The portal parser
  reads most fields from a list of candidate leaf names, first present wins —
  the fuel level alone has five. `field_sources` recorded which *channel* won
  and `field_captured_ts` when the car measured it; neither recorded which
  *leaf* won. Elimination could not recover it either, because `first()` marks
  every candidate of a call as consumed along with their walker synonyms, so all
  five vanish from the unmapped-field list together. And the function that
  stashes the provenance was already being handed the chosen leaf — it used it
  to look up a timestamp and then discarded the name.

  It is kept now, as `field_source_leaf`, following the same path as its two
  siblings: never gap-filled field by field, rebuilt in the channel merge from
  whichever channel owns the surviving value, and carried with the value through
  a historical import. That last part is the one with teeth — a leaf name that
  outlived the value it described would blame a portal field for a reading that
  came from somewhere else, which is worse than recording nothing, so a test
  measures a merge where one field keeps its leaf and another loses it in the
  same pass. The fuel level, having now been disputed by two reporters, was also
  added to the handful of fields that record their provenance at all
  ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465)).
- **A refused command now explains itself in the log, not only in the Home
  Assistant dialog.** @Joassens tested the MBB client-identity refusal on a
  Passat GTE and confirmed the message reads correctly in the UI — the car's
  gateway accepted the S-PIN and then refused this integration's client
  identity, none of it the owner's fault. Then he looked at the log file for the
  same event and found one line: `command_start_climate(***074295) failed:
  VehicleCommandError (status=None)`. The whole explanation lived only in the
  error the UI surfaced, so anyone working from a log — which, when a command
  fails, is usually the person who was asked to send one — got a class name and
  a null status.

  The reason a command error carries is now part of that error line. It applies
  to `VehicleCommandError` alone, because every reason that class carries is
  prose written for the owner and already shown to them; for every other
  exception the line still logs the class and HTTP status only. That restriction
  was already there and stays, but its stated justification was out of date: it
  said a raw exception string can carry the VIN-bearing command URL, and
  `APIError` has masked the VIN out of its own message since the #1355 redaction
  work. What the restriction actually protects against is the arbitrary
  exceptions that land in the same handler — a network or ADB library error
  whose text nobody here has vetted. Both halves of that are now pinned by
  tests, including one that fails if `APIError` ever stops redacting, so the
  comment above the log line cannot quietly become wrong again
  ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)).
- **A Companion screen that could not be read is no longer reported as a screen
  with nothing on it, and one failed read no longer costs half an hour of
  them.** Two defects of the same shape, found by reading the three Companion
  transports against each other.

  The direct-ADB transport has refused a screen dump with no node tree in it
  since v2.26.0, because a failed `uiautomator` run leaves its output file
  untouched and the previous screen would otherwise be parsed as the live one.
  The phone-agent relay overrode that method and returned whatever the agent
  sent, so an agent that walked the accessibility tree and found no window —
  display off, a secure screen, the car app not in front — reported success with
  nothing in it. Zero nodes is what the read path treats as a car that had
  nothing to say: the overview anchor check is skipped, the adaptive failure
  backoff is reset, and the poll is recorded as healthy. The one outcome that
  most needed to be visible was the only one that left no trace anywhere. The
  relay now applies the same guard as its sibling.

  And on the ADB side a single empty dump bought the full failure backoff — 30
  minutes, doubling per consecutive failure to six hours — with no second
  attempt. But `uiautomator dump` gives up when the screen does not go idle,
  and an animation or a passing toast is enough to cause that; it is gone a
  second later. The dump is now retried once, after a short settle, before it
  becomes a failure, and the error says it tried twice. Three deliberate limits:
  the retry re-runs the whole command rather than only re-reading the dump file,
  so the stale-screen protection stays intact; a transport error is **not**
  retried, because the connection has already been dropped for the next read to
  rebuild and a second attempt could only report "not connected" over the real
  reason; and the healthy path still costs exactly one round trip. On the relay
  there is no retry, because another attempt there means another trip through
  the agent's own poll and the usual cause of an empty tree does not change in
  that time.
- **The token refresh limit no longer announces a pause it never takes, and no
  longer reports itself at error level once every poll.** The limit itself is
  unchanged and correct: three refreshes per rolling hour, which is what keeps a
  misbehaving entry from hammering the sign-in until the account is locked. What
  was wrong was everything it said about itself. The message read *"pausing to
  prevent IP ban; please reauthenticate from the UI"*, and nothing paused — the
  call refuses one attempt and returns, so the next poll asks again and is
  refused again. @georghaberkorn68-ctrl's CUPRA logged that sentence three times
  per cycle, every three minutes, for hours across two days, which reads as a
  runaway loop rather than as a limit doing its job. And the one instruction it
  gave could not help him: his primary sign-in was being refused outright before
  the portal fallback took over, so no credential he could type would change the
  answer.

  The refusal now says what it does — that it is refusing further refreshes, and
  roughly when the next one is allowed, computed from the oldest attempt still
  inside the window rather than from a constant. It is logged at error level
  once per episode and at debug level while the budget stays spent, and the
  "episode" resets as soon as an attempt is actually booked, so a genuinely new
  storm weeks later is reported as news again. Where credentials are mentioned
  at all, it is to say that re-entering them will not help when the sign-in
  itself is what is being refused, and the errors that say *why* it is refused
  sit directly above the line. The same guard exists a second time in the
  Porsche client, which is not a subclass and had its own copy of both the
  wording and the level; both are fixed, and a test fails if a third copy of the
  old sentence ever ships
  ([#1866](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1866)).
- **Volkswagen Companion (ADB) reads on VW app 4.8.1.** The parking position
  read taps the button around the app's *Vehicle location* label (4.8.1 made
  the label itself not clickable) and never the map. The Driving data
  carousel is read whatever card it opens on; the first read sweeps both ends
  and remembers which cards exist, again daily. Departure timers read their
  weekdays from the list's recurrence label and Repeat from the new editor
  (gszigethy/vwgroup-connect-ha#112, gszigethy/vwgroup-connect-ha#113).

- **Importing a historical export that no longer exists now says so, instead of
  showing a green tick.** @placidcasual98 confirmed that after v5.0.0 the
  import works — battery level, electric range, charging schedule and the three
  departure timers all arrived on his car and stayed — but he got there the slow
  way. His first attempt ran against an export that had expired off the portal,
  and `vag_connect.import_historical_export` returned quietly, which ends the
  service call normally and makes Home Assistant draw a success tick. Nothing
  had been imported. He only worked out why by opening the portal himself, and
  said what would have saved him the time: *"A message saying no file was found
  would have saved me some time."*

  The service already logged which of the failure modes it was; what it did not
  do was fail. It now raises, exactly as the neighbouring branch already does
  when the portal is not ready at all, and the message carries the portal's own
  reason — `no_request` means the one-time export was never requested or has
  since expired, `empty` or `no_content` means the portal took the request but
  has not produced the file yet. In all twelve languages. A failed import still
  writes nothing, pushes nothing and leaves the snapshot untouched, which is the
  half of the old behaviour that was always right
  ([#1403](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1403)).

- **A Companion cancellation test no longer fails at random.**
  `test_cancelling_during_the_upload_lets_it_finish_before_cleanup` waited a
  fixed 0.05 s and then assumed the helper upload was in flight. In a full-suite
  run on a loaded thread pool it sometimes is not: the work item is still queued,
  cancelling drops it before it ever starts, and the test then fails for the one
  reason that is not a defect — there was no upload to let finish, and so no
  cleanup race either. It now waits for the upload thread to actually start
  before cancelling, which is what the test's own name claims it does. No
  production code changed; the behaviour it guards is unaltered.

- **A portal session that has expired no longer makes the integration re-post a
  data request and re-raise the same notice on every restart.** @alagerqv read
  the kickoff loop and found what his own entry was doing: his recorded attempt
  time sat frozen at 10 October, long past the 24-hour window that is supposed
  to hold the next attempt off, so every setup tried again and raised the
  "portal session expired" card again.

  The cause is one word. The loop records the attempt before posting, with a
  comment explaining that the record is what makes the backoff survive a
  restart — and the session-expired handler then returned straight out of the
  method, past the only line that writes it. The promise in the comment and the
  behaviour of the code had been disagreeing since the handler was added. It
  breaks out of the loop now instead, so the record reaches the write.

  That alone would have fixed only half of it. The handler also records the
  attempt itself when nothing has yet: a refused *probe* raises before the
  record is made, and a probe the portal refuses is a failed attempt exactly as
  much as a refused post is. An identifier adopted for an earlier vehicle in the
  same pass now survives too, instead of being discarded along with everything
  else.

  And three places raised this condition without logging anything, which is why
  the card turned up in his log with no line next to it saying where it came
  from — one of them sitting directly above a sibling branch that has always
  logged its status. All three now say what happened, and the card itself
  announces that it is being raised at a level a normal installation records
  ([#1867](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1867)).
- **A trigger or condition scoped to one car no longer applies to every car on
  the account when the scope cannot be resolved.** The helper that turns a
  config's `vin:` option or `target: device_id` into a set of VINs returned an
  empty set for four different situations and documented one of them: nothing
  was asked for; a config shape we cannot read; a `device_id` the registry no
  longer knows, which is what a car removed and re-added leaves behind; and a
  `target:` expressed with any other field, such as an area or a label.

  Both callers then failed open on all four. The trigger ended up subscribing
  with `vin=None`, which is the account-wide listener the dispatcher fires for
  every VIN, and the condition's `if vins and …` guard is skipped entirely on a
  falsy empty set, so every vehicle was tested. The two cases that say *"I meant
  one car"* therefore did the opposite of what was asked, and said nothing about
  it — an automation written to unlock-trigger on one car ran for all of them.

  The helper now answers three ways instead of two: nothing asked for, a
  resolved scope, or **asked and resolved to nothing** — and the last of those
  matches nothing rather than everything. It also logs a warning naming the
  target that could not be resolved, because an automation that has been firing
  account-wide by accident would otherwise just stop one day with no
  explanation. Unscoped triggers and conditions are untouched and still apply
  to every vehicle, which is their documented behaviour.

- **Two portal buttons no longer show a success tick over a refusal.**
  @Dulcow pressed "Create EU Data Act data request", watched his activity list,
  and saw the press recorded and then nothing at all — no success, no failure.
  He found out only by opening the portal himself that no request had been
  created. The integration had the portal's answer the whole time: it records
  the status for diagnostics, and had no way to reach the person standing in
  front of the button.

  Its sibling had the same shape. The one-time historical export returned
  quietly both when the portal refused the request and when the session had
  expired, so that button reported success too — while the *import* half of the
  same feature was changed for exactly this a few hours earlier. Two halves of
  one feature should not disagree about whether a failure is worth mentioning.

  Both now say what happened, with the portal's own reason where there is one,
  in all twelve languages. The create button passes its vehicle so the answer
  is about *that* car, and clears any verdict left by an earlier press so the
  message belongs to the press you just made. Two things deliberately did not
  change: a successful press is still silent, and a refused one still leaves
  nothing behind — in particular a refused export does not start the
  client-side "pending" clock, which would have shown an export that does not
  exist. The export's error is raised by the button rather than deeper down,
  because the same code also runs while Home Assistant is shutting the entry
  down, where a failure is neither a refusal nor something anyone is waiting
  to be told about.
- **A Volkswagen server outage or a rate-limited account is no longer reported
  as a wrong password.** The login walks a list of strategies, and its catch-all
  redacts the message of whatever the last one raised — for a good reason,
  written at the site: a low-level network error's text can carry the full OAuth
  callback URL, and those tokens decode to the owner's e-mail and a working
  access token. That redaction stays. What was wrong is that the error's **class**
  was thrown away with its message, so everything came out as a plain
  authentication failure.

  That was never only a wording problem. On the polling path an authentication
  failure becomes "invalid credentials" and starts a re-authentication flow, so
  a VW 5xx storm or an account their backend had temporarily rate-limited asked
  people to re-enter credentials that were never wrong — the exact
  reconfiguring-during-an-outage that the dedicated error classes were created
  to prevent, with their own translated messages already sitting in the config
  flow and their own handling already in the coordinator's self-healing-error
  check. All of it was simply unreachable from that one `raise`.

  Three classes now come through as themselves: the backend-unavailable error,
  the rate-limit error, and the volkswagen.de site-unavailable error. The bar
  for being on that list is deliberately narrow and is pinned by a test: the
  message has to be one this integration wrote, built from a status code and a
  brand name, and must never be able to carry a URL, an address or a token.
  Everything else, including an error carrying a request URL of our own, is
  still redacted and still flattened exactly as before
  ([#1855](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1855)).

### Sicherheit / Security

- **Sign-in host hardening.** Two guards in the login code decided whether a
  host was the manufacturer's by looking for a name *inside* it rather than
  matching the name itself, and one step followed a continuation link offered
  by a page without checking where that link pointed. All three now match on a
  name boundary, and the link is followed only back to the page that offered
  it, to the manufacturer's own sign-in hosts, or to the portal.

  **Nothing about a working sign-in changes.** The same reference
  implementations the portal operator points maintainers at already validate
  the same thing, every legitimate value in the project's own fixtures was
  checked against the new rule, and a live read-only portal login completes
  unchanged. A value outside that set now ends the sign-in with the same notice
  an absent one already produced, instead of being followed, and the notice
  names the page rather than the value.

## [5.0.0] - 2026-10-16 — Two doors the manufacturer closed / Zwei Türen, die der Hersteller zugemacht hat

- **Volkswagen Companion (ADB): VW app 4.6.4 mapping, controls, more reads and safety gates.** Developed against a Tiguan eHybrid (reads verified on the car) in [gszigethy/vwgroup-connect-ha](https://github.com/gszigethy/vwgroup-connect-ha) (fork releases 4.11.0-1 to 4.13.0-4, plus the fixes from this PR's review; PR numbers below refer to that repository). Thanks @gszigethy; app captures from @plainmad (Mk8 Golf GTE), @kgroshert (ID.4, e-up!) and @WEZANGO (CUPRA Born) ([#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968)). Functional and technical design: [docs/COMPANION.md](docs/COMPANION.md).

### Hinzugefügt / Added

- **Your car can tell you when a trailer is hooked up.** Two Audis reported the tow-hitch
  module's own verdict on whether something is attached, and there was nowhere for it to go:
  the integration had no trailer field at all, so this is a new reading rather than one that
  was being dropped. Both cars happened to report "nothing attached", so the wording for the
  opposite case is taken from the pair rather than seen on a car, and anything the module
  says that is neither of the two leaves the sensor unknown instead of telling you the
  trailer is off. People build automations on this one, and a confident wrong "no trailer"
  is worse than no reading. The sensor appears only on cars that report the field. Thanks
  @heldenbariton-ship-it and @marcus-stem (#1798, #1802).
- **Four new readings for the remaining life of each wheel's tyre pressure sensor.** Five
  Audi owners reported the same four diagnostic values on every poll, the largest group in
  the backlog, and not one of them was ever read. The reason was the shape of the payload:
  it arrives encoded, and the decoder expected a document inside it, while these four send
  a plain number. They are decoded now, one per wheel. On four of the five cars the value
  the car sends is the byte that means "not available", so those cars get no sensor at all
  rather than four sensors reading 255, and the one car that sends a real value gets its
  four. The portal documents neither a unit nor a meaning for them, so they are unitless
  and off by default, exactly like the other tyre values whose unit the portal leaves open.
  Thanks @zdimic1, @N85UK, @derschneewolf, @heldenbariton-ship-it and @marcus-stem (#1767).
- **A charge level and an electric range from a one time export now reach your car.** The
  15 minute feed and the one time export name the same readings differently, and the
  integration only ever knew the feed's names: of the seventeen charge level names it looks
  for, exactly one appears in the portal's own catalogue of export fields, and of the range
  names, none at all. So a reporter whose Audi delivers its charge level only in the export
  watched the import report success while his car still had no battery entity at all, because
  the flag that decides whether a car gets electric entities is derived from exactly those
  readings. The export's own spellings are now read, for the charge level and for the electric
  range. It still only fills what the feed left empty, a value the car could not report is
  still dropped rather than published, and the 12 V starter battery is deliberately kept out
  of it, since it sits one letter from the traction pack in the same catalogue. Charging
  sessions out of the file are not read as current state either: this car's export holds
  eleven of them, and a session's charge level is not the car's charge level now. Thanks
  @placidcasual98, who ran every test asked of him and whose negative results are what pinned
  this down (#1403).

#### Reads from the VW app

The Companion channel drives the VW app on a spare Android phone over ADB and reads what the app shows. All reads are phone navigation only and never wake the car. Labels are matched against the installed app's own string table, so the reads work in any app language; the English and German patterns stay as the fallback.

- **Overview, every poll:**
  - Battery level, separate from the charge limit.
  - Electric range, and petrol range on plug-in hybrids, which also enables the combustion sensors.
  - Charging state, read as a state ("Currently charging") (gszigethy/vwgroup-connect-ha#7).
  - Lock and climate tiles (gszigethy/vwgroup-connect-ha#11).
  - **Last vehicle sync**: when the car last sent the app data, from the app's "Synchronised … ago" line. It counts any reason the car sent data, only moves forward, and starts from the last known time after a restart or reload (gszigethy/vwgroup-connect-ha#79).
  - **App request status**: *Available* or *Restricted*. A request-limit pause still running after a restart shows as *Restricted* straight away.
- **Charge sheet:**
  - Charge limit, power, speed and remaining time. Spelled-out hours are counted ("One hour and 40 minutes" = 100 min) (gszigethy/vwgroup-connect-ha#39).
  - **Charging Mode** sensor, from the range sheet's charging method (gszigethy/vwgroup-connect-ha#13). It becomes unavailable 24 h after its last read (gszigethy/vwgroup-connect-ha#90).
- **Air Conditioning sheet:**
  - Whether climatisation is running, window heating, remaining time, target and outside temperature.
  - **Climate mode**: whether the app's Start starts the air conditioning or the window heating, shown as the climate entity's preset (a sensor in Read-only Mode).
- **Air Conditioning Settings:**
  - Climate at unlock, automatic window heating, air conditioning on battery.
  - **Climate zones** front left and front right.
- **Vehicle Health Report:**
  - Odometer, and service and oil-service due **in days and in km**. Miles are converted (gszigethy/vwgroup-connect-ha#8).
  - **Warnings**: active, count and the categories that carry one (gszigethy/vwgroup-connect-ha#14).
- **Vehicle Settings:** *Automatically release AC connector* (gszigethy/vwgroup-connect-ha#9).
- **Departure times** (opt-in): each timer's time, on/off, weekdays and Repeat (gszigethy/vwgroup-connect-ha#15, gszigethy/vwgroup-connect-ha#42).
- **Charging locations** (opt-in): up to five locations from the app's Departure times screen (gszigethy/vwgroup-connect-ha#85).
  - For each location: the name, whether the car is parked there, the number of active departure times, its three charging timers (on/off, time, days), and two AC settings (reduced charging current, automatically release connector).
  - Sensors for the number of locations and the current location.
  - Read-only; it never changes a setting.
  - A location's two charge-level sliders can't be read: the app draws their values without any readable text.
  - A Departure times screen that shows no locations, as the app does while the car's request limit is reached, leaves the last values in place.
  - A location deleted in the car stays in the app, and in these entities, until the app is closed and restarted; a vehicle sync does not refresh the list (gszigethy/vwgroup-connect-ha#97).
- **Driving data** (opt-in): the last trip and the trip since charging or refuelling. Covers distance, consumption, average speed and driving time; miles are converted (gszigethy/vwgroup-connect-ha#16).
- **Parking position** (opt-in), read from the share preview.

#### Read switches

Each deeper read is a switch on the *VW Group Connect Settings* device: charge detail, Vehicle Health & Settings, climate detail, climate settings, parking position, departure times, charging locations and driving data (gszigethy/vwgroup-connect-ha#18, gszigethy/vwgroup-connect-ha#85).
- A change applies on the next poll, without a restart.
- Turning a read off drops the values it supplied.
- The switches are also available in Read-only Mode.

#### Controls

Every control is refused:
- in Read-only Mode;
- on an app version not verified for commands (currently 4.6.4);
- within 60 s of the previous command;
- while the car's request limit is paused.

Every control starts from the overview and checks the result on screen.

| Control | Behaviour | PRs |
|---|---|---|
| Start / Stop charging | Taps the charge sheet's Start or Stop. A greyed-out Start is never pressed. | gszigethy/vwgroup-connect-ha#49 |
| Charge limit | 50–100 % in 10 % steps. Moves the Settings slider and presses Save only when the screen shows exactly the requested value; otherwise cancels. | gszigethy/vwgroup-connect-ha#49 |
| **Climate entity** | On/off, target temperature 15.5–30 °C (LO–HI) and the presets *Air conditioning* and *Window heating*. While off, the preset and temperature are held in Home Assistant, survive a restart and send nothing. Turning on sets the app's mode picker and dial, reads both back, and presses Start only if they match; turning off is the app's single Stop. Window heating is one-shot, as in the app: after a run the preset returns to *Air conditioning*. The preset cannot change while climate runs. A dial changed in the app updates the entity. | gszigethy/vwgroup-connect-ha#40, gszigethy/vwgroup-connect-ha#64, gszigethy/vwgroup-connect-ha#103 |
| **Temperature change on a running climate** | While the air conditioning runs, a change moves the dial of the Air Conditioning sheet and reads it back; the app sends the new temperature to the car. One step is a tap on the next label, 1 °C is one slow drag. A change takes at most two moves (2 °C, two car requests); a larger change is refused before anything moves. With the climate off, or on window heating alone, a change is stored for the next Start. | gszigethy/vwgroup-connect-ha#73, gszigethy/vwgroup-connect-ha#76 |
| Climate Settings switches | Auxiliary air conditioning, automatic window heating, zone front left and front right. Taps Save and reads the page back; a value already in place sends nothing. | gszigethy/vwgroup-connect-ha#41 |
| Departure timers (switch, time and `set_departure_timer`) | On/off, time, days and Repeat. A timer is found by its content, not its row; two timers with the same time are refused. Saves only when the page shows exactly what was asked. | gszigethy/vwgroup-connect-ha#42, gszigethy/vwgroup-connect-ha#55 |
| **Refresh vehicle data** button | Taps vehicle Settings → *Synchronise now*, then re-reads the app after 3 minutes. A refused sync is reported at once. | gszigethy/vwgroup-connect-ha#25 |
| **Refresh app screen data** button | Re-reads the app's screens now; the car is not asked for new data. With *Refresh vehicle data* and *Reset companion connection* it sits in the device's Configuration section, as all three maintain the data rather than operate the car. Cloud entries keep *Refresh Data*. | gszigethy/vwgroup-connect-ha#101 |
| **Vehicle sync interval** | Runs *Synchronise now* on a timer. Off by default, minimum 60 min. The interval counts from the newest of the last sync attempt, the car's last data and the last command tap, so a car that sent data on its own (for example while driven) gets no extra tap. After a restart an overdue sync runs at once; a recent one is never repeated. Each sync wakes the car. | gszigethy/vwgroup-connect-ha#54, gszigethy/vwgroup-connect-ha#100 |

Charge limit, automatic window heating, climate at unlock and the climate zones sit in the device's Controls section; cloud entries keep the charge limit in Configuration (gszigethy/vwgroup-connect-ha#102).

Lock and unlock are deliberately not offered. They would need the S-PIN over ADB, the slider has no reliable target, and a wrong tap risks the opposite command or an S-PIN lockout (gszigethy/vwgroup-connect-ha#36).

#### VW app 4.6.4

VW app 4.6.4 is supported (gszigethy/vwgroup-connect-ha#28, gszigethy/vwgroup-connect-ha#37). Reads also accept newer app builds (gszigethy/vwgroup-connect-ha#31). Commands run only on builds verified for them (gszigethy/vwgroup-connect-ha#51).

### Geändert / Changed

- **The "volkswagen.de read channel needs re-login" notice now says which car it means.** If you run more than one vehicle, two accounts produced two identical notices and nothing distinguished them, so you could not tell which password belonged to which. The notice carries the last six characters of the car's VIN now — the same short form the logs and the diagnostics download already use, never the full identifier. Thanks @kalwados (#1843).
- **Some cars that the legacy MBB host turns away now get their service list from the EU-DP
  host.** When the legacy host answers `401 gw.error.authentication`, the operationList is now
  requested once from the EU-DP host before the car is marked "no legacy". That list is used
  only if it parses and contains services; an empty or error body records the verdict exactly
  as before. Read-only: commands stay hidden for these cars and are refused before any S-PIN
  step, because the S-PIN host has not been checked yet. Diagnostics show such cars under
  `mbb_eudp_oplist`, and the debug log names the host each service points to (#1766).
- **Car request budget:**
  - The car's "Too many requests" and "Request limit reached" alerts are recognised in any app language.
  - Either alert always pauses commands for 12 h, even when it appears late. The pause and the 60 s command gap survive a restart (gszigethy/vwgroup-connect-ha#50).
  - The pause ends early once the car sends new data: when the overview's sync time is later than the alert, or the Driving data tile shows a new trip, controls and *Synchronise now* work again and *App request status* returns to *Available*. The alerts themselves say that starting the car makes everything available again (gszigethy/vwgroup-connect-ha#96).
  - Screen reads continue during the pause; only commands wait.
  - The battery level is read from the charge sheet during the pause, when the overview hides it.
  - A sync never probes through a backend "too many requests" pause (gszigethy/vwgroup-connect-ha#54).
- **Synchronise now is opt-in.** It is off by default and never turned on by an upgrade. An interval you set yourself is kept (gszigethy/vwgroup-connect-ha#54).
- **Read cadence:**
  - Detail-screen reads follow the poll slider (gszigethy/vwgroup-connect-ha#38).
  - A command no longer triggers a re-read of every screen.
  - The Air Conditioning sheet and its Settings are read on one walk (gszigethy/vwgroup-connect-ha#6).
  - Driving data, the parking position, charging locations and Vehicle Health are read only when they can have changed (gszigethy/vwgroup-connect-ha#80, gszigethy/vwgroup-connect-ha#85): driving data and the parking position when a trip has ended or the car sent new data and the range dropped; Vehicle Health when the car sent new data (the *Synchronised … ago* time moved and then stood still for 10 minutes); charging locations on a trip change. All are also read on the first poll after a start, when their switch is turned on, every 12 hours, on **Refresh data** and after **Force vehicle refresh**. Vehicle Settings (the charge limit) is still read on every poll.
- **Faster phone navigation:**
  - Fewer screen dumps per walk.
  - One ADB shell call per dump.
  - Shorter waits after a tap or BACK.
- **Stale values:** health, parking, driving, charging-location and Charging Mode values become unavailable after 24 h without a successful read (gszigethy/vwgroup-connect-ha#59, gszigethy/vwgroup-connect-ha#90).
- **Startup:** setup no longer waits for the first app-screen read; that read runs in the background (gszigethy/vwgroup-connect-ha#44).
- **Reloads:** a reload waits for a running walk to finish (gszigethy/vwgroup-connect-ha#60). Wake/sleep and close-app options apply without a reload (gszigethy/vwgroup-connect-ha#59).
- **App prompts:** the Google Maps consent is accepted only during the parking read (gszigethy/vwgroup-connect-ha#56). The app's rating prompt is closed with BACK, never answered (gszigethy/vwgroup-connect-ha#29).
- **App string table:** fetched only when the app version changes. Without it, commands and sync are refused unless the UI language can be confirmed (gszigethy/vwgroup-connect-ha#58).
- **One entity per value (breaking only on a Volkswagen Companion entry with Read-only Mode off, the one place these removals happen):**
  - The read-only sensor and binary sensor that repeated a control's value are removed. This covers climate at unlock, window heating, the zones, climatisation, charging, charge target and the departure timers.
  - The app's own target temperature and start mode readings are shown by the climate entity (gszigethy/vwgroup-connect-ha#65, gszigethy/vwgroup-connect-ha#103).
  - Climate runs from the climate entity alone: use its on/off instead of a climate switch. No 4.x release created that switch on a Companion entry, so no 4.x upgrade loses one — setup only clears a leftover registry entry from the single much older release that did (gszigethy/vwgroup-connect-ha#103). Entities ARE removed by this group; the bullets above say which.
- **Cloud-only diagnostics removed from companion entries:** push event, API observer findings and wake count today (gszigethy/vwgroup-connect-ha#66).
- **Data source label:** shows the companion transport (`companion_adb`) instead of "Volkswagen EU (WeConnect ID)" (gszigethy/vwgroup-connect-ha#67).
- **Companion entity ids carry "adb"** (for example `sensor.tiguan_adb_battery_level`, named "Tiguan Battery Level"), so companion and EU Data Act entities can be told apart. Existing entity ids are unchanged (gszigethy/vwgroup-connect-ha#68, gszigethy/vwgroup-connect-ha#81).
- **The vehicle sync warning is translated.** The note that each sync wakes the car appears in every supported language.
- **Relay errors are reported only as fixed codes**, never as free text from the phone.
- **Release documentation corrected** (`RELEASE_PROCESS.md` and the CI prose):
  the prescribed changelog heading format was one no parser accepts, the
  coverage gate was quoted with stale values in three places, and eight links
  pointed at a file that no longer exists.

### Behoben / Fixed

- **The diagnostics now say when one of the extra read channels dropped out.** If the
  `volkswagen.de` channel or the EU Data Act portal fails during a poll, the integration keeps
  going on the others, which is right. Until now it kept going silently: the skip was written
  only to a debug log, so a downloaded diagnostics file could not tell you whether a channel had
  fallen over or had simply found nothing that round. Those two look identical from the outside
  and have different causes, and the download now distinguishes them per channel.

  This matters beyond tidiness. When every extra channel drops out, the rule that stops an older
  batch reading from outranking a live one has nothing to compare and does not run — so a value
  can look stale for a reason that was, until now, invisible in the file. If you report an
  unexpected reading, the answer should be in the diagnostics you attach rather than cost you a
  round of "please switch on debug logging first".

  The per-channel lines describe the poll the file was taken on and nothing earlier: a channel you
  switch off stops claiming an outcome instead of leaving its last one behind, on every kind of
  entry. Worth saying because the entries alongside them do not work that way — those are written
  when a read is attempted and stay put when it is not, so a reading there cannot be dated from the
  file. One exception, so you are not misled by it: if you switch off the *last* of your extra read
  channels, that final set of per-channel lines stays in the file until the integration restarts.
- **The "sign in again" notice no longer sends an Audi owner to a door the manufacturer
  locked.** When a passwordless entry's session expires, the notice told everyone to choose
  Reauthenticate and scan the sign-in code again. For Audi that cannot work: Volkswagen
  switched off the app sign-in that brand used, so the code sign-in refuses to start and the
  reauth lands on a banner saying so. @ratclma reported hitting exactly that, after following
  this advice from us, which is how it was found.

  The sign-in prompt now reads the brand and the kind of sign-in the entry actually stored.
  Where the code sign-in still works it hands off to it as before. Where the manufacturer
  retired it, the prompt asks for your email address and password instead, and attaches them to
  the existing entry, so its history, its settings, its entity names and any extra channels you
  had set up all survive. The email field is deliberately left empty: these entries store an
  internal account identifier rather than an address, and a pre-filled box would invite you to
  type only a password, which is the one thing that cannot work.

  This is fixed in the sign-in prompt rather than in the repair notice on purpose. Home
  Assistant opens that prompt by itself whenever the session has expired, so a notice pointing
  elsewhere would have left the dead end reachable without you clicking anything.

  The first round of this stopped the integration guessing on its own. Such an entry no
  longer attempts, unprompted and in the background, the email-and-password sign-in it has
  no stored password for — which had been putting the
  account's internal identifier in the email field once an hour for seven hours, and
  reporting the refusal as a portal action the car in question could not even use. It now
  says the session expired and gives up after two failed rounds instead of retrying hourly,
  the same rule Porsche entries have had since 4.7.8.

  Two further defects in the same notice went with it: its title said "VW Group" instead of
  naming the brand, and although it told you to go and do something, it offered no Repair button
  at all. Both notices have one now
  ([#1813](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1813)).

- **A car whose service list comes from the read-only host keeps its remote commands blocked
  even right after a restart.** That block was already there and already correct, but it was
  checked a moment too early: the integration looked at its own note of which cars are affected
  before the step that writes that note, so on the first command after a restart the note was
  still empty and the block did not catch. The entity for the command stays hidden either way,
  so this only mattered to someone calling the service directly from an automation, and only
  until the first data refresh of that session. It is checked again at the right moment now.
  The reason it is worth a separate fix rather than a footnote: what gets lost when the block
  misses is an attempt at your vehicle PIN, and the car locks the PIN after a few wrong ones.
  Groundwork and the original block are @fschulte2812's (#1807).

- **Your tyre pressures show their decimal again.** The portal sends a value like 2.8 bar, and
  every tyre-pressure sensor was showing 2. The number was being read as a whole number and the
  fraction thrown away, on all four corners and the spare, in the actual, the target and the
  deviation readings alike. They are measurements with one decimal and are read as such now.
  Rounding would have been the same mistake wearing a different hat, since 2.8 bar is not 3 bar.
  A car that reports whole units instead of bar is unaffected.
  The half nobody could see from the outside was worse. The sensor that tells you whether your
  car measures each tyre individually or only estimates it reads the same numbers, and the field
  catalogue uses 1 to mean "no reading available". Throwing the fraction away turned every
  pressure between 1 and 2 bar into exactly 1, so a car with one soft tyre was reported as not
  measuring its tyres at all. That is the moment the reading matters most, and it now reads as
  the measurement it is. Thanks @Kolbi, who quoted the raw value straight from the portal
  response (#1819).
- **Your car is no longer told it is a model it isn't.** An Audi e-tron 55 from 2019 was
  informed by the integration that it is "an MEB / ID-family car (ID.3/4/5/7, Enyaq, Born,
  Q4)". It is not one, and its owner said so. The notice was built from the backend's
  refusal and not from any check of the car: when the durable Car-Net login answers
  "Unknown user", the integration concluded the car must be an ID. That answer only says
  the car is not registered in the old Car-Net system, which is the expected case for ID
  and MEB models and equally what an older car answers once the brand has moved it off
  that system. The outcome was right, since the refusal is real and commands genuinely
  cannot be sent, but the explanation sent people looking for an answer that does not
  exist. The notice and the setup message now say what the refusal actually tells us.
  German and English are corrected; the other languages still carry the old wording until
  a native speaker gets to them. Thanks @jocke-w (#1809).
- **An error report now says what the backend actually answered.** A report reached the
  tracker saying only that a request had failed with a 400, which is not something anyone
  can act on: a 400 can mean an expired subscription, a passing backend problem, or a
  mistake in what the integration sent, and only the answer's own text separates those. The
  text was being read and then dropped, because the part of the code that writes the report
  deliberately keeps it out of the message to avoid putting a VIN in a log. It is now
  included in the report, masked the same way as everything else in it. A failure that
  repeats is also no longer twenty copies of itself: the report keeps one entry with a count
  of how often it happened, so the rest of the history survives and anyone reading it can
  see how persistent the problem is. Thanks @moltke69 (#1808).
- **Three cars stop reporting the same three fields on every poll.** A VW and two CUPRA
  sent a companion value that says whether a reading next to it can be trusted. It is not a
  reading itself, so it was never going to become a sensor showing you the word "VALID",
  but nothing used it either, which is why it kept being offered as something new. It is
  used now for what it is: it decides whether the reading beside it counts, it is kept in
  the diagnostics so nothing is hidden, and it no longer comes back on the next poll. Every
  value seen so far says the reading is valid, so nothing changes on your car unless the
  portal itself ever says otherwise. Thanks @tertius1, @StoneH74 and @Thunderhawk2001
  (#1797, #1803, #1795).
- **A value filled in from a one time export now says when the car captured it.** The sensors
  fed by the 15 minute feed carry the car's own capture time and whether that time belongs to
  the reading or to the file it came in. The ones filled in by the import carried neither, so
  there was no way to tell whether an imported door state was from this morning or from three
  days ago. The cause was that the two pieces of bookkeeping are stored next to the readings
  rather than on them, and the import skipped them on any car that already had a live feed.
  Imported values now carry their own capture time where the export supplied one, and say
  plainly that the age is the file's where it did not. A live reading keeps its own time and is
  still never overwritten. Thanks @kmeinderink, who measured the missing attributes and then
  said which half of the problem actually mattered to him, which is what made this small
  instead of large.

- **The one time export now identifies this project to the portal, like the rest of the
  integration already did.** The portal's operator asked that requests to their domain carry a
  name, so they can attribute traffic and report a problem back to whoever causes it. We did
  that, but only for the login and the dataset download: the one time export and the automatic
  data request lived in their own module and still went out anonymously, including the two
  requests that actually create a data request on the portal. That is not only a courtesy. On
  9 October the portal answered logins with an error for hours purely on the strength of a
  header, so unidentified requests were exposed to exactly that kind of gate. Every request
  from that module now carries the name, and the headers it already sent are kept rather than
  replaced.

- **The clear message when the car's gateway refuses a command now actually appears.** The last
  release announced that a command refused on its final leg would explain itself instead of
  surfacing a raw 403. It did not. The check looked for the gateway's own words in the error's
  message, and that message is deliberately stripped of the response body so that logging or
  re-raising it cannot leak your car's identifier. The words were therefore never in it, both
  explanations were unreachable, and a reporter who tested the release still got the bare 403.
  The same mistake sat on the locked-S-PIN detection in two other places, where it cost the one
  message that tells you what to do about it. All three now read the response body, and the
  decision lives in a single function that the tests call directly instead of re-implementing
  it, because the old test did re-implement it and passed against code that could not run.
  Thanks @panther7 for testing the release and reporting that commands still failed (#584).
- **An electric car no longer loses its battery entities a quarter of an hour after they
  appear.** The snapshot the integration keeps carries a charge level and a range forward when
  a poll does not report them, but it did not carry the flag that says the car HAS a battery,
  and that flag is what decides whether the electric entities exist at all. So a car whose
  charge level had been filled in from a one time export kept the number and lost the flag on
  the very next feed snapshot, and the entities disappeared again with their own values sitting
  right there. The flag is now worked out again from the readings that survived, through the
  same single rule the rest of the integration uses, and only ever upward: a car that reports
  fuel as well as charge stays a hybrid rather than being turned into an EV, and a car we know
  nothing about stays unclassified instead of being called electric. A plug in hybrid also
  stops losing the word hybrid on every poll that omits the flags.
- **A charge level the car could not report is no longer published as a reading.** When a car
  cannot report its charge level it sends a placeholder number instead, and we put that
  straight on the battery sensor: a car that said "no reading" showed up as 255 % charged. The
  sensor feeds Home Assistant's long term statistics, so the nonsense was written into your
  history as well. Anything outside 0 to 100 is now treated as no reading and left empty,
  which is what the integration already did for one of the other charge level sources but
  never for this one. 0 % and 100 % are of course still real readings, and a car that reported
  nothing valid no longer looks like it has a battery at all.
- **A petrol or diesel car no longer reads as an electric one.** The one time export names its
  own engine type and we were throwing that away, so a car whose own file said petrol had its
  fuel range copied onto the electric range sensor and was marked as an EV. The engine type is
  now read and the range lands on the combustion sensor where it belongs. The plug in hybrids
  whose two ranges were swapped back in an earlier release are deliberately untouched by this,
  and there are tests to keep them that way.
- **A connected charging cable no longer says "not connected".** The portal writes the plug
  state as a long protocol word and the check only understood the short form, so a plugged in
  car was told its cable was out, as a definite no rather than an honest unknown. The value a
  car sends when it cannot report the plug at all was being turned into a "no" too, and now
  stays unknown. Thanks @placidcasual98, whose own export is what showed this (#1403).
- **The charge limit from a one time export is read again.** The field name we were looking for
  had a capital letter that the portal's own catalogue never uses, so no real export could
  match it.
- **The privacy note on an automatic report no longer reads as covering the file you attach
  yourself.** What the integration generates is masked, and that has not changed: the vehicle
  identifier in a report is cut to its last six characters and a model name that turns out to be
  an identifier is left out entirely. But that promise prints directly above the box you drag a
  file into, and a data export downloaded from the portal is named with your full vehicle
  identifier, so people have been attaching one without realising. Six of the open reports carry
  one that way. The note now says plainly that your own attachments are not covered, and suggests
  renaming the file first.

- **A refused lock or unlock now explains itself, like a refused climate command already did.**
  The last release added a clear message for a command the car's gateway turns down on its final
  step, and credited the reporter who worked it out. His own command was locking, and that path
  never received the message: it had no handler on that step at all, so he would have seen the
  same bare error a third time. Both paths now share one classification, so they cannot disagree
  about what you are told, and the specific code his car returns is recognised as well, which
  means we no longer have to ask anyone for a description the integration does not print. Thanks
  @panther7 for testing the release and saying it still failed, and @Joassens, whose instrumented
  logs are what made the messages possible in the first place (#584).

- **The stale-data warning no longer tells you to re-request your data sharing.** The portal's
  operator has asked that nobody file further data requests while they work through a backlog,
  because it does not speed anything up and can put you further back in the queue. Our warning
  had been advising exactly that, in all twelve languages. It now points at re-adding the channel
  instead, and in English it says plainly that empty or unchanged downloads are a hold-up on the
  portal's side rather than yours. The other eleven languages have the bad advice removed; the
  added explanation follows in a later pass rather than being machine-translated into an
  instruction nobody here can check.

- **Missing entities when the car is also in an EU Data Act entry.**
  - Battery, range, charging and lock entities from the companion were dropped as duplicates.
  - Companion entities now have their own unique ids (`{vin}_companion_{key}`). A one-time migration keeps the existing entity ids and history (gszigethy/vwgroup-connect-ha#47).
- **No stuck charging values after a reload.** A screen read still running while the entry unloaded could create the charging power, charging speed, remaining time and vehicle status sensors on the unloading entry, where they kept their last value and blocked the reloaded entry's own sensors. A read that finishes during an unload now creates nothing (gszigethy/vwgroup-connect-ha#83).
- **Commands for a car in several entries** go to the entry that can send them (gszigethy/vwgroup-connect-ha#48).
- **An idle car no longer reads as climate on.** The running state now comes from the Start/Stop button.
- **The walk back** recognises the 4.3.2 overview and no longer presses BACK out of the app.
- **A broken ADB connection** ("Broken pipe") is reopened on the next read (gszigethy/vwgroup-connect-ha#27).
- **Climate:**
  - The dial is walked only when its labels show °C; a reading outside 15.5–30 °C is never tapped (gszigethy/vwgroup-connect-ha#61).
  - An unrecognised mode refuses Start.
  - Error messages no longer quote screen text (gszigethy/vwgroup-connect-ha#52).
- **An interrupted walk** discards any setting it left unsaved instead of sending it with the next command (gszigethy/vwgroup-connect-ha#53).
- **Departure timers** that were not read show unknown, not off (gszigethy/vwgroup-connect-ha#10).
- **Vehicle Settings** is read even when the charge target is already known (gszigethy/vwgroup-connect-ha#9).
- **A stale battery level on a car whose volkswagen.de channel was plainly being read.**
  The poll opens with a relations lookup that resolves which platform the car is on, and a
  refusal there used to abandon the rest of the poll — so the charging read never ran, the
  volkswagen.de snapshot carried no battery level at all, and the merge kept the only value it
  had: the portal feed's last capture, days old next to a channel that looked live. Nothing in
  the merge was wrong. The refusal is now recorded and the remaining reads still run, exactly
  as a refusal on one read already stopped costing the others. On a car that is not MEB the
  platform stays unresolved after such a refusal and those reads are expected to come back
  empty, which the diagnostics name. Thanks @Fishermanjb (#1827).
- **A session that had really expired stopped being noticed.** At the end of the same poll the
  integration decides whether a refused read means "this one car is walled" or "the session is
  dead", and it decided by asking whether a model name or colour had been filled in. Those are
  kept for a day once read, so from the first successful poll onward the answer was always yes:
  the "session is dead" branch could not be reached again for as long as Home Assistant stayed
  running, and reconnecting was left to the ten-minute background refresh on its own. The
  question is now whether a read actually reached Volkswagen during that poll. The model,
  colour and renders do not flicker as a result — they are held a layer further up, which is
  what that was always for. Found while looking into #1827.

#### Fixes in shared code (all channels)

- **Read-only Mode stops commands from controls that were already loaded.** The option applies without a reload, so a control created while the entry was writable could still send a command. The command dispatch now refuses it.
- **A command for a car that sits in several entries** goes to the first entry that can send it, instead of failing on a read-only one listed first (gszigethy/vwgroup-connect-ha#48).
- **No entities are created on an entry that is unloading**, and a poll that finishes during shutdown no longer notifies listeners (gszigethy/vwgroup-connect-ha#83). Cores without `ConfigEntryState.UNLOAD_IN_PROGRESS` are unaffected.
- **Charging switch during conservation charging.** The switch showed off while the car was conservation charging; it now shows on.
- **Charging session with an unknown plug state.** A session is no longer cancelled when the channel cannot see the plug.
- **Climate `set_hvac_mode` / `set_temperature`.** A mode the entity does not list raises a validation error instead of being treated as off (gszigethy/vwgroup-connect-ha#52).
- **`set_departure_timer`.** `enabled` is optional. The companion can change only the time or the days; the cloud channels return a clear error if `enabled` is left out (gszigethy/vwgroup-connect-ha#55).

### Sicherheit / Security

- **Diagnostics redaction hardening.** The diagnostics download masks more of what it carries
  before you attach it to an issue, in both the per-vehicle and the raw-payload section.
  Nothing about the integration's behaviour changes and no sensor is affected. Two of the
  newly masked entries are containers rather than single values, so a raw capture now shows a
  note about their kind in place of their inner shape — worth knowing if you use that section
  to help map a new field. Thanks @Fishermanjb, whose report of a neighbouring problem is what
  led here.
- **Tokens:**
  - New ADB Bridge add-on setups require a token.
  - The relay token form suggests a random token, and a custom token needs at least 32 characters with enough variety.
  - Existing entries keep their tokens.
- **Diagnostics:** the add-on token, the agent token and the phone's host address are redacted.
- **Screen dumps:** a dump that contains an XML DOCTYPE or ENTITY declaration is refused before it is parsed (gszigethy/vwgroup-connect-ha#57).
- **Vehicle identification numbers:** CI refuses a VIN-shaped literal in the repository that carries no visible mark of being made up.
- **For VW and Audi, the name you give your car in the brand's app is kept out of the model field.** It is shown as the vehicle nickname instead, which a diagnostics download redacts. The Škoda official-API channel still puts that name in the model field; that is a separate change, because the same field carries the real model for every owner who never renamed their car. Entity IDs that already exist are not renamed. On a NEW setup the device is named after the model — and where the brand's garage entry carries only your name and no model, the device falls back to the brand plus the last six characters of the VIN, so a new entry can read "Volkswagen 1234AB" where it would previously have read your own wording.
- **Vehicle Data Scout:** the masking that prepares a sample value for a public
  issue now covers another of the encodings the portal uses, so an encoded field
  is replaced by a note about its kind and size rather than shortened. Reported
  as a new field by @autosklo (#1830); nothing was exposed in that report.


## [4.13.0] - 2026-10-10 — Six reporters' diagnostic readings, and two accounts that read the same car

### Hinzugefügt / Added
- **Doors, windows, boot and bonnet now read from a one-time export.** The 15-minute feed and
  the one-time export describe the car's body in two different dialects: the feed sends numeric
  codes, the export sends words under per-part containers. We only ever understood the feed, so
  a reporter whose Audi delivers these fields only in the export watched those entities sit at
  `unknown` while his own downloaded file said CLOSED and LOCKED for every one of them. Both
  dialects are now read, per door and per window, plus the boot's lock, the bonnet, the window
  opening percentage and the parking lights. The export never overwrites a live reading — it
  only fills what the feed left empty — and a part the car reports as unsupported or invalid
  stays unknown rather than being called closed (#1780, thanks @kmeinderink, whose own
  correction after checking his diagnostics is what made the cause findable).

### Geändert / Changed
- **A car park no longer means a login each.** One portal connection serves every vehicle on
  an account, and the integration reads the cars at the same time — so a three-car account
  could ask the portal to log the same person in three times at once, and any car hitting an
  expired session added another. Now the first login runs and the others simply wait for it:
  one identity, one login. A failure is shared with whoever was waiting instead of being tried
  again by each of them, because seven attempts with a wrong password is how an account gets
  locked out by a fix. Nothing is cached — the next poll still logs in normally, so an expired
  session is still replaced. This was not our finding: two other portal readers shipped the
  same change within two days of each other after running into it, and we are in the middle of
  a conversation with the portal's operator about request volume (#1778).

### Behoben / Fixed
- **Two accounts no longer end up reading the same car.** If you run two config entries for
  two different portal accounts, both could show both cars with neither working. The portal
  identifies you by cookie rather than by a token, and Home Assistant gives every integration
  one shared connection to the internet — so the second account's login wrote its cookies over
  the first one's, and from then on both entries read whichever car had logged in last. Each
  entry now gets its own cookie storage for the portal, and only for the portal: everything
  else keeps sharing, because nothing else is identified that way. If you removed one of your
  entries to work around this, you can add it back (#1774, thanks @kalwados, whose "both hubs
  still show both cars" is what pinned it down, and who tested the release that did not fix it
  so we would know).
- **231 field names the car sends could never be discovered.** Fields whose name ends in a
  generic word — `…value`, `…unit`, `…state` — were treated as envelope packaging and dropped
  before the Vehicle Data Scout could report them. That rule is right for a bare `timestamp`
  and wrong for an official field name that happens to end that way, and it silenced an entire
  family: every per-door and per-window state, the unit companions that let us map a quantity
  without guessing its scale, the low-voltage battery level, the per-tyre state. It is also why
  nobody had ever reported them — discovery could not see them, and the one reporter who found
  them had to read his export by hand. A generic ending now only counts as packaging when the
  whole name is generic. Expect the Scout to start reporting fields it was previously blind to;
  that is the point, and it is how the next ones get mapped (#1780).
- **Importing a one-time export could not create a single electric entity, and a reload threw
  the import away.** Two faults with one symptom: you ran the import, it reported success, and
  nothing appeared. The flag every electric entity is gated on is a plain true/false rather
  than "unknown", and the merge only fills a field it has no value for at all — so the export
  handed over a state of charge and the flag in the same breath, the reading landed and the
  flag was refused. That gate is checked before the one that hides empty entities, which is why
  there was no battery entity to find rather than an empty one, and why switching "hide entities
  without data" off changed nothing. The flag is now re-derived through the same rule the
  multi-channel merge has always used — it can only ever add a drivetrain, never take one away,
  so a plug-in hybrid cannot be turned into an electric car by an export that says nothing about
  fuel. Second: the merged values are now saved. They had only ever been written to disk by the
  regular poll, so the advice to reload afterwards discarded them unless a poll happened to land
  in between (#1776, found grounding @placidcasual98's report on #1403).
- **A command your car refuses now says what it refused.** On some older cars the gateway
  accepts your S-PIN and then declines the request anyway, and until now that arrived as an
  unexplained error — which reads like a wrong password or a lapsed subscription. Both had
  been verified fine in the case this comes from: the subscription active until 2027, the
  car's own service list granting the operation, the S-PIN handshake completed. The message
  now rules those out by name and says plainly that some cars only accept commands from the
  manufacturer's own app, which an open-source client cannot imitate, and that reading data
  is unaffected. A second, different refusal is kept separate rather than lumped in: when the
  car calls the request *invalid* instead of forbidden, that means this model's software does
  not take that particular setting at all — so the control stays available, because the
  account is allowed to send it (#584, thanks @Joassens, who instrumented all three
  authorisation steps and then captured the official app to settle which of the two
  explanations it was).
- **Eight readings an electric car already sends were being thrown away over a single
  space.** In the diagnostic and battery-module field families the portal appends a unit
  token to each value, and does so even when the unit is empty — so a base64 diagnostic
  envelope arrives with a trailing separator.
  Our decoder rejected the whole envelope because of it, which silently cost one ID.4 every
  one of the eight diagnostic responses we know how to read: both high-voltage battery
  temperature extremes, both cell-voltage extremes, the 12 V battery cluster, the outside
  humidity sensor, the standard ambient conditions and the range the instrument cluster
  displays. The leading token is now taken as the payload, the same way the plain scalar
  readings have been handled since #1622. Strictness is unchanged otherwise: a genuinely
  corrupt value still produces no reading and stays visible on the raw-fields sensor rather
  than half-parsing into something plausible (#1772, thanks @HeBraun; the deciding evidence
  came from @derschneewolf's attachment on #1769).
- **Four tyre-sensor fields now show their official name instead of nothing.** The field
  catalogue is extracted from the official PDF, and the extraction left line-wrap spaces
  inside 43 field names — so the tyre-pressure-sensor service-life family is catalogued
  twice, once broken and once with every space removed, while cars send a third spelling.
  All three missed each other, so those fields reported no official name at all even though
  the catalogue describes them. Names are now matched with whitespace collapsed on both
  sides, as a last resort after the exact lookups, so nothing that already resolved changes.
  No unit is invented along the way: where the catalogue publishes none — as it does for
  this family — none is shown, and a name whose space-free form is shared by entries with
  different units stays deliberately unresolved rather than inheriting one of them
  (#1767, thanks @zdimic1; same four fields on @derschneewolf's car in #1769).

## [4.12.0] - 2026-10-09 — The portal login works again / Die Portal-Anmeldung geht wieder

### Hinzugefügt / Added
- **A car reading the EU Data Act portal gains one more diagnostic: when the instrument cluster
  last recorded a warning.** A Touareg reported the field, and every sample we have of it — four,
  from three different cars — carries an absolute timestamp, so it becomes a timestamp sensor
  beside the existing raw warning value rather than being folded into it. Off by default, like
  every diagnostic of this kind, and it only appears on cars that actually send it (#1757, thanks
  @robertbakum).
- Internal, no user-visible change: three further fields the same car reported stay deliberately
  unmapped. The official field catalogue gives them no meaning and no unit at all, and every
  sample so far is empty — so they raise no repair card, while staying visible on the raw-fields
  sensor, which is what keeps a car that one day sends a real value findable (#1757, #1164).
- **Six Škoda commands can now fall back to the official Škoda API when the app backend refuses
  them.** Every Škoda command goes through the reverse-engineered app backend today, and that
  backend is expected to be switched off. The official public API — the one you already use for
  readings if you have a key — implements six of the same commands: start and stop charging,
  start and stop climatisation, start and stop active ventilation. If the app backend refuses one
  of those in a way that proves your car never received it, the official API is tried once.
  Nothing changes while the app backend works.
- **Six of twenty-four, and that is the honest number.** Locking, unlocking, flashing, waking and
  every charging-settings change have no equivalent on the official API — it has nine endpoints
  and no way to write settings at all — so they cannot be covered, now or later. If the app
  backend goes away, those stop working. This buys time for the commands people use daily, not
  for all of them.
- Internal, no user-visible change: the fallback is deliberately narrow. It fires only on a
  refusal that proves nothing was actuated, never after a server error or a dropped connection —
  those are already retried up to three times underneath, so the car may have received the
  command and a second channel would send it again. Auxiliary heating is excluded although the
  official API has it, because the S-PIN is held per entry there and per vehicle here, and
  repeated wrong PINs are how a vehicle PIN gets locked.

### Geändert / Changed
- **The "MBB operationList → 401" warning no longer tells primary users to become primary user (#584, #923).**
  The warning asked "is the account the primary user in the brand app?" as if that were the only cause. On a
  Tiguan eHybrid MY2026 whose relation reads `PRIMARY_USER`, `enrollmentStatus COMPLETED`, `carnetIndicator true`
  — and whose own pre-flight says `mbb_eligibility: eligible` — the same 401 still arrives, so the question sent
  the owner looking for a problem on the account side that is not there. The message now says the legacy gateway
  refuses the car, that this also happens on fully enrolled accounts, and — for entries with a volkswagen.de
  channel — points at `mbb_eligibility` to tell the two apart (empty means that check has not run). It no longer
  promises that all vehicle data is unaffected, only readings from volkswagen.de or the EU Data Act portal. Log
  text only; the verdict and its handling are unchanged.
- Internal, no user-visible change: Home Assistant 2026.10 replaced the library it validates
  configuration with. Nothing about this integration broke — Home Assistant keeps the old name
  working on purpose, and names custom integrations as the reason — but our type checking had to
  follow it, and until it did, every change to this project failed its automated checks. The
  validation library is now reached through one documented place instead of six, so the next step
  of that migration is a one-line change, and nine repair dialogs carry the result type Home
  Assistant now expects. Verified against both the new release and the previous one.
- **Requests to the EU Data Act portal now say who they are, and the login makes one fewer
  round trip (#1740, thanks @VWGroupDatahub).** The portal's operator asked for a dedicated
  user-agent on requests to their domain so they can tell traffic apart and report problems
  back to whoever is causing them — our data requests had been going out under the HTTP
  library's default name. They also confirmed the priming request we made before signing in
  was unnecessary, because the load balancer hands over the cookie it was there to collect
  on the redirect from the login server anyway. Nothing changes for you; signing in is one
  request shorter.
- Internal, no user-visible change: the dedicated agent goes on portal-domain requests only.
  The sign-in steps keep the browser agent they have carried since v2.10.x, when the WAF in
  front of the login server started answering `403` to a non-browser one (#388, #393).

### Behoben / Fixed
- **A diagnostics download could carry more vehicle identification than it should.** Tightened, and
  any card created before this update is cleared on upgrade so nothing lingers. If you have already
  shared a diagnostics file publicly, consider replacing it (#1768, thanks @kalwados).
  > **Correction, 2026-10-23.** The second sentence was wrong. New cards stopped
  > carrying a raw VIN, but **an existing card was not cleared on upgrade** — the
  > deletion only ran when that same repair was next raised or cleared, and for an
  > export already timed out neither ever happens. A user two releases later
  > uploaded a diagnostics file that still carried one. The sweep this promised
  > ships in the entry under `[Unreleased]`. If you shared a diagnostics file
  > before that version, replacing it is still worth doing.
- **A Škoda API key you typed in yourself is no longer thrown away when another car enrols
  automatically.** Arming the official channel from the stored keys replaced it with only the
  automatic ones, so a car that depended on the key you entered quietly lost its backup
  connection — and, since the official channel started carrying commands, its commands too.
  Nothing reported it, because the arming itself succeeded.
- **The message announcing automatic Škoda enrolment no longer describes an older version of
  itself.** It said the official channel "stays on standby and only reads when your main
  connection can't". That stopped being true in v4.6.1, when the channel became a live source
  read on every update. It now says what actually happens — read every cycle alongside the normal
  connection, stepping in on its own if that fails, paced so the hourly limit is never the
  bottleneck — in all thirteen languages.
- **Two things Home Assistant 2026.10 started warning about in our LLM tools are dealt with before
  they become errors.** Each of the Škoda tools now names the integration it comes from, and a tool
  hands its result back in the container the newer Home Assistant expects instead of a bare object.
  Home Assistant had been papering over both and writing a deprecation line into your log on every
  tool call; the first becomes a hard error in 2027.10, the second in 2027.11. Nothing changes in
  what the tools do or what an assistant sees, and older Home Assistant builds still get exactly
  the shape they expect.
- A car sending an empty value for the raw dashboard-warning reading no longer creates a sensor
  that shows nothing. Found while mapping its sibling above.
- **A solved Porsche captcha is now replayed into the login it belongs to.** When Porsche puts a
  captcha in front of you, the integration showed it, you typed it, and the answer went back on a
  brand-new connection that had forgotten everything about the sign-in it was answering for — so
  Porsche could reasonably refuse a correct answer. The login now carries its session across the
  pause while you read the image. Every other project that handles this captcha keeps that session
  alive; we were the one that did not. Honest caveat: nobody here has an account that produces a
  Porsche captcha, so this is reasoned from the code and from what the working clients do, not
  confirmed on a real one — if you hit it, the report link in the dialog is still worth using
  (#1752).
- **A Porsche login that stops now asks you for something you can actually produce.** The
  report link the dialog hands you carried one set of instructions for everyone: turn on debug
  logging from the integration's three-dots menu and try the login again. That menu only exists
  once the integration is set up, so everyone whose very first setup failed was being sent to a
  button they do not have. And when the login hits the my.porsche.com wall, the line we need is
  already in your normal log from the attempt you just made, so asking for another attempt cost
  you a retry for nothing on an account where repeated failures cause lockouts. A failed setup now
  gets the `configuration.yaml` route instead, a wall report points at the line already written,
  and neither asks you to try again (#1737).
- **A password Porsche refuses at the captcha step is no longer reported as a used-up captcha.**
  Typing a correct captcha with an e-mail or password Porsche rejects produced "that captcha could
  not be verified and it is now used up", which sent people to re-check a challenge that was fine
  and invited exactly the retry that step exists to prevent. It now says what happened (#1752).
- Porsche login reports name the integration version, the way the Scout and error reports already
  do — one less round of "which version are you on" (#1736/#1738).
- **A single rate-limit response from the official Škoda API could silence its readings long
  after the limit had passed.** The `Retry-After` value from a throttled response was kept and
  then re-applied to any later refusal, so one busy minute could park the channel for the whole
  window again and again. The block now comes from the response in front of it.

## [4.11.1] - 2026-10-06 — The Fix button actually fixes / Der Fix-Knopf tut jetzt was er sagt

### Behoben / Fixed
- **The "Volkswagen.de channel needs re-login" Fix button now actually logs you in (#1717, thanks @fschulte2812).**
  It was shipped broken in 4.11.0: pressing Fix closed the dialog, made the notice disappear and did nothing else —
  no login appeared and the channel stayed down. @fschulte2812 found it and read the code to work out why. The repair
  was handing the job to a settings screen that Home Assistant never shows when something other than you opens it,
  and then marking itself done regardless. The login now happens inside the notice itself: e-mail and password, then
  the one-time code if Volkswagen asks for it, and the notice only clears once you are actually signed in again.

### Geändert / Changed
- **The Volkswagen.de Data Act login stops one page earlier, and is a little quicker for it
  (#1740, thanks @VWGroupDatahub).** Signing in used to end with a request for a portal content page
  that the integration reads nothing from — the page before it is the one that hands out the
  session. That last request is gone. You will not see a difference beyond a slightly faster
  login; it matters because the portal's own team told us the hop is about to change, and they
  sent the fix before it did. Volkswagen's consent, legal-terms and optional marketing-consent
  pages are handled exactly as before.
- Internal, no user-visible change: following that chain by hand means the integration now
  applies the rules a browser used to apply for it. The ones worth naming: a `303` does not
  re-send your password to the next address, a redirect that leaves the host drops any
  credential header instead of carrying it along, a redirect off `https` is not followed at
  all, and a chain that never ends gives up after ten hops instead of spinning.
- **A Vehicle Data Scout report now says which version of the integration produced it
  (#1736, #1738).** It always had room for that line and never filled it, so every report
  that reached me started with me asking you which version you were on — three times in the
  past week. In one of those the field had been mapped thirty-seven minutes before the report
  was filed, which nobody could tell from the report itself. The same line is now on the error
  reporter's output. Nothing about what is collected changes: same fields, same masking, no
  raw API response.
- **The trip-computer distance since the last fill-up is a normal sensor now, visible without
  hunting for it (#1655, thanks @fschulte2812).** It arrived as a hidden diagnostic entity
  while the two memories next to it — total distance and last journey — were ordinary sensors,
  which is why @fschulte2812 went looking and could not find it. That caution was for a value
  nobody had seen on a real car yet; several cars have reported it since. If you enabled it by
  hand, nothing changes for you.

### Docs
- Internal note only, no user-visible change: the device-grant source file still claimed Audi's app
  client returned `200` from Volkswagen's device-code endpoint. That stopped being true when VW walled
  the Audi app login (#1364), and a stale comment saying a dead login works is how someone later sends
  a user down it. Corrected, together with why Audi deliberately stays in the brand list anyway: it is
  what lets an Audi user reach the honest "this login was switched off" message instead of finding the
  brand quietly missing from the picker.
- Internal note only, no user-visible change: the rule that recognises a manufacturer-retired app
  login (#1364, #1337) was written inline inside the browser-login error handler, which meant the
  test covering it had copied the rule into its own body and was asserting on the copy — it could
  not have failed if the real rule changed. The rule now lives in one place that the test actually
  calls, with the first negative cases it has ever had, so a timeout or a 503 can no longer be
  mistaken for a brand's login being permanently gone.

## [4.11.0] - 2026-10-04 — Trip figures and a Fix button / Fahrtdaten und ein Fix-Knopf

### Added
- **Trip and consumption figures for Car-Net cars on the volkswagen.de channel (#1313, thanks @realynot).**
  Older Volkswagens whose data comes through the volkswagen.de channel now get their three trip-computer memories:
  the last trip, the cumulative long-term one, and the distance since refuelling — each with distance, duration,
  average speed and average consumption, fuel and electric separately. These are the figures the car shows on its
  own display and the website shows online, and on these cars the EU Data Act portal does not deliver them at all.
  @realynot captured all three from his Tiguan in one session a month ago, including the awkward cases: a downhill
  trip where the electric consumption is **negative** because the car recovered more than it used (the website shows
  that too, and the sign is kept), a leg driven purely on electricity where the fuel figure is simply absent, and a
  month of individual trips that arrive in no particular order, so the newest is picked by its timestamp rather than
  by position.

### Changed
- **The "Volkswagen.de channel needs re-login" notice now has a Fix button that takes you straight to the login (#1717, thanks @Ra72xx).**
  Volkswagen asks for the e-mail one-time code again every few weeks, and until now the notice about it only told you
  what to do: open the integration's options and re-run "Add a Volkswagen.de read channel". Following that meant
  Settings, then Devices & Services, then finding the integration, then finding the **right** entry — anyone with two
  accounts or two cars set up separately has several, and the notice never said which — then Configure, then hunting
  for the tick box in the full options form. Six steps before you reached the login. Selecting **Fix** now does all of
  that for you and opens the login for the car the notice is about. The one-time code itself is unchanged: Volkswagen
  wants it and only you have it.

## [4.10.0] - 2026-10-04 — Full release / Voll-Release

The stable release that gathers the whole 4.10.0 beta line (b1–b5). The headline is that the
**volkswagen.de read channel works again**: from the morning of 2 October the site began answering
only over HTTP/2, which returned an error for every request this integration made, and every sensor
on that channel went unavailable. It now speaks HTTP/2, and a stored login survives the update.

Alongside that, the beta line brought: a battery charge level for plug-in hybrids on the
volkswagen.de channel; sixteen more high-voltage, thermal and climate readings for cars on the raw
portal feed, plus a lot of data the portal was already sending in a shape that got ignored; a sensor
for the portal's own delivery trigger; the distance since your last fill-up; the climatisation
duration the portal sends; and fixes so a frozen timestamp from the car no longer makes fresh data
look days old, an electric car without a reported charge level no longer loses every EV entity, the
channel no longer has to be re-added after each restart, a read refused for a missing subscription
says so, cars set to miles no longer get a 1.6× service interval, and the login stops claiming your
password is wrong when it isn't. The Vehicle Data Scout can also no longer post a VIN into a public
issue.

Thanks to everyone whose reports and captures drove this line: @Joassens, @eurojojo, @fschulte2812,
@Ra72xx, @Fishermanjb, @realynot, @dasebi91, @Datendieb, @kalwados, @josie127-neu, @user222008,
@iansyder8, @DanyZdog93 and @keithellis74.

Four more fixes land on top of the betas:

### Fixed
- **A volkswagen.de login that ends on an error page is no longer treated as a successful login.**
  The channel considered itself connected as soon as the final page came from volkswagen.de. But the manufacturer
  serves its own error pages from that same address, and the check above it only rejects outright HTTP failures —
  so an error page delivered as a normal page passed both. Reconfiguring then looked like it had worked while
  nothing usable was stored, and the car silently ran without its volkswagen.de data. The rule that the silent
  background refresh has always applied — an address carrying an error marker is not a login — now applies to the
  interactive login too. The error marker itself is checked for plausibility before being shown, so an
  upstream-supplied value cannot ride into a log or a bug report.
- **A portal outage no longer looks like an expired session, and no longer replays your password (#465).**
  Listing the cars on your account is the one portal call that has to fail loudly — an empty list would read as
  "this account has no cars" and end the setup. It did fail loudly, but as an authentication error, and the code
  that handles that has exactly one move: refresh the token or send the password again, retry, and then raise a
  "session expired" repair notice. So a portal hiccup lasting seconds sent your credentials back over the wire
  and then told you your login had gone stale. A server error now reports itself as what it is — the manufacturer's
  portal being unavailable — which skips the re-login entirely, keeps the message off the "check your password"
  track, and lets the next poll recover on its own. This is the same misdiagnosis fixed for the volkswagen.de
  channel in 4.10.0b4, one channel over, and this one sits in the **primary** read path for Volkswagen EU.
  A genuine 401 or 403 still means your session, and a 404 still means the data request is not provisioned yet;
  both behave exactly as before.
- **"Vehicle last reported" could run ahead of the mileage it describes, on cars whose odometer arrives under an opaque key (#1688, #529).**
  The freshness work in 4.10.0b5 anchors the reported time on the odometer's own capture, so the time can never be newer
  than the reading it belongs to — otherwise Home Assistant sees the mileage change, sees the time move past it, and can
  conclude the car was driven when it was not. Finding the odometer's capture time used a list of four field names, but
  some cars deliver the odometer under one of two opaque identifiers instead. On those cars the list found nothing and
  the code fell back to the newest timestamp in the file, which is exactly the thing it was written to avoid. It now
  asks which field the odometer was actually read from, so the two cannot drift apart, and when the answer is unavailable
  it leaves the time alone instead of guessing. The same four-name list was also used by the older safeguard twenty lines
  below, which had been silently inactive on those same cars; it is now wired to the same answer.
- **A Porsche login error could print part of the server's reply into a message you are asked to share.**
  When a Porsche sign-in or token refresh is rejected, the error shown in Home Assistant names the reason the
  server gave. That reason was taken from the reply and passed through **unchecked**, so if the server put
  something long in that field — an echoed request, or a token — it ended up verbatim in a message people paste
  into bug reports. The helper doing this was written to prevent exactly that and dropped the rest of the reply,
  but nothing bounded the one field it kept. It is now shared with the other login paths and only ever shows a
  value that actually looks like an error code; anything else reports as "no usable error code".
  Two things improve as a side effect: Porsche errors now also read the second field manufacturers use for the
  reason, which is the one carrying it in most real replies, so previously blank reasons will now be named — and
  there is one implementation of this for every brand instead of two that disagreed.

## [4.10.0b5] - 2026-10-04 — The timestamps that were in the file all along, and an error that finally names the page

### Fixed
- **The "data is stale" warning stops firing on fresh data, and per-field capture times finally appear (#1688, thanks @Datendieb).**
  He downloaded one of his own portal files and found what the integration had been missing: **every reading in it carries
  its own capture time**, minutes old — while the single "vehicle last reported" value the manufacturer sends alongside
  was frozen five days earlier. The integration only ever read that one frozen value, so it announced data as four days
  old while the readings beside it were from that afternoon. The earlier fix helped only for the one poll in which a
  reading happened to change, which is why he kept seeing the warning come back minutes later.
  The reason the per-reading times were ignored is embarrassingly small: they arrive under a spelling the parser did not
  recognise — and it is the most common spelling there is, 411 of the stored sample files use it against 140 for the one
  the parser knew. Two more things were quietly broken by the same gap. The per-reading capture times were empty
  everywhere (he spotted that too), and when a file repeats the same reading at different times — which this feed does
  constantly — the integration could pick the older one, because with no timestamps to compare it fell back to the order
  the file happened to list them in.
  Freshness now anchors on the readings themselves whenever the manufacturer's own timestamp is older than they are,
  preferring the odometer's own capture so the "last reported" time can never run ahead of the reading it describes.
  Cars that send no per-reading times behave exactly as before.

### Changed
- **A failed login now says which page it landed on, instead of just "no form fields found" (#1712).**
  When the login page is not the classic form, the error said nothing about what it actually was — not the address,
  not the form it found, not the field names it saw. That one line existed only in debug logging, so every report
  started with a round of "please switch on debug logging and try again" before anyone could tell which login variant
  had been served. It matters because there is more than one: the integration only treats a page as the modern login
  when the address says so, and the manufacturer demonstrably serves others — error, consent and terms pages all live
  under a different address, and our own stored samples contain seven of them. The message now names the page, the form
  it found, whether there was a form at all, and the field names it saw. Addresses are reported without their query
  string and with account identifiers masked, and field **names** are reported without their values, so the message
  stays safe to paste into a public issue.
- **A rejected token exchange now names the reason, not just "HTTP 400" (#1712).**
  The reason is in the reply and it distinguishes a wrong client, a spent code, an account that is not authorized and a
  refused method. Which key carries it was counted rather than assumed: 90 of the stored samples use `errorCode`
  against 18 for the one the standard prescribes, so reading only the standard key — as the first version of this did —
  would have found nothing on most real replies. Only a value shaped like an error code is ever shown; free-text
  descriptions, which echo request content back, are deliberately not read.

## [4.10.0b4] - 2026-10-04 — A channel that logged in and then said nothing

### Fixed
- **The volkswagen.de channel delivers data again (regression in 4.10.0b3 — thanks @fschulte2812 and @Joassens).**
  b3 gave that channel the HTTP/2 transport it needs, and the login worked — which is exactly why the rest looked
  fine. But every data read failed: the new response object did not accept one of the arguments the reading code
  passes it, which raised an error that the enrichment steps quietly skip over. The visible result was a channel
  that logged in happily and then reported nothing: the platform lookup died first, plug-in hybrids fell back to the
  wrong backend, every live read was refused, and all the sensors from this channel went unavailable. Both reporters
  found it within the hour, ran the same one-line fix on their own cars, and got the whole channel back — drive
  battery, electric range, fuel, combustion range, oil level, service interval. That fix is in here, along with
  returning nothing rather than an error for an empty response body, which is what the old library did.
  The test that was supposed to prevent exactly this checked which members the response has, not which arguments
  they accept. It now binds every real call site against the real signature, so the next mismatch fails in CI
  instead of in someone's house.

## [4.10.0b3] - 2026-10-03 — The wall that had broken volkswagen.de for everyone, a distance nobody could name, and four readings that were 1.6x too high

### Added
- **The distance since your last fill-up is now a sensor (Vehicle Data Scout, #1655 and nine more reports — thanks @user222008, @iansyder8, @DanyZdog93, @Nicohlav, @Neurupp2, @4ndy-bo and @checkner89).**
  Ten reports from seven accounts kept naming the same unmapped value, and it is in none of the 6610 entries of
  the manufacturer's own field catalogue, so for a week it was held rather than given a guessed meaning. Three
  things settled it. @iansyder8 happened to report the same car twice in one day, five and a half hours apart,
  with the value sixteen higher — so it counts up as you drive. The catalogue documents its two siblings as the
  car's short-term and long-term trip memories, both in kilometres, which fixes the unit. And @DanyZdog93 pinned
  the meaning from his dashboard: it is the counter with the fuel-pump icon, resetting when he refuels rather
  than at the start or end of a trip. The manufacturer's own app agrees — it has a whole screen for this memory,
  labelled "From refuelling" and described as "all journeys between two fill-ups" (on a hybrid, "from charging
  or refuelling").
  Diagnostic, off by default, and deliberately not wired to the odometer: the two are different quantities, and
  filling the odometer from a counter that resets would be a confident wrong answer on every car that has reset
  it. For the same reason the sensor records the value without claiming a long-term total. One thing is still
  open and asked in #1578: on a pure electric car nothing seems to reset it, so there the name is the closest
  honest label rather than the whole truth.
- **The climatisation duration the portal sends is visible instead of swallowed (Vehicle Data Scout, #1689 and thirteen more reports).**
  Twelve accounts reported this leaf, and the catalogue does not document it either. "Duration" could be how long a
  climatisation run lasted, how long one was configured for, or how long is left — three different sensors with three
  different units. All fourteen reports read zero, and in the seven that also carried the climatisation state it was
  off, which hints at a run time without proving it. Rather than invent a unit, the raw number gets its own sensor with no unit at all and
  "(raw)" in its name, off by default, and it is kept well away from the climate ETA sensor beside it, which is
  documented in minutes. A leaf nobody maps is re-reported on every poll, which is how fourteen issues happened.

### Fixed
- **The volkswagen.de channel works again: the site now requires HTTP/2 (#1679, thanks @eurojojo; #1313, thanks @fschulte2812; #1659, thanks @Joassens).**
  Since early October every request to volkswagen.de's app endpoints came back with a 502, which took the whole
  volkswagen.de channel down — logins, vehicle reads, everything. The cause is not the login, the account or the car:
  the site stopped answering those paths over HTTP/1.1 and now serves them only over HTTP/2. Browsers negotiate that
  automatically, the library this integration uses for every request speaks only HTTP/1.1, so it hit a wall it could
  not see. @eurojojo found it and proved it with a side-by-side of five different clients; @fschulte2812 and
  @Joassens then confirmed independently that reads, a credential login and an e-mail code all work over HTTP/2.
  This channel now speaks HTTP/2, and only this channel — nothing else in the integration changes. Your saved login
  is reused as before: the cookies live where they always did, so no re-adding and no new e-mail code.
- **A server outage no longer gets reported as an expired session (#1679, #1313).**
  The same 502 was being read as "your session died", because the error came back for the login address itself and
  so looked like a login page. Two things followed from that, and both were worse than the wrong message. The
  integration replayed your stored password to recover — which on accounts that use e-mail codes sent you a code for
  nothing — and it then told you to re-add the channel, while the saved session was in fact still perfectly valid.
  @fschulte2812 proved that: his three-day-old cookies resumed on the first try once the transport could reach the
  site. A server error now says so plainly, leaves the saved login untouched, never replays the password, and simply
  retries on the next poll.
- **A single junk number from the portal could discard a whole snapshot.**
  JSON allows the bare literals `NaN` and `Infinity`, and the portal is parsed as JSON, so one of those really can
  arrive in a reading. It then flowed straight through the parser's number conversion — where turning it into a whole
  number raises an error, and that aborted the mapping of everything else delivered in the same snapshot. If it did
  land in a sensor instead, it made the diagnostics download invalid JSON, so the dump attached to a bug report could
  no longer be read. The same literal in a capture-time field was worse again: that value is the sort key for picking
  the freshest of several readings, and since every comparison against it is false, "freshest" became arbitrary — and
  if it reached the last-seen anchor, the freshness check itself raised. Non-finite values are now dropped where they
  are converted, like any other unusable reading, and everything sent beside them survives. Found by a test written
  for the duration sensor above.
- **A negative reading from the car's trip computer no longer reaches a distance or duration sensor.**
  Three of the trip-computer values already ignored a negative reading; their twenty-odd siblings did not, so a
  negative could land on a sensor where it makes no sense — a trip distance below zero, a negative travel time, a
  negative average speed — and from there into long-term statistics, where it stays. Sixteen of those values now
  ignore a negative reading, and a plain zero still counts as real (a trip that was just reset genuinely reads zero).
  Decided value by value rather than by family name, because this family is mixed in two directions. The service and
  oil countdowns are *documented* as going negative: once you pass the interval, the manufacturer sends how far you
  have driven since, as a negative number, and the integration already turns that into a positive "overdue by" —
  a blanket rule would have replaced a real overdue service with no reading at all. In the other direction, the
  average monthly distance carries the maintenance prefix but is a distance you drove, so it does get the guard.
  Left alone on purpose: electric, auxiliary and recuperation averages, which are net-energy figures — a downhill
  trip can recover more than it uses, so a negative there may be the truth.
- **Cars set to miles no longer get a 1.6x service interval, oil interval, monthly average or last-trip distance.**
  A UK or US car's portal feed says which unit the car *displays*, and the integration used to convert every distance
  it had mapped whenever it saw "miles". But only some of the portal's distances actually follow the car's display:
  the manufacturer's own field catalogue gives a unit companion to exactly eight data points — the odometer, a
  generic distance, the two estimated cruising ranges, the per-engine range list, the two service-due values and tyre
  pressures — and documents every other distance as kilometres outright, several of them spelled out as "always in
  km". So four readings were being multiplied although they already arrived in kilometres: the distance to the next
  service and to the next oil change, the average monthly distance, and the last trip. On cars that report their
  ranges under the catalogue's kilometre-documented names, the range sensors were inflated the same way.
  Whether a value needs converting is now decided from the field it came from rather than from the sensor it feeds —
  which matters because most of these sensors can be filled from either kind of field, sometimes on the same car.
  Nothing changes for a car reporting kilometres, the odometer still converts as before, and readings from the older
  flat payload dialects — which is where the conversion was originally established from real cars — keep converting
  too, since nothing documents those either way.

## [4.10.0b2] - 2026-10-03 — A VIN the Scout should never have printed, two repairs that told the truth, and a charge level MBB hybrids never had

### Added
- **Plug-in hybrids on the volkswagen.de channel finally get a battery charge level (#1313, thanks @realynot and @fschulte2812).**
  On MBB plug-in hybrids the EU Data Act feed carries no drive-battery charge at all and the charging read is refused,
  so those cars have had no state of charge — the one number most people actually want. There is another read on the
  same session that returns both drives, and it is now used: drive-battery charge and electric range, plus fuel level,
  combustion range and oil level. Which drive is the electric one is taken from the data rather than from its position
  in the response, so a car that lists its engines the other way round still maps correctly. A reading from a live
  brand channel still wins where one exists.
- **Battery-care mode now reports why it last spoke up (Vehicle Data Scout, #1444, thanks @josie127-neu).**
  A new diagnostic sensor (off by default) shows the battery-care notification state — whether the charge target was
  reset for the next charge, whether care mode is off, or whether the care score hit its warning threshold. It had
  been left unmapped because its meaning was a guess; VW's own field catalogue documents the values, so there was
  nothing left to guess. Two long-standing neighbours of it (the care score and its threshold) were also quietly
  re-reporting themselves to the Scout on every poll for cars that send them nested — that's fixed in passing.

### Changed
- **A read refused for a missing subscription now says so (#1659, thanks @Joassens).**
  His maintenance read came back as `4007 connectivityLicenseInactive`, which is precise and tells you nothing about
  what to do — he read it as a registration problem, so did I, and he eventually solved it by buying the paid Car-Net
  subscription, which is exactly what the code meant. Those refusals now spell out the action, once per read, in the
  log and in the error. The two cases are worded differently on purpose: an expired subscription needs paying for, an
  account that isn't enrolled needs enrolling — and a refusal we haven't understood still says nothing rather than
  guessing.

### Fixed
- **A frozen timestamp from the car no longer makes fresh data look days old (#1688, thanks @Datendieb).**
  His portal kept delivering all afternoon — odometer and charge level visibly moving — while the timestamp the car
  reports about itself stayed five days old. The "data is stale" warning and problem sensor were built on that
  timestamp alone, so they claimed 105 hours on data that was minutes old. A reading that has actually changed since
  the last poll now proves the data is live and overrides the timestamp. Deliberately one-directional: unchanged
  readings still prove nothing, because a car parked for days repeats them and a genuinely dead feed must still be
  reported. He also spotted that "minutes since last snapshot" contradicted the snapshot time right next to it —
  that field was measuring the car's timestamp instead of the snapshot, and now measures the snapshot.
- **The "no vehicle data yet" warning really does name the car now (#1656, thanks @kalwados).**
  The first attempt at this shipped in the last beta and still showed only the brand. The warning is raised from the
  portal's own state, which is independent of any per-car flag — and the flag the first version filtered on isn't
  reliably set, so on exactly the accounts this warning fires for, nothing matched and it fell back to the brand.
  It now prefers the car that is actually flagged (useful when one car on the account works and another doesn't) and
  otherwise names every car on the account, since the warning means the account's portal is delivering nothing.
- **The volkswagen.de channel no longer tells you your password is wrong when it isn't (#1679, thanks @Fishermanjb; #1313, thanks @realynot).**
  Both reporters had the channel refuse them with "email address or password incorrect" while the very same
  credentials signed in fine on volkswagen.de and even reached the e-mail-code step. The login itself was careful
  about this — it only gets a real "wrong credentials" answer from a specific refusal — but both places that show
  you the result threw every other failure (an expired session, a redirect loop, a page it didn't recognise, the
  portal being down) into the same message. So people were sent off to reset a password that was never the problem.
  Only the genuine credential refusal says that now; everything else says it is *not* your password and points at
  the log, which has carried the real reason for a while.
- **The Porsche login now tells Auth0 which language and country you are in.**
  The official Porsche app passes the device locale into its login call; we sent
  nothing, so the page we land on came back in whatever language Auth0 guessed.
  That matters less for you than for us: when a login runs into one of Porsche's
  wall screens, the integration describes it by looking for English keywords, so
  an unexpected language could leave a report saying nothing at all about what
  was hit. It now sends your Home Assistant language and country, which also
  matches what the app does. Nothing is invented — a country the integration
  doesn't know is simply left out rather than guessed.

### Security
- **The Vehicle Data Scout can no longer post your VIN into a public issue (#1690).**
  One portal field carries a credential blob with the car's VIN encoded inside it. The Scout masks VINs by looking
  for them as readable text, so it never saw this one, and the length limit that follows happened to leave the VIN
  inside the part that got posted. It had leaked five times — four of those were cleaned up by hand afterwards
  without the masking itself being fixed. Encoded identifiers are now detected and the whole blob is replaced before
  anything is written out; what remains says only what kind of value was removed and how long it was. Already-posted
  issues were redacted. Nothing about ordinary readings changes.

## [4.10.0b1] - 2026-10-02 — An EV that was not recognised as one, the data the portal hid in blobs, and a channel that needed re-adding after every restart

### Added
- **Sixteen more HV, thermal and climate readings for cars on the raw-signal portal feed (#1661, thanks @dasebi91).**
  The same feed we already read cell voltages from, but this car sends a different signal set from different control
  units. New: drive-battery current (the sign is kept exactly as the car reports it — charging is positive), energy
  drawn from the pack and whether those counters have wrapped, the coolant feed temperature and the whole HV coolant
  loop, the two coolant valves, where in the pack the hottest/coldest sensor and the highest/lowest cell actually sit,
  the climate and heat-pump state, the blower target, and the outside temperature. Two readings are deliberately not
  believed: a −40 °C "no reading" sentinel, and a charge-plug status that reports as uninitialised — calling that
  "no cable" would be a confident wrong answer.
- **A lot of data the portal was already sending, in a shape we ignored (#1661, thanks @dasebi91).**
  Some cars' portal feed carries whole vehicle diagnostic responses as encoded blobs — on the reporter's car that was
  ten of them, thrown away on every poll. They're decoded now, which brings: the range the car's own display shows,
  the complete 12 V battery picture (voltage, charge, temperature, ageing, current), an outside humidity and dew-point
  reading (the integration had no humidity at all before), plus the odometer and a genuine per-read capture time.
  The 12 V battery's charge is kept strictly apart from the drive battery's — they are not the same number. Blobs we
  can't interpret yet are deliberately left untouched so they keep being reported instead of silently vanishing.
- **The portal's own data-delivery trigger now has a sensor (Vehicle Data Scout, #1637 and 16 more reports).**
  Twenty-two Scout reports landed in two days, across Volkswagen, VW Commercial, Audi and CUPRA, all for the same
  leaf: the delivery trigger the EU Data Act snapshot carries about itself. It gets its own diagnostic sensor rather
  than being folded into the existing report trigger — the official portal field catalogue documents those as two
  different things with different value sets, so one sensor for both would have mixed two unrelated enums. Off by
  default. A leaf nobody maps is re-reported on every single poll, which is how twenty-two issues happened.

### Changed
- **The "portal has no vehicle data yet" warning now names the car it's about (#1656, thanks @kalwados).**
  The warning is raised once per account and only mentioned the brand, so with two Volkswagens on one account there
  was no way to tell which car was affected — and it really can be one and not the other. It now lists the cars that
  are actually without data, with the VIN shortened to its last six characters, because people paste these warnings
  into bug reports. With nothing known yet it falls back to the brand name, exactly as before.

### Fixed
- **An electric car whose feed has no state of charge no longer hides every EV entity (#1661, thanks @dasebi91).**
  The integration decided a car was electric from its state of charge, electric range or charging state. The
  reporter's ID.7 sends none of those three — but it does report a 218 Ah drive battery at 355 V with per-cell
  voltages and pack temperatures, and it was still treated as not-electric, so the whole EV entity set stayed hidden.
  That is what it looked like as "missing battery SoC": the sensor wasn't empty, the car wasn't recognised as electric
  at all. A drive battery above 60 V (the legal high-voltage threshold, so a 48 V mild hybrid can't trip it) now
  counts as evidence on its own. It only says "this car has a drive battery" — it deliberately doesn't claim the car
  has no engine, because a pack voltage doesn't prove that.
- **The volkswagen.de read channel no longer has to be re-added after every restart (#1659, thanks @Joassens).**
  On some accounts the silent session resume bounced straight back to the portal's own login page. That landing
  wasn't recognised as a dead session, so the channel reported "could not silently resume" and never tried the
  stored-password re-login some users had switched on — it just told them to re-add the channel, every single
  restart. It's recognised now: the opt-in re-login gets its chance, and if it isn't on, the message says the
  session expired instead of something opaque.

## [4.9.0] - 2026-10-01 — Portal climate target temperature, a deleted-car cleanup, and a VIN kept out of the repair id

### Added
- **Climate target temperature now shows for portal-read cars (Vehicle Data Scout, #1624 and many more reports).**
  The modern MEB EU Data Act export carries the set cabin temperature under its climatisation-settings block as a raw
  bus value. It now feeds the existing target-temperature sensor for cars that only have the portal read, decoded from
  that bus value (multiple reporters cross-confirmed the scaling). A brand-native or app-backend reading still wins
  where one is present.
- **The mirror-heating setting now fills for modern portal cars too (Vehicle Data Scout, #1637, thanks @pietervanhertum).**
  The modern MEB export carries the mirror-heating enable under its climatisation-settings block; it was the one leaf in
  that block without a modern alias (the climate zones already had theirs), so it now feeds the existing mirror-heating
  sensor instead of re-filing on the Scout.
- **Companion (ADB): optionally close the car app after each read (#1552, thanks @nekas123).** A new
  opt-in force-stops the car app once each poll finishes, so the next read relaunches it fresh instead
  of scraping a screen the app left cached. It's for devices where the app freezes its own values
  between reads; it's off by default (a cold relaunch is slower) and sits next to the existing companion
  toggles in Configure. Reload after toggling.

### Fixed
- **A car removed from your account is no longer polled forever (#1628, thanks @ekirchma).** The vehicle list was read
  from the account only at setup and the cache was never reconciled against it, so a deleted car kept getting polled
  and 404-spamming the error log. On a genuine account read, a cached vehicle that's no longer on the account is now
  pruned, so a reload/restart clears the removed car and its stale device is removed automatically. A partial or failed
  enumeration never prunes, so a real car is never dropped by mistake.
- **The climate "time remaining to target temperature" no longer stays frozen after a run ends (#1231, thanks @Ra72xx).**
  On a multi-channel car the climate ETA could come from the EU Data Act portal's batch feed, which keeps re-sending
  the last run's value, while the live climatisation state (from the live channel) already reads off. The ETA now
  zeroes whenever climatisation reads off — matching the app and the pre-heater timer — and it joins the live-supersede
  rule the charging-time ETA already uses, so a live channel's value wins over a stale portal one.

### Security
- **The stale-data repair no longer embeds your full VIN in its id (#1626, thanks @eddieari).** Home Assistant's
  stale-data repair keyed its internal id on the raw VIN, which is written as-is into a diagnostics download — unlike
  the VIN fields, which are masked — so a shared diagnostic could expose the full VIN. The id now uses the masked VIN,
  and an id raised before the upgrade is cleared automatically.

## [4.8.0] - 2026-09-29 — BMS cell telemetry, a brake-fluid warning, and multi-channel SoC/typing fixes

### Added
- **Brake-fluid warning now surfaces as its own binary sensor where the car reports it (Vehicle Data
  Scout, #1592).** An Audi Q6 (PPE) ships the brake-fluid warning lamp as a raw FlexRay/ESC signal in
  its Data Act export. It's now decoded into a "Brake Fluid" problem binary sensor (on = warning
  active); cars that don't report the signal get no entity. Only the OFF state is confirmed so far, so
  the active decode is conservative (anything that isn't the OFF value reads as a warning).
- **Battery cell-level telemetry for cars that report it (Vehicle Data Scout, #1622).** Some VW cars
  ship raw battery-management (BMS) signals in their Data Act export. These now surface as diagnostic
  sensors — highest/lowest cell voltage, battery coolant return temperature, battery capacity,
  recuperated energy and pack voltage — and the cell-temperature extremes feed the existing HV battery
  temperature (min/max) sensors. All are disabled by default and only created for cars that actually
  report the signals; the raw module/cell index fields stay visible in diagnostics until their meaning
  is documented.

### Fixed
- **A live vw.de state-of-charge no longer gets dragged to the EU Data Act battery figure (discussion #1231, thanks @Ra72xx).**
  On a multi-channel car (vw.de read live + the EU Data Act portal filling gaps) the fresh vw.de SoC could be
  overwritten by the portal's battery-energy figure, so the reading "bounced" to a lower number and lagged the live
  channel. The portal feed is a ~15-minute batch that can re-send a frozen stop-charging snapshot, so a live on-demand
  reading now always wins over it for SoC — on both the energy-sanity and the contested-value paths. Single-channel
  portal cars are unchanged: there the battery figure still corrects a genuinely stuck reading.
- **A combustion car with an empty data feed is now typed correctly (#1538, thanks @Latte9090).** A Golf
  GTD (diesel / ICE) read over the vw.de channel showed `has_combustion = false` when its EU Data Act
  feed was empty and the status carried no fuel/range block — even though VW's own relations response
  classifies the car as ICE (`carnetAllocationType`). We now read that classification and set the
  drivetrain from it (ICE → combustion, BEV → electric, hybrid → both), additively — only ever setting
  a flag true, never forcing it false — so an empty feed no longer mistypes the car.
- **An odometer sitting at exactly 65,535 km is no longer blanked.** `65535` (0xFFFF) is VW's
  "no reading" marker on bounded portal fields (state of charge, range, charge time, temperature), so
  it was dropped everywhere — including a genuine 65,535 km reading on the odometer / lifetime-distance.
  It's now kept for the mileage/odometer family (a plausible real value there) while still being
  dropped on the bounded fields; the separate odometer guard still screens VW's real 32-bit "no value"
  markers.
- **Companion (ADB) EV cars now get their battery entities (#1552, thanks @nekas123).** A companion-only
  read that parsed a valid state of charge / range still left `has_battery` false, so the Battery SoC,
  Electric Range and charging entities never appeared. A companion read now infers the battery from a
  present SoC/range (like the brand parsers already do); it only ever sets the flag true, so a
  combustion car is unaffected.
- **Companion (ADB) detail-screen values no longer freeze after the first read (#1552, thanks @nekas123).**
  The nav-read cache was re-applied before the "is a refresh due?" check, so the detail walk saw its
  targets already filled and skipped forever after the first read — charge target / power / time (and,
  on newer layouts, SoC and range) went stale. The scheduled refresh now runs first, and a fresh detail
  value wins over a stale overview one.
- **Companion (ADB) no longer halves its overnight poll rate for no reason (#1552, thanks @nekas123).**
  The 22:00–05:00 cadence reduction saves cloud API calls, which a local ADB read doesn't make — so it
  now skips a companion entry, unless the wake/sleep opt-in is on (there the slower night cadence also
  cuts how often the phone screen wakes).
- **The portal `climacontrol` flag now feeds the climate-active sensor instead of just being noise
  (Vehicle Data Scout, #1603).** A VW Passat's Data Act export carries a bare `climacontrol` on/off flag
  — the same "climate is running" datum the climatisation-active sensor already shows. It's now folded
  in as a fallback (the richer climate-state read still wins) and no longer flagged as an unmapped field.
- **A car the BFF doesn't serve no longer spams the log with 404s (#1590).** An Audi Q4 whose
  selectivestatus read persistently returns 404 (the backend simply doesn't serve it) used to raise on
  every poll — filling the error report and re-hitting the dead endpoint. After a few consecutive
  structured 404s the integration now backs off for a few hours (re-probing automatically) and shows
  the car's last-known data as stale instead of erroring, while a one-off or transient 404 still
  surfaces as before.

### Docs
- **Clearer where the test-cohort opt-in actually lives (#584, thanks @Donath206).** A new FAQ entry
  spells out that the toggle sits in **Configure** on the existing entry (dialog "VW Group Connect —
  Settings"), not in the "Add integration" / „einrichten" wizard where you pick a login method — with
  the German UI labels too, since that's exactly where the mix-up happened.

## [4.7.16] - 2026-09-25 — A signed VIN-bearing auth token, kept out of diagnostics

### Security
- **A signed auth token that embeds the VIN is now withheld from discovery (#1510).** The portal ships
  `auth_signature_response` — a hex blob containing the VIN plus a cryptographic signature. It's
  credential/identity material, not vehicle data, so it now joins `idp_idt` in the withheld set: it
  never reaches the raw-discovery diagnostic sensor (and therefore never a diagnostics download or a
  public Vehicle Data Scout report). A Scout issue had already surfaced a decodable VIN inside it.

## [4.7.15] - 2026-09-25 — The new MEB climate dialect, mapped — and the Scout flood it caused, silenced

### Added
- **Climate state now shows for portal-read cars (Vehicle Data Scout, 2026-09-25).** The EU Data Act
  portal reports `climatisation_state` (OFF / HEATING / COOLING / …), flagged by ~8 VW ID.x reporters.
  It now feeds the existing climatisation-state sensor for portal cars — the redundant
  `CLIMATISATION_STATE_` prefix is stripped to match the OFF/HEATING format the brand channels use.
- **More climate settings + the hood fill in for portal-read cars (Vehicle Data Scout, 2026-09-25).**
  The newer MEB portal moved several fields to a nested `climatisation_settings` block with slightly
  different names — the four climate-zone enables (incl. a rear pair the old dialect lacked),
  climatise-at-unlock and climatise-without-HV-power. They now feed the SAME existing sensors as the
  older dialect. Some cars also report the hood as a percentage (`position_of_hood`, 0 = closed)
  rather than an open/closed enum — that feeds the existing hood sensor too (VW T-Roc, #1446).
  (The nested `target_temperature` VW is now shipping stays unmapped for now — its unit isn't in the
  published data dictionary and one sample isn't enough to decode safely.)
- **Climate error code + trigger reason for portal cars (Vehicle Data Scout, #1492, VW Touareg).** A car
  reporting a climate fault now surfaces the code on the existing climate-error-code sensor
  (`climatisation_state_error_code` → `climate_error_code`), and the climatise trigger reason
  (`climatisation_reason_trigger`, e.g. IMMEDIATE) is captured in diagnostics. (The same car's
  `cycle_data_mileage` stays unmapped — it isn't in the data dictionary and its unit can't be decoded
  from one sample.)


### Changed
- **Two portal request-metadata fields no longer flood the Vehicle Data Scout (2026-09-25).** The
  export's `auth_level` (consent level) and `transaction_id` (the export request's id) describe the
  request, not the car, and repeated on every poll. They join the existing envelope carve-out
  (alongside account id / VIN / timestamps). Leaf-matched, so the meaningful charging-session
  `ocpp_transaction_id` stays fully visible.
- **The MEB speedometer calibration curve is bundled instead of flooding the Scout (2026-09-25).**
  Newer MEB cars ship `setup_real_speed_ratios.*` — a fixed factory speed-calibration curve (~4
  control points, ~10 fields per car). It's real vehicle data but not a live reading, so rather than
  suppress it (it isn't envelope metadata) or spawn ten meaningless sensors, the whole curve is
  bundled into one `speed_ratio_calibration` value kept in the diagnostics download, and its fields
  are consumed so they stop re-filing Scout issues on every MEB car.
- **A failed Data Act request-kickoff now records why (#1439, thanks @maki040).** When the portal
  can't create a Custom Data Request (e.g. a 503 backend error, or a 4xx account rejection), the
  reason is captured per VIN and surfaced in diagnostics as `data_act_kickoff_errors`, so it stays
  visible during the re-POST backoff and after a restart — no debug logging needed.
- **Repo hygiene.** Removed a shadowed duplicate departure-timer sensor block (a VW-EU twin that never
  spawned, because the Škoda block registers the same keys first); corrected the outdated
  "requirements: []" notes in dependabot.yml and quality_scale.yaml (there are three opt-in
  dependencies — firebase-messaging, aiomqtt, adb-shell — for the push and companion channels); and
  raised the CI coverage floor from 65% to 75% (actual is 79%).

### Fixed
- **A climate system reporting "error" no longer reads as actively climatising (#1492).** The portal
  `climatisation_state` can be `error`; it now surfaces as ERROR but derives climatisation-active as
  false (only OFF and ERROR are non-active), instead of treating the fault as an active state.
- **A vehicle disabled in HA (sold, retired) stayed fully polled by three background paths
  (#1434, thanks @skornehl).** `async_setup()`'s one-time prefetch already filtered its VIN
  list through `_active_vins()`, but that isn't the periodic driver — `update_interval` is
  `None`, so `_poll_loop()` is. It built its VIN list straight from `self.vehicles.keys()`
  with no filtering, and so did every best-effort refresh inside it (trip stats, charging
  history, fueling, parking, predictive maintenance, departure timers, consents, charging
  profiles, battery care — nine calls total), `_async_update_data()` (the manual-refresh path
  fired after every command against ANY vehicle on the account), and
  `_refresh_mbb_command_capabilities()` (warms the MBB operationList, called from both loops).
  All four now apply the same `_active_vins()` filter `async_setup()` already used, so a
  user-disabled vehicle stays fully quiet — sending a command to your active car, or the
  regular poll tick, no longer re-touches a car you disabled. History and entities are
  untouched either way; only re-enabling the device resumes polling that VIN.
- **…and the Data Act portal request-kickoff is filtered too (#1434 follow-up).** The one remaining
  periodic path that still touched a user-disabled vehicle — the EU Data Act 15-minute request
  probe/kickoff in portal mode (reachable from the poll loop and from the manual-refresh path) — now
  applies the same `_active_vins()` filter, so a disabled car is genuinely fully quiet.

## [4.7.14] - 2026-09-23 — The reads a 403 used to hide, and a login that skips the login page

### Added
- **Škoda: fuel level and oil-service distance over the Data Act portal (#1430, Vehicle Data Scout).**
  Two Škoda EU-portal leaves the Scout surfaced — `fuelLevel` and `inspectionOilDistance` — now map
  onto the existing fuel-level and oil-service-distance sensors, so a portal-read Škoda fills those
  in instead of leaving them empty. (The VW `energy_contents.*.value_type` and `open` qualifiers stay
  mapped-but-unpromoted by design — they gate other values rather than earning their own sensor.)


### Changed
- **Repo hygiene.** Two module headers that still read "Apache License 2.0" now match their own AGPL
  SPDX line and the rest of the tree; the release action is pinned to a commit SHA; the prerelease
  detection recognises any beta/rc tag regardless of patch number (a `vX.Y.14b1` no longer publishes
  as a full release); and SECURITY.md's supported-versions table is current.
- **Brand-support docs corrected (#464, #1432).** Bentley is marked untested (offered on the Audi
  tenant but never logged in), a 2026-09 report of Canada VW sign-in hitting device attestation is
  noted, and the FAQ brand table now matches the README (SEAT/CUPRA shown as read-only with commands
  blocked).
- **A failed MBB command now logs the commanded service's own licence (#584).** The command log
  showed the shared subscription licence but not the per-service one, so a charge or climate command
  that failed on an expired `rbatterycharge_v1` / `rclima_v1` licence looked identical to any other
  refusal. The service's own licence status + expiry are now in the log.

### Fixed
- **A fresh reading next to a frozen one no longer triggers a false "data is N hours old" (#1431,
  thanks @Lagaff86).** The EU Data Act feed can ship a fresh block beside a frozen one, so a single
  poll may carry the older stamp; the staleness watchdog measured that stamp directly and raised a
  repair (e.g. 166 h) even though the recorded snapshot was current (3.5 h). It now measures against
  the freshest capture available, so the repair fires only when the data is genuinely frozen and
  clears the moment a fresher reading lands.
- **Diagnostics can name why a vw.de read was refused (#1313).** A walled core read recorded only the
  HTTP status, so a plain dead-session 403 looked identical to a per-consent refusal. When the refusal
  body carries a known CARIAD error code it is now decoded into the log and the diagnostics (e.g.
  "403 (BFF 2101 userNotEnrolled)") — structured code only, never any body text.
- **A charging wall on vw.de no longer hides the mileage (#1313, #923).** The charging and
  maintenance reads shared a single guard, so when the charging endpoint returned 403/401 for a car,
  the maintenance read — which carries the odometer — was skipped entirely; three reporters saw an
  empty mileage as a result. Each read is now guarded on its own: a wall on one is recorded for
  diagnostics and the other still runs, and the poll is only abandoned (and the session re-checked)
  when nothing at all came back.
- **Audi and VW browser login recovers when the login page is skipped (#1439, thanks @maki040).** With
  a warm single-sign-on session the identity provider can jump straight to the app's own return
  address instead of rendering the login page, and the HTTP client cannot follow that address — so the
  attempt used to be thrown away and the login fell back to the portal strategy. The tokens carried in
  that return address are now read directly, and the login completes.
- **Entities survive a restart even when the first poll fails (portal-safety cache).** On startup the
  integration restores the last-known-good snapshot, but it did not carry the "last good" timestamp
  with it, so a single failed first poll after a restart dropped every entity to unavailable although
  a valid snapshot was loaded. The restore now seeds that timestamp from the snapshot's own save time.
- **Departure timers stay off combustion cars (#1316, from EcksteinU's diagnostics).** The three
  Škoda departure-timer time sensors and their "enabled" binary_sensors were the last timer entities
  without the electric-only gate their VW-EU twins already carry, so a diesel or petrol car could
  spawn charging-departure timers that never apply to it. They now appear only on cars with a battery.

## [4.7.13] - 2026-09-17 — Three fixes the reporters' own captures found

### Fixed
- **vw.de: colour, model and renders really arrive now when the live reads are walled (#465, toglo's
  4.7.11 log).** 4.7.11 fetched them on a walled poll and then threw the result away by re-raising the
  core failure, so the channel contributed nothing and the log showed the wall twice per poll. The
  partial snapshot (static fields only) is now returned; a genuinely dead session still triggers the
  refresh and retry.
  The render and master-data reads also record their own status, so diagnostics can tell a refused
  read apart from one that answered with nothing.
- **A Data Act request the portal refuses for an account reason is no longer re-sent every few hours
  (#1412, thanks @chrisbamtam).** When the portal answers "primary user relation is missing tag
  EUDA_SCOPED" no Identifier is ever stored, and the attempt timestamp was only checked when one
  existed — so the request was posted again on every setup, reload and six-hourly retry, twice per
  pass. The same 24-hour backoff now applies without an Identifier; the manual "create data request"
  button still retries immediately.
- **Diagnostics can tell a missing position from a rejected one (#923).** The portal's `persLocation`
  leaf is consumed whether or not it parses, so a pin we refused (malformed, out of range, 0/0) used
  to leave no trace at all. The refusal is now recorded — the value's shape only, never coordinates.

## [4.7.12] - 2026-09-17 — What the new Škoda and Porsche apps brought, plus the MBB market fix

### Fixed
- **MBB commands on a car outside Germany no longer default to the `/VW/DE/` market path.** The
  final charge/climate action is the only leg that carries a market segment; it came from the
  account token or fell back to a hard `DE`, so a Dutch Passat GTE passed both S-PIN legs and was
  refused at the action. The segment now falls back to your Home Assistant country before `DE`, and
  every MBB command logs one line with the service, whether the car's service list grants it, the
  host VW handed us and the market segment with its source — no VIN (#584, thanks @pp2stay for the
  controlled re-test).
- **Scout: seven `*.is_set` envelope flags no longer show up as undiscovered fields** (#1421, thanks
  @skornehl). They say "this block was populated"; the values they belong to were already mapped.

### Added
- **Škoda: battery state of health.** MyŠkoda 8.16.0 added a battery-health read; the *Battery State
  of Health* sensor now fills on Škoda cars that report it, with the health status as an attribute.
- **Škoda: brake-pad wear prediction.** The predictive-maintenance feed grew a predictions block;
  a new diagnostic sensor shows it (*Brake Pads Wear Prediction*).
- **Škoda: official API key minting checks the car's capability first.** Cars without
  `PUBLIC_API_KEY_MANAGEMENT` are skipped with a clear diagnostic reason instead of a bare 400
  (#1286, #1310 — this is the likely explanation for both reports).
- **Porsche: charging session history.** The app's charging history (per session: start, end,
  plug-in/out, duration, AC/DC, average and peak power, energy, start and end battery %) now feeds the
  existing last-charging-session sensors and the recent-sessions attribute — the data was already being
  fetched and dropped.
- **Porsche: `unlock_trunk` service (experimental).** The app now exposes the tailgate unlock as a
  user action; the command existed in the integration but had no service. Same S-PIN flow as unlock;
  not live-verified yet.
- **Porsche: more raw-capture measurement keys** (trip statistics short/long/cyclic, dampers, tyre
  sealant, tyre-pressure warnings) so the Scout can show their shape.
- **App Atlas tracks the rest-of-world Porsche app** (`de.porsche.one`) next to the North-America
  build; both are identical code at 20.26.37. The verified 20.26.31→20.26.37 and 8.15.0→8.16.0 diffs
  are on the atlas pages.

## [4.7.11] - 2026-09-16 — Competitor parity round: vw.de master data that stays, fresher portal readings, richer timers, honest diagnostics

### Fixed
- **vw.de: colour, model and the exterior pictures no longer vanish when the live web reads are refused.**
  Those three come only from the vw.de channel. When VW refuses the channel's live reads for a car, the
  read aborted before the calls that fetch them, and a poll that brought nothing new wiped the values
  already shown. They are now fetched on their own even when the live reads are walled, kept as
  last-known values across empty polls (they don't change for a car), and the log names which vw.de
  read was refused and with which status — so the next capture says what VW actually serves
  (#465, thanks @toglo for both logs).
- **vw.de debug lines now mask the VIN inside request paths.** A second pattern with the same name
  had shadowed the URL masker, so the path VIN slipped through into debug logs (the JSON-body masking
  was unaffected). Found while adding the line above.
- **"Closures secured" no longer flips to false on a closed bonnet/tailgate.** VW's bonnet and tailgate
  "safe state" values don't follow the door polarity (a live capture shows 3 while closed); the
  aggregate now uses the three door fields only.
- **Diagnostics show the vw.de channel's read outcomes.** The vw.de charging/maintenance reads record
  their status, and the connector's outcomes are exported even before the first read — the table a
  reporter asked for was never wired (#1313, thanks @realynot).
- **The portal's `heading` value finally has a sensor.** 4.7.6 parsed the heading that arrives next to
  `persLocation` on MEB portal cars, and its release note said it came through as a sensor — it didn't;
  there was no entity. *Heading* (degrees, disabled by default) now exists (#1378, thanks @Laurentwb).
- **Options help text for the EU Data Act auto-kickoff said "opt-in, off by default" — it has been on by
  default since v2.17.1.** Corrected in all 13 languages; taken literally, the old text could talk you into
  switching off the very thing that creates your data request.
- **SEAT/CUPRA probe script: a host name that doesn't exist no longer reads as "unreachable from you".**
  `mal.prd.ece.vwg-connect.com` was only ever a token audience, not a host (NXDOMAIN at VW's own
  nameserver); the probe dropped it and now tells a DNS miss apart from a connection failure instead of
  blaming the reporter's network (#306, thanks @goncal for the three-resolver check).
- **CONTRIBUTORS.md caught up:** 18 reporters credited in the 4.7.x notes were missing from the list.
- **CUPRA/SEAT browser-login entries: the portal fallback now says why it can't sign in.** The 4.7.10
  automatic EU Data Act portal fallback signs in with the stored e-mail + password — an entry set up
  with the browser login stores none, so the sign-in failed silently and readings stayed empty with only
  the "arming" line in the log. The doomed attempt is skipped and the log now names the fix (Configure →
  "Add or refresh the EU Data Act portal read channel"); a failed portal sign-in is logged too (#306,
  D#1415).

### Added
- **Portal feed health shows how much of VW's export actually carries values.** VW's EU Data Act
  export can deliver field names with timestamps but no value at all (a Tiguan III export: 10 fields,
  3 with values). The portal-feed-health sensor now reports the fields with values, the count of
  fields delivered without one, and their names — so "ok" no longer reads as "complete" when it isn't
  (#465, thanks @BooM80 for reproducing it in VW's own export).
- **Scout feed: `ErrorReason`** now feeds a diagnostic *Error Reason Code* sensor (disabled by default,
  raw code, "0" = no error) (#1421, thanks @skornehl).
- **vw.de: opt-in re-login with the stored password when the web session dies.** Off by default. When
  the silent session resume fails and you've switched it on, the integration signs in once with your
  stored password (at most every 15 minutes); if VW asks for an e-mail code it stops there without
  submitting anything and the usual re-add-with-code path applies. Mirrors what the other volkswagen.de
  project does, kept opt-in because a fresh sign-in can trigger one e-mail code (#465, #632, #966).
- **Portal readings say how fresh they are.** Sensors fed by the EU Data Act feed carry
  `data_captured_at`, `freshness_source` and `ambiguous_reading` attributes (the last one flags a
  reading whose candidates disagreed under one capture time) — no per-poll churn, no new entities
  (#465, #529, #1218).
- **Departure timers can carry charging, climatisation, target battery % and a one-off date.** The
  `set_departure_timer` service accepts the extra fields; they are sent on the CARIAD path only for
  entries in the test cohort until one live capture confirms the field names, and ignored otherwise.
- **Connected-services breakdown.** The subscription diagnostic sensor lists each connected service
  with its expiry and status as attributes (capped), not just the earliest expiry.
- **vw.de cars: the side/¾ render becomes the vehicle picture**, and the (static) model name and
  render list are cached for 24 h / 6 h instead of being re-fetched every poll (#1229).
- **Porsche: charging power on newer cars** (`chargingPowerkW`, the legacy field reads 0 on a 2026 Macan
  Electric) and the climatiser target temperature now feed their sensors.
- **Seven ready-made automation blueprints** — charge complete, low battery, door/window/trunk left open
  while away, pre-heat before departure, service due, tyre-pressure warning, parking position changed —
  under *Settings → Automations → Blueprints*; notifications were the most-requested thing across every
  car integration's tracker, and the data was already there.
- **Named triggers and conditions can target one car.** An optional `vin` (or the car's device) scopes
  the experimental named triggers/conditions; unset keeps today's account-wide behaviour.

## [4.7.10] - 2026-09-14 — Portal logins that actually complete, and a refresh loop that hammered vw.de

### Fixed
- **Audi/VW Group portal login no longer dies on the Terms & Conditions step with an "accept in the app"
  message when nothing is pending.** The T&C auto-accept posted the form without the page's own query
  parameters, which the sign-in service rejects with a branded error page — the same mistake the consent
  step had been cured of earlier this year. The accept now posts exactly like the consent step does, and a
  sign-in-service error page is reported as what it is instead of being blamed on unaccepted terms
  (#1417, thanks @jens762001-cpu).
- **A supplementary vw.de channel with a dead web session no longer drags the integration into a refresh
  loop.** Every re-login attempt rotated the stored cookies, storing them counted as a settings change, and a
  settings change triggered another refresh — one full cycle every ~10 s, hammering VW's identity server
  and flipping the source sensors. The integration's own bookkeeping writes no longer count as settings
  changes, the vw.de re-login is attempted once per cycle, and manual refreshes compute the channel status
  the same way scheduled polls do (#465, thanks @toglo for the debug log).
- **CUPRA/SEAT: when VW's attestation wall blocks every per-car read while the garage still answers, the
  read-only EU Data Act portal is armed automatically.** Until now that only happened when the garage call
  itself was blocked; the per-car case left the entry stuck with empty readings, no fallback and a
  re-authentication that changed nothing (#465, thanks @anju1337 for the smoking-gun log).
- **"Vehicle data not updated for N hours" no longer fires on cars whose live channel is vw.de.** The
  warning measured the age of the EU Data Act portal snapshot only; the vw.de channel now stamps its own
  capture time and the freshest capture across channels counts (#1419, thanks @Ra72xx).
- **Porsche: a login that Porsche hands over to its web portal is explained, not just declared a wall.**
  The message now says what to do (sign in once at my.porsche.com in a normal browser, complete what it
  shows, retry) and the report link carries the exact portal path (#1400, #1337, #1414).
- **EU Data Act request creation: the portal's actual reason is logged when it refuses a request.** Only the
  length of the reply was logged, and the wording claimed a rejected duration it could not know (#1412,
  thanks @chrisbamtam).

### Added
- **Scout feed: single-port charge/fuel flap fields.** `flap_state`, `flap_lock_state`, `flap_error_state`
  and `plug_lock_state` now feed sensors (the dual-port variants already did) (#1413, thanks @hietaki).
- **Test cohort: a third MBB probe target** (operation list on the EU-DP host) and a 404 class marker, so
  the #584 answer can distinguish a missing route from a gateway "not found" (thanks @Testius007).

## [4.7.9] - 2026-09-11 — The test cohort finally reaches the MBB command connector

### Fixed
- **Test cohort: the MBB command connector never received the opt-in flag.** The connector was
  created before the flag was applied, so the #584 fetched-role probe — the whole reason to opt
  in on a car marked `mbb_no_legacy` — could not fire for anyone. The flag now reaches the
  connector, applies live when you toggle it (no restart), and the probe runs for cars already
  carrying the no-legacy verdict. The per-device diagnostics download now includes the probe
  results and the car's MBB eligibility, so a single-car file finally carries the datapoint
  (#584, #923 — thanks @Testius007 for the diagnostics that exposed it).

## [4.7.8] - 2026-09-11 — Porsche login done the reference way, and a round of honesty fixes

### Fixed
- **Porsche: the login now pauses briefly after the password step, exactly like the proven
  reference client does.** That client waits a moment before following Porsche's redirect chain;
  we didn't, and on accounts with a car attached the chain kept landing on the `my.porsche.com`
  wall even after the captcha was solved right. The client also now identifies itself plainly as
  this integration instead of borrowing a phone's identity — the same thing the reference client
  does, and it has been stable for years. When a wall still appears, the message and the pre-filled
  report link now name the exact Porsche screen it stopped on, so a report is actionable on the
  first try (#1337, #1400).
- **Porsche: a dead refresh token now asks you to sign in again instead of failing quietly.** If
  every car read fails authentication, the integration opens the re-authentication dialog rather
  than retrying a token Porsche has already thrown away. Setup also no longer signs in twice on the
  first retry, and the solved-captcha token handed over from setup is only reused when it actually
  carries a refresh token, and the hand-over copy is always removed from the entry afterwards. A hiccup
  of Porsche's token endpoint (a 5xx) is no longer mistaken for a dead token, several cars sharing one
  login now refresh it once instead of once per car, and re-authentication is only requested after two
  consecutive polls in which every car failed authentication (#1337).
- **Porsche: "everything is empty" is now visible instead of silent.** When Porsche's status
  endpoint refuses a car, that's logged once as a warning per car, and a new diagnostic
  *Connect Contract Active* binary sensor shows whether Porsche reports an active Connect
  contract at all — the usual reason a Porsche shows up with no data (#1337).
- **Portal: the "session expired" repair finally goes away once you're signed in again.** It was
  raised by setup, the data-request kickoff and the historical export, but never cleared — so it
  outlived the re-login it asked for. It now clears the moment data flows through the portal again.
- **Scout feed: short-term consumption on combustion cars, engine starts, and the charge-report
  battery %.** The short-term consumption leaf arrives as l/100 km on ICE and plug-in hybrids —
  v4.7.6 read it and then dropped it. It now feeds its own *Short Term Average Fuel Consumption*
  sensor. The SCR engine-starts counter only shows up on combustion cars (every EV was getting a
  disabled "Engine Starts" entity), and its two status codes (14/15) are no longer recorded as a
  count. The "battery % at the last charge report" snapshot gets a disabled-by-default diagnostic
  sensor, so the Scout stops re-reporting it every poll and it can't shadow the live battery %
  (#1195, #1380, #1382–#1401).
- **Scout feed: anti-theft alarm reason (CUPRA Raval).** The portal's `dwa_alarm_reason` leaf (e.g.
  "ALARM_REASON_DRIVERSDOOROPEN") now feeds a diagnostic *Alarm Reason* sensor, kept verbatim. The
  bare `data` leaf that came with it is a small DER-encoded export envelope (two timestamps, no
  reading) and is recognised as such instead of being reported as a new field every poll (#1396).
- **Position: the freshest fix wins when a car has more than one data channel.** Merging used to
  take the primary channel's coordinates first and only fill gaps from the others, so a stale pin
  could beat a newer fix from the second channel. Position, heading and capture time now come from
  whichever channel reported most recently.
- **Trip sensors on VW-EU portal cars are no longer hidden by a capability the car doesn't need.**
  The "no trip-statistics capability" gate hid trip sensors even when the EU Data Act feed had
  already delivered the values. It now only applies when the car has no trip value at all
  (#923, thanks @guiumb).
- **Options flow: the "Terms & Conditions" sign-in message showed as a raw key** in the re-login
  dialog; it now has its text in all 12 translations.

### Changed
- **Captcha dialog wording is now accurate.** The v4.7.6 text said the captcha answer "never leaves
  your Home Assistant instance" — that was wrong: it is sent to Porsche's login service (and nowhere
  else). The dialog now says exactly that. The v4.7.6 notes below were corrected the same way.

## [4.7.7] - 2026-09-10 — Porsche login remembers itself (captcha only once)

### Fixed
- **Porsche no longer asks for the captcha on every restart.** The Porsche login token is now kept
  and reused across restarts — refreshed silently through the token endpoint the same way every other
  brand's is, which is never captcha-gated. So the interactive login (the only place Porsche's captcha
  appears) runs essentially once, at first setup, instead of on every Home Assistant restart. The
  captcha you solve during setup is carried straight into the running integration, so setup no longer
  trips a second captcha right after it (#1337).

## [4.7.6] - 2026-09-10 — More live fields from the Scout feed, and an interactive Porsche captcha

### Added
- **GPS position, heading, short-term consumption and an engine-starts count from the live Scout
  feed.** The portal's continuous feed carries several fields the integration wasn't surfacing yet:
  on cars whose feed includes `persLocation` (seen on a Škoda Elroq) the GPS position and heading,
  plus the short-term average electric consumption and the SCR engine-starts counter now come
  through as sensors. The per-trip id is recognised as metadata so it stops being reported as an
  undiscovered field. Grounded on real Škoda Elroq and Audi captures (#1378, #1375).
  *(Corrected in 4.7.8: the original note implied every car sends `persLocation` and that the trip
  id is used for correlation — neither is the case. Corrected in 4.7.11: heading was parsed but had
  no sensor until 4.7.11.)*
- **Porsche's captcha can now be solved right in the setup dialog.** Porsche's login can put up an
  Auth0 captcha; the integration now shows it inline during setup, re-authentication and reconfigure
  so you can type it and continue. The login also stops declaring passkey support (matching a proven
  reference client), which keeps Porsche on the solvable captcha path instead of bouncing straight
  to the `my.porsche.com` wall — confirmed on a real account without a vehicle attached; accounts
  with a car could still hit that wall after the password step, which 4.7.8 addresses. A captcha
  Porsche presents after the password step is answered on the screen that showed it (pinned to
  Porsche's own domain). Retries are bounded (too many can lock a Porsche account), what you type is
  sent only to Porsche's login service, and any login that still can't be cleared gives an honest
  message plus a pre-filled report link (no personal data in it) that tells you which log lines to
  attach (#1337).
  *(Corrected in 4.7.8: the original note claimed the answer "never leaves your Home Assistant
  instance" and that the link attaches diagnostics automatically — both were wrong.)*

### Fixed
- **Battery % right after plugging in: two more source fields covered.** The v4.7.5 fix that stops the
  "SoC at charge start" snapshot from briefly beating the live battery % now also covers two more
  portal content fields that carry that snapshot, so a poll that includes only one of them can't
  re-latch the stale value either. Thanks again to @hangout6690 (#1380).

## [4.7.5] - 2026-09-09 — Correct battery % on portal cars while charging

### Fixed
- **No more wrong battery % right after you plug in (VW-EU portal cars).** VW's EU Data Act portal
  sends the battery state-of-charge twice — the live value and a separate "SoC at the moment charging
  started" snapshot — and it stamps that snapshot as freshly updated whenever a charge begins. The
  integration could then briefly show the stale charge-start figure instead of the real one (e.g. 37%
  when the car was actually at 24%). The known charge-start reading is now kept apart, so the live
  battery % always wins. Thanks to @hangout6690 for tracking it down to the exact source fields (#1195).

## [4.7.4] - 2026-09-09 — Fresher VW-EU data, richer Porsche readings, per-car source priority

### Fixed
- **vw.de channel now delivers electric range (and fresher SoC/odometer) on ID./MEB cars.** The
  vw.de charging and maintenance reads were the only live-status calls sent without the per-platform
  `gdc` parameter and VCF host, so on ID.x/MEB cars VW's backend returned no live body for them — the
  electric-range sensor stayed empty and SoC/odometer fell back to the slower EU Data Act portal feed.
  Those reads now carry the same `gdc` + host the already-working warning-lights read uses, so the
  vw.de channel supplies range, SoC and odometer directly (#1357).
- **Porsche electric range, odometer and service intervals now actually populate.** The Porsche
  `measurements` reads were pulling the inner value under the wrong key names (guessed from the
  measurement enum names), so battery range, the odometer and the service intervals came through
  empty. Corrected against a real Taycan capture — they now read the `kilometers` member the backend
  actually sends (E_RANGE, MILEAGE and the service ranges).

### Added
- **Test cohort: a measurements-range + usable-capacity probe (diagnostics only).** For opt-in test
  cohort members, the vw.de channel now also probes the `measurements` job (electric / AdBlue /
  combustion / total range) for firmware that ships range only there, and reads usable battery
  capacity from the existing State-of-Health body. It records into diagnostics only — no sensor is
  fed until a live capture confirms the field — so nothing changes for your entities.
- **More Porsche vehicle data: windows, spoiler, charge/service flaps, parking brake & light, oil
  level and service interval.** Porsche already fetched these `mf` measurements but the parser
  dropped them; they're now wired onto the same sensors other brands use. Inner-value shapes are
  grounded against a real Taycan capture and every reader fail-softs to "unknown" on an unexpected
  shape (#1370).
- **Choose which data source wins per car (EU Data Act portal vs live vw.de).** When a car reads over
  both the EU Data Act portal and the live vw.de channel, the portal (a batched feed) wins every
  shared field by default — which on some cars means slower, occasionally stale data even though the
  live vw.de channel has a fresher value. A new per-car **"Data source priority"** option (in the
  integration's options, shown when a vw.de channel is configured) lets you pick **"Prefer live
  vw.de data"** for that car, so the live channel wins the fields it carries and the portal keeps
  filling the rest. Default is **Automatic** — existing setups are unchanged (#1357).

## [4.7.3] - 2026-09-09 — Porsche login clarity + finding the command gate on newer VW cars

### Fixed
- **Porsche login no longer says "wrong password" when that isn't the problem.** After the password
  step, Porsche's identity provider sometimes renders a captcha/consent wall instead of signing you
  in. The setup dialog was labelling that as "Email address or password incorrect" even with
  correct credentials — it now tells the two apart and shows an honest, actionable message about the
  wall it actually hit, so you're not chasing a password that was fine all along (#1337).

### Added
- **Newer VW cars (MBB_ODP): a read-only diagnostic that looks for the modern command gate.** On
  some newer VW cars the classic Car-Net command service is switched off at the backend — you may
  see MBB commands unavailable while reads keep working. VW's own app reads its command permissions
  from a newer endpoint on a different host instead. For members of the opt-in test cohort, the
  integration now quietly checks whether that newer endpoint answers on affected cars and records
  only the result (an HTTP status, no VIN/token/data) in the diagnostics file. Nothing is sent to
  the car and nothing changes — it's purely how we find out whether commands can be brought back for
  these cars (#584). Off unless you join the test cohort.

## [4.7.2] - 2026-09-08 — No more phantom "battery 0%", richer vw.de charging data

### Fixed
- **No more false "battery 0%" low-battery alerts on cars without a traction battery.** VW's EU Data
  Act portal always sends the 12V/auxiliary battery reading as `0` — it's a placeholder, never a real
  value (a car that can still talk to the cloud is never at a true 0%). Home Assistant treats that as
  a battery and fired low-battery notifications, most visibly on plain combustion cars that have no
  high-voltage battery at all (e.g. a petrol Arteon). The always-zero reading is now suppressed, so
  the phantom "12V battery" sensor and its notifications go away (#923). Grounded on 53 real
  diagnostics where this field was 0 every single time.

### Added
- **The vw.de channel now reads AC/DC charge type and HV battery cell temperatures.** If you use the
  supplementary vw.de channel, it now also delivers the charge type (AC vs DC) and the high-voltage
  battery's minimum/maximum cell temperature — the same fields VW's own backend exposes, which the EU
  Data Act portal feed never carries. They feed the existing sensors, so nothing new to set up.

## [4.7.1] - 2026-09-08 — Porsche: login, commands, vehicle data, and real two-way control

A from-the-ground-up pass on Porsche, grounded against a full read-through of the real app's own
code (not just a reference library) plus a live login test on a real account (#1337).

### Fixed
- **Porsche login gets further than before.** The password login was giving up whenever Porsche's
  identity provider rendered a page instead of redirecting, assuming it was an unsolvable captcha.
  On a real account it turned out that step is often just an optional "set up a passkey?" screen —
  the integration now declines it automatically and continues, instead of stopping the login right
  there. Login also skips the whole sign-in form if you already had a valid session, and now tells
  wrong credentials apart from an actual wall instead of one vague message for both. **Live-verified
  end to end on a real account** — this specific fix is confirmed working, not just grounded.
- **Every Porsche command was very likely silently failing, not just unlock.** Commands were sent
  with the wrong JSON field name entirely (`commandName` instead of `key`), confirmed against a
  maintained third-party library that has kept working against Porsche's API. Since Porsche login
  was blocked until the fix above, no command had ever actually been tested against the real
  backend — lock, unlock, climate, charging, honk-and-flash, timers, all of it. Commands are now
  also (best-effort) verified to have actually succeeded instead of just assuming a 200 meant it
  worked.
- **Unlock needs your S-PIN, and now actually uses it.** The setting was there, but nothing ever
  read it or sent it to Porsche, so unlock most likely never worked at all. It now runs the proper
  challenge/response Porsche expects.
- **Vehicle data used a request shape that was never confirmed to work**, and tire pressure was
  requesting a field that doesn't exist on Porsche's backend at all. Both switched to the real
  shape a full read-through of the app's own code confirmed (tire pressure is four separate
  per-corner fields, not one combined one) — TPMS has very likely been silently empty until now.
- Charging target now clamps to 25–100% and checks which of two different ways your car exposes it
  instead of assuming everyone's car works the same way. Honk-and-flash now distinguishes "flash
  only" from "honk and flash". 429 backoff honors Porsche's own suggested wait time when it sends
  one. Token refresh treats both of Porsche's "expired" signals as expired (not just one) and
  refreshes proactively instead of always waiting for a request to fail first.
- **VW EU — combustion cars no longer show a phantom electric range or get flagged as a hybrid.** On
  a diesel Transporter T6.1 (Commercial Vehicles / Nutzfahrzeuge feed) the portal sends a second
  range figure alongside the fuel range, and the integration was mistaking it for an electric range —
  so a plain diesel with no battery grew an "electric range" sensor and was mislabelled a plug-in
  hybrid. A combustion-only car (fuel or CNG, no high-voltage battery, not charging) now keeps only
  its combustion range; that stray figure is folded back into the fuel range where it belongs. Also
  covers natural-gas (CNG/TGI) cars, which hit the same trap, and self-heals the cached value for
  anyone who already saw the phantom. Thanks @EcksteinU for the diagnostics that pinned it down
  (#1316).

### Added
- **Real two-way control for geofence alerts, speed alerts, valet mode, and saved destinations** —
  editing location-based alarms, speed alarms, valet-mode configuration, and adding, updating or
  deleting a saved destination. Every field in these commands was recovered by disassembling
  Porsche's own app code directly, not guessed and not something the reference library this
  integration is grounded against has either. One coordinate format is inferred from a different,
  already-confirmed field on the same API rather than directly confirmed; adding/updating a
  destination is safest by reading an existing one back and resending it with only the changed
  field edited, since hand-building one from scratch touches a richer nested object than it looks.
- **New simple commands**: trunk unlock (separate from unlocking the whole car), opening/closing/
  venting the windows and sunroof remotely, starting/consenting to a software update, resetting
  service-due predictions, and disabling valet mode. None of the new commands above are exposed as
  buttons/switches in the UI yet — that's a larger change across every brand's shared entity files,
  not just Porsche's, and is tracked as a follow-up.
- **~20 more real vehicle-data fields requested** that weren't being pulled before (valet alarm,
  location/speed alerts, per-charging-session stats, software-update status, and more) — even
  before there's a dedicated sensor for each one, so a diagnostics export shows what they actually
  contain, which is the fastest path to building the sensor once someone's car returns real data.
  Deliberately not requested: digital-key pairing fields, since one of them plausibly carries a live
  pairing credential and there's no reason to pull that in for zero benefit.
- **Porsche login can now solve a captcha instead of just giving up.** If Porsche's sign-in shows a
  captcha, the integration displays it right in the setup screen and lets you type the answer in.
  Deliberately cautious: one attempt per screen, no automatic retry. Repeatedly retrying a wrong
  guess is how real Porsche accounts have ended up locked for "suspicious activity" elsewhere — if
  you see this screen, take your best shot; if it's wrong, wait rather than mashing retry.
- One thing found and confirmed NOT to exist: `POI_SEND_TO_CAR` is a real command name in the app
  but isn't wired to anything in the shipped app itself — not implemented, and not a gap.

**Honest status**: only the login fix above is live-verified on a real account. Everything else in
this release — commands, vehicle data, the new two-way control, the captcha screen — is grounded
directly against the real app's own code but has NOT been tried against a real car yet. Porsche
stays marked experimental. If you use Porsche, testing it and reporting back (either "it
works" or exactly what broke) is genuinely how the rest of this gets confirmed (#1337).

## [4.7.0] - 2026-09-07 — Full release / Voll-Release

The stable release that gathers the whole 4.7.0 beta line (b1–b17): integration-wide debug-log
redaction hardening, EU Data Act resilience (automatic terms-and-conditions accept, escalating
portal backoff, older-dataset fallback), per-brand portal logins, a "data is stale" sensor, the
Škoda manual-official-key repair, and the opt-in monthly `utility_meter` helpers. Two more fixes
land on top of the betas:

### Fixed
- **The "12V Battery Power Level" no longer mirrors the main battery on electric Škodas.** On a BEV
  (e.g. Enyaq) that sensor was showing the high-voltage traction battery's charge, because the
  car reports the drive-battery SoC in the same field a combustion car uses for a low-voltage
  reading. It's now hidden on electric cars, where it was only ever a duplicate of the main
  battery. Combustion Škodas are unaffected. Thanks @Seccados (#1359).
- **Battery % no longer bounces or lags when a car combines the vw.de channel with the EU Data Act
  portal.** A guard written for portal-only cars was overriding the live vw.de reading and pinning
  the percentage to the portal's ~15-minute cadence (it would step back to the previous value each
  time the portal poll arrived without its high-voltage pair). The live reading now stands. Thanks
  @Ra72xx for the side-by-side captures (#1231).

### Changed
- The "add a read channel" options (Volkswagen.de / EU Data Act portal / Tibber) now read
  "Add/refresh…" instead of "Add a…", so it's clearer they're one-shot actions you can re-run, not
  on/off state toggles (#950).
- **Audi & Porsche app login: both have now hit the manufacturer's attestation wall — for now,
  read-only Portal only.** VW and Porsche have both moved these brands' app sign-in to a new login
  (Auth0) with on-device app verification. This was already visible in the app a few weeks ago as a
  staged migration; it has now landed and taken the login down with it. The passwordless / browser
  login can no longer complete: the final token step is attestation-gated and can't be done
  headlessly — confirmed on real accounts, where even a fully completed interactive browser login
  can't pass it. Until we find a way through, **Audi is available read-only via the EU Data Act
  Portal** and Porsche stays blocked; the setup wizard now says so plainly instead of showing a raw
  failure (#1364, #1337).

### Docs
- The README now covers the opt-in monthly meters, and documents what to do on a brand-new or UK
  MIB4 car whose EU Data Act data request has to be created by hand on the portal when the
  automatic kickoff can't register one (#1227). Refreshed in all 12 languages.

## [4.7.0b17] - 2026-09-06 — Monthly meters, built for you / Monatliche Zähler, automatisch

### Added
- **Optional: monthly "utility meter" helpers, created automatically.** Turn it on and the
  integration builds Home Assistant `utility_meter` helpers that total your charged energy and
  mileage per calendar month — one per car — so you don't have to wire them up by hand. It's off by
  default and only offered in the options when a car actually reports a matching sensor, so a non-EV
  never sees a charged-energy meter it can't fill. These are permanent helpers: switching it back
  off stops new ones being created but leaves the ones already made (remove those under Settings →
  Devices & Services → Helpers). Early opt-in for beta testers — the exact provisioning timing on a
  live install is still being validated, so try it and report back.

## [4.7.0b16] - 2026-09-06 — Škoda manual-key fallback, EU Data Act resilience + hardening

### Added
- **Škoda official API — a manual fallback when auto-setup can't create a key.** The integration
  still sets up your official API key automatically whenever it can. When it can't — for example
  the key service rejects the request, or you're signed in without the native app login — it now
  shows a repair that lets you create a key in the MyŠkoda app and paste it in for the vehicle,
  instead of silently doing nothing.
- **The EU Data Act portal now accepts an updated terms-and-conditions step for you.** After you
  sign in, VW can show a "please accept the updated terms" page — the same kind of interstitial as
  the data-consent page we already accept. It's now accepted automatically so the login completes,
  instead of stopping and asking you to do it in a browser. If it ever can't, the existing repair
  still appears. Thanks @tuhriel for the clean log that pinned the terms-page classification (#1268).
- **A "data is stale" sensor you can build automations on.** A new diagnostic binary sensor turns
  on when your car's own data-capture time has been frozen for too long (a lapsed portal feed can
  keep serving days-old values as if they were live). The information was already there via the
  portal-health sensor; this makes it a simple on/off you can alert on. Hidden for cars that don't
  report a capture time.
- **A dashboard-warning field some VWs report is now read.** A VW variant of the instrument-cluster
  active-warnings field was going unmapped; it now feeds the existing (disabled-by-default)
  raw-dashboard-warnings diagnostic (#1358).

### Fixed
- **The portal login check no longer false-flags a valid session.** The b15 anonymous-session
  check compared cookie domains by plain substring, which missed a real session cookie scoped
  to the parent domain and could then mark an authenticated login as anonymous. It now matches
  host and parent domains correctly.
- **A leftover "connectivity" entity no longer lingers as unavailable.** When an account's set of
  read channels changed across versions, an old per-source connectivity sensor could stay in the
  entity registry forever as `unavailable`/`unknown`. It's now cleaned up automatically once the
  current channels are known. Thanks @cyrano330 (#1340).
- **We stop hammering VW's portal during a portal-side outage.** When the EU Data Act portal is
  returning server errors for a while, the poll now backs off (5 → 15 → 30 min) instead of retrying
  every minute, and returns to normal cadence the moment data flows again.
- **A brief download hiccup no longer wastes a whole poll.** If downloading the newest portal
  dataset hits a transient error, the integration now falls back to the next-older delivered
  dataset instead of skipping the poll — so you get data when the portal has any to give.

### Changed
- **Log redaction hardening.** An internal review pass tightened how the integration writes URLs
  and errors to debug logs across all channels, so a debug log you paste into an issue stays clean.

## [4.7.0b15] - 2026-09-05 — Debug-log redaction + portal login-success hardening

### Fixed
- **Debug logs no longer leak login secrets.** On the legacy sign-in path, the OIDC redirect
  hops were written to the debug log as truncated URLs — which still exposed the `code`
  (authorization token) and `user_id` (account id) carried in the query string. They're now
  logged as host + path only, so a debug log you paste into an issue stays clean. Thanks
  @cyrano330 (#1340).

### Changed
- **The EU Data Act portal login now checks it actually authenticated.** "Landed on the portal"
  was too weak a success test — a portal that signs you in anonymously (the shape of the
  Audi/Škoda/Bentley brand-client bug) looked like success and only failed a call later. It now
  catches an anonymous session at login time and shows the portal repair, so a future client
  change surfaces clearly instead of as a silently empty feed. Thanks @cyrano330 (#1340).

## [4.7.0b14] - 2026-09-05 — Audi/Škoda/Bentley EU Data Act fix + experimental automation triggers

### Fixed
- **Audi, Škoda and Bentley now actually read from the EU Data Act portal.** They were signing in
  with the Volkswagen portal login, so the sign-in *looked* like it worked but the session stayed
  anonymous and every data request came back empty (a hidden 401). Each brand now uses its own
  portal login — the one the portal's per-brand sign-in actually expects — on both the cookie and
  the token channel. Huge thanks to @cyrano330 for the root-cause trace (#1340).

### Added
- **Automations can now react to your car directly (experimental, opt-in).** New named
  triggers — started/stopped charging, plugged in/unplugged, locked/unlocked, started/stopped
  preconditioning, and charge target reached — plus matching conditions (is charging, is
  plugged in, is locked, is preconditioning, charge target reached). They're derived purely
  from data the integration already polls, so they add no extra API calls. This rides a Home
  Assistant platform its own developers still flag as "may change without notice", so treat it
  as a preview: it only registers on cores new enough to support it and quietly does nothing on
  older ones.

### Changed
- **Clearer, safer "no data yet" portal help.** The EU Data Act repair guide now explains that the
  portal keeps one active request *per car*: delete an older request only for the **same** vehicle,
  and on a mixed passenger + commercial account keep each car's request under its own brand view
  instead of deleting the other car's. In all 12 supported languages. Thanks @cyrano330 (#1340).
- **Tidier, safer portal debug log.** The redacted 401 auth-state line (debug only) now masks the
  UUID inside session-cookie names, logs once per setup instead of repeating, and adds a
  portal-domain-cookies field that shows at a glance whether a failing request went out anonymous
  or authenticated-but-refused. Thanks @cyrano330 (#1340).

## [4.7.0b13] - 2026-09-04 — HA-near clean-up (quality + deprecations + a diagnostic)

### Fixed
- **The "portal session not authorised" repair no longer appears twice.** A b12 change
  registered that repair through two code paths with mirrored ids (one of them mislabelled
  as a generic authentication failure); it now registers exactly once, with the correct
  brand-aware text. Thanks @cyrano330 (#1340).

### Changed
- **Quieter and more future-proof under the hood** (no user-visible change): the
  conversation-agent tools are now namespaced (`vag_connect__…`) the way Home Assistant
  2026.9 requires; the deprecated device-registry lookup was swapped for the entry-scoped
  one (Home Assistant 2026.8+, with a fallback for older cores); and the "parallel updates"
  quality rule is now declared where Home Assistant actually reads it.

### Added
- **A redacted portal-401 diagnostic** (debug-log only): when the EU Data Act portal rejects
  the vehicle list after a successful login, turning on debug logging now records — names and
  flags only, never any secret — whether the request went out authenticated or anonymous, to
  help pin down the cause. Thanks @cyrano330 (#1340).

## [4.7.0b12] - 2026-09-04 — Repair message + diagnostics fixes (EU Audi)

### Fixed
- **A post-login portal error no longer tells you to fix a correct password.** When an
  EU Audi's login succeeds but the EU Data Act portal then rejects the vehicle list (a
  401 *after* sign-in), the repair now says the portal session needs re-establishing —
  instead of the misleading "invalid credentials". A genuine wrong password is still
  reported as such. Thanks @cyrano330 (#1340).
- **Downloading diagnostics no longer fails with a 500 when setup didn't complete.**
  Exactly when the download is most useful — an entry stuck in `setup_error` — the
  diagnostics handler used to error out. It now returns the redacted config plus a note
  about the incomplete setup, so a failed setup can actually be triaged. Thanks
  @cyrano330 (#1340).

## [4.7.0b11] - 2026-09-04 — Škoda charge-current fix + quieter logs

### Fixed
- **Škoda "Max. charge current" no longer shows Unknown on cars without charging
  profiles.** Some Škoda plug-in hybrids (e.g. an older Superb iV) report the max
  charge current only as a plain MAXIMUM/REDUCED setting rather than via a charging
  profile — and the dropdown only ever read the profile, so it sat at Unknown. It now
  falls back to that plain setting. Thanks @n300home (#1343).

### Changed
- **The EU Data Act request kickoff no longer logs a scary "no data feed will start"
  warning when a feed is actually live.** On accounts where the portal keeps the
  session anonymous, the kickoff can't read its own request back and used to warn on
  every restart even while data was flowing. That case is now a quiet INFO note; a
  genuine request rejection (4xx) still warns. Nothing about the feed itself changed —
  only the false alarm is gone. Thanks @steemandavid (#1273).
- **The Porsche login now writes a redacted step-by-step debug trace.** Turning on
  debug logging previously showed nothing at all for Porsche sign-in; it now logs each
  redirect hop (host + status only — never the URL, code or credentials), so a failed
  login capture actually reveals where it stops, which is usually Porsche's
  captcha/consent page. Thanks @Hollywoodchaos (#1337).

## [4.7.0b10] - 2026-09-04 — Auth resilience (preventive)

### Fixed
- **A brief VW sign-in server hiccup no longer forces a full re-login.** When the VW
  identity server rejected a token refresh with a transient `invalid_client` (a known
  wobble that clears itself), the integration used to bounce you straight to a re-login
  prompt on the very first hit. It now treats that as transient and simply retries on the
  next poll — exactly the way the QR and durable-MBB login paths already did. A genuinely
  dead session still asks you to re-authenticate. Grounded against the cooperating
  audi_connect project, which saw the same recurring server-side wobble.
- **QR / passwordless logins can finally re-authenticate without deleting the car.** A
  passwordless entry (browser-QR or durable-MBB) sent to the re-login prompt used to land
  on a password form it could never satisfy — the only way out was removing and re-adding
  the integration. Re-login now re-runs the QR sign-in and refreshes the existing car in
  place.

### Added
- **A manual-entry fallback link on the browser-login screen.** VW's pre-filled sign-in
  link occasionally shows an error page ("Provided request is invalid" or a 500); the
  login notification now also gives you the plain sign-in URL to open and type the code
  by hand.

## [4.7.0b9] - 2026-09-04 — Regression fix + portal reliability

### Fixed
- **Climate no longer stays "on" after pre-conditioning has finished.** A b7 change
  made the climate entity and the climatisation switch read "on" for terminal states
  (Škoda `completed`/`unknown`, SEAT/CUPRA `unsupported`) where they should read off.
  Both now derive from the same "is climatising" flag, so they always agree and turn
  off once a session ends.
- **A parked car no longer loses its map location after a day.** The last-known parked
  position now stays visible past the 24-hour freshness window (a parked car really is
  still there) but is flagged stale via a `position_is_stale` attribute, instead of
  disappearing. A follow-up to the b7 stale-position change.
- **The "sign-in failed" repair no longer shows a blank message** on an EU Audi whose
  post-login vehicle list is rejected. Thanks @cyrano330 (#1340).

### Added
- **`cancel_historical_export` service.** Stops an accidentally-triggered one-time
  EU Data Act historical export from re-attempting every ~30 minutes until its
  deadline. A live continuous data request is untouched. Thanks @steemandavid (#1273).

### Changed
- **The EU Data Act request kickoff no longer re-hammers the portal on every restart.**
  When a valid data request already exists for a car, the integration trusts it for a
  day before re-checking, instead of re-requesting it — which the portal rejects with a
  500 and could storm on each reload. Thanks @steemandavid (#1273).

## [4.7.0b8] - 2026-09-03 — Last-trip travel-time sensor

### Added
- **Last-trip travel-time sensor.** Every trip already carried its duration in the data,
  but there was no entity for it — now a **Last Trip Duration** sensor (minutes) sits
  alongside the last-trip distance and average-speed sensors. Thanks @indigomejor for the
  request (#1310).
- **Trip sensors now also spawn on the Audi plug&play (OBD-dongle) setup.** The plug&play
  channel fills last-trip distance and duration, but they were being hidden by the trip
  brand gate; they now appear like on the other brands.

## [4.7.0b7] - 2026-09-03 — Grounded audit sweep: safer commands, fewer false readings, fuller Škoda official channel

Every fix below was cross-checked against how the leading open-source VW / Škoda
libraries handle the same code path before it shipped.

### Fixed
- **Climate no longer shows "off" while the car is actively heating or cooling.** On
  VW / SEAT / CUPRA the climate entity read Off during pre-conditioning (so a
  `heat_cool` automation never fired) because the backend sends the state in
  lowercase and the entity compared case-sensitively. It now matches the
  climatisation switch exactly.
- **A remote command can no longer be sent to the car twice.** On a multi-vehicle /
  portal account a slow refresh could blow the 60-second command lock, after which
  the physical command (charging / unlock / aux-heating) was re-sent **unlocked**.
  The lock now guards only acquiring the turn and never re-sends on timeout, and the
  follow-up refresh runs outside the command so a portal hiccup can't be reported as
  a failed button press.
- **Parked location stops going stale on Škoda / SEAT / CUPRA.** The 24-hour guard
  against showing an ancient parked position was silently skipped for these brands, so
  a location could read as "current" indefinitely once the backend stopped serving it.
- **Aux-heating now honours your duration / temperature sliders** instead of always
  falling back to 30 min / 21 °C.
- **The Škoda official channel can no longer push the odometer backwards.** A staler
  rate-limited reading could overwrite a fresher mileage; it now never regresses.
- **No more false red tyre-pressure warning.** A car reporting an
  "unavailable / unknown / not-supported" tyre status lit the tyre problem sensor red
  with no actual fault. Absent-telemetry statuses no longer trigger a warning; a real
  low-pressure fault still does.
- **Škoda "charged energy" total no longer spikes the Energy Dashboard.** The lifetime
  figure could drop and be read as a meter reset (phantom kWh). It is now clamped so it
  never goes backwards. Interim — a true lifetime total is coming.

### Added
- **SEAT / CUPRA trip-statistics sensors now appear.** Last-trip distance, average
  speed and consumption, and lifetime distance were already fetched every poll but
  never shown for these two brands. Thanks @indigomejor for flagging the trip-stats
  gap (#1309 / #1310).
- **The Škoda official public-API channel now surfaces much more.** When the official
  channel is your source it now also shows charge rate / type / completion time,
  battery-care and plug auto-unlock state, climate-ready time and window heating,
  lights / sunroof / bonnet, AdBlue range, the secondary engine on plug-in hybrids,
  and the car image — plus the auxiliary-heating status and active-ventilation state
  that previously read "unknown" on Škoda.

### Security
- **Parking city no longer leaks in a diagnostics download.** The diagnostics file (the
  one you are steered to attach to a GitHub issue) redacted the parking address but left
  the parking *city* in cleartext. It is now redacted with the rest of the location data.

## [4.7.0b6] - 2026-09-03 — Volkswagen Commercial Vehicles (Nutzfahrzeuge) + issue-sweep fixes

### Added
- **Volkswagen Commercial Vehicles is now its own brand.** VW runs Passenger Cars and
  Commercial Vehicles (Nutzfahrzeuge) as **separate** data-controllers in the EU Data Act
  portal — so a T6.1 / Transporter / Crafter registered under the commercial realm never
  delivered through the "Volkswagen EU" setup (it showed as a car but stayed empty). Pick
  **Volkswagen Commercial Vehicles** at setup — or add it as a second entry alongside your
  passenger VW — and its portal feed comes through. Read-only via the EU Data Act portal,
  same as passenger VW. Thanks @EcksteinU for the clear ID.3 + T6.1 report (#1316).
- **Tyre pressure monitoring type sensor.** Cars with an indirect (ABS-based) TPMS never
  report per-wheel pressures, so they showed no tyre entities at all. A new diagnostic
  "Tyre pressure monitoring" sensor now says whether your car measures per-wheel pressures
  or uses an indirect system (#528, #538).
- **Škoda: software update status sensor.** Surfaces the software-update lifecycle the
  readiness endpoint reports (e.g. "update in progress"). Thanks to the Vehicle Data Scout
  on the Elroq (#1333).

### Fixed
- **Lifetime trip totals no longer go blank between deliveries.** The cumulative lifetime_*
  sensors (distance, avg speed, avg consumption, …) dropped to "unknown" on any poll that
  didn't re-send the block — annoying in history and automations. They now keep their last
  value until a fresh one arrives (a genuine reset still lands). Thanks @indigomejor (#1310).
- **Reconfigure no longer crashes the background poll.** A Reconfigure could null the client
  mid-cycle and the next poll raised "NoneType has no attribute get_status". The poll loop
  now captures the client up front and skips the cycle cleanly if it's gone (#584).
- **VW: "no legacy Car-Net" cars stop offering dead command buttons.** When a car's MBB
  command channel definitively has no legacy enrolment, its command controls are now hidden
  (instead of failing on every press) and the integration stops re-poking the gateway for it
  each poll — and the diagnostics now report it correctly (#1150, #584).
- **EU Data Act portal login: the state locale order is now correct for non-matching
  country/language.** The portal expects `{country}__{language}` (a German account viewing in
  English is `de__en`); a secondary login helper had the two halves reversed. The active
  reader was already correct, so this only tidies the dormant helper — no behaviour change
  for the de_DE majority — with a regression guard added.

## [4.7.0b5] - 2026-09-02 — EU Data Act: the data request actually gets created + portal-feed observability

### Fixed
- **The automatic EU Data Act data-request creation was silently giving up on every account — now it goes through.**
  Getting a car onto the portal feed depends on the integration creating a "continuous 15-minute"
  data request for you (and the one-time historical export works the same way). Both were bailing
  out *before ever sending the request*: they waited for a security token from the portal's older
  page layer, and that token now comes back empty for everyone — so they waited forever and no feed
  was ever created. The car just stayed empty, with nothing in the log but "no CSRF token". Turns
  out the portal's data-request API is authenticated by your logged-in session, not by that token
  at all. The request is now sent on your session directly; the token is only attached if the
  portal ever actually provides one. **Live-verified end-to-end**: the create now returns success
  and the 15-minute request appears on the account. Thanks @steemandavid for the diagnosis
  (#709, #966, #1273).
- **Audi plug&play (OBD dongle): the car's location now always gets a map tracker.** The
  dongle only reports GPS from its last parked snapshot, so the position comes and goes
  between drives — and the device tracker could fail to appear (or get purged during a
  gap), leaving the location unbound. It's now created unconditionally for plug&play
  entries, the same way the volkswagen.de channel already is, so the car stays on the map
  (reading unavailable between fixes).

### Added
- **Diagnostic sensors that show what the EU Data Act portal feed is actually doing**, so a
  quiet car stops being a mystery. **Portal feed health** now tells a genuine VW-side portal
  outage ("Portal error") apart from a request that simply isn't delivering yet, and names a
  healthy feed **Live**. Plus four new per-car diagnostic sensors (portal-read cars only):
  **Data request created** (when your continuous request was set up), **Last snapshot
  received**, **Last no-data poll**, and **No-data polls** (how often the portal came back
  empty). Thanks @HA28320 and @riteman for the feed samples that made this concrete
  (#465, #1273). All 12 languages.
- **Škoda: choose how the official manufacturer API is used.** A new per-car option
  ("Škoda official-API source mode") lets you pick: **Automatic** (both channels, the
  official API's readings preferred — the default, unchanged); **Prefer the official
  API**; **Official API as failover only**; **Official API only** (turn the standard
  channel off); or **Standard channel only** (turn the official API off entirely). So if
  you'd rather not lean on the reverse-engineered channel — or would rather not use the
  official one — it's a switch now instead of automatic. Thanks @n3roGit (#1286). All 12
  languages.

## [4.7.0b4] - 2026-09-02 — EU Data Act: clearer "no vehicle data yet" guidance (carries 4.6.3)

### Changed
- **The EU Data Act "no vehicle data yet" notification now explains what to actually do.**
  On some accounts the portal keeps the browser session anonymous, so the automatic
  data-request creation (and the in-app button) can't complete — the message now says so
  and walks you through it: confirm ownership/usership in the portal, and if the automatic
  creation didn't take, create the continuous data request yourself (all clusters,
  15-minute). It also points to the read-only volkswagen.de website channel as an
  alternative source for cars where the portal feed is thin. Thanks to @steemandavid for
  the detailed diagnosis (#1273, #465). All 12 languages. (Also released as 4.6.3.)

## [4.6.3] - 2026-09-02 — EU Data Act: clearer "no vehicle data yet" guidance

### Changed
- **The EU Data Act "no vehicle data yet" notification now explains what to actually do.**
  On some accounts the portal keeps the browser session anonymous, so the integration's
  automatic data-request creation (and the in-app button) can't complete — the message now
  says so plainly and walks you through it: confirm your vehicle's ownership/usership in the
  portal, and if the automatic creation didn't take, create the continuous data request
  yourself (all clusters, 15-minute frequency). It also points to the read-only
  volkswagen.de website channel as an alternative source for cars where the portal feed is
  thin. Thanks to @steemandavid for the detailed diagnosis (#1273, #465). All 12 languages.

## [4.7.0b3] - 2026-09-02 — Škoda: clear the stored official API key from the options

### Added
- **Škoda: a switch to clear the stored official API key.** If you rotate or delete your
  official API key (for example after it was exposed), you can now remove it from the
  integration too. A **"Clear the stored Škoda official API key"** switch appears in the
  integration's options when a key is stored — ticking it and submitting wipes both the
  manually-entered key and the auto-enrolled per-car key(s). A native MyŠkoda login then
  mints a fresh key automatically on the next update, so the official channel keeps
  working with a clean key. Until now an auto-enrolled key had no removal control in the
  UI (#1286). All 12 languages.

## [4.7.0b2] - 2026-09-02 — Škoda: last-trip sensors from real per-trip data · carries the 4.6.2 security + fixes

### Added
- **Škoda: the last-trip sensors now populate from real per-trip data.** The last-trip
  distance, duration, average speed and average fuel consumption weren't appearing on many
  Škoda cars because the weekly trip-statistics overview returns those per-entry values
  empty on combustion cars. We now read the dedicated single-trips endpoint — the one
  source that carries genuine per-trip average speed and consumption — and fill the
  last-trip sensors from your most recent trip. Reported by @indigomejor (#1310).

### Security
- Carries the 4.6.2 fix that **redacts the Škoda official API key in diagnostics** — it was
  leaking in plaintext in the diagnostics download. If you've posted a diagnostics file
  with an official key set, treat it as exposed and recreate it in the app (see 4.6.2) (#1286).

### Fixed
- Carries the 4.6.2 fix for the **official channel's 12V "state of charge" mirroring the
  fuel level** on combustion Škodas (#1310).

## [4.7.0b1] - 2026-09-02 — Škoda official API: automatic key creation matched byte-for-byte to the app · per-car manual keys

### Added
- **Škoda: enter an official API key per car.** Official public-API keys are tied to one
  vehicle each (you create them in the MyŠkoda app, up to 5 per car), so an account with
  more than one Škoda now gets one key field per VIN in the integration's options — on top
  of the single fallback field. Each car then reads its own official channel with its own
  key. Single-car setups are unchanged: the one field still covers you. A blank per-car
  field is left as-is, so it never wipes a key that was set or auto-created for that car
  (#1286).

### Fixed
- **Škoda official-API enrolment now matches the app's request byte-for-byte.** Enrolment
  and the key list/delete calls now send the same app-identity headers the MyŠkoda app
  attaches (app version, platform, install id, device language/country, trace id), which
  the ordinary read endpoints don't require. Field testing pinned what each part fixes:
  these headers fix the **empty key list** on the official API — the endpoint was returning
  "no eligible vehicles" until we asked with them, and now your key is listed correctly.
  (The HTTP 400 on key *creation* was a separate issue — the key **name** — already fixed
  in 4.6.1.) Thanks to @indigomejor and @n3roGit for the before/after captures (#1286).

## [4.6.2] - 2026-09-02 — Security: Škoda official API key redacted in diagnostics · combustion 12V mirror on the official channel

### Security
- **The Škoda official API key was leaking in plaintext in the diagnostics download.**
  The official public-API key — the single manual key and every auto-enrolled per-car
  key — is a credential that grants access to your car's official API, but it was
  missing from the diagnostics redaction set, so it appeared in clear text in the
  config-entry diagnostics file people attach to GitHub issues. It is now masked (the
  per-car map keeps its count for triage but hides each key). **If you have ever posted
  a diagnostics file with an official key set, treat that key as exposed and recreate it
  in the MyŠkoda app (Smart Home → Keys) — deleting the old one there.** (#1286)

### Fixed
- **Škoda official API channel: the 12V "state of charge" no longer mirrors the fuel
  level on combustion cars.** On a petrol/diesel Škoda the official API mirrors the fuel
  level into the engine "state of charge" field — the same quirk the reverse-engineered
  channel has — so the official channel briefly re-introduced the mirror that 4.6.0
  fixed (a "12V" reading that just tracked the tank). It now applies the same guard and
  suppresses the duplicate. Reported by @indigomejor (#1310).

## [4.6.1] - 2026-09-02 — Škoda official API now reads live every cycle, not just on failover

### Changed
- **Škoda official API is now an active live data source.** If you have connected Škoda's
  official public API (with an API key), it is now read on every regular update — not only
  as an emergency failover when your main channel goes down. Its manufacturer-grade
  readings (odometer, battery/fuel, range, lock and opening status, climate, charging and
  the GPS parking position) are merged straight into your existing sensors as an
  authoritative live source, so the values you already have simply get fresher and
  steadier — there are no new entities to adopt. It still doubles as the failover on a hard
  outage, and it stays inside Škoda's 20-requests-per-hour budget: the read self-skips once
  the quota is spent, so normal poll intervals (5–10 min) never breach it. Existing values
  are never overwritten by a blank — the official read only ever fills or refreshes a real
  reading, and "last seen" is never moved backwards. The connectivity sensor now reports
  the official channel as "active" (with its live reading count) while it is contributing,
  instead of always "standby (failover)" (#1286).

### Fixed
- **Škoda official API: key created with a plain name.** Automatic enrolment now names the
  API key simply "Home Assistant" (previously "Home Assistant (vag_connect)"), matching the
  format the Škoda app itself uses — ruling the key name out as a factor in the enrolment
  rejection some accounts still see (#1286).

## [4.6.0] - 2026-09-02 — Škoda data-quality wave · per-source connectivity · sturdier token refresh · Audi plug&play logbook

### Added
- **See which data sources each car is connected to.** A new connectivity sensor per
  source (EU Data Act portal, vw.de website, Car-Net, the brand app, the Škoda official
  API, …) shows at a glance which channels your car is on — including a standby failover
  like the Škoda official API that only reads when your main channel is down. Each one
  carries attributes: whether it is actively feeding data or on standby, how many of the
  car's readings it currently provides, when it last delivered, and — for the EU Data Act
  portal — its feed health. Works across all brands (#1286).
- **VW EU login: auto-skip the optional marketing-consent page.** VW's login sometimes
  interjects an optional marketing-consent screen after your password is accepted. On the
  EU Data Act portal channel that used to stop the login and ask you to clear it yourself;
  now it is continued past automatically on the "not now" path — no marketing consent
  granted, nothing to click. A genuine Terms & Conditions page is deliberately left
  untouched (that is a real legal acceptance, so it still points you to accept it once).
- **Škoda: last-trip sensors now appear.** The last-trip distance, average speed, average
  consumption and date are read from Škoda's own channel but were gated to Audi/VW and
  never spawned — they now show up on Škoda too, filled from the most recent day. (The
  long-term "lifetime" aggregates stay Audi/VW-only: Škoda's endpoint returns a weekly
  window, not a lifetime total.) Reported by @indigomejor (#1310).
- **Škoda official API: a heads-up if another integration is using it too.** If the
  account holds more official-API keys than we created, a second integration or app is
  probably reading the same official Škoda API. That is fine to run, but both share the
  same small per-car request budget — so you now get a dismissible notice explaining that
  the combined usage can hit Škoda's rate limit sooner and, in the worst case, get the
  account temporarily (or eventually permanently) blocked, plus how to remove the key you
  do not need (#1286). All 12 languages.
- **Audi plug&play (OBD dongle): last-trip stats, a precise odometer, and a real "last
  parked" time.** The dongle's trip logbook now fills the last-trip distance, duration and
  start odometer, and the main odometer switches to the driverlog's sub-metre value
  (fresher and more accurate than the coarse snapshot one). The parked-position age now
  comes from the GPS fix's own timestamp instead of the unreliable sync stamp.
- **Audi plug&play: EcoScore, refuel "from → to" litres, trip count and driver-score
  points.** The dongle's logbook and fuel log also surface the last trip's EcoScore and
  average intake-air temperature, how many litres each fill-up added (with the tank level
  before and after it, and the odometer at the time), how many trips are on record, and
  your account's driver-score points — all diagnostic, only on plug&play cars that have
  the data. Full 12-language names.

### Changed
- **The Škoda official-API enrolment notice now explains it is a rate-limited standby
  channel.** So nobody wonders why it is not updating constantly: the official channel is
  capped at a few requests an hour, sits on standby, and only reads when the main
  connection cannot — it will not slow anything down.

### Fixed
- **A brief backend hiccup during a token refresh no longer forces you to log in again.**
  When the login server rejected a token refresh, we treated every rejection the same —
  including a temporary "try again later" one — and bounced you to a fresh QR / password
  re-auth. Now only a genuinely dead login does that; a transient server error, rate blip
  or network wobble just retries on the next poll and your entry stays live. Applies to
  both the device-code/QR login and the Car-Net (MBB) refresh path.
- **Škoda official-API auto-enrolment: do not skip a valid login over a token-format
  check.** The gate required the login token to look like a specific JWT before it would
  mint the official-API key; a legitimate native token in a slightly different shape was
  silently skipped, so the "it just works" enrolment never fired. The gate now trusts a
  native login and lets the mint attempt run — a backend rejection is captured in the
  privacy-safe diagnostics instead of the feature quietly no-op'ing (#1286).
- **Škoda: the phantom "12V battery" that was really the fuel level is gone.** On a
  combustion Škoda the backend sends the same number in the SoC and fuel-level fields, and
  we had been surfacing that as a 12V battery charge (from an unverified early note). It is
  now shown only when it is a genuinely distinct value, and it no longer latches at a stale
  reading. Thanks to @indigomejor for the side-by-side captures that pinned it down (#1310).
- **Škoda: the "driving" sensor no longer flickers in and out of existence.** It was only
  set when the car's readiness block was in a given poll, so a poll that momentarily did
  not include it made the sensor disappear (and reappear next time). It is now always a
  real on/off value — off when there is no motion signal, on only when the car reports it
  is moving. Reported by @indigomejor (#1310).
- **Škoda: no more phantom "last fill-up" from a car you used to own.** The last fill-up
  comes from an account-wide history with no car link, so on a new car it could show an old
  session from a previous vehicle. A "latest" fill-up older than a year is now treated as
  stale and hidden (#1310, @indigomejor).
- **Škoda: service reminders you never set no longer show a raw `NOT_SET`.** An unconfigured
  reminder came back as the literal text `NOT_SET`, which reads as a real value in
  automations. It is now left blank (unknown) instead (#1310).
- **Škoda: the equipment count stops flickering to "unknown".** It does not change between
  polls but vanished whenever a poll returned a leaner payload; it is now held at its last
  value like the other stable readings (#1310).
- **The account "settings" device is no longer confusingly named like your car.** The
  integration always creates a small account-level settings device (it holds the
  poll-interval control). It was named "VW Group Connect", identical to the integration
  itself, so when downloading diagnostics people picked it by mistake and got a file with
  no vehicle data. It is now "VW Group Connect Settings", and the test-cohort share prompt
  spells out to download diagnostics from your car's own device and links #923.
- **When a car goes unreachable, the entities that explain why no longer vanish with it.**
  A failed poll (past the tolerance window) took the whole car's entities down — including
  "Vehicle Last Reported", the data-source and connectivity indicators, and the
  error-reporter counts. Those connection-status diagnostics now stay available regardless
  of the poll outcome, so you are never left blind at the moment the car drops off.
- **Privacy: a diagnostics download no longer leaks the full VIN.** The Škoda widget's
  render-image URL embeds the VIN in its filename; the redaction masked the VIN everywhere
  else but missed that one string. It is now masked there too (#1310, @indigomejor).

## [4.5.0] - 2026-09-01 — Škoda official public API: automatic, zero-setup enrolment · Audi battery-health capacity

### Added
- **Škoda official public API — automatic enrolment, zero setup.** Škoda opened a
  public data API (app v8.16+). Already-logged-in Škoda owners are now enrolled
  automatically: we mint a per-car API key from the existing login, wire it up as a
  durable failover read channel, and drop a one-time notification that it's live —
  nothing to paste, nothing to configure. New users get it the same painless way.
  The key is minted once and remembered, honours the 5-keys-per-car limit, and the
  channel stays rate-limited (20 requests/hour per car) so it's only read when the
  primary channel is down. A manual key field stays in the options as a fallback.
  The key-mint step also writes a privacy-safe outcome line into the integration
  diagnostics (HTTP status + response field names only — no VIN, body, or secret),
  so if the mint ever misbehaves on a real car the download tells us exactly what
  happened.

### Changed
- **Audi battery net-capacity now also comes from the health read.** The battery
  State-of-Health response we already fetch on Audi device-grant cars carries the
  usable net capacity in kWh; we now use it to fill the battery-capacity sensor on
  cars whose main status bundle didn't include it. No new entity — just an extra
  source for the existing sensor (grounded on the myAudi 5.7.0 data model).

### Fixed
- **Škoda official-API channel: correctness + rate-limit hardening** (validated
  against the live public API spec). Climate start now sends an empty body where
  the API requires one (a missing body was rejected); the channel honours its
  20-requests/hour budget by self-blocking when the server reports the quota is
  spent (RateLimit-Remaining 0 or a Retry-After on 429/503), so the failover read
  never breaches the limit. Off unless you add an official API key.

## [4.4.0] - 2026-08-31 — iOS Live Activities · durable Audi + VW two-way (MBB) · EU-Data-Act multi-channel merge · friendly channel names

_Consolidates the 4.4.0b1–b5 betas into one stable release._

> [!IMPORTANT]
> **The big one: native iOS 2026.8 Live Activities.** A live charging countdown now runs on the iPhone Lock Screen and in the Dynamic Island (and iPad, new in 2026.8), driven entirely by this integration's charging sensors — no templating. It needs the **Home Assistant Companion app on iOS 2026.8 or later**, where the redesigned Live Activity lands. Around it, this release brings **durable two-way commands for Audi *and* Volkswagen** over the resilient Car-Net (MBB) channel, an **EU-Data-Act portal that merges cleanly with every live channel** (a fresh reading always beats a stale portal snapshot), full **7-brand support** (VW · Audi · Škoda · SEAT · CUPRA, plus the plug&play and companion paths), **plain-language channel names**, tidier **car-render images**, the **#923 export button** and **#1301 SEAT/CUPRA repair** fixes, and a self-updating **Sponsors** list in the README.

### Added
- **iOS 2026.8 Live Activities — an EV charging countdown on the Lock Screen and Dynamic Island.** The integration already exposes an absolute charge-finish timestamp (`charge_complete_eta` on every EV), so iOS renders a self-ticking countdown with a state-of-charge bar — it starts when charging begins and clears when it stops, with no per-second push. Needs the **Home Assistant Companion app on iOS 2026.8+** (the redesigned Live Activity and iPad support arrive there). The charging blueprint now points at `charge_complete_eta`, so the Lock-Screen countdown works on *any* electric car, not just VW-portal ones. Most of what else is new over there — the Energy and Calendar widgets, the redesigned Apple Watch app, CarPlay climate, Spotlight search — already works with the sensors, calendars and controls this integration exposes; your connected-services (We Connect / Car-Net) subscription end date now shows up on the service calendar the new Calendar widget follows.
- **Audi: durable two-way commands (MBB).** Car-Net Audis (most PHEV / combustion, pre-ID/MEB) can now enable the durable MBB command channel — a live validation confirmed an Audi account mints the durable MBB bearer, so lock/unlock, climate and charge route through the resilient legacy Car-Net path (survives restarts and the Play-Integrity wall). This joins the Volkswagen MBB two-way already shipped, so both brands now have a durable command channel. Off by default; newer ID / MEB Audis aren't eligible and simply won't offer it.
- **Companion phone: a third way to connect, where the phone calls Home Assistant (#968).** Instead of HA reaching *into* the phone (ADB over TCP or the ADB Bridge add-on — where setups get stuck), a companion **agent app** can hold an ordinary outbound long-poll to HA, so NAT, changing IPs, guest/IoT Wi-Fi isolation and Android's wireless-debugging dance all stop mattering. Tick "Use the companion agent app" at setup and paste the agent's token; the endpoint is gated by that per-vehicle token (constant-time compare, redacted in diagnostics) and only ever carries a short fixed list of screen verbs, never a shell. The Home Assistant half plus the protocol ship here ([`docs/COMPANION_AGENT.md`](docs/COMPANION_AGENT.md)); the phone-side agent app is a separate artifact. Read-only on Volkswagen. ADB and the ADB Bridge add-on remain supported and untouched.
- **Companion nav-reads: parking position, odometer, next service, charge limit, target & outside temperature (#923, #968).** A VW-EU car read only over the portal has no position data point at all; the companion channel can walk the app's own share sheet to read the parked coordinates and come back, and pull mileage / service countdown / charge limit / temperatures from the detail screens We Connect 4.3.2 moved them to. Each path is its own opt-in, off by default and read-only, and the walk returns through the app's own close controls (not Android BACK) so the next poll always finds the car overview.
- **Groundwork for an opt-in official Škoda API channel (#1286).** Škoda has launched a first-party, attestation-free vehicle API; this lands the client, the full grounded spec, and an automated 4-hourly watch for the app version that unlocks it (the key is minted in the Škoda app). On a Škoda entry you can add an official API key so the channel acts as an **automatic failover** — if the primary channel ever hard-fails, the read is served from the official API instead of freezing on last-known data. Failover-only (never polled continuously, because it's rate-limited to 20 requests/hour/key), off by default, and its state parsing is grounded on the API's documented values (`doorsLocked` = `YES`/`NO`/`OPENED`). No change unless you add a key.
- **Portal feed health sensor for EU Data Act cars.** A new **Portal feed health** sensor says at a glance whether the portal is actually delivering — `ok`, `waiting_for_portal_data`, `empty_snapshots` (car asleep), `delivery_not_ready`, or `stale` (the poll keeps succeeding but the car's capture time has frozen — the field's most common gotcha, previously invisible). A companion **Minutes since last snapshot** diagnostic (off by default) exposes the exact capture age for staleness automations.
- **A safety net around the one-time historical export.** A **Request historical export** button asks the portal for the config data (timers, charge profiles, climate settings) the 15-minute feed doesn't carry, tracked by a **Historical export** sensor. It runs its own client-side deadline (the portal gives the request no terminal state, so it can silently produce nothing a day later) and refuses only while *your own* one-time export is still pending — field testing showed the portal happily runs a one-time export alongside the continuous feed. A kill-switch can disable the whole path.
- **Three new diagnostic sensors for Audi/VW-EU, from the render-image query we already run:** **Drivetrain** (official BEV/PHEV/… classification, not guessed from telemetry), **Customer service ID** (`csid`, off by default), and **Parked since** (turns the parking timestamp into a proper "last parked" sensor). All gap-fill only, never overwrite a real value, and ship with all 12 translations.
- **Self-updating Sponsors list in the README.** A scheduled workflow refreshes the README's Sponsors section from GitHub Sponsors. Privacy is the point: **only public sponsors are named**, private ones show as an aggregate "and N private sponsors" count, and a token/auth/empty-result failure makes *no* change — a transient hiccup can never blank the list or drop a real sponsor.
- **SEAT/CUPRA locale check (opt-in test cohort).** For a cohort member with a SEAT/CUPRA car, a once-per-vehicle diagnostic samples the `mycar` localized strings with our default headers vs `Accept-Language: en_GB`, so a real account can tell us whether adding that header would localise strings or just force English — before we change anything. VIN/email-masked, off unless you're in the cohort.

### Changed
- **The data-source sensor now reads in plain language.** When a car is fed by several logins at once, "Data source channel" showed cryptic tokens like `eu_data_act+mbb`. It now reads "EU Data Act portal + Car-Net", lists each source under a `channels` attribute, and shows the same friendly name as the `source` attribute on every reading — so you can see at a glance which login produced what, and one car is never listed twice. The raw tokens stay under a `raw` attribute for support.
- **The car-render images no longer crowd the device page.** Audi/VW cars ship the same render in seven sizes and angles; enabling all seven buried the device page under near-identical photos. Now only the recommended one (the large side view) is on by default — the other six are still created but switched off, so you can enable exactly the size/angle you want in one click. Existing setups keep whatever they already have.
- **EU Data Act polls now align to the portal's ~15-minute delivery cadence.** A portal car's next poll is anchored to when the next snapshot should land (plus a short buffer) and retries faster when a drop is overdue, so fresh data is picked up shortly after it's delivered instead of drifting out of phase. Bounded so it never polls faster than the 3-minute floor nor slower than your configured interval, and only for cars actually read over the portal.
- **All 12 languages tidied up.** The new Audi backup-connection setup screen, the portal-feed and one-time-export sensor states, and the vehicle-image entities now read in your own language instead of falling back to English — and a handful of stray English labels (a couple of password fields, "Stale" / "Delivered" / "Timed out") got translated too.
- **New app icon.** The project now uses the VW Group Connect ID.Buzz artwork — a clean full-bleed rounded square, deep navy to the edge — across the integration and the README.
- **Durable-MBB pre-flight (internal).** The volkswagen.de relations read now surfaces each car's Car-Net provisioning up front and classifies whether arming MBB is even worth it, so a later change can skip the device-grant login on cars that could never command it (a guest on a shared car, or a WeConnect/ID car whose two-way is the BFF). The per-car verdict (`eligible` / `not_provisioned` / `not_mbb` / `unknown`) is now in the diagnostics download. Observability only — nothing in the poll or command path acts on it yet.

### Fixed
- **Audi cars finally show their real model — the bare "Audi (2021)" S6 becomes "Audi S6 Avant TDI quattro tiptronic".** The localized `media.shortName`/`longName` are only returned when the model query carries a locale; our request omitted `Accept-Language` + `X-User-Country`, so the backend answered with just the model year and a null `media`. Proven with a same-account A/B test (no headers → blank; headers → full name). The request now always sends a valid locale (from the account's country), the list is read from the myAudi app-API first (web-proxy as fallback), and the render-image entities got clean, consistent, localized names too.
- **Portal-primary cars no longer show a stale door / window / lock state.** If the EU Data Act portal is your main channel and a live channel (the CARIAD BFF or vw.de) is also connected, the current door / window / lock / trunk reading from the live channel now wins over the portal's up-to-15-minute-old snapshot — the same cross-channel rule we already apply to charging and SoC (a door-open warning automation was exactly the kind of thing that could act on the stale value). Odometer, GPS position and service intervals are deliberately left untouched.

  > **Later correction (2026-10-30, #1950):** "up-to-15-minute-old" above is
  > wrong, and is left standing as it shipped. 15 minutes is the portal's publish
  > cadence, not a bound on how old a portal value is: a car that has had no wake
  > event keeps re-delivering its last export, and #1688 had the car's own capture
  > field frozen five days behind the data points beside it. The rule this entry
  > describes does not rest on that number — it hands the field to the
  > highest-priority live channel whenever the batch feed owns it, whatever the
  > batch value's age. If anything the wrong number understated why the rule is
  > needed.
- **The EU-Data-Act export buttons now appear on a command car that also reads the portal (#923).** If your car sends remote commands *and* pulls the EU Data Act feed, the "Request historical export" / data-request buttons were missing — the gate only recognised a read-only portal or the explicit option. It now also spots a live portal connection (or a saved active data request), on merged setups too, so the buttons show up on their own and a merged setup can import the result. Thanks @naked-head and @dazzzl — the toggle A/B test pinned it exactly.
- **SEAT/CUPRA: the "outdated OLA headers" repair no longer gets stuck on (#1301).** For cars that read via the portal (the SEAT/CUPRA online API is switched off at VW's end), that repair could latch on and re-announce itself on every poll — it was built to clear only on a successful call to an API that can no longer answer. It now auto-resolves whenever the portal is serving your data and stays gone. Thanks @anju1337 for the precise report.
- **VW trunk-open now reads the portal's dotted `trunk.open` field (#1293).** The EU Data Act feed can report the trunk state as a dotted boolean (`trunk.open: "true"`), the same way it already does for `trunk.locked`; we only read the numeric enum and UUID form, so on that dialect the trunk-open sensor stayed empty. Thanks @MirkoKas.
- **Audi/VW-EU doors and trunk now report open/closed correctly (#1281).** A door entry carries both its lock word and its open word in one list (`["unlocked", "open"]`); we read only the first, so every physically open side door — and the trunk — showed closed even though the lock state was right. The trunk's own "open" and "locked" sensors populate now too. Thanks @peterbauer1709.
- **Audi PPE (S6 / Q6 e-tron) windows and doors now read their real open/closed state (#1279).** On PPE cars each access-status entry ships its `status` as a list of plain strings (`["open"]`) rather than objects; we only read the object form, so an open window or door parsed to *closed*. It now reads either shape and also surfaces each window's opening percentage. Thanks @peterbauer1709.
- **Audi plug&play (OBD dongle): recovers from an expired token instead of spamming errors, and keeps its data across a restart.** The acpp channel never refreshed its ~1h token — once it expired, every poll 401'd and the Error Reporter filled with repeated 401s. It now refreshes and retries on a 401 (rotating the refresh token), raises a single re-auth prompt for a genuinely dead token, no longer discards the restored last-known-good snapshot after a restart, and polls hourly by default (was every 10 min) since the dongle only uploads after a drive — identical data, far less token churn.
- **The garage list survives a backend path change.** myAudi 5.7.0 moved the vehicle-list endpoint; if VW ever retires the old path, the integration now falls back to the alternate (vgql) garage enumeration instead of losing every Audi. Purely defensive.
- **Portal feed health no longer says `ok` when the portal has never delivered (#1273).** For a car where the portal is a *supplementary* channel, the health sensor was reading the merged data's no-data flag (which the primary channel sets) instead of the portal connector's own status. It now reads the portal's own reason and correctly reports `empty_snapshots` / `waiting_for_portal_data`. Thanks @riteman.
- **Companion channel (We Connect 4.3.2): a charging car now reads as charging, and the climate switches show their real state (#968).** Grounded on live 4.3.2 dumps: the app narrates the active state as "Currently charging" (now recognised), and the climate toggles are non-checkable rows whose real state lives in their description text ("Active"/"Off"), so that is read now. Also fixed on the companion: a plugged-but-not-charging car no longer reads as charging, a grouped-thousands odometer (`27,886 km`) no longer collapses to its first digits, a greyed-out control is no longer treated as a tap target, and the two advanced toggles now take effect when changed in Options. Thanks @plainmad.
- **Account-level resilience (#1234).** A car that Home Assistant disabled for its own internal reasons no longer silently drops out of polling (only a car *you* disabled is skipped); one vehicle's portal block (e.g. an IDP browser-feature block) no longer tears the whole account into reauth and takes a healthy second vehicle offline with it; and a blocked or incomplete VW-EU portal login is no longer reported as "invalid credentials" — it surfaces the real reason, while a genuine wrong password still maps correctly. Thanks @eddieari for the detailed diagnostics.
- **Portal VW cars now show their model — even for a guest on a family car.** The model was fetched only from a vehicle-file endpoint VW blocks (403) for anyone who isn't the primary user, and that block aborted the read before the flat vehicle-data endpoint (which returns the model even for a guest) was tried. The read now degrades per-endpoint, and the engine-power figure the primary-user endpoint returns is surfaced as a sensor too.
- **Error-reporter links stay submittable even on long reports.** A report with many errors could build a pre-filled GitHub URL too long to send: the cap was on the raw body, but url-encoding a traceback-heavy body inflates it 2–3×. The cap is now on the final encoded URL and trimmed conservatively — the full report is always available under Diagnostics.
- **The companion agent / add-on tokens are now redacted in the diagnostics download.** The agent-relay endpoint is gated entirely by a per-entry token; neither it nor the ADB-bridge add-on token was on the redaction list, so both would have appeared in clear text in files people attach to public GitHub issues. They now redact by default like every other stored secret.
- **The volkswagen.de profile block is now redacted in a diagnostics download (D#1231).** The number plate, owner-chosen nickname and render image URLs were written in the clear; they now redact by default like the VIN and address already do. Thanks @Ra72xx.


## [4.3.0] - 2026-08-25 — Audi plug&play OBD dongle, V6.0 dictionary & live-telemetry

### Added
- **New source: Audi plug&play (OBD dongle) with full factory master-data.** Older Audis with no built-in connectivity that use a TEXA OBD dongle (pre-connectivity A4/A5, Touareg, e-up!, …) are invisible to the modern CARIAD backend and the EU Data Act portal — this integration can now read them. Pick **"Audi plug&play — OBD dongle"** at setup: vehicles are discovered automatically and it reads the dongle's cloud snapshot (odometer, 12V battery voltage, warning lights, last parking position), read-only in its own token silo, live-validated on a real enrolled car. It also surfaces the dongle's carport master-data: the proper "ab Haus" model designation in the same style as a connected car — e.g. **"Audi" + "A5 Coupé TDI"** (body form decoded from the Audi sales-type code) with a clean manufacturer — plus a **fuel-level sensor in litres**, one consolidated **engine-power** figure ("176 kW / 239 PS"), **displacement, torque, cylinder count, engine code, fuel type, transmission** (with gearbox code) and **exterior + interior colour**, all localized in 12 languages, plus a **"Data as of" timestamp**. First-registration / delivery and warranty-end dates become service-calendar events. (acpp exposes no vehicle image or reliable inspection date — verified — so those are omitted.) VW We Connect Go dongles are mapped but stay tester-gated.
- **Optional fuel-level percentage for litres-only sources.** A new **fuel-tank capacity (litres)** option lets the plug&play reader derive a fuel-level % for the nicer gauge/bar UX. Off by default; it only fills the percentage when the car itself reports none.
- **EU Data Act data dictionary updated to the official V6.0 (2026-07-24).** Every portal field now resolves to a name instead of a raw UUID — the continuous feed plus the full historical export set, with the previous dictionary's curated names preserved. The GPS coordinate block (latitude/longitude, altitude, precision, heading, and the *moving* / *outdated* staleness flags) is mapped, and the coordinate "false friends" (charging-record and navigation-destination coordinates) are written out by name so a location read can never mistake a charging stop or a saved destination for where the car actually is. Huge thanks to **@naked-head** for parsing both official V6.0 dictionaries in full and hand-checking the GPS block.
- **Per-window opening position (%) sensors.** Cars that report window-lifter positions on the EU Data Act portal now get a percentage-open sensor per window (front/rear × left/right), localized in all 12 languages. Self-gating — a car that reports no window position gets no entity, so there's no "unknown" clutter.

### Fixed
- **Battery, charging and climate readings no longer step backwards when the EU Data Act portal re-sends a stale block (D#1231, #1195-family).** The portal's 15-minute feed re-sends a frozen "stop-charging" snapshot — sometimes re-stamped with a fresh timestamp — which could out-rank a genuinely live channel (volkswagen.de, the brand app backend) in the cross-channel merge, letting state-of-charge, charge power/rate, remaining time, plug state, range and climate state jump backwards mid-charge. A live channel's reading now always supersedes the batch feed's for those fields, across every brand; cars that only have the portal are unchanged.
- **Audi and VW EU cars now show their real model name instead of just "Audi (2024)".** When the vehicles-list gave no model name (e.g. an Audi S6 returned an empty one), the device fell back to the brand + year. The proper localized designation ("S6 Avant TDI") — and the exterior colour — are already fetched from the vgql media block for render images; those are now used as the model name and colour when the list has none.
- **A transient VW gateway "404" no longer raises an error report (#1233, #1242, #1244, #1245, #1247).** The CARIAD edge (`emea.bff.cariad.digital`) intermittently returns a generic "404 page not found" for the main status read and recovers on the next poll — several Audi owners hit the exact same blip within seconds of each other. That kind of transient gateway 404 now self-heals quietly the way a 5xx already does, instead of surfacing as a user-facing error report. A structured, per-vehicle 404 still reports as before.
- **Vehicle-position groundwork for VW EU cars (#923), and honest skip reasons.** The portal's coordinates live only in the one-time historical export, never in the continuous feed; the field map for reading them is now in place (the reader itself waits on a real export sample so its shape isn't guessed). Separately, re-examined the intentionally-unmapped fields against the complete V6.0 dictionary and documented why each stays that way (e.g. `scope_potential_total` is an internal PPE engineering ID, and the two "ownerless" opening UUIDs are the only openings the official dictionary still leaves without a body part).
- **Audi plug&play master-data no longer comes back empty on a live read.** The carport endpoint reads its language from `Accept-Language` and rejects a multi-value / q-weighted value (`de-DE, en-US;q=0.9`) with HTTP 400 while accepting a bare `de-DE` — so every carport-derived field silently came back empty against a real car even though the mocked tests were green. Now sends a single tag, and a non-200 sub-resource is logged in debug instead of being dropped silently, so a future live-only regression is visible.
- **The Vehicle Data Scout no longer re-flags a climatisation-timer field it already reads (#1237).** On some Audis the singular `automation.climatisationTimer.requests` queue counter kept surfacing as a "new field" even though its value is already parsed into the climatisation-timers sensor — a silencer-registry gap, not a missing feature. Thanks @arcticMariner.

## [4.2.1] - 2026-08-24 — Honest diagnostics & a sweep of leaked `invalid` placeholders

### Changed
- **The charging-port sensor now shows a translated Connected / Disconnected label (#1055).** `plug_state` ("Charging Port") is now a proper enum sensor with localized states in all 12 languages, instead of passing VW's raw English word straight through. The value is normalized across brands (e.g. Škoda sends it uppercase), and VW's occasional `invalid`/`unsupported` placeholder now reads as unavailable rather than a stray raw label. Thanks @ChristophCaina.

### Fixed
- **Empty fields in a diagnostics download no longer masquerade as redacted data (#923).** Privacy-masked fields — position, parking address and the like — were printed as `**REDACTED**` even when they were actually empty, so "the car never reported a position" looked identical to "position is present but hidden". That quietly sent triage down the wrong path. Empty values now stay visibly empty and only real values are masked, so the `field_sources` list stays the honest signal for what a channel actually populated. Thanks @naked-head for the precise diagnosis.
- **Two more charging fields no longer show the raw `invalid` / `unsupported` placeholder (#923).** On cars that don't expose them (MQB-schema residue), the charging *reason* surfaced a literal `invalid` and the target-SoC remaining-time surfaced `unsupported`, instead of reading unavailable. Both now drop the no-reading sentinel the same way the charge-type field already does. Thanks @naked-head.
- **Trip statistics are no longer re-fetched on every poll.** The CARIAD-BFF trip-statistics endpoint is dead (404) for most cars since the backend lockdown, yet it was hit three times on every single poll — a stream of wasted requests and failed-job telemetry. It's now fetched at most once an hour per car and reused from cache in between, so nothing flickers and the log stays quiet; the coordinator's own hourly, capability-gated refresh is unchanged.
- **A sweep of real diagnostics caught eleven more fields leaking a backend `invalid` / `unavailable` / `unsupported` placeholder (#923).** The charging state, charging scenario, plug LED colour, preferred charging mode, climatisation state, external-power-supply state, charge-rate unit, profile charge reason, start/stop action and modification, and the "target SoC reachable" flag all passed the no-reading sentinel straight through to their sensors on cars that don't report them. Every write path that produces them — EU Data Act portal, CARIAD BFF, VW US and the volkswagen.de channel — now screens the value through the shared guard, so they read unavailable instead of a stray `invalid`. (charge type, plug state and range already handled this — those older captures were pre-fix.)

## [4.2.0] - 2026-08-23 — VW render photos, consistent full model names across brands & self-diagnosing "no data" downloads

### Added
- **VW cars can show their photos now (#1229).** VW EU render images were never fetched, so VW devices had no picture at all (the app-backend image endpoint is blocked for these cars, and the EU Data Act portal carries no images). If you've enabled the optional **volkswagen.de** channel, we now pull the exterior renders from it — each angle becomes its own image entity with the car photo on the device. Portal-only cars still have no render source on VW's side. Thanks @Ra72xx.
- **More Audi angles.** Audi render images are no longer limited to a fixed handful; every angle the backend offers is surfaced as its own image entity.

### Changed
- **The device model name is now the full marketing name, consistently across every brand.** The device page prefers the long name ("Audi Q4 50 e-tron quattro") — Audi/VW pull it from the render fetch, SEAT/CUPRA from their media data — instead of each brand showing a different, shorter label (or, for Audi, sometimes just "Audi"). It falls back through the short name and the brand-specific model, and never shows the bare brand alone.
- **Diagnostics now record why a car has no data (#1227).** When the EU Data Act portal delivers nothing, the download now carries the reason — `no_request` (no continuous data request set up for the car yet), `empty` (a transient VW-side portal error) or `no_content` (the request is live but the car hasn't fed telemetry in yet) — so a "no data" report is triageable straight from the diagnostics instead of a round-trip to read the log. Thanks @ccsnet.

### Fixed
- **The car photo no longer replaces every entity's icon (#1229).** The vehicle render now lives on the device and the map, and the ~100 sensors keep their own icons in dashboards instead of all showing the car image. The render is still available as its own image entity. Thanks @Ra72xx.

## [4.1.2] - 2026-08-21 — no more false "stale data" warnings from a frozen capture timestamp

### Fixed
- **No more false "vehicle data hasn't refreshed in N hours" warnings (#465).** On the EU Data Act portal the car's capture timestamp arrives contested — a fresh reading next to a frozen one from an old stop-charging report. A poll that carried only the stale stamp could drag the "last reported" time backwards and fire a false staleness warning (one owner saw "138 hours" while live values were current). The last-reported time is now held monotonically — an older stamp never overwrites a newer recorded one, and a genuinely fresher reading still clears the warning. Thanks @shaarkys for the diagnostic.

## [4.1.1] - 2026-08-21 — dashboard warning lights work again on current Audi firmware

### Fixed
- **Dashboard warning lights work again on current Audi/BFF firmware.** VW's newer firmware wraps the warning lights in a `{warningLights: […], campaigns: […]}` object instead of a plain list, and labels each fault under `category`/`type` instead of the old `warningType`. The integration only understood the old shape, so it silently dropped every warning — an Audi Q6 with four real active faults (lighting failures) reported *zero*. It now reads both shapes, so the warning count, the warning-active flag and the messages sensor light up again. Found by mining the diagnostic archive.

### Added
- **Service & recall campaigns sensor.** The same warnings block carries the dealer/software-update campaigns the manufacturer app shows the owner (e.g. a pending "Combined software update"). These are now surfaced in a new **Service Campaigns** sensor (diagnostic, off by default). Translated across all 12 languages.
- **Charging scenario now populates on the app-backend path too.** The `charging_scenario` sensor was only ever filled by the EU Data Act portal; the CARIAD-BFF read path never set it, so it stayed unavailable on Audi and other BFF-primary cars. It now reads on both paths.

## [4.1.0] - 2026-08-21 — Audi battery health, PHEV pre-heater, parked-battery stability, CNG level & a clearer North-America sign-in

_Consolidates the 4.1.0b1–b2 betas plus the North-America sign-in fix into one stable release._

### Added
- **Battery State-of-Health read (Audi).** We Connect 4.3.2 exposes SoH through a separate `batteryHealthState` BFF read (not part of the main status bundle); the integration now fetches it best-effort and maps the usable-battery-energy percentage onto the State-of-Health sensor. This read is attestation-walled for Volkswagen EU passenger cars (unchanged, fails soft), but Audi device-grant entries now get a real SoH value. The measured reading always wins over the optional nominal-capacity estimate, so setting a nominal on an Audi never overwrites the car's own number.
- **Plug-in hybrid parking/pre-heater status (Volkswagen & Audi).** PHEVs (Golf/Passat GTE and the like) report their auxiliary heater under a distinct `hybridCarAuxiliaryHeating` job that the integration wasn't requesting, so their aux-heat status never populated. Grounded against the We Connect app, that job is now fetched and its `hybridCarAuxiliaryHeatingStatus` mapped onto the same aux-heating status/active/remaining fields the BEV path uses.
- **CNG tank level now reads over the EU Data Act portal (Scout #1225).** Volkswagen TGI / natural-gas cars publish `cng_gas_level` (%) through the portal, but the portal reader wasn't picking it up. It now feeds the existing CNG-level sensor — the same one already populated on the SEAT/CUPRA and VW-EU app paths — so a gas car read only through the portal finally gets its tank gauge. Thanks @ChibiDanjo for the Scout report.

### Fixed
- **North-America sign-in no longer looks like a wrong password (#1165, #659).** Since VW switched on Play-Integrity attestation on the North-America sign-in (~2026-07-30), the token exchange fails before any vehicle read — and the integration reported that as "email or password incorrect", so US/CA owners kept re-entering their credentials in a loop. It now detects that specific VW-side lock and shows a clear message explaining it's a device-attestation block, not a credentials problem, so people stop fighting the login. Translated across all 12 languages. Thanks @fg877khkv8-maker and @briancmoses for the logs.
- **The North-America MBB tester probe now targets the NA login server (#1215).** `scripts/vw_na_mbb_probe.py` was building its device grant against the EU IDP (`identity.vwgroup.io`), which doesn't recognise a North-America Volkswagen ID; it now points at `identity.na.vwgroup.io` so US/CA testers can actually probe the legacy Car-Net path. Thanks @mvasilakis for the debugging and the fix.
- **A parked car's battery percentage no longer jumps to a stale value on a partial poll (#1195, #465).** On the EU Data Act portal the reliable SoC is a single-occurrence, VALID `battery_level_HV` reading; a poll that omits it carries only a `battery_state_report.soc` leaf that can be the frozen value from the last stop-charging report, stamped with a fresh-looking capture time. On a car that normally reports the HV reading, such a poll now holds the recorded value instead of publishing that stale leaf, so the percentage stops showing phantom ups and downs while parked. Thanks @soulriding for the 16-dataset analysis and @Arno-MA-73 for the corroborating case. (Cars that never report the HV pair — e.g. some ID.4 firmware — are untouched by this and still rely on the energy cross-check, which is being improved separately.)

### Documentation
- **Documented the VW EU GPS limitation — now confirmed by VW itself.** Volkswagen Group Info Services confirmed in writing that the EU Data Act continuous-export Data Dictionary lists a *Vehicle Location Tracking* cluster but no defined data point for a car's current GPS coordinates, so a VW EU car read only through the portal shows its location as `unknown`. This is documented in the README's *Known limitations* in all 12 languages, citing VW's reply. Thanks @mathep34 for chasing the portal support team down.

## [4.0.0] - 2026-08-20 — the Volkswagen grounding wave: durable Car-Net (MBB) two-way, deeper reads, and a data-quality pass

_The 4.0.0 line is a deep pass over the Volkswagen side of the integration, grounded field-by-field against the We Connect app (androguard vs We Connect 4.3.2). Midway through, on **2026-08-18 Volkswagen disabled the login** the modern (CARIAD) two-way used — so this release ships that channel **greyed out** (all its code kept) and leans on the **durable Car-Net (MBB) two-way** as the way to send commands to a Volkswagen. Alongside the two-way work: a capabilities-first read foundation, grounded VW/Audi commands, a data-quality pass on the EU Data Act portal, and the companion brought up to the current app. Consolidates the v4.0.0b1–b6 betas and the v3.3.0b1 data-quality beta._

### Added
- **Durable Car-Net (MBB) two-way for Volkswagen — the VW command channel (opt-in, BETA).** Remote lock/unlock, climate and charging for **legacy MQB / Car-Net** Volkswagens, riding a refreshable token VW has not blocked. It's presented in setup as the recommended VW two-way (all twelve languages), with guidance on which cars it fits — most PHEV / combustion, pre-ID; **MEB / ID-family cars (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) aren't eligible**. A backup client is included so the channel survives VW pulling a single one. Testers welcome in **#584**.
- **VW EU Two-Way (modern CARIAD, opt-in) — added, then disabled by VW.** b1 shipped an opt-in Volkswagen-ID channel for live CARIAD reads and commands; on 2026-08-18 VW disabled the login it renews, so it is **greyed out** in this release — all the code is kept, so it flips back on in a single line the moment VW reopens it, and existing users get a one-time notice that their reads keep flowing through the EU Data Act portal. Credit to **@magicus** for surfacing the device-grant client this builds on.
- **Capability-first read foundation.** Read entities can now be gated on the car's advertised capabilities (not just on whether data is present), using the same capabilities document the command entities consult. The gate is deliberately soft — a sensor is hidden only when the capabilities list is loaded and explicitly says the feature is absent, never when it's missing or loading — and it's grounded against the app so app-only features (media, maps, web apps) never become entities.
- **Remote cabin ventilation for Volkswagen & Audi.** The "active ventilation" switch (airing the cabin without heating) now works on VW/Audi, not just Škoda, using the app's grounded `activeventilation/start|stop` commands.
- **Two tester probes** (in `scripts/`): one for VW EU two-way commands + live reads (#584), one for the North-America attestation situation (#1215). Both use a browser login (no password ever in the script), mask VIN/tokens, and print a paste-safe block for the issue thread.

### Changed
- **Two-way is the authoritative data source when it's on, with EU Data Act as a gap-filler.** While two-way is active, the live reading wins every field it provides and the portal only fills fields two-way doesn't offer, so a slower portal export can never overwrite a fresh value with an older one. If two-way drops out, the integration falls back to the portal in the *same* poll instead of freezing, and resumes automatically when it recovers.
- **MBB is presented as the VW two-way in setup, not a footnote.** The Volkswagen portal path spells out that durable two-way commands ride along via the classic Car-Net (MBB) backend, and the toggle explains when it fits. Same wording in all twelve languages.
- **Vehicle wake tries the paths the official app actually uses.** Grounding the app showed it wakes the car via `vehiclewakeuptrigger` / `access/wakeup`; the integration tries those first and keeps the previous path as a fallback, so a car that only accepts the app's spelling wakes reliably.
- **Fewer Vehicle Data Scout prompts on the EU Data Act portal.** The portal's "is this field populated" envelope flags (`mileage.is_set`, `hvbatterytemperature.is_set`, `trunk.is_set`, …) no longer prompt a report — they carry no value beyond what a present/absent reading already shows. Surfaced by @Schraube11 (#465) and #1216.
- **The Volkswagen two-way setup strings are localized in all twelve languages.** The VW EU Two-Way options, their auth errors, the channel-disabled notice and the repair message were shipping as English placeholders in the non-English UI; they read in the user's own language now. The translated READMEs also gained the cross-brand auxiliary-heating and per-session charging-history notes.

### Fixed
- **A dead upstream VW sign-in no longer tears down the whole entry (#1222).** Since VW disabled the modern VW EU login, an affected car could fail setup with "Invalid credentials" and take *every* entity offline — including the EU Data Act sensors that never used that login. Setup now keeps the entry alive by reading the vehicle list from the portal, so those sensors keep serving and only the dead channel is degraded. Reported by @ggfbrkt6mc-max.
- **Battery-care mode is now actually settable on Volkswagen & Audi.** The battery-care switch and its target-charge slider appeared but did nothing on VW/Audi (the command was never implemented for the CARIAD backend); they now send the app's real battery-care commands.
- **Primary range comes back on newer platforms (e.g. CUPRA Raval) (#1220).** These cars report the range under a newer official field name the parser wasn't reading, so the range sensor silently stayed empty. It's picked up now.
- **Battery percentage no longer sticks at an old value while the pack tells a different story (#1195).** When the portal shipped the charge level twice under one timestamp with different numbers, we could latch a stale value (@Fishermanjb's ID.4 sat at 94 % while the car was really around 67 %). We now cross-check against the pack's own energy content: when the shown percentage sits well above what the pack actually holds on a car that isn't charging, we trust the measurement. Thanks @Fishermanjb for the repeated fresh diagnostics.
- **Vehicle data no longer looks days old when it isn't (#1218).** A single portal export can carry several capture timestamps; the "last reported" age used to lock onto one by field name, so a stale sibling could make the data look ~91 hours old. It now anchors on the freshest capture time actually present. Thanks @Lagaff86 for the precise timestamp breakdown.
- **A stuck, implausible interior temperature is no longer shown (#465).** The portal's "no reading" placeholder encodes at the floor of the temperature range, so it surfaced as a fixed, impossible cabin temperature (a −43.9 °C that never changed). It's kept only when physically plausible now. Reported by @Schraube11.
- **The companion accepts We Connect 4.3.2 and reads imperial range correctly (#968).** The app version check disabled every screen-read after 4.2.1 → 4.3.2; it now accepts the current app (and the internal build strings that ship the same layout), pins the charge-detail tile to a stable node, and converts a range narrated in miles to km instead of storing the bare number. Thanks @Philip-Wiege, @plainmad and @kgroshert.
- **The EU Data Act identifier is no longer written in clear text in diagnostics (#923, #1222).** The per-VIN identifier map masked the VIN used as its key but left the identifier value in plaintext, so it went out in the download people attach to public issues. The values are redacted now while the map shape stays. Thanks @ggfbrkt6mc-max.
- **Parking address carries the suburb and state, not just the city (#1219).** The reverse geocoder only surfaced the city, so a car parked in a suburb showed the wrong locality and dropped the state/postcode the brand app shows. It now reads the suburb (with fallbacks), state and postcode, and orders the house number correctly outside the German-order countries. Thanks @mhanline.
- **Bruno CI is green again** — a Škoda `/api/v1/users` endpoint had no matching Bruno file, which failed the strict URL-drift check on every push.
- **Release asset could be missing after a tag** — a single tag push occasionally started two racing release jobs and the loser could leave the release without its `vag_connect.zip`; the workflow now serialises per tag.

### Note
- If a two-way command does nothing and the **official VW app also can't control the car**, the account is rate-limited or temporarily locked — enable only one two-way integration per car at a time.

## [3.2.4] - 2026-08-17 — vw.de session persists across every refresh

### Changed
- **Quieter Vehicle Data Scout on Audi.** The Audi charge-care request queue (`batteryChargingCare.chargingCareSettings.requests`) is internal metadata alongside the already-handled charge-care feature, so it no longer trips the Scout. Reported by @lexathon (#1214).

### Fixed
- **The volkswagen.de session now survives a restart even hours later (#966).** v3.2.3 stopped the cookie set from doubling, but the session could still expire shortly after a restart: the rotated cookies were saved when the channel first armed, but the immediate follow-up read a few seconds later silently refreshed the session again and rotated the sign-in cookie without saving it, so a restart replayed the older, already-superseded cookie. The rotated cookies are now saved after every supplementary read, so the persisted session is always the current one. Grounded in @Arno-MA-73's precise v3.2.3 re-test.

## [3.2.3] - 2026-08-16 — vw.de survives repeated restarts + SoC recovers after charging a parked car

### Fixed
- **The volkswagen.de session survives more than one restart (#966).** The supplementary volkswagen.de channel could resume fine on the first restart and then fail on the second. A host-only sign-in cookie is broadcast to both VW hosts on load; on the next save it came back once per host and the set kept both copies, so the cookie set doubled every cycle (an 11-cookie login became a 22-cookie restore) and the superseded twin overwrote the still-good `identity.vwgroup.io` sign-in cookie — which looks like an expired session but is really the integration clobbering its own cookie. The save now folds a byte-identical broadcast twin, so the set no longer grows and the good cookie survives. Grounded in @Arno-MA-73's exact 11→22 reproduction; also covers the second-restart loop @bobbasli reported in #875.
- **A frozen State-of-Charge now recovers after charging a parked car (#1195).** The v3.2.0 recover-from-stale fix leaned on either the odometer advancing or the energy reading being fresh — but neither holds when you charge without driving: the car didn't move, and the derived available-energy figure still lags the charge, so it pointed back at the pre-charge value and stayed stuck (a plugged ID.4 charged to 99 % kept showing 94 %). When the car is plugged in and demonstrably hasn't moved, SoC can only have risen, so the higher of the two disagreeing values is now taken. Unplugged/parked cars are untouched, so the spurious-twin guards still hold. Grounded in @Fishermanjb's v3.2.0 diagnostics.

## [3.2.2] - 2026-08-16 — Škoda push FCM registration fix + diagnostics say why a push channel didn't connect

### Fixed
- **Škoda push registration now uses the right Firebase project (#602).** The Škoda MQTT push needs a Firebase Cloud Messaging token as its credential, and registering for that token was pointed at the wrong Firebase project — the numeric sender id (`678067506455`) was being passed where the project *slug* (`myskoda-ng`) belongs, so every registration failed with "Unable to register with fcm" and the push channel tripped its breaker without ever connecting. All four Firebase values are now verbatim from the MySkoda app (verified against the 8.15.0 APK), with the project id set to the slug. This clears the specific failure a tester's log showed; a broker-accepted end-to-end connection is still being confirmed on a live Škoda account. Grounded in Marco Schmidt's push log via the Home Assistant *Tipps und Tricks* Facebook group.

### Added
- **A push channel that won't connect now says why in the diagnostics.** When a cloud-push channel shows up as `tripped` / `reconnecting` in the diagnostics dump, it was impossible to tell *why* without digging the WARNING line out of the Home Assistant log — the export only carried the state, not the reason. The circuit-breaker now remembers a value-safe reason for the last failed connect (the error type plus a short message, never a token), and it's exported as `push_last_errors` alongside `push_states`. So a Škoda MQTT channel that trips because the broker refused the credentials, or because the FCM registration failed, now says so right in the diagnostics. Prompted by Marco Schmidt's push testing via the Home Assistant *Tipps und Tricks* Facebook group.

## [3.2.1] - 2026-08-16 — Škoda Standheizung back + push user-id from the right place

### Fixed
- **The Škoda auxiliary-heating (Standheizung) switch is back on cars that actually have one.** v3.2.0 added a heuristic that hid the switch whenever a Škoda reported no aux-heating telemetry — but a car whose air-conditioning is temporarily in an `INVALID` / not-fully-authorised state reports exactly the same "nothing" as a car with no heater, so the switch also vanished on aux-equipped Octavias. Checked against the MySkoda app (8.15.0): aux heating is a real per-car capability (`AUXILIARY_HEATING`), so the switch is now gated on that when the car advertises its capabilities, and simply shown otherwise — the project never hides a control on an unknown, exactly like every other switch. The v3.2.0 "phantom heater" report turned out to be the same transient `INVALID` state, not a car without a heater: the diesel Octavia and a gasoline Octavia produced byte-identical telemetry. Reported by Marco Schmidt, and originally by Wehrfried, both via the Home Assistant *Tipps und Tricks* Facebook group.
- **The whole Škoda capability table is now the app's real capability names, not guesses.** The ids that decide whether to show a Škoda control (lock, climate, charging, window-heating, ventilation, aux-heating, departure timers, …) were educated guesses (`air-conditioning`, `charging`, `honk-and-flash`, `departure-timers`) that never match what the MySkoda backend actually sends — verified verbatim against the 8.15.0 app's capability list. Harmless while a car's capability list is empty, but each one would have wrongly hidden its control the moment the list populated. Every id is now a real one, and features with genuine platform variants (charging = classic vs MEB, lock with vs without an S-PIN) accept either variant so a control is never hidden by guessing the wrong one. A guard test pins the whole table to the real 156-entry vocabulary so a future guess can't slip back in.
- **Škoda push really arms now — the account user-id comes from the right place (#602).** v3.2.0 tried to read the user-id out of the login token; on a classic MySkoda login that field is empty, so the push channel still never armed (Marco's diagnostics showed it dead, `push_states` empty). The MySkoda app reads the id from `GET /api/v1/users`, so the integration now does the same during the normal vehicle fetch — the id is set before the push channel starts. Reported by Marco Schmidt via the Home Assistant *Tipps und Tricks* Facebook group.

## [3.2.0] - 2026-08-16 — Škoda active ventilation, MEB charge-telemetry, SoC-freeze & token-storm fixes

### Added
- **Škoda active ventilation switch (cabin airing without heating).** The MySkoda app's "Lüften" — air the cabin without running the heater — was in the API client but had no HA switch. It now has its own switch, routed to the Škoda `command_start_active_ventilation` command. It can never collide with the existing SEAT/CUPRA ventilation switch: each command lives on a different brand's client. Optimistic state, since the Škoda read path doesn't report a ventilation state. Requested by Wehrfried via the Home Assistant *Tipps und Tricks* Facebook group.
- **CUPRA remaining-charge-time now reads (#1202).** SEAT/CUPRA ship the time-until-charging-finishes as a `remaining_time_finished` value + `TIME_UNIT_*` unit pair (a dictionary field that wasn't wired to a sensor). It now feeds the remaining-charge-time sensor, converted to minutes from whatever unit the car sends — as a last-resort fallback that never overrides a canonical `remaining_charging_time`. Both leaves are consumed so they stop surfacing to the Scout. First surfaced by a CUPRA Raval.
- **Disabling a vehicle now actually stops polling it.** If you have more than one car on an account and disable one in Home Assistant (its device page), the integration no longer keeps polling that VIN in the background — so a car you don't want stops consuming the daily request budget. It resumes automatically if you re-enable the device. Reported by Marco Schmidt via the Home Assistant *Tipps und Tricks* Facebook group.

### Fixed
- **A frozen State-of-Charge now recovers instead of latching on the stale value (#1195).** VW's portal sometimes reports SoC under two disagreeing values and stamps the *stale* one with a *newer* capture time, so the reading is left contested; the reconcile step then kept whichever candidate was closest to the last reading, which **latches** — once stuck, the stale value is both the anchor and a candidate, so a genuinely changed SoC could never land (an ID.4 froze at 94 % while the car was at 57 %). Contested SoC is now arbitrated with independent live evidence: the **energy-content ratio** (`battery_available_kwh / battery_cap_kwh`, which isn't part of the contest and is stateless) and whether **the car actually moved** (odometer advanced → the SoC must have changed, so a candidate still equal to the frozen value is the stale one and is dropped). Parked cars with no evidence fall back to the previous behaviour, so the spurious-twin guards still hold. Grounded in @Fishermanjb's diagnostics.
- **Škoda sensors no longer drop to "unknown" from a false token-refresh storm (#1078).** A single poll fans out ~14 concurrent requests; when they all hit a just-expired token at once, each one independently refreshed it, so one expiry event burned the whole "3 refreshes/hour" safety budget in seconds and tripped the storm guard at a perfectly healthy 30-minute interval. Refreshes now coalesce — a request that finds the token already rotated by a sibling reuses it instead of refreshing again, so one expiry costs one refresh. A genuine storm (a refresh that keeps failing) still trips. Grounded in @foobarth's report, and independently confirmed on a Škoda Octavia by Marco Schmidt via the Home Assistant *Tipps und Tricks* Facebook group.
- **No more phantom "auxiliary heating" switch on a Škoda without a heater.** Škoda declares no fuel-fired aux heater and carries no aux-heating capability id, so the "don't hide on unknown" rule spawned a Standheizung switch that did nothing on a diesel Octavia. The switch now needs positive evidence on a brand that declares no aux heater (a mapped capability the backend confirms, or an actual aux-heating reading); brands that declare the heater (VW/Audi) or carry a mapped capability (SEAT/CUPRA) are unchanged. Reported by Wehrfried via the Home Assistant *Tipps und Tricks* Facebook group.
- **Škoda diesels stop hammering the charging endpoint.** A combustion-only Škoda has no HV battery, so `/charging` returns 403 on every poll forever. Once a poll's driving-range tells us the car is pure-combustion, that read is skipped — no repeated 403s, no charging sensors on a diesel. EV and PHEV are never skipped. Same report from Wehrfried, and seen again on Marco Schmidt's Octavia (same Facebook group).
- **Remaining-charge-time sensors no longer freeze after a charge ends (#632).** Sibling of the charge power/rate freeze (#1090): some backends keep sending the last "minutes remaining" value once a session stops, so the ETA sat stuck (a captured VW ID.7 showed 70 minutes remaining while parked at `NOT_READY_FOR_CHARGING`; other portal VWs showed 5 and 115). The `remaining_charge_time_min` sensors (incl. the nav- and bulk-current variants) now read 0 once charging is *explicitly* off. Unlike power/rate this also covers EU-Data-Act portal cars, which never report the charge plug, so the rule keys on the charging flag being off rather than the plug — and never fires while the charge state is unknown, where the ETA may be real. Surfaced from @gr6803's ID.7 diagnostics.
- **Charge target now shows the real cap when Battery Care is on (#632).** On a MEB car with Battery Care active the charge-target sensor read the raw profile ceiling (100%) even though the car actually stops at the Battery-Care threshold (e.g. 80%). The target now reads the lower of the two whenever Battery Care is active, so it matches what the car will really charge to. Cars without Battery Care, or with it off, are untouched. From @gr6803's VW ID.7 diagnostics.
- **Charge power and rate stop lingering after a charge ends on portal cars (#632).** The stale-after-stop zeroing (#1090) only fired when the car reported a charge plug, which EU-Data-Act portal cars never do — so a VW ID.7 kept showing a charging rate of 29 km/h while parked. Those sensors now also zero once charging is explicitly off, matching the remaining-time behaviour, without faking a 0 on a car that never reported one.
- **Škoda climate sensor no longer shows a raw "INVALID".** On a combustion Škoda (or whenever the air-conditioning endpoint returns no valid state) the climate-state sensor displayed the literal `INVALID`. It now reads unavailable instead, which is what "no valid climate state" actually means; the climate entity already treated it as off. Reported by Marco Schmidt via the Home Assistant *Tipps und Tricks* Facebook group.
- **Škoda push now arms after a restart (#602).** The MQTT push channel needs the account user-id, which was only captured during an interactive login. On a normal restart (persisted tokens, no interactive login) it was never captured, so the channel silently never armed — the push sensor stayed "unknown" with nothing in the log. The user-id is now also decoded from the persisted id-token, so the channel arms and its state becomes visible after a restart. (Reaching a live connection still depends on the experimental Škoda broker path.) Reported by Marco Schmidt via the Home Assistant *Tipps und Tricks* Facebook group.
- **ADB companion reads State-of-Charge on a Mk8 Golf GTE (#968).** On the Golf 8 the We Connect app shows the battery percentage on the charge-detail sheet, not the overview the selectors read, so the companion channel saw only the departure timers. SoC is now read from the charge-detail screen (`rangeArcBatterySoc` / "Battery … per cent"), and resource-id matching tolerates the package prefix so a bare id in one build matches a prefixed id in another. Enable the "read charge detail" option to pick it up. Grounded in @plainmad's Mk8 dumps. (Range in imperial "miles" is a separate follow-up so it's never mislabelled as km.)
- **A refused VW US/CA remote lock/unlock now explains itself (#1082).** On some US cars (e.g. a 2023 ID.4 whose software level doesn't provision remote lock/unlock) the command comes back as a bare `500` from VW while the lock state still reads correctly. Instead of an opaque error, the command now reports that it's most likely a vehicle capability limit rather than something to keep retrying. The control isn't hidden — the project doesn't remove a button on an unconfirmed 500, in case it's a genuine transient hiccup. Grounded in @fg877khkv8-maker's report.

### Changed
- **The "raise your update interval" advice now uses VW's real per-account budget when it's available (#1078).** Instead of a blunt fixed step-up, when VW sends its `X-RateLimit-Remaining` header (already surfaced as the "requests remaining today" sensor) the recommendation spreads the remaining calls over the time until the budget resets. It can only tighten the advice, never drop it below the existing guard, and falls back to the guard unchanged when the header isn't present.
- **The VW US/CA "vehicle data blocked" repair no longer blames an inactive subscription outright (#659).** Some cars 403 every read while the subscription is active and the MyVW app still shows live data — VW simply isn't authorising the third-party client. The repair now says so instead of insisting the subscription has lapsed, so owners with an active plan aren't sent chasing a renewal that won't help. Reworded across all 12 languages. Prompted by @jarmbruster74.
- **New debug line for diagnosing empty VW US/CA reads (#1082).** When VW US/CA reads come back empty without a 403, there was nothing in the logs to say why. A value-safe fingerprint (whether the S-PIN read path engaged, the country client, the scope, the privileges status) now prints every poll under debug — no VIN, UUID, or token in it. Helps ground the @jarmbruster74 case.

## [3.1.1] - 2026-08-15 — iOS charging Live Activity, PPE false-OK fix, Scout SoC de-dup + docs/i18n polish

### Added
- **iOS Live Activity — charging countdown on the Lock Screen + Dynamic Island.** A shipped automation blueprint (*"Live Activity — EV charging countdown (iOS)"*) drives a native iOS Live Activity from the existing charging sensors: a live-ticking countdown to the absolute `charge_target_time`, plus a state-of-charge progress bar. Starts when charging begins, refreshes as the ETA / SoC move, clears when it stops. Needs the Companion app's Live Activities (iOS 17.2+, HA Core 2026.7+ — currently a Labs/TestFlight feature); ships now so it's ready the day it goes public.

### Fixed
- **Finished localising the experimental ADB companion setup step.** Its config step + three error messages were still English in the 11 non-English locales; now fully translated (de, fr, it, es, nl, pl, cs, sv, da, nb, fi).
- **A command the car accepts but never carries out no longer shows a false "OK" (#912, #940).** The completion poll only ever caught an *explicit* backend rejection; a request that the car accepts and then leaves running forever (the Audi PPE "vehicle does not answer" / `e:CV.PA.29` case — the car never actuates and no rejection code ever reaches the data we poll) timed out and was accepted optimistically. It's now reported as **unconfirmed** when the request stays non-terminal for the whole confirmation window, so Home Assistant reverts the optimistic state instead of claiming success. A fast command whose request clears before we poll is unaffected (still optimistic), so normal commands don't turn into false failures. Grounded in @Mirjam9's cohort diagnostics.
- **Stopped the Vehicle Data Scout from re-filing the same already-mapped SoC field (#1179-#1184).** On EVs that report a VALID high-voltage battery level, the State-of-Charge resolver correctly took that value (per #1088) but short-circuited past the step that marks the co-present `battery_state_report.soc` leaf as consumed — so it re-surfaced as an "undiscovered field" every poll and opened a fresh Scout issue per car (six in a day). The resolver now runs its alias-consumption step unconditionally; the SoC reading is unchanged, the duplicate reports stop. A genuinely-new field still surfaces.

## [3.1.0] - 2026-08-14 — Logbook events, firmware & calendar cards, freeze warning + HA coverage sweep

### Added
- **"Data hasn't refreshed" warning for a frozen vehicle feed (#465).** When the integration keeps polling successfully but the car's own data-capture time stops advancing (a lapsed EU Data Act feed presenting days-old data as live), a dismissible per-vehicle Repair now points it out — and explains it may just be a parked, sleeping car. Auto-clears the moment a fresher reading arrives. Grounded in @TomJonesGreggs's ID. Buzz freeze; complements the new "Vehicle Last Reported" sensor from 3.0.6.
- **Push events are now first-class HA entities.** Manufacturer push notifications (Škoda / Audi / VW / CUPRA / SEAT) already fired on the event bus; each vehicle now also gets a proper `event` entity, so they show in the Logbook, drive automations without a YAML bus filter, and keep per-car history. Unknown backend event types are preserved verbatim under an `event_type_raw` attribute.
- **Firmware `update` entity.** The car's installed software version + "update available" status now render as a native HA update card (with a release-notes link where provided) — read-only, since VAG firmware is flashed by the car, not by HA. Škoda today.
- **Charging & service calendars.** Two read-only calendars per vehicle: a *charging schedule* (departure timers + charge/climate ETAs) and a *service schedule* (service/oil/brake due dates) — the scheduling data on a timeline instead of scattered across time/date sensors.
- **Per-device diagnostics download.** You can now download diagnostics for a single car (from its device page) instead of the whole account — smaller, and easier to share for a bug report. Same redaction as the full export.

### Fixed
- **Lifetime travel-time now records long-term statistics.** It was missing a `state_class`, so it produced no history — corrected to `TOTAL_INCREASING` like its distance siblings. (HA feature-coverage audit.)
- **12 V starter-battery SoC now tagged as a battery.** Added the `battery` device class for a correct icon/UX. (HA audit.)
- **system_health version lookup cleaned up** — dropped a dead branch that always raised into the fallback. (HA audit.)

### Internal
- **Opt-in capture of a command's backend result (#912).** For test-cohort users, a command's `pendingrequests` response is kept (redacted) in diagnostics, so an Audi PPE reporter can hand over the exact rejection shape (`E:CV.PA.31`) needed to teach the confirmation logic. Off for everyone else; no extra request. The test-cohort share prompt now also reaches BFF/Audi users, and its text is generalised (no longer GPS-specific).

## [3.0.6] - 2026-08-14 — charging state, climate confirm, staleness + Scout tidy-up

### Fixed
- **CUPRA (and other EU-DA cars) no longer show "not charging" while actively charging (#632).** Some portal firmwares send a charge *scenario* but not the raw charge-state, so `is_charging` stayed off and the plug read "not connected" mid-charge. An in-progress scenario (`…_ACTIVE`) now lifts charging and infers the plug — without ever overriding a real reading. Thanks @gr6803.
- **Audi PPE climate no longer reports a false "OK" when the car rejects it (#912).** The rich `start_climate_control` path skipped the command-confirmation poll the basic climate command already runs, so an asynchronous backend rejection (e.g. `E:CV.PA.31` on A6/Q6 e-tron) looked like success. It now confirms through the same poll — best-effort, so it can't regress a working command. Thanks @Mirjam9 (and #940 @loeildubush).

### Added
- **"Vehicle Last Reported" diagnostic sensor (#465).** Shows the car's own data-capture time, distinct from the poll time ("Last Update"). On a frozen-but-non-empty EU Data Act feed the poll keeps succeeding while the data is days old — now "reported 2 days ago" next to "updated 1 minute ago" makes a silent freeze obvious. Reporter's own idea; thanks @TomJonesGreggs.

### Internal
- **The Scout stops spamming a new GitHub issue per user for fields we intentionally never map (#1151/#1156/#1164/#1166/#1167, #1140/#1149/#1152/#1161/#1168).** `scope_potential_total` (PPE-opaque) and the ownerless opening UUIDs `c0bb1348`/`d5dc7c87` are kept out of the user-facing "report this" repair while staying fully Scout-visible in diagnostics; a genuinely-new field or opening UUID still raises it.
- **Mapped the remaining Scout fields from #1164 (@morpheusbdf).** `state_ext_cond_available_*` (static per-zone climate availability) and `tank_accuracy` (folds into the existing fuel-level-estimated flag) are now consumed, so the Scout stops re-flagging them.

## [3.0.5] - 2026-08-14 — cohort probe observability + SoC / interval fixes

### Fixed
- **Battery SoC no longer sticks on a stale value on some EU cars (#1088).** A few cars (ID. Buzz) ship `battery_state_report.soc` twice — and VW stamps the *stale* value with the *newer* capture time, so the freshness resolver picked the wrong one and the contested-reading guard never noticed (the timestamps genuinely differ, so it isn't a tie). When VW marks the HV battery level `VALID`, that single, unambiguous reading is now trusted over the contested SoC leaf. Grounded in @ggfbrkt6mc-max's raw export (36 VALID vs the stale 18). Inert for cars that don't ship the HV pair.
- **The "raise your update interval" tip no longer suggests an interval you can't select (#1115).** The advice is now clamped to the 60-minute maximum the options picker allows; when you're already at the ceiling the tip is suppressed instead of asking you to set 61 or 75 minutes. Thanks @Reluca and @christianmhz.
- **Audi aux-heating request-queue field no longer re-flagged by the Scout (#1154).** `climatisation.auxiliaryHeatingStatus.requests` (an internal empty-list counter) is now silenced — it had slipped past the existing wildcards. Thanks @neuweddemer.

### Internal
- **Experimental vw.de probes now record their outcome in diagnostics (#923/#1157).** The opt-in GPS (parkingposition) and battery State-of-Health probes run fail-soft, so a 403/404/412 refusal or an empty 200 previously left no trace — the test cohort was flying blind. A new `probe_outcomes` block in the config-entry diagnostics now shows each probe's status (`404`, `412`, `200 no-coords`, …), merged up from the supplementary connector. Bare status labels only, no PII.
- **`battery_charging_status_soc` wired as a last-resort SoC source (#1164).** A charging-status HV SoC (`%`) recovers the reading for a car that ships nothing else, ranked below the canonical sources. Thanks @morpheusbdf.

## [3.0.4] - 2026-08-13 — odometer self-heal + attestation-free SoH probe

### Fixed
- **Odometer frozen at 429,496,729 km now clears itself (#1122).** v3.0.2 added a guard that drops this implausible reading — the uint32 "no value" sentinel scaled by the odometer's 0.1 km unit — on every channel, but a car that had already cached the bad value before updating kept showing it: the last-known-value layer both refilled it whenever a poll omitted the odometer, AND — because an odometer only ever counts up — treated the real, much lower reading as "went backwards" and kept the sentinel. The merge now purges a sentinel from the restored snapshot first, so the cache self-heals on the next poll and the true mileage lands. Thanks to @dpk1987 (Golf 8 mHEV) for catching that the first fix hadn't taken, with the exact before/after values.

### Internal
- **Diagnostics now flag a "no legacy MBB enrolment" car (#584).** When a car set up on the durable-MBB channel gets the definitive `gw.error.authentication` reject on its service list — the fingerprint of a car/account with no legacy Car-Net enrolment (reads still work over the EU Data Act / volkswagen.de channel, but MBB commands never will) — the config-entry diagnostics now list that VIN under `mbb_no_legacy`. So a report of "MBB set up but no commands appear" is answerable straight from the diagnostics instead of asking for a debug log, and the verdict clears the moment the car's service list succeeds again (e.g. after becoming the primary user in the brand app). Grounded in the B8 Passat GTE reports (@Mattheisen87, @BengtKR79) and @JustAnotherDud's Polo probing.
- **Opt-in probe for an attestation-free battery State-of-Health reading (We Connect 4.3.2).** VW's 4.3.2 app added a native `batteryHealthState` capability (`stateOfHealth.ubeIndicator_pct`, "usable battery energy" %), but the app reads it through the Play-Integrity-walled CARIAD backend (403 for VW EU passenger cars). Test-cohort users on the volkswagen.de channel now run a self-limiting, fail-soft probe that checks whether the attestation-free vw.de reverse-proxy exposes the same value (ranked candidate subpaths; the raw response lands VIN/token-redacted in the shared diagnostics so the real shape is inspectable). Diagnostics-only — the State-of-Health sensor stays the user-nominal estimate until a real value is confirmed across cars, and there is no effect at all for users not opted into the test cohort.

## [3.0.3] - 2026-08-11 — vw.de session resilience + reporter fixes

### Added
- **New opt-in "test cohort" option — help unlock features for your car.** A new tick-box in the integration's options (off by default). When you turn it on, the integration may run experimental reads on your car — the first one being an attempt to recover **GPS location for Volkswagen EU cars** over the volkswagen.de channel — and, occasionally, show a dismissible notification asking you to share a diagnostics file so a new capability can be confirmed for your exact model. Everything shared is redacted automatically before it leaves your system (no VIN, GPS, tokens or e-mail), and turning the option back off stops the experiments and the notifications. It's how features like location get proven across the many different VW EU platforms without one person's single car having to represent them all. (#923)

### Fixed
- **The volkswagen.de channel now tells you when Volkswagen wants you to accept updated terms.** If VW puts up a terms-and-conditions wall during sign-in, the channel used to report a generic "session expired" and loop forever; it now says plainly to open volkswagen.de, accept the terms, and re-add the channel — the actual fix.
- **A volkswagen.de session that has just failed no longer overwrites your good saved cookies.** If a refresh fails mid-poll, the integration now keeps the last known-good cookies instead of saving the dead set over them, so a later restart can still resume silently instead of being stuck.
- **The volkswagen.de channel is more likely to survive a Home Assistant restart without asking you to re-add it.** Volkswagen reuses the same cookie names (its sign-in cookies) on *both* the login host and the website host with different values; the way the session was saved could collapse the two and overwrite the one that actually keeps you signed in — so after a restart the silent resume landed on the login page and asked for the e-mail code again. The save now keeps each cookie distinct per host, the host allow-list is an exact check instead of a loose text match, and the silent-resume step follows Volkswagen's longer sign-in redirect chain (it recently grew past the old limit). If the prompt still returns after this, the debug log now shows exactly which cookie/host is missing. Thanks @Arno-MA-73 for an exceptionally precise write-up that pinned the failure to the cookie round-trip.
- **Older Car-Net (MBB) cars get their volkswagen.de live-status readings back.** Warning-lights, lock/unlock history and service status are fetched with a per-car "data-centre" id that depends on the car's platform; the platform was matched too strictly, so a Car-Net car whose platform id carries a suffix was sent the wrong id and every one of those reads came back empty. It now matches the platform family, so those cars get the readings instead of nothing. The portal ships a `vehicleIsStandingStill` motion flag that was catalogued but never mapped; it now drives the existing *Driving* sensor (standing still ⇒ not driving) on cars that send it. Some vehicles don't send it at all — that's a data gap on VW's side, not a parsing one — so it's only surfaced when actually present. Thanks @zdravac, who found it in the data dictionary and confirmed which fields were and weren't reaching entities.
- **A Volkswagen EU car read over the volkswagen.de channel no longer falsely shows OFFLINE.** That channel (and the EU Data Act one) can't tell the integration whether the car is online, and an *unknown* online state was being treated as *offline* — so a car that was answering its reads perfectly well still reported OFFLINE. It now says OFFLINE only when the backend actually reports the car as offline, and otherwise leaves the state unknown rather than inventing one. Thanks @fight3, whose T-Roc showed this alongside the separate, still-open missing-GPS question in #923.
- **Volkswagen US/Canada cars no longer show a range of −1.** VW's US/Canada backend sends `cruiseRange: -1` as a "no value" marker; it was taken literally, so the Range entity read −1 — and because the field was then set, it also blocked the car's real (EV) range from filling in. A negative range is now treated as unknown, so the genuine range shows through instead. Thanks @fg877khkv8-maker, whose field-by-field raw capture on a 2023 ID.4 pinned it. (#1082)
- **The ABRP "upload on data change" automation no longer strands after a single failed upload (#1135).** The blueprint fired only when the "ABRP data changed" sensor turned on, and that sensor only clears once an upload actually succeeds — so if the one upload on that edge failed (a transient network / ABRP error), the sensor stayed on with no further trigger, and every later change silently stopped reaching ABRP. The blueprint now also re-checks every few minutes and re-sends whenever there is still unsent data, so a stuck state heals itself on the next tick. If you use this automation, re-import the updated blueprint to get the fix. Thanks @Fishermanjb for the precise diagnosis and the screenshots that pinned it.

### Internal
- **VW EU position reads now explain themselves in the debug log.** The CARIAD parking-position endpoint being closed for EU passenger cars (403) is logged at debug instead of being swallowed silently, so a "device_tracker stays unknown" report (#923) is diagnosable rather than looking like a dropped read.
- **The volkswagen.de channel logs which cookies it saves and restores — names, hosts and expiry only, never values.** When a resume works once and then dies ~20–30 seconds later on the next reload, the cookie that changed between the two is what tells us whether the session was overwritten on our side or expired on Volkswagen's; export and import now record that value-free list at debug level so it's diagnosable from one log. Thanks @Jradon001 for a repro precise to the second. (#966)

## [3.0.2] - 2026-08-10 — the reporter batch (cross-brand reliability)

A round of fixes driven entirely by reporter diagnostics in the hours after 3.0.0: two cross-brand sentinel screens (charging type and odometer), Volkswagen US climate + door-lock mapping, volkswagen.de sessions that finally survive a restart, a diagnosable EU data-request creation, and the Škoda push channel that can now actually start. Thank you to everyone who sent logs and diagnostics.

### Fixed
- **A battery level that shows up several times in one data export now settles on the value the export repeats, not a lone stale copy.** Some Volkswagen EU exports list the state of charge more than twice under one capture time with no per-point clock to separate them — for example 71 once and 60 twice. The integration now treats a value the export repeats as the real reading and keeps it, instead of possibly latching onto the single odd-one-out when your last known level happened to sit near it. A genuine two-way tie (each value once) is unchanged and still reconciles against your last known value. Thanks @PeterPrelo for the export that showed the three-way case.
- **Volkswagen US/Canada: the climate temperature and the door-lock state now show up.** Both were in the data the car sent all along. The target temperature arrives wrapped together with its unit (70 °F, for example) and the reader only understood a plain number, so it came out empty — the same wrapped shape this integration itself sends when you set the temperature. The lock state is reported per door on this firmware, in a form the reader mistook for a single value and then discarded, so the lock showed Unknown even with all four doors reporting locked. Thanks @fg877khkv8-maker for the diagnostics that showed exactly this.
- **Škoda push updates can actually start now.** The near-real-time push channel for Škoda needs the account id to subscribe, and the Škoda client never picked one up — so the channel quietly refused to start on every setup, without a single line in the log to say why. Škoda now captures that id the same way SEAT/CUPRA and VW US/CA do, and the skipped-setup case explains itself in the debug log. Push is still an opt-in beta and the Škoda handshake may yet need more work, but it can now be attempted at all. Thanks @thiete, who found this by reading the code.
- **Creating the EU data request explains itself when it fails — and now tries to recover.** The button that sets up the 15-minute data feed could fail with nothing useful in the log. The portal actually runs two separate sign-ins behind one address: one for reading your data, one for the page itself. Your session can be perfectly valid for reads while being signed out for the page — and the piece needed to create a request lives on the page side. The log now says plainly which of the two is missing, and the integration reloads the portal page once to try to restore it before giving up. Thanks @Jradon001, whose log made this findable.
- **volkswagen.de sessions now actually survive a restart.** Two more faults in how the saved session was restored: a sign-in cookie meant for the whole `vwgroup.io` family was being pinned to a single address, so other steps of the sign-in never received it; and the cookie that has to reach *both* sites was only ever arriving at one of them, because the same object was reused for both — meaning the part this was written to guarantee had silently never worked. Both are fixed, which should end the repeated re-add prompts for good.
- **The volkswagen.de channel no longer asks to be re-added over and over.** After signing in with the e-mail code, the channel could immediately report its session as expired — so the repair notification came straight back, and re-adding it produced the same result forever. The check that decides whether the session resumed was reading the whole callback address, so a perfectly good sign-in was mistaken for an expired one whenever that address happened to mention the login page. It now looks at where you actually landed. The session is also kept fresh while it is in use, instead of only being renewed after a read has already failed. Thanks @fight3, @shaarkys and @Jradon001 for the logs that made this findable.
- **A newly-discovered field the car sends now says which reading it belongs to.** The data portal packs about ten different opening states — doors, windows, sunroof, boot, bonnet — into one generic `open` field, told apart only by an internal id. The Vehicle Data Scout was showing just `open: true`, so every reporter filed an identical row that nobody could act on. The report now names that id, which is what lets a field like this actually get mapped. Thanks to everyone who kept sending these in.
- **The "update interval too short" message no longer asks you to raise an interval you already exceed.** A Škoda owner who had already gone up to 31 minutes kept being told to raise it to 30 minutes or more, which reads as nonsense. The suggestion now always steps up from the value you actually have configured. Thanks @starwarsfan.
- **The charging-type sensor no longer shows "invalid".** When the backend has no charge type to report it sends an `invalid` placeholder, and that was being shown as if it were a real charging type — so the history painted "invalid" bands, often for ten minutes at a time while the car sat parked and not charging. It's now dropped on **every brand**: Volkswagen, Audi, Škoda, SEAT, CUPRA, Bentley, whether the data comes from the brand backend or the EU data portal. The sensor simply stays clear until a real type comes back. Thanks @Lagaff86, whose Recorder audit of 90 occurrences pinned the pattern down — and who caught that the first attempt only covered one of the four data paths and left his own car unfixed.
- **The odometer no longer reads 429 million kilometres.** When the backend has no mileage to report it sends a placeholder — the largest value a 32-bit field can hold, scaled down by the field's unit to `429,496,729` — and that was surfaced as if it were a real reading, so the odometer jumped to an impossible number and stuck there. It's now recognised as the placeholder it is and screened out on **every brand and every data path** (EU data portal, brand backend and volkswagen.de alike), so an absurd value can't land — exactly the same one-guard-everywhere approach as the charging-type fix above. Thanks @dpk1987, whose diagnostics gave the exact figure that pinned it as a sentinel.

### Internal
- **The data-dictionary watcher no longer opens an empty pull request when Volkswagen only re-publishes the source page.** The automation that watches the EU-Data-Act dictionary was treating any change to the source page as a new dictionary, even a cosmetic re-deploy — which produced a pull request whose only real difference was the date. It now regenerates only when the dictionary's *version* or download links actually change (the PDFs are versioned in their own filename), and treats a same-version page change as noise. No user-facing effect.

## [3.0.1] - 2026-08-09 — Škoda login + diagnostics-redaction hotfix

Two quick fixes on the heels of 3.0.0: Škoda's passwordless login (which Volkswagen switched off on their side), and a VIN that could slip through the diagnostics redaction.

### Security
- **The "Download diagnostics" export no longer leaks your VIN when the car's data uses the VIN as a section key.** The auto-redaction masked VINs that appear as field *values*, but not when a VIN was used as a dictionary *key* (for example under `data_act_identifiers`) — so it could still show up in plain text in a file people attach to public issues. Dictionary keys are now masked too (VIN and tokens; harmless UUID keys are kept for troubleshooting). If you downloaded and attached a diagnostics file from 3.0.0, it's worth a look. Thanks @fight3 and @PeterPrelo, who both spotted this and hand-redacted their VIN before posting.

### Fixed
- **Škoda's passwordless (QR) login no longer dead-ends — it points you to email + password instead.** Volkswagen switched off the device-code (QR) login for Škoda on their side, so the QR screen kept reloading with nothing to scan. Škoda is no longer offered that path: it now signs in with your MyŠkoda email and password — a separate login that VW's change doesn't affect — and if you somehow still land on the old QR option you get a clear message telling you exactly where to go instead of a silent reload. Existing Škoda setups that were created via QR move over to email + password automatically the next time they ask you to sign in, so nothing gets stuck. Audi, SEAT and CUPRA keep their QR login. Thanks to the Škoda owners who flagged this within hours of the 3.0.0 release.

> If VW Group Connect is worth something to you, please consider **[sponsoring continued maintenance](https://github.com/sponsors/its-me-prash)**. 🙏

---

## [3.0.0] - 2026-08-08 — "Bazinga" (Škoda Wave)

A big Škoda-focused release: your car's own in-car assistant now lives inside Home Assistant, alongside a wave of new Škoda commands and read-only sensors — every field read straight out of the current MyŠkoda app so the names match what your car actually sends. It also carries the EU Data Act feed fixes previously staged as 2.30.3 (see below).

### Added
- **"Laura", the MyŠkoda in-car assistant, now works from Home Assistant.** Ask it about range, charging or a trip and the answer comes back into Home Assistant — as a service you can call, and as a tool that any conversation agent (the built-in Assist, or OpenAI / Anthropic / Google / Ollama) can decide to use on its own. It is read-only advice and never drives the car. When it plans a route, the structured stops come back with it, so a route-to-car automation can read the coordinates directly instead of parsing text.
- **Send a destination to a Škoda's navigation.** The "send destination" service now works on Škoda as well as SEAT/CUPRA, so an automation — or Laura — can push where you're going straight to the car.
- **Per-location charging target on Škoda.** Set a different target charge level for a specific charging profile / location, the same idea Volkswagen and Audi already had.
- **Camping mode and auto-unlock-when-charged, as switches.** Turn Škoda's camping/sleep mode on and off, and choose whether the charging plug releases automatically once charging finishes.
- **Seat-heating control on Škoda.**
- **A batch of read-only Škoda sensors.** Your last fill-up (fuel, amount, cost, station), your current paid-parking session (where, cost, whether it is still running), service reminders (inspection, seasonal tyre change, first-aid kit, tyre-repair kit), departure timers, and the preferred charge mode. There is nothing to set — they simply appear when your account has the data.
- **Your Škoda data-sharing consents are visible**, and if the mandatory service agreement is missing you get a repair prompt so you know to accept it in the app.
- **Help build support for your own car, straight from Home Assistant.** When the integration spots data your car sends that it doesn't map yet, the "Vehicle Data Scout" repair now says plainly that forwarding your report is what lets us build support for it. Your **Download diagnostics** file now includes the full API response with those new fields in context — aggressively redacted, with VINs, GPS, tokens, e-mails and licence plates removed — so attaching it to a GitHub issue is all it takes to turn a new field into an entity. Volkswagen US/Canada responses and the `volkswagen.de` web-channel responses are captured for this now too, which is what we need to sort out the US read-path and the vw.de location/login reports.

### Fixed
- **Škoda now shows the right model and model year**, read from the field the app actually uses.
- **Honk-and-flash on Škoda now includes the car's position, which the backend requires.** If the location isn't known yet it tells you to wake or refresh the car and try again, instead of silently failing on a rejected request.
- **Your current paid-parking session now actually shows up.** The parking endpoint returns a single session rather than a list, a shape the reader didn't recognise, so the sensors never appeared even when there was a session.
- **A round of Škoda command fixes** read out of the current app, so lock/unlock, flash and the climate/charge commands use the routes and fields the car expects.
- **Charging power and rate now drop to zero the moment a charge stops (#1090).** Some cars — the Audi e-tron GT for one — keep reporting the last charging power for several minutes after charging has actually finished, and the integration showed that stale value and let it linger in your history. It now reads zero as soon as charging is definitively over, while still showing the real figure during normal and conservation charging. Thanks @Lagaff86 for the exact e-tron GT timeline — a forced refresh that still returned the stale value — that pinned it down.
- **Volkswagen EU battery level no longer flips between two values on the data portal (#465).** On some cars the portal's data log carries the same battery reading more than once with no reliable per-point time of its own, and because Volkswagen re-orders that log between exports, a stale reading could inherit a newer-looking marker and out-rank the real one — so the state of charge oscillated (for example 57% vs 81% while the car actually sat near 80%). The integration now treats those order-dependent timestamps as unreliable and reconciles the reading against your last known value, so it settles on the plausible one instead of flipping. Thanks @Arno-MA-73 for pinning the exact mechanism.
- **State of charge no longer sticks on a stale value when the data export lists it twice (#1088).** Some Volkswagen EU exports — seen on the ID.7 and e-Golf — carry the same battery field twice with different values and no timestamp to tell them apart, and the integration could pick the older one by position. It now flags the disagreement so the reading is reconciled against your last known value instead of guessing by order. Thanks @PeterPrelo for the report and the two disagreeing values that showed the field was duplicated.
- **Audi US accounts can now discover their vehicles after QR login (#13).** The login itself worked, but the integration sent the US access token to the EMEA vehicle service, which rejected it (`401 expected user token`). US vehicle requests now route through the regional host the myAudi market configuration specifies; Canada is unchanged. Thanks @pouwerkerk for the diagnosis, the fix, and a live test on a 2026 Q5.

### Translations
- All the new sensors, switches, services and repairs are translated across all twelve languages (Czech, Danish, German, English, Spanish, Finnish, French, Italian, Norwegian, Dutch, Polish, Swedish).

### Thanks
- **The new Škoda switches and sensors are built on fields that owners surfaced through the Vehicle Data Scout.** Camping mode came from @MavericklCS and @whaak58, with @tritanium73, @microcens, @derolli1976, @ichwars and @mk-lp; auto-unlock-when-charged, seat heating and the preferred charge mode from @whaak58 (#143); and the departure timers and service-reminder fields from @tritanium73 (#107), with @MavericklCS (#116), @Chr1sDub (#130) and @christianmhz (#133). Your reports are what turn a field the car sends into an entity here.
- A community code contribution from **@pouwerkerk** (Audi US vehicle-discovery routing), plus every reporter, tester and diagnostic named above — this release is built on their work. If VW Group Connect is worth something to you, please consider **[sponsoring continued maintenance](https://github.com/sponsors/its-me-prash)**. 🙏

---

## [2.30.3] - 2026-08-07

### Added
- **Optional diagnostic archive of raw EU Data Act datasets.** A new advanced option keeps the last few raw dataset files the portal delivers on disk, per vehicle and size-capped, so if a value ever reads wrong or goes missing it can be reproduced from the exact data your car sent, instead of asking you to extract and share it by hand. It is off by default and only does anything on the EU Data Act portal channel — the files contain your location, VIN and telemetry, so you turn it on knowingly, and only while troubleshooting. Your recorded values already survive a restart without this; it exists purely to make problems reproducible.

### Fixed
- **Service and oil-change "distance/time to service" no longer shows a wrong "overdue" on some cars.** The EU Data Act portal reports the remaining interval with an inconsistent sign: most cars send it as a negative number, but some send it already positive. The integration negated it unconditionally, so the positive-sign cars flipped to a false "overdue". It now normalises to a positive countdown either way.
- **State of charge now reads on Enyaq and e-up cars that report it under a bespoke field.** Those cars ship the traction SoC under a `currentSoc` field that the mapper did not recognise, so the battery level stayed empty on the read-only portal channel; it is recognised now.
- **The EU Data Act 15-minute feed is more reliable to set up (#957, #966).** When the integration creates the continuous data request for you, two things could leave you with no feed and no error. It asked for an "unlimited" request but attached a contradictory ten-year end date, a shape the portal never produces itself, and it trusted the portal's "created" response without checking the request actually landed. Now the unlimited request is created the way the portal's own website does it (no end date), and after creating one the integration reads it back to confirm it exists, falling back to a one-month request if it does not, instead of going quiet for hours. Thanks @Ra72xx and @PeterSchroederPaderborn for the diagnosis.
- **The 15-minute feed no longer stays stuck on "no data request yet" when one actually exists (#957, #966).** The portal returns your active request as a list, but the poll only recognised it in one other shape, so on some accounts every poll reported "no data-request set up yet" even though the feed was live — and worse, the setup path and the poll path could disagree about the very same request. Both now share one reader, so the list shape is always recognised. As a bonus, if you delete and re-create the request in the portal, the next poll picks up the new one on its own without a restart.

## [2.30.2] - 2026-08-07

### Fixed
- **Battery level no longer flips between two values on the EU Data Act portal (#465).** Some cars report the state of charge under two different fields that do not always agree, a fresh reading and a stale one, and the integration picked between them by a fixed priority order rather than by which one was newer. So the battery level could bounce between, for example, 57% and 81% while the real value sat steady near 80%. It now picks the freshest reading when they disagree (ties keep the previous order, so nothing changes for the normal case), and logs the candidates at debug level so a mismatch is traceable. Thanks @Arno-MA-73 for reading the mapper and pinning the exact cause.

## [2.30.1] - 2026-08-07

### Fixed
- **Škoda (and any car using the data portal as an extra channel) now tells you when it needs new terms accepted, instead of just going quiet (#465, #1027).** When the data portal sign-in lands on Volkswagen Group's updated terms-of-use page, that is a required service agreement, separate from marketing consent. If the portal was your main sign-in this already showed up as a repair, but if it was a secondary channel on top of a working one, the terms page was hit later, during normal polling, and only ended up in the log with no repair, so there was no hint anything needed doing. It now raises the same "accept terms and conditions" repair with the one-click accept link in that case too, and clears itself the moment the next sign-in gets through, so accepting the terms is enough and you do not have to reload anything. Thanks @foobarth for the logs that pinned it down.

## [2.30.0] - 2026-08-07

### Added
- **Per-location charging targets now work on Volkswagen and Audi, not just SEAT and CUPRA (#442).** If you set a different charge limit for "Home", "Work" and so on in the app, the sensor that shows the active profile's target SoC now fills in for VW and Audi too: it reads the full charging-profile list and follows the profile your car is parked at, the same way SEAT and CUPRA already did. The exact field names were read out of the current We Connect app so they match what your car actually sends, and unknown shapes are skipped rather than guessed. Thanks @nekas123 for the request and the patience.
- **Optional battery State of Health sensor.** Volkswagen never reports a battery-health figure and the official app does not calculate one either, so this cannot be guessed from the data. If you enter your car's nameplate net battery capacity (kWh) in the integration options, a new "Battery health" sensor shows the current maximum capacity as a percentage of that nameplate. It is disabled by default and does nothing until you supply the capacity; a wrong-sized capacity for one car on a multi-car account is simply ignored rather than shown as a wrong number.
- **You can now see when two portal readings disagreed.** When the data portal delivers two samples stamped with the same capture time but different values for a field, the "Data source" diagnostic sensor now lists which field was contested and the values that tied, so a value that briefly jumps around is explainable instead of mysterious.

### Fixed
- **Škoda no longer goes quiet and wrongly tells you to re-login (#1078).** Škoda hands out short-lived tokens, so at the default 10-minute interval nearly every poll had to refresh the token, which tripped the safety limit that stops us hammering the account — and then the integration told you to reauthenticate, which does not help because nothing is wrong with your login. Now it says what actually fixes it: raise your update interval (30 minutes is Škoda's own recommendation), shown as a repair you can act on that clears itself the moment polling recovers. Thanks @foobarth.

### Translations
- **Six languages that were half in English are now fully translated.** Czech, Spanish, French, Dutch, Polish and Swedish had fallen back to English for a large chunk of the setup screens, options, repairs and service descriptions; those are now translated, alongside Danish, German, Finnish, Italian and Norwegian which were already complete.

## [2.29.6] - 2026-08-07

### Fixed
- **Volkswagen Canada now shows its data, not just logs in (#990).** After Canadian accounts could sign in again in 2.29.5, the values still stayed empty: the Canadian backend wraps every response in an extra layer that the parser never unwrapped, so charge, location, range and doors all came back blank. That layer is now unwrapped, a charging Canadian car is recognised as charging, the door-lock state reads from the field Canada actually uses, and an electric car that reports an empty fuel tank is no longer mistaken for a petrol car. Volkswagen US is untouched. Thanks to @vrouleau for tracking it down and testing it against a real Canadian ID.4.
- **Charging power and charging speed read the right number on more cars (#1022, #717, #1002, #931).** The data portal sends these two values in two different encodings, and until now we guessed which one from the number itself, which broke on cars that send a plain value that happens to be a round number (an ID.7 charging at 10.4 kW was shown as 1 kW). We now read the encoding from the field's own dictionary entry instead of guessing, so both the cars that report already in kW or km per hour and the cars that report in tenths come out right. Thanks to @mce2024, @RaAdNe and @SparkyDan555 for the raw values that made it testable.
- **A charging car is no longer shown as "not charging" (#1002, #1022).** The live 15-minute portal feed spells the charging state differently from the one-time export, and we only recognised the second spelling, so ID.5 and ID.7 owners saw "not charging" while the car was plugged in and drawing power. Both spellings are recognised now.

### Changed
- **One internal portal field stops appearing as an undiscovered field.** A capabilities-status queue counter on Audi (a list of in-flight requests, not a vehicle reading) was reported as a new field on every poll; it is now recognised as the plumbing it is, with no sensor added. Thanks @neuhausf.

## [2.29.5] - 2026-08-06

> 🎉 **Release number 300.** Three hundred releases on from a small community project, thanks to everyone who filed a bug, ran a capture on their own car, tested a fix, corrected a translation or sent a log. This integration exists because of you, and it stays free. It is a one-person project kept alive against a moving target, so if it is worth something to you, [GitHub Sponsors](https://github.com/sponsors/its-me-prash) helps keep the reverse-engineering going. Here is to the next three hundred.

### Fixed
- **Volkswagen Canada login that failed with a server error now works (#990, #659, #915).** Canadian accounts were being routed to the US login server with the US app client, and Volkswagen answered that mismatch with a server error at the password step even though the official app worked fine. Canada now logs in on its own server with its own app client, exactly the way the US already does. Volkswagen US is untouched. Thanks to @vrouleau and @shaunadam for running it on real Canadian accounts and sending the logs that pinned it down.
- **Headlight flash on Volkswagen US and Canada sends the request the car understands (#659).** Flash had gone from one wrong answer to the next as we narrowed it down: first the wrong request type, then, once that was fixed, a server error because the payload itself was wrong. The value we sent was copied from the European app and does not exist in North America. Read out of the current app, the real request is two switches, a horn flag and a lights flag, exactly like lock is a single lock switch. Flash now sends lights on and horn off, and the honk option that was quietly ignored before now actually sounds the horn. Thanks to @chrisspatrickk1-sys for the testing and the remote-start research.
- **A car no longer blanks out its charge, mileage and range after a command when the data portal briefly returns nothing (#702).** A refresh runs after every command, and an empty portal response was overwriting good values with blanks that then stuck across a restart. It now keeps the last known values when the portal has nothing new, the same protection the scheduled poll already had.
- **A SEAT or CUPRA server error is no longer mistaken for a blocked-device error.** A non-403 failure whose text merely contained "403" somewhere (a trace id, a timestamp) was being counted toward a device-attestation block and could raise a false repair notice. The check now reads the real status code.
- **Charge, range and mileage now appear on more cars that report only through the EU Data Act portal.** Some cars label these values by an internal id instead of a name; those ids are now recognised as a last resort, so a portal-only car (for example a carnet-retired ID.x) is no longer left blank. It never overrides a real named value.
- **Two entity names were corrected in German and Dutch.** The German downhill-consumption label contradicted itself, and two Dutch labels used a German word and the wrong term for monthly distance.

### Changed
- **The Volkswagen US and Canada capture script can now map which features a specific car is actually allowed (#659).** The app checks each remote action against a per-car permission before offering it, the North American counterpart to the licence check the European cars use, with the same "not permitted by licence or configuration" wording. The capture script now reads those checks for climate, locks, flash, charging, wake and engine start, so a single run tells us which buttons a car is entitled to and which sit behind a subscription. It also probes a few feature groups the earlier look missed entirely: trip statistics, geofence and curfew and speed and valet alerts, and over-the-air update history. Still read-only, still masked.

## [2.29.4] - 2026-08-05

### Changed
- **The Volkswagen US and Canada capture script now reaches the parts of the app we have never seen (#659).** The official app calls a good deal more than we read: a vehicle-health service, public charging sessions, a message centre, an activity feed, trips, send-to-car and more. We have never seen a single response from any of them, so nothing can be built on guesses. The capture script an owner can run now probes all of them in one go, and two of its existing checks were sending truncated addresses that could only fail. Every request is a read, and the output masks your VIN, identifiers, locations, names and any message text before you paste it anywhere. Waking the car for the health check is a separate opt-in switch, off by default.
- **Three vehicle-health probes for US and Canada were removed.** They pointed at an address that does not exist on the North American backend, sat on a client that could never run them, and were registered under a name that never matched, so nothing ever ran while the code looked as though it did.

### Fixed
- **Volkswagen US and Canada commands report the car's real answer, not just "sent" (#659).** A remote command is accepted first and carried out a moment later, so a command the car quietly refused still looked successful here. While looking into remote start we noticed the app confirms the outcome afterwards, which we were not doing. Lock, unlock, flash and charge now wait for the car's actual result and surface a refusal as an error instead of a false success. The wait is short and best effort, so a slow or unavailable check never turns a command that worked into a reported failure.

## [2.29.3] - 2026-08-05

### Fixed
- **Headlight flash on Volkswagen US and Canada uses the right request type (#659).** With v2.29.2 a North American owner confirmed lock and unlock now work, but flash still bounced because it was sent as the wrong request type, the same problem lock had. It now matches the shape the app uses. (The exact flash-versus-honk body is still a best guess; if a car reports a different error now, that is the next thing to pin.)
- **An expired portal data feed is renewed instead of quietly staying dead (#465).** The data portal keeps old requests in its list even after they lapse, and we adopted the first one we found without checking whether it was still live. So once a request created with the older one-month duration ran out, about four weeks after setup, we kept pointing at the dead one and never asked for a fresh feed: the sensors just stopped moving while everything looked healthy. We now skip a request whose window has ended and start a new feed in its place. A no-expiry request keeps its far-future end date and is never mistaken for a dead one.

## [2.29.2] - 2026-08-05

### Fixed
- **The connector-lock status shows on Volkswagen US and Canada.** The charging read already carried whether the charge cable is latched, but that one field was never picked up, so the connector-lock sensor stayed blank on those cars. It is read now.
- **A throttled Volkswagen North America sign-in is no longer mistaken for a wrong password.** When the North American login is rate-limited it answers with an ordinary-looking page instead of a clear "too many attempts", so the login read it as bad credentials and prompted a re-login — which only piled on more attempts. It is recognised as the rate-limit it is now, and the integration backs off instead.
- **Minutes-until-ready fills in for Volkswagen North America climate.** The remaining pre-conditioning time was already a sensor for other brands; it now populates for VW US/CA too.

### Changed
- **Every Volkswagen US and Canada remote command was rewritten to the shape the app actually sends (#659, #1059).** Lock, unlock, wake, flash, charge start/stop, the charge target, climate start/stop and temperature, window heating and the departure timer were all being sent in a form the server refused: a `405 Method Not Allowed` on lock, and a `403 User Not Authorized` on the rest. Both are now explained: the lock endpoint wants a different request type than we used, and since late July North America requires every command to be signed with a per-car token instead of the plain login. They now go out the way the official app sends them, with that token. Two North American owners reported the exact `405` and `403` codes, which is what confirms the direction, though a note back on whether lock and unlock now actually actuate is still the thing that closes it out.

## [2.29.1] - 2026-08-05

### Fixed
- **Volkswagen US and Canada could not be added since 30 July (#1012).** Sign-in itself was working: it ran through to an authorization code and only the step that trades that code for a token was refused, with a 401 that read like a wrong password but was not one. On 30 July VW's North American token service began requiring a field that was not there before, and every request without it now bounces. That field is sent now, on both the initial token exchange and the refresh, so an affected account adds and stays signed in. Confirmed by three owners, whose reports all point at the same 04:00 UTC cut-over. Thanks to @briancmoses, @chrisspatrickk1-sys and @savabg (see [CONTRIBUTORS.md](CONTRIBUTORS.md)).
- **Porsche login follows the Auth0 resume step instead of giving up (experimental).** In Auth0's identifier-first flow the password step does not redirect straight to the app callback: it returns a resume URL that has to be followed before the authorization code appears. The login required the callback immediately, so it always ended in "wrong credentials or captcha" even when the credentials were right, a failure of our own regardless of any app migration. It now follows the resume hop (relative or absolute, bounded so it cannot loop) through to the code. Porsche stays experimental and still needs a Porsche owner to confirm the full login end to end.
- **Ten of the eleven translations were missing the companion-channel strings.** Home Assistant does not fall back to English for a custom integration, so a key that exists only in English renders as the raw key or as nothing at all. The twelve strings added with the companion channel and the export-file import had reached German only, which left the add-on checkbox, its error message, the two companion option toggles and the three import error messages blank for everyone running Home Assistant in French, Spanish, Italian, Dutch, Polish, Czech, Swedish, Danish, Norwegian or Finnish. All twelve are translated now, and a test fails the build if a language ever falls behind again.
- **The companion channel could not read the range off the Volkswagen app.** The app narrates its units in words, so the overview tile reads "Batteriereichweite: 253 Kilometer", while the selector required the symbol "km". On those cars the channel reported itself healthy and read no range at all. Grounded in two accessibility dumps from We Connect 4.2.1, an ID.4 and an e-up. Thanks to @kgroshert for the dumps.
- **A reading of zero no longer makes a sensor disappear.** The parsers read the same quantity under several field names and took whichever answered, which quietly skipped a legitimate zero. That is the value that matters most: a service interval of 0 km means due now, an empty tank reports 0 km of range, a flat battery reports 0 %, and 0 degrees is an ordinary winter morning. Each of those arrived as "no reading at all", so with hide-empty-entities on the sensor vanished at the moment it was worth looking at. Worse, the combustion and battery capability flags were derived from the same collapsed value, so a tank showing 0 km made the car count as not-a-combustion-car and took every combustion entity with it. Affects SEAT and CUPRA most, plus Skoda ranges, VW US/CA odometer and charge power, and the VW EU brake-service intervals.

### Changed
- **An identity token from the portal export no longer enters field discovery.** The export carries `idp_idt`, which identifies the account holder rather than anything about the car, and it was reaching the Vehicle Data Scout as an unmapped field. Only the token masker kept its value out of a public issue. It is now withheld from discovery entirely, so it can never end up in an entity attribute, a backup or a diagnostics download. This is a deliberate single exception to the rule that every discovered field stays visible until mapped, it is scoped to one named field, and each withholding is logged.

## [2.29.0] - 2026-08-04

### Fixed
- **A charge level that flipped between two numbers now settles (#957, #1002).** The portal export sometimes carries the same reading twice inside one snapshot with different values and nothing to tell them apart, so the sensor jumped between them on a car that was neither driven nor charged, and the charge target did the same. Deciding inside the file does not work, because the obvious tie-breaker is duplicated too. The integration now compares the candidates against the last reading it already had and keeps the one that fits, so a car that is genuinely charging is still followed and only the impossible jump is dropped. Nothing changes on a poll where the export was unambiguous.
- **Charge power and charge rate are no longer a tenth of the truth on some cars (#1022, #1002).** The feed uses two encodings for the same number and we only understood one of them, so cars sending the plain value had it divided by ten: 10.4 kW showed as 1.0. Both encodings are now recognised.
- **The terms-and-conditions message points at the right place (#1027, #465).** Two Audi owners were stuck at a consent page after having accepted everything in the brand app, because the data portal asks separately. The message named only the app, so they went looking in the wrong place. It now names both and says that accepting in one does not cover the other.
- **Queued climate-timer changes are counted on Audi firmware too (#1030).** That firmware ships the same queue under a different name, so the sensor stayed empty.
- **The portal feed no longer expires after four weeks.** Every feed was created with a one-month duration, so roughly four weeks after setup the data quietly stopped: no error, no warning, just sensors that stopped moving while the integration reported itself healthy. The feed is now requested without an expiry date. If a portal ever refuses that, we still ask for the month rather than end up with no feed at all.

### Added
- **Battery calibration sensors (#1020).** Cars that ask for a high-voltage battery calibration now report it: the request and its two escalation steps, the method being asked for, and whether an attempt failed. Seven diagnostic sensors, off by default, in all twelve languages.

## [2.28.0] - 2026-08-01

### Added
- **The vehicle-signal service can now choose duration and horn (#1009).** The manufacturer app's signal screen lets you pick how long the car signals and whether the horn joins in, and `flash_lights` only ever sent a fixed ten-second flash. It now takes an optional duration (10, 20 or 30 seconds) and signal type (lights only, or horn and lights). Leaving both out does exactly what it did before, so nothing changes for existing automations. Volkswagen and Audi honour both settings and Skoda honours the horn; on the remaining brands the values are not documented in their apps, so they are accepted and ignored rather than guessed at. Thanks to @Kimmy42-J for the request.

## [2.27.0] - 2026-08-01

### Added
- **The companion channel can now run through the ADB Bridge add-on (#968).** On a phone running Android 11 or newer, the only way in is wireless debugging, which needs a TLS handshake and a pairing step that the built-in connection cannot do. It reaches the phone and fails, which is as far as most people got. The [ADB Bridge add-on](https://github.com/its-me-prash/vwgroup-app-adb-bridge) bundles the real tooling and does the pairing, and the integration can now talk to it instead: tick "Connect through the ADB Bridge add-on" when you add the companion channel, and give the add-on's address instead of the phone's. Everything after that is unchanged, including the read-only quarantine, so an older phone still connects directly exactly as before. Thanks to @plainmad for testing the add-on and reporting precisely where it stopped.

## [2.26.3] - 2026-08-01

### Fixed
- **A backend hiccup no longer makes every entity look broken.** The integration has always been meant to keep showing a car's last known values through a short outage, with the "last updated" timestamp telling you how old they are. That tolerance never actually applied when the whole poll failed, which on a single-car account is any brief error at all, so entities went unavailable immediately instead. They now stay visible with their last known values, exactly as intended, and still disappear once the data is genuinely too old.
- **A sensor whose value changes type no longer breaks.** When a manufacturer turns a number into a text value (CUPRA once changed the max charge current to "maximum"/"reduced"), the affected sensor used to break outright. Each case was patched individually after someone had already hit it. Any sensor that expects a number now simply reports unknown and logs why, so one changed field cannot take an entity down.
- **A brief portal error during startup no longer costs you the setup.** Listing your cars gave up on the first server error, while the very same call already retried three times if the connection timed out instead. Both are now retried the same way. If the portal is genuinely down the result is unchanged.

### Added
- **A charge target for cars that only report a battery-care limit.** Some cars (the Audi Q4 e-tron is the known one) send a battery-care charge ceiling and no separate charge target, so the target sensor stayed empty even though the car does have a limit. That ceiling now fills the target when nothing else provides one, and it is still shown separately as before.

## [2.26.2] - 2026-08-01

### Fixed
- **The "Visit" link on the car's device page works again (#1001).** The Volkswagen, Skoda and SEAT links pointed at owner pages those brands have since renamed, so the button led to a 404. All brand links were re-checked and the dead ones now point at pages that exist.
- **The saved volkswagen.de session no longer sends one host the wrong cookie.** VW reuses a few cookie names across its two sign-in hosts with different values for each. Restoring the saved session pushed every cookie to both hosts, so for those names whichever one was written last won on both and one host always got the wrong value. Names that differ per host are now restored only to the host they came from; everything else, including the single sign-on cookie that makes the silent resume work, is unchanged.
- **SEAT and CUPRA doors could still read "open" on a locked car.** When the car reports locked but the (sometimes stale) door positions still say open, the integration trusts the lock and forces the doors closed. That safeguard was written before the v2.23.2 open/closed correction and was missed by it, so it forced them to the wrong value and every per-door sensor showed "Open" on a locked car. It now writes closed, as its own log line always claimed. A second, dormant path that reads the older flat door format had the same leftover inversion and is fixed too, and the tests for both now drive the real parser instead of a copy of the logic, which is why this went unnoticed for so long.
- **Resuming the extra volkswagen.de session no longer gives up on a longer sign-in chain.** The silent resume sends exactly the same request as the interactive login, but it allowed only half as many redirect hops and reported the resulting failure as a generic, redacted error. If the sign-in chain gets longer at VW's end, the resume would fail while a fresh login still worked, and the log would not say why. It now uses the same budget as the login and reports a clear "re-authentication needed" instead.

## [2.26.1] - 2026-07-29

### Fixed
- **Volkswagen Canada sign-in reaches the right host again (#990, #915).** v2.26.0 sent Canada to its own regional host (ca00) for everything, including the login. That was half right: the vehicle data does live on ca00, but the login does not, and ca00 has no working authorize endpoint, so Canadian setup started failing at the login step with an HTTP 400 (before v2.26.0 it got past the login and failed later with a 500). A Canadian owner confirmed the official app signs in on the shared North America identity host, so the login now goes back there (as it did in 2.25.0) while only the vehicle data stays on ca00. Thanks to @vrouleau for the capture and the details.

## [2.26.0] - 2026-07-27

> This release is about the companion (ADB) channel from 2.25.0, and it changes nothing for anyone not using it. Two things stand out: the Volkswagen screen-reading is now grounded against a real, independently verified reference instead of our own guesses, and CUPRA reads real data for the first time thanks to a contributor's screen dump. Command sending on the companion channel is paused for now — see below.

### Changed

- **Volkswagen companion reads are re-grounded against a verified reference.** The words we looked for on screen (state of charge, range, charge target) were our best guess and did not actually match what the We Connect app shows. They are now aligned with a real-device reference, so the values read reliably. The old wording is kept as a fallback, so nothing that already worked stops working.
- **CUPRA now reads real data.** Thanks to a screen dump a CUPRA owner shared (#968), the app's actual layout is known: it shows the numbers as bare values without the labels we were looking for, so the previous version read nothing. It now reads charge, range, lock state and engine state, plus how long ago the car last synced. Still read-only until an owner confirms the command screens.

### Added

- **Charge target on Volkswagen (opt-in).** The charge target, live power and remaining time live on a detail screen you have to open, so reading them means the integration briefly navigates there in the app and comes back. Because that taps the phone, it is off by default and runs at most every 15 minutes when on. Turn it on under the companion entry's options once you have confirmed it behaves on your phone.
- **Wake screen to poll, sleep after (opt-in) (#974).** A new companion option that wakes the phone's display for the read and puts it back to sleep afterwards, so a locked or sleeping phone shows the app without you having to keep the screen on permanently.
- **"Reset companion connection" button.** Clears a stuck back-off (after a failure run or an app rate-limit) and reads again immediately, instead of waiting the back-off out.
- **Bidirectional (V2G) charging usage sensors (#981).** For cars that support vehicle-to-grid, eight new diagnostic sensors surface the usage accounting the car keeps: energy dispensed, charge cycles, operating hours and quota, each with its limit. Disabled by default. Values are shown as-is (the data source does not state a unit, so none is invented).
- **Import a data-export ZIP you downloaded yourself (#702).** If a car is not enrolled in the EU Data Act portal, the connector has nothing to fetch for it, so the existing import brought nothing back. A new service, `import_export_file`, lets you point the connector at the ZIP you downloaded from the VW data portal by hand: it parses the file exactly the way the portal path does and fills in only the empty values, never overwriting live data. Put the file in your Home Assistant config folder (or another allowed folder) and give the service its name plus the VIN.

### Fixed

- **Setting up the companion channel on a modern phone now tells you what to do.** On an Android 11+ phone the direct ADB connection fails with a cryptic error, because that phone uses wireless debugging (TLS + pairing) which the built-in connection cannot speak. Instead of a generic "could not connect", the setup now recognises that case and points you at the companion add-on (older phones still connect directly). The setup screen says the same.
- **The off-peak charge reason is read again on cars that report it in a sub-block (#978).** Some cars nest `profile_charge_reason` inside a `charging_state_report` container; that spelling was being flagged as an unknown field instead of filling the existing sensor. Now handled.
- **A companion rate-limit now survives a restart.** If the app shows a "too many requests" screen the channel backs off for hours, and that back-off is now remembered across a Home Assistant restart — a real account lockout should not be cleared just by restarting the way a brief network blip is.
- **Volkswagen Canada now uses its own regional backend (#915).** Canada was being sent to the US host, which returns HTTP 500 for a Canadian car. A Canadian owner captured the official app and it talks to the Canada host (`ca00`) directly — the host is built from the country code at runtime, so it never showed up in a static scan of the app, which is why we had it pointed at the US host. Canada now goes to its own host. (If your Canada login still fails after this, a fresh log would show what the Canada backend wants next — it could not be worse than the 500 it returned before.)
- **Setup no longer hangs on the best-effort prefetches (#909).** After reading your cars, the integration warms a few caches (capabilities, static info, command availability) and kicks off the Data Act data request. These are meant not to block setup, but they were being awaited during it, so a slow or flaky backend could leave the entry stuck on "still setting up" for a long time (and Home Assistant kept retrying). They now run in the background once setup has returned; entities appear right away from the restored snapshot and these fill in a moment later.
- **The map marker no longer disappears when the volkswagen.de sign-in expires (#984).** On a car whose GPS comes only from the extra volkswagen.de channel, an expired session meant there were no coordinates, so the tracker was never created — and an existing one eventually got cleaned up by Home Assistant, breaking maps and automations that pointed at it. The tracker is now kept whenever that channel is set up: it simply reads unavailable while the session is expired and fills back in once you sign in again, instead of vanishing.

> **Note on Volkswagen commands (climate / charge start-stop).** These are paused on the companion channel in this release. They never actually worked: the app needs a two-step tap (open a tile, then press the button on the detail screen) that the old code did not do, so a command could only ever fail silently. Rather than ship buttons that do nothing, the companion Volkswagen entry is read-only for now; the command path returns once the two-step flow is confirmed on a real car. The network command paths (QR / portal / MBB) are unaffected.

## [2.25.0] - 2026-07-27

> The companion (ADB) channel that was briefly pre-released as 3.0.0a1 ships here in the stable line instead. It is still opt-in and experimental, and it changes nothing unless you set it up: if you do not pick it in the hub menu, the integration behaves exactly like 2.24.2.

### Added

- **Companion phone (ADB) channel — experimental, opt-in.** A fourth source in the hub menu at the start of setup, next to the QR login, the portal login, and MBB. It drives the official manufacturer app on a spare Android phone over ADB and reads the values off the screen, so it works as a last-resort two-way path on cars where the network side is read-only. There is no separate login and no credentials are stored: the phone is already signed in, nothing is rooted, and no app tokens are read. The integration only reads the screen and taps buttons.
  - **Volkswagen is verified** (built and tested against the We Connect app 4.2.1): it reads state of charge, range and charging state, and can start/stop climate and charging.
  - **Audi, Škoda, SEAT and CUPRA ship read-only for now.** The structure is there, but their on-screen maps are not yet confirmed against a real device, so they read what they can and refuse to tap a button rather than risk hitting the wrong control. They switch to two-way once a tester with that car confirms the screen map.
  - Safety built in: a write quarantine that disables taps whenever the app version on the phone differs from the one a preset was verified against (reads keep working), and a cooldown after a connection failure so a sleeping phone never turns into an error storm.
  - Needs a spare Android phone signed into the brand app with ADB over Wi-Fi, and the app language set to German or English. See the tracking issue to set it up and to volunteer as a tester for the non-VW brands.

### Fixed

- **The extra volkswagen.de channel no longer loses its session on every restart (#966, #632).** After you added the channel with the email code, its sign-in cookies were never saved back as they refreshed, so every restart replayed the original ones until they expired and the channel reported "SSO session expired, full re-login required" even though it had been working moments earlier. The refreshed cookies are now stored the same way the standalone volkswagen.de mode already did, so the session carries across restarts. (This is the standalone channel's twin; the main channel was already fine.)
- **A car that is currently sending a "no reading" placeholder no longer re-reports the same field as new on every poll (#958, #969, #970).** Some readings, most visibly tyre pressures, come through as a placeholder meaning "no value right now" when the car has nothing to report. Those fields are already mapped, so the placeholder was being flagged as an undiscovered field over and over. It is now recognised as the mapped field it is: the sensor stays unavailable until a real value arrives, and the repeated reports stop. Genuinely unknown fields still surface for mapping exactly as before.

## [2.24.2] - 2026-07-27

### Fixed

- **A command the car declines now explains itself instead of looking like a crash.** When the gateway refuses to hand over the list of services a car offers, the resulting "not available on this vehicle" was thrown at Home Assistant in a form it does not recognise, so pressing a button produced an "Unexpected exception" with a full traceback. The explanation was there the whole time and was being thrown away. It is now shown as a normal, readable message. The same thing was already fixed for the S-PIN check a while back and simply never carried over to this one.
- **A single unlucky rejection no longer keeps a working car quiet for half a day.** When the gateway explicitly says the account is not authorised for a car, that is a decision only you can change in the brand app, so we stop asking for twelve hours. That was also being applied to any other rejection, including ones that are merely temporary, so one bad response could silence a perfectly fine car until the next day. Those now back off for half an hour and recover on their own.
- **Two readings stopped being reported as "undiscovered" on every single poll (#959, #960, #961, #963).** Both were already being read correctly, but the bookkeeping never recorded that, so the same one-line report kept coming back and there was nothing anyone could do about it. One affected an opening state (three people filed the identical report within a day, and the report could not identify which opening it referred to because around ten of them share the same name). The other affected cars that send a measurement's quality marker without the measurement itself. Nothing was ever suppressed to achieve this, the fields are simply accounted for properly now.
- **The log no longer floods when SEAT or CUPRA online services are blocked (#779).** One poll asks around nineteen addresses, and each refusal wrote its own warning, so a blocked account produced roughly twenty identical lines every few minutes for something the owner cannot fix. The retry is routine and is now quiet. The single clear error and the repair notice are unchanged.
- **A volkswagen.de channel that stops resuming now says why.** Previously only the error type was logged, so an expired sign-in, a redirect loop and an outage looked identical and reports arrived with nothing to work from. Note this is the already-added channel; adding a new one was fixed in v2.24.1. Unknown errors still have their details held back deliberately, because some of them carry the sign-in address including access tokens.
- **The historical import service says what happened.** It reported nothing at all in several completely different situations: no export requested yet, the portal still preparing the file, an empty file, or a successful read where every value was already up to date. All four now say so plainly in the log.
- **Two log lines that were still in German are now English**, like the rest of the log.

## [2.24.1] - 2026-07-27

### Fixed

- **Your car's recorded values are no longer wiped when a restart happens during a backend outage (#702).** If the very first data fetch after starting Home Assistant came back empty, the integration wrote that emptiness over everything it had saved, and the next poll then made it permanent. So a car that the portal was quiet about lost its history on every restart, and importing an older export was pointless because the next restart deleted it again. The periodic polls have been protected against this for a while; the fetch that runs at startup was not, and now is. A brand new car still appears normally on its first setup.
- **A parking position that is being kept during an outage now says how old it is.** Keeping the last known position when the backend answers without coordinates is deliberate, since a parked car has not moved. But it was being kept indefinitely and with nothing to indicate its age, so a position from last week looked exactly like one from a minute ago. It is now kept for at most a day, the map entry carries the time the car itself reported that position, and the address is kept and dropped together with the coordinates instead of leaving a half-filled location behind.
- **Parking lights and parking brake no longer read as "on" when the car says they are off.** Some cars send a flag that only means "this section of the report is present" alongside the real reading. That flag was being trusted first, so a car reporting both parking lights explicitly off, or the parking brake explicitly released, was still shown as on or engaged. The real reading now wins. Cars that send nothing but the flag are unaffected.
- **Adding the volkswagen.de channel now says why it failed.** Every failure was reported as a wrong password and nothing was written to the log, so an expired session, a redirect loop and an actual typo all looked the same and none of them could be told apart. The reason is now logged, exactly like the equivalent step during initial setup already did.

## [2.24.0] - 2026-07-26

### Added

- **Two new battery-care sensors on EU-portal cars (#938, #947).** The portal ships a score for how well the battery charging care mode is being used, plus the threshold it's measured against. Both are diagnostic and off by default, and they have no unit because the data dictionary doesn't give one.

### Changed

- **We identify as the current We Connect app version again.** One of the two places that announce the VW app version had drifted two releases behind the other, so the integration was introducing itself with two different app versions depending on which channel it used. Both now say 4.2.1, which is what the live app sends. Nothing else about the app changed.

### Fixed

- **Audi US / Canada email and password login: found the actual reason it never worked (#13).** The token step was being sent to Audi's identity server directly, and that endpoint requires a client secret which Audi's app-style login simply does not have, so it always came back as "invalid client". The exchange now goes through the North-American backend that does accept it. This also explains why adding a secret never helped: the endpoint was wrong, not the credential. The QR login was unaffected and keeps working the way it did. Still needs a confirmation on a real US or Canadian Audi before it can be called done.
- **VW Canada sign-ins no longer get blamed on your password when VW is having an outage (#915).** If VW's own login server answered with a server error, the integration told you your credentials were wrong and opened a login prompt that could never succeed. It now says plainly that this is a problem on the manufacturer's side and retries on its own. A genuinely wrong password is still reported as such.
- **The start_climate_control service works on Audi PPE cars again (#912).** The "force PPE climate" option was only being applied to the simple climate start, so the service with the richer options kept sending a target temperature that PPE cars reject, and the whole command failed. Both paths now respect the option.
- **Charging speed is no longer about ten times too high, and it respects the unit your car uses (#931).** One of the charge rate readings was published exactly as the portal sent it instead of being scaled, and a car reporting miles per hour was shown as if the number were km/h. Both are corrected, so the sensor now means what it says.
- **A car the VW gateway refuses to describe is no longer asked about on every single poll (#909).** That refusal is about how the car is registered to your account and cannot change by itself, so it is now remembered for a while and explained once in the log instead of repeating the same warning every few minutes. On top of that, a setup that fails on something only you can fix (pending terms, missing consent, two factor, wrong password) now asks you to sign in again instead of retrying forever in the background.
- **The integration's own rate-limit pause is no longer treated as a backend failure (#933).** When it deliberately pauses to protect your account from being locked out, that is normal and temporary, so it no longer counts as an error worth escalating.
- **A missing position no longer wipes your car's last known location (#923).** When the backend answers without coordinates, the previous parking position is kept instead of the car jumping to an unknown location until the next good poll.
- **Ambient temperature and parking brake stopped showing up as "new fields" every poll (#938, #947).** Some cars send those two readings under a doubled-up name. The value was already being read, but the doubled spelling kept getting reported as undiscovered. Nothing changes on the entities themselves.
- **A sign-in that lands on a proxied login page no longer risks a confusing server error.** The integration now takes the client identifier from the page it actually landed on instead of assuming it matches the one it started with. North American VW logins go through a proxy that uses its own identifier, and guessing wrong there produced a server error that looked like an outage.
- **Settings groups we cannot map yet no longer hide their own contents (#843, #868).** A group of settings was being filtered out together with everything inside it, which meant a diagnostic sent in to help map those settings could not actually contain them. The group itself stays quiet, but the individual settings inside it are visible again, so they can be mapped from a real report.
- **The window-heating command queue no longer counts as an unknown field (#934).** It's the same pending-command list the charging and climate blocks already have, so it's now recognised as such instead of being reported.

## [2.23.3] - 2026-07-24

### Fixed

- **VW US / CA logins that returned "no vehicles" despite a successful sign-in now find the car (#503, #659).** The North-American garage response nests the vehicle list differently for some (e.g. Canadian) accounts, and the parser was looking in one fixed spot. It now walks the whole response to find your vehicle wherever it sits. A genuinely empty account still reports empty.
- **The charge-mode selector no longer appears in read-only mode.** It sends a command, so like the other command entities it's now hidden when the integration is running read-only.
- **Audi/VW render images show a localized name.** The seven fixed render viewpoints (side/angle/large/small…) were showing their hardcoded German label in every language; they now use the translated name.

### Changed

- **Fewer duplicate diagnostic sensors.** Six sensors that mirror another sensor's value from a second source (two max-AC-current variants, the charging-block HV min/max temperature clones, and the EU-portal battery-care and energy-flow twins) are now diagnostic and disabled by default. Nothing is removed — existing setups keep them, and the primary sensor of each pair stays enabled.

## [2.23.2] - 2026-07-24

### Fixed

- **SEAT and CUPRA per-door sensors were showing open/closed backwards.** The individual door binary sensors on SEAT/CUPRA cars stored "closed" where the rest of the integration means "open", so a closed door read as open and vice-versa. They now match the correct convention.
- **Eight climate/connection/power binary sensors had no name.** A handful of entities (climate zones, "Connection active", the daily-power-budget and low-battery warnings) had their name filed in the wrong place internally, so they showed up unnamed. They now have proper names in all 12 languages.
- **French, Spanish, Dutch, Polish, Czech and Swedish are now fully translated.** Around 70 entity names were still showing in English in those six languages while the others were translated. They're now complete.
- **The vehicle-render image entity now shows a localized name** instead of a hardcoded English "Vehicle Render".

## [2.23.1] - 2026-07-23

### Fixed

- **Door, window and light sensors now show localized names.** The per-part door / window / light binary sensors hardcoded their English names ("Door Front Left", "Trunk", "Light left"…), so they stayed English even in a German (or French, Spanish, …) Home Assistant while their neighbours were translated. They now use proper translation keys with names in all 12 languages ("Tür vorne links", "Kofferraum", "Licht links"…). Entity IDs are unchanged, only the display names.

### Changed

- **Clearer message when the account has no vehicle yet.** When login works but the manufacturer lists no vehicle, the setup error used to say "No vehicles found. Check credentials and network." — which is misleading, since the credentials are fine. It now explains the real common causes: a VW data-sharing request still propagating, or a primary-user ("Hauptnutzer") re-confirmation that the brand app requires after you change your S-PIN or account settings.
- **Fewer duplicate range and fuel sensors.** On a single-energy car (pure petrol/diesel) the total-range and combustion-range sensors just repeated the main "Range" value, so three identical range sensors showed up; the redundant two are now hidden on those cars while genuine hybrids still get the full electric / combustion / total breakdown. The second fuel-level sensor ("primary engine fuel level"), which mirrors the main tank sensor, is now a diagnostic that is disabled by default (existing setups keep it).

## [2.23.0] - 2026-07-23

### Added

- **In-repo EU Data Act data dictionary + auto-update watcher.** The official SVK data-dictionary fields (what every EU Data Act portal key means, with types and units) are now documented in-repo at [`docs/EU_DATA_ACT_DATA_DICTIONARY.md`](docs/EU_DATA_ACT_DATA_DICTIONARY.md), linked from all 12 READMEs. A weekly GitHub Action watches the upstream source PDFs and opens an issue when a fresher version appears, so the doc stays current.
- **Four new driving-telemetry entities from the EU Data Act feed (#901).** Some VW cars report live speed, ignition state, a "driver is braking" flag, and a brake-pressure indication. They now show up as diagnostic entities (disabled by default) — speed as a proper km/h sensor (auto-converts to mph), the other three surfaced as-is while we confirm their exact meaning. Picked up from a Scout report.
- **The poll interval is now a slider you can automate (#847).** Until now the interval only lived in the integration's options; it's now also a Number entity (in minutes) on a per-account "VW Group Connect" device, so you can drive it from an automation — for example poll more often while you're driving and back off overnight — to go easier on the manufacturer's servers. It shows up for every account, including read-only / portal ones, and takes effect on the next poll without a restart.

### Fixed

- **Two-way commands on legacy Car-Net cars no longer refuse themselves with a false "not granted / check your subscription".** The service-directory grant check was treated as the final word, but it can briefly drop grants right after a reconfigure (or vary by cache) even on cars that fully allow the command. It's now advisory: on a negative result it refetches the service directory once and, if still unconfirmed, goes ahead — letting the car's own security-token step be the authority (which safely rejects a genuinely-ungranted command before any S-PIN attempt is spent).
- **A locked S-PIN no longer hides your lock / climate / charge buttons for a day.** After too many wrong S-PIN tries the car returns a "security PIN locked" error; the integration was misreading that as "your account isn't entitled", which hid the command entities for ~24 h and pointed you at a phantom subscription renewal. It's now correctly treated as an S-PIN problem — unlock it in the brand app and the buttons stay put.
- **A locked S-PIN now shows a plain "unlock it in the app" message instead of a scary error dump.** Pressing a command with a locked (or missing) S-PIN used to log a raw Python traceback that looked like the integration crashed. It's now a clean, one-line notification telling you what to do. This covers every command, including window heating.
- **Missing/locked-S-PIN feedback also reaches window heating.** Same clean-error handling as the other commands — no more traceback when you start window heating without a valid S-PIN.
- **You can finish enabling MBB commands even when your account uses two-factor login.** If a VW/Audi login needed a 2FA code, ticking "enable MBB commands" was silently dropped and you ended up with a read-only entry. The command-channel setup now continues after the 2FA step, exactly like a non-2FA login.
- **A per-vehicle S-PIN can now be removed again.** Clearing a car's individual S-PIN field in the options used to do nothing — the old value stuck around. Blanking it now actually clears it (falling back to the shared S-PIN).
- **Optimistic button states no longer snap back for a moment after a refresh.** Right after you pressed lock/climate/charge, the next data poll could briefly show the old state before settling. The poll now respects the short optimistic hold, so the button stays where you put it.
- **"Push notifications" no longer shows up as a permanent "capability drift" in diagnostics.** Push is off by default (and can be blocked by the manufacturer's app-attestation), so "declared but not seen" is its normal state — it's no longer reported as a mismatch. Genuine vehicle-data gaps are still surfaced.
- **The 12V-battery alert-time sensor reads plain durations correctly.** When the EU Data Act feed sends `bem_alert_time` as a countdown rather than a wall-clock time, it's no longer misread as a date far in the past/future.

## [2.22.1] - 2026-07-22

### Added

- **New auxiliary-battery alert-time sensor from the EU Data Act feed.** Some VW cars report a `bem_alert_time` — the moment the 12V (auxiliary) battery's BEM level-2 pre-warning kicks in. It now shows up as a diagnostic timestamp sensor (disabled by default). Picked up from a Scout report; the tyre-pressure and charge-rate fields in the same report were already mapped in earlier versions.

### Fixed

- **Audi US / CA login now completes instead of failing with "Invalid credentials" (#13).** The North-American login itself was working — the app sign-in went through and handed back an authorization code — but the integration then tried to exchange that code at the European backend, which can't read a code the US identity server issued (it came back `invalid key id`). The exchange (and token refresh) now go to the North-American identity endpoint that issued the code, matching the QR / device-code path. Reads are unchanged (they still use the shared global backend).

### Thanks

Thanks to **@coreywillwhat** for loading the integration onto a real US Audi and sending the full logs that pinned down the #13 token-exchange endpoint — credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.22.0] - 2026-07-22

### Added

- **evcc integration (read path, works on every brand).** You can now feed your car's state of charge, range and charging status straight into [evcc](https://evcc.io) — it reads them from Home Assistant's own REST API, so nothing extra runs inside this integration. A new diagnostic sensor **evcc charge status** (the A/B/C plug/charge state evcc expects, which it can't derive from our raw status text) is added per EV, disabled by default — enable it and follow the copy-paste recipe in [docs/EVCC.md](docs/EVCC.md). The read path (SoC / range / status / charge-limit / climate) works everywhere, including read-only VW EU; the write path (start/stop charging) works only on a two-way car (Audi / Škoda via MBB).

### Fixed

- **Two-way MBB commands (lock, climate, charging) no longer refuse themselves on cars that don't report an S-PIN attempt count.** When you send a command, the car first hands back a security challenge — and many cars report the remaining-tries count as `-1` at that stage, which just means "not tracked yet" (the real count only shows up if you actually get the PIN wrong). The command path was reading that `-1` as "you have -1 tries left" and blocking every lock/climate/charge command to dodge a lockout that couldn't happen. It now only holds back when there really are 0 or 1 attempts left.
- **The "please reauthenticate" prompt no longer fires on legacy Car-Net cars whose command gateway rejects them (#584).** On some MQB / Car-Net cars the command service-directory call comes back with an authorization rejection that a fresh login can't fix — it's an enrolment / primary-user thing on that car's account, not a token problem (confirmed by re-approving a brand-new token that still gets rejected one second later). The integration used to refresh the token and retry on every poll, which slowly tripped the "token refresh storm — please reauthenticate" guard and sent you off to re-log-in for nothing. It now recognises that rejection for what it is, logs a clear one-line explanation, and stops hammering the login endpoint.
- **No more `'NoneType' object has no attribute 'get_status'` right after a Reconfigure (#584).** Reconfiguring an entry could race a manual refresh that was already in flight, briefly leaving it without a client handle mid-fetch.

### Thanks

Thanks to **@Mattheisen87** for the meticulous #584 diagnostics that pinned down both guard fixes — the authorization-401 refresh storm and the reconfigure crash — and to **@nekas123** for raising the evcc use-case that motivated the read-path connector. Both credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.21.1] - 2026-07-21

### Fixed

- **VW EU cars no longer get a false "authentication expired / check your password" (#875).** On MEB / ID. cars, the WeConnect login path is blocked by VW's device-attestation wall, so its saved token can't be refreshed. The integration was treating that dead refresh as a login failure and taking the whole entry down — even though the EU Data Act portal login (the one that actually feeds your data) was working fine. It now falls back to a fresh portal login and keeps going, instead of asking you to re-enter a password that was never wrong. A genuinely wrong password is still reported as before.

### Thanks

Thanks to **@bobbasli**, **@leMineGaming**, **@m3gg3** and **@shaarkys** for the reports and the debug logs that pinned this down (#875) — credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.21.0] - 2026-07-21

### Added

- **12V battery-support sensor (MEB / ID. cars).** Newer MEB firmware reports a "battery support" state (`enabled` / `disabled`) that keeps the 12V battery topped up. It's now a diagnostic sensor (off by default — enable it under the device if you want it). This is the field a whole wave of Vehicle Data Scout reports flagged as unmapped; it's now mapped instead of just silenced.

### Fixed

- **Vehicle Data Scout stops flooding on `batterySupport` and active-ventilation.** Two fields were slipping past the Scout's noise filter because their real payload nested one level deeper than the interim filter reached — so dozens of ID./MEB cars kept opening "new field" reports for the same two items. Both are now properly consumed (the battery-support state as the new sensor above; the active-ventilation state + remaining time fold into the existing Active Ventilation sensors), so they no longer surface as unmapped.

### Thanks

Thanks to the many ID./MEB owners who reported the `batterySupport` field (#832 and ~26 more) and the active-ventilation spelling (#845, #856, #859) — all now credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.20.1] - 2026-07-21

### Fixed

- **Škoda charge controls work again (#866).** Setting the charge limit — plus the battery-care, charging-current and auto-unlock controls alongside it — failed with a server error even though the official app worked. They were being sent as an *action* rather than a *settings change*, so Škoda's backend rejected them. All four now use the exact request the app sends, checked against the actively-maintained Škoda library.
- **Two-way controls no longer vanish on older Car-Net cars.** On some legacy Car-Net vehicles the integration couldn't read the car's service directory (it came back "unauthorised"), and a v2.20.0 change then hid *every* lock / climate / charging control for the rest of the session. Now, when that directory simply can't be read, the controls stay available (a failed command is reported when you use it) instead of disappearing — while a car that genuinely proves it lacks a service still correctly hides it. That directory read is now also retried once after refreshing the login.

### Changed

- Internal tidy-up of some out-of-date code comments left by the v2.20.0 command-routing change. No behaviour change.

### Thanks

Thanks to **@tader** for the clean Škoda charge-limit report (#866). The full roll of reporters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.20.0] - 2026-07-20

### Added

- **Clear reasons when a control is missing or a command is refused (#752).** Until now, if a lock / climate / charge control couldn't be offered, it just quietly disappeared — and if a command failed, you got a bare error. The integration now decodes the backend's own error codes and per-service licence status into a plain reason: *your subscription has expired*, *this feature isn't licensed on this car*, *terms & conditions not accepted*, *privacy mode is on*, *the car is offline / in deep sleep*, and so on. So instead of a silent gap you get told **why** — and what, if anything, you can do about it.
- **Škoda: care-mode, auto-unlock-plug and active-ventilation controls (experimental).** Grounded in the current myŠkoda app's own routes. Treat as experimental until a Škoda owner confirms them on a real car.

### Fixed

- **Licence "days remaining" no longer goes negative on an active subscription.** On some cars (seen on an Audi S6 with a live subscription) a long-lapsed side-feature's old expiry date was winning out and showing the subscription as expired with negative days left. Only genuinely entitled services now count toward the expiry, so the figure reflects your real, active plan.
- **SEAT / CUPRA remote commands removed — they could only ever fail.** VW guards SEAT/CUPRA remote control behind a Google device-attestation check that only the official app on a real phone can pass, so lock / climate / charging sent from here were always refused. Those controls are now hidden, with an honest one-line explanation, instead of showing buttons that don't work. Vehicle **data still updates** as before.
- **Legacy Car-Net two-way now only offers controls the car actually grants.** For older Car-Net vehicles driven through the durable command channel, the integration reads the car's own service directory and creates a lock / climate / charge control **only** when that car currently licenses it — so you no longer get, say, a lock button on a car whose plan doesn't include remote lock. Nothing invented that can't run.
- **Škoda battery-care switch works again.** It was wired to a stub that raised instead of sending the command; it now sends the real care-mode request.
- **More command routes and payloads corrected to match the current official apps.** A fresh, byte-for-byte pass over the latest Audi / VW / Škoda / SEAT / CUPRA / VW-US apps caught several commands still using an old route or a mis-named field (Škoda flash + charge-target, SEAT/CUPRA battery-care + charge-target + climate temperature, VW-US flash / wake / charge-target, separate window-heating routes), plus the app-version headers were refreshed to the current builds.
- **VW US / Canada: Canada now uses the working US configuration.** The current myVW app ships no Canada-specific server or login client, so Canadian cars now use the same US endpoint that already works, instead of an unverified Canada-only config. (A Canadian tester should still confirm.)
- **Lock / climate / charge commands stop wasting a failed first attempt.** They were trying a combined endpoint that no current app exposes — always a 404 — before falling back to the route that works. The working route is now tried first, so commands are a touch faster and don't burn a needless round-trip.
- **Quieter, more honest logs; account e-mail masked (#779, #709).** The CUPRA/SEAT read channel no longer floods the log on a repeated backend refusal (it says once, plainly, what's happening), and your account e-mail is masked wherever it appears in logs.

### Changed

- **A few backend-error classifications corrected** so a transient or consent-related backend response no longer hides a working entity for a day.

### Thanks

Thanks to **@heyensh-sys**, whose reports on missing controls drove the "explain why" work (#752); **@rmalbrecht** (#779) and **@dazj1990** (#709) for the read-channel and logging reports. The full roll of reporters, requesters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you. 🙏

## [2.19.1] - 2026-07-19

### Fixed

- **PHEV charging power was reading 10× too high (#764).** On plug-in hybrids the portal feed reports charge power in tenths of a kW, but it was being taken as whole kW — so a 1.9 kW trickle showed as 19 kW, above what the car can even draw. It's now scaled correctly. The same real-world charging export also surfaced three smaller portal glitches, all fixed too: the charging state no longer flips to a junk value mid-charge, an odd placeholder charge-mode is ignored instead of shown, and a sentinel "0" odometer at trip start no longer masquerades as a real reading.
- **Cabin and outside temperature from the portal feed were decoded wrong.** Both were read as deci-Kelvin, but the data dictionary actually encodes them with a 0.1 °C step and a −46 °C offset — so a normal 22 °C cabin could come out around −205 °C. Both now use the correct formula (including the nested one-time-export spelling of the outside reading), with the Fahrenheit sub-range handled too.
- **Several Audi / VW commands were hitting the wrong backend path and silently failing (#752).** Parking-heater start, climate start, charge-mode and vehicle wake were each using a mistyped route or a mis-named field, so the backend answered with a 404 that led nowhere. The routes and payloads now match what the official app actually sends (parking-heater, charge-mode on its own route, the climate temperature / at-unlock keys, wake), and the VIN is upper-cased before every command because some backend nodes are case-sensitive. Note: on a car where a given function simply isn't provisioned for remote control, the backend will still legitimately refuse it.
- **Honk & flash ignored the requested duration.** The duration field was mis-named, so "flash the lights" always ran the backend's default length instead of the value sent. Fixed, grounded in the official app's own wire format.
- **Your car's model now shows even when the long name is missing (#764).** When the backend returns no full model name, the device now falls back to the short model name from the vehicle list before dropping to a plain brand label.
- **CUPRA / SEAT read channel: app-version header refreshed (#779).** Bumped to the current version so requests keep matching what the backend expects.
- **The "no data yet" help text now leads with the consent step (#755).** If the portal feed hasn't produced anything, the guidance starts with enabling the continuous-data consent in your VW/Audi account — the step people most often miss — before the rest.

### Changed

- **Commands now wait to confirm they actually ran (#666).** Instead of firing a command and assuming success, the integration briefly polls the backend until the request reaches a final state, so a genuine failure surfaces as an error instead of looking like it silently did nothing. It adds a little latency but is far more honest about what happened.

### Thanks

Huge thanks to **@Motii08**, whose real charging export pinned down the 10× power bug and three other portal glitches (#764); **@heyensh-sys** for patiently testing the Audi commands and sending the exact error logs that isolated the route bugs (#752); **@dazj1990** (#709) and **@rmalbrecht** (#779) for the read-channel reports; **@Mech0z** for flagging the confusing "no data" guidance (#755); and **@torstentosh**, whose command errors drove the completion-confirmation work (#666). The full roll of reporters, requesters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you. 🙏

## [2.19.0] - 2026-07-18

### Fixed

- **Your car's model + year now show properly on the device page.** Instead of a bare "VAG Vehicle", the device model reads like "S6 Avant TDI quattro tiptronic (2021)" — the redundant leading brand is stripped (the manufacturer field already shows it) and the model year is appended. Cars with no model name at all fall back to a clean brand label rather than "VAG Vehicle", and the VIN stays the device serial number.
- **Trunk, engine hood and sunroof open-state can read from the newer portal feed too (#794, #807).** Some cars send openings in a compact form where the trunk, the hood, the sunroof, every door and every window all share one generic `open` flag — told apart only by a hidden dictionary ID — so on its own the flag was meaningless (which is why the Scout kept surfacing a bare `open`). We now decode that ID against the official data dictionary and route trunk / hood / front-sunroof to their existing sensors. (Per-door and per-window openings share the same shape but are position-indexed — a follow-up; and real-feed confirmation is still pending, so treat it as best-effort.)
- **A brief DNS/network hiccup no longer files a spurious error report (#814).** When your Home Assistant box momentarily can't reach the VW backend (a DNS timeout), the integration already retries and recovers on its own — but that self-healing blip was still being escalated to the Error Reporter, which auto-files a GitHub issue. Those transient network errors are now recognised and logged quietly instead of raised.

### Added

- **Audi US / CA groundwork (experimental).** myAudi in North America runs on the same CARIAD backend as Europe, just the North-American region — so there's now an "Audi US / CA" brand wired to the real NA endpoints (host, identity provider and the live app client), with device-code (QR) login. Heads-up: it's a login foundation — whether North-American Audi vehicle data comes through off-device still needs a real US Audi tester to confirm, so treat it as experimental until then.
- **Tibber can now fill in your EV's charge data (EU, opt-in).** If you're a Tibber customer with your car paired, you can add Tibber as an extra read channel in the integration options — it reads state of charge, target SoC, range and plug/charging status from Tibber's official Data API and folds them in as a *lowest-priority* source: only filling gaps your car's own channels left empty, never overwriting fresher data. Read-only (Tibber can't command the car). One-time setup: create your own OAuth2 client on the Tibber developer portal, authorize once, and the integration keeps the token refreshed from there. Because Tibber only updates while the car is connected/charging, its readings are treated as the least-trusted source, and every field it contributes is attributed to the `tibber` channel.

### Thanks

Thanks to **@gomble**, whose error report showed the integration was filing a GitHub issue over a brief DNS blip that fixes itself (#814). **@loungelizard2018** and **@cafemonkey**'s Scout reports are what surfaced the packed opening states we now decode (#794, #807). The full roll of reporters, requesters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you. 🙏

## [2.18.1] - 2026-07-17

### Fixed

- **Closed windows and the roof no longer read as "open" on Audi / VW-EU cars.** Every window on the CARIAD channel — plus the rear sunroof and roof cover — showed *open* while the car was shut, even though the aggregate "windows open" sensor said closed. Two causes in the parser: the per-window map stored the state inverted (the lone place breaking the `True == closed` convention the rest of the integration follows), and option-dependent roof parts on a car without an opening roof were written as "open" instead of not shown at all. Both fixed — shut windows read *closed* and non-existent roofs don't surface. Thanks **@lucson**, verified on a real PPE Audi Q6 (#810).
- **A handful of Vehicle Data Scout reports that wouldn't go away — none of them real gaps.** Aux-heating (Standheizung) started turning up in a second spot on Audis, and the climate-timer's error wrapper read as an unknown field (#752, #785, #789); Škoda's AC charge-current-in-amps was already being read but was never ticked off the catalogue (#781, #795); and on the EU Data Act feed the raw oil-level status is recognised now (#794). The catalogue simply hadn't been told about these — so the Scout stops flagging them.
- **The portal Scout stops crying wolf on account/envelope metadata.** The EU Data Act feed repeats your account id, VIN, poll/message timestamps and a pile of per-export UUIDs on every single poll — none of it mappable vehicle data. These used to stay visible on principle; they're now dropped from the Scout/diagnostic surface (anything with a real, vehicle-specific field name still shows up), which clears a long tail of pure-repetition "N new fields" reports (#747, #782, #804 and a dozen more like them).

## [2.18.0] - 2026-07-17

### Fixed

- **Settings you'd saved were being read back empty — the big one, found by @lucson (#806).** Home Assistant hands the integration your saved configuration as a read-only mapping, not a plain dictionary, and a type check deep in the read was written for the wrong one. So it came back empty on every real install, no matter that you'd saved it correctly. This is why S-PIN commands told you to "configure your S-PIN" when you already had (that whole #666 saga), why the aux-heating sliders snapped back to their default, why turning read-only mode on could be silently ignored, and why the PPE climate flag did nothing. The tests had faked the saved config as a plain dictionary, so it looked verified for as long as it shipped. All four now read what you actually set.
- **Two settings that shipped but never switched on.** The push toggles (Škoda MQTT, CUPRA/SEAT and Audi/VW notifications) and the saved per-vehicle S-PIN map were read from an area Home Assistant blanks on save, and opening Options even wrote blanks back over the map. Nobody has ever had working push; the per-vehicle S-PIN (#759) is now read from where it lands, and Options stops clobbering it.
- **Your data stops disappearing after a command.** If your car is read over more than one channel, locking it — or restarting Home Assistant — used to blank out everything the second channel contributed until the next poll. Those readings are kept now.
- **Scout reports stop crying wolf.** A day's worth of reports arrived and almost none contained a field we don't already read — our own catalogue simply hadn't been told. The rear climate zones, the climate mode, the battery-care error notice and the capture timestamp are all recognised now, plus two new "changes pending" counters (queued charging-profile and climate-timer edits) that a couple of Audis surfaced (#799, #801).
- **A failing button gives you an error instead of a crash report.** Pressing e.g. Wake on a car that refuses it produced "Unexpected exception" and a Python traceback; you now get what the car actually said.
- **Diagnostics tells the truth about push.** It reported push as active on every setup, including ones with all push toggles off.
- **The portal is no longer re-probed on every restart**, and Škoda's AC charge-current limit is read.
- **A failed portal data-request now says why it failed (#709).** When the portal's security-token fetch fell over, the log said only "no CSRF token — aborting", which made a stuck feed impossible to diagnose (a 403, a 404, a timeout and a renamed field all looked identical). It now names the status or the reason — never the token value.
- **MBB commands died after about an hour (#584).** The refresh request was malformed — it announced `grant_type=refresh_token` but carried no refresh token in it, just an empty scope and the value under the wrong field. **@Mattheisen87**'s diagnostics show the result: a 500 error on every refresh and a token expiry frozen for four days on a 60-minute token, so it never once succeeded — and the 500 (rather than a clean rejection) is why it kept looking like a passing VW hiccup. The request is now well-formed and standard; whether that fully clears the 500 wants confirming on a real car, so if you run MBB, please shout.
- **And once MBB was on, there was no way back to the approval (#584).** The re-approval was gated off the moment the channel was armed — precisely the state you're in when you need it — and the checkbox showed unticked no matter what was stored, so it looked off while the code thought it was on. The only escape was deleting the integration and re-adding it, which renames every entity and takes your dashboards with it. Both fixed; re-run Reconfigure with the box ticked to re-approve.
- **The app watcher opened a pull request every single day (#727)** announcing version changes that weren't there — it was comparing the file, and the file always carries the time it last looked. It also never managed to check Volkswagen at all: the mirrors it asked don't carry the app, so it recorded "checked" and learned nothing, for months. It asks Google Play first now, which is where the apps actually come from.

### Added

- **Battery care is settable, not just visible.** A switch and a target slider — the reading has been there since 2.10.0, the control never was. Appears only on cars whose backend actually reports it.
- **Every reading tells you where it came from.** Each entity carries a `source` attribute naming its read channel, and the data-source sensor now works for single-channel cars too — on a Golf GTE the fuel level and the charge level genuinely come from different places.
- Both new controls are translated in 12 languages.
- **One-time historical export from the EU Data Act portal (Phase C, opt-in).** The portal offers a second kind of data pull besides the 15-minute feed: a one-time snapshot of your car's full configuration — departure timers, charge profiles, climate settings, the charge floor — in the older Car-Net format. Two new services: `request_historical_export` asks the portal to build it (it takes roughly half an hour), and `import_historical_export` fetches the ready file and folds its settings into your car's data. It only ever fills gaps — your live readings are never overwritten, so a hybrid can't get mislabelled electric by the older dump. This is wired end-to-end (the request, download and parse are all built from real portal traces) but the very last step, confirming a freshly-built export flows all the way through on a live account, still wants a real round-trip — so treat it as a beta.
- **Groundwork for Touareg-era cars (2021), which this release does _not_ yet fix.** Those cars ship the old Car-Net export format and we now understand it — charge level, charge mode, current limit, target temperature. But understanding it changes nothing on its own: the portal offers those cars only a one-time export, we only ever create and read the continuous 15-minute feed, and so we never actually fetch a payload for the mapping to work on. Reading one-time exports is the missing piece and it isn't built. #702 stays open.

### Removed

- **Three settings that did nothing.** Wake-before-poll (and its delay slider), force-access, and the EU Data Act browser fallback. None of them had ever been wired to anything — ticking them changed nothing.

### Docs

- **The README was sending people to look for a switch that doesn't exist.** It told you to enable a "continuous data request" in the VW portal; the integration creates that itself. It also called the auto-kickoff opt-in and promised we "won't do it without your say-so" — it has been on by default since 2.17.1, and the 1-month subscription it registers is free. Corrected in all 12 languages, along with two translation errors found on the way.

### Thanks

**@lucson** found the config-entry type bug and sent a fix for it — the reason so many "I saved it but it does nothing" reports never resolved. **@ChristophCaina** asked for the per-vehicle S-PIN, and **@Mattheisen87** put a real car on the MBB channel and pinned down both of its failures. **@shaunadam** turned on raw logging and sent the log that showed us the traceback. **Bugi66**'s export is what makes the Touareg-era format work possible (the reading itself is still to come), and **Mech0z** is why the README stopped lying. **@DvorakMartin1** surfaced Škoda's charge-current limit, **@thcherry**'s diagnostics caught the push mislabel, and **@Motii08** offered to charge their car for us. Thanks also to **@neuhausf**, **@dlupsa**, **@fefe-home**, **@jandebeule**, **@alexthegalex13**, **@YouriJansen**, **@GiuseppeAlbano** and **@Lagaff86**, whose Scout reports showed our catalogue was the thing that was out of date. The full roll is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you, all of you. 🙏

## [2.17.5] - 2026-07-13

### Fixed

- **No more "30 / 46 / 55 new field(s)" Scout reports full of cryptic ids.** A change in 2.17.4 accidentally surfaced every internal id-only data-point as its own "new field", so cars started filing huge Scout reports. Those ids are handled internally again; only genuinely new, readable fields are reported now.
- **The charging plug no longer shows a raw "invalid" state.** When the car reports an "invalid"/"unsupported" plug state, the text sensor now stays unknown instead of showing the raw marker (the plugged-in yes/no was already correct).
- **Boot/trunk lock is read correctly on cars that report it in a compact form** — and it no longer accidentally drives the *doors* locked state.

### Added

- **More coverage over the EU Data Act portal, reusing existing sensors:** oil low-level warning (petrol cars), rear climate-zone on/off, and sunroof position on cars that report it in a second slot.
- **Live "currently active" sensors** for mirror heating and each climate zone (front/rear, left/right) — the live-status companions to the existing on/off settings. Diagnostic, off by default.
- **"Battery Care Changes Pending"** diagnostic sensor.
- **Parking-light coverage** for cars that report it as a single flag.
- **A different S-PIN per vehicle (#759).** If the cars on your account each have their own S-PIN, you can now set a per-vehicle S-PIN under Settings → the integration → Configure. Leave a vehicle blank to keep using the shared S-PIN. Thanks **@ChristophCaina** for the request.
- All new entities are translated in 12 languages.

### Thanks

Every fix and field above started with someone filing a report, a request or a diagnostic. Special thanks to **@ChristophCaina** for the per-vehicle S-PIN request, and to everyone whose Vehicle Data Scout reports surfaced the new portal fields and flagged the field-list flood. The full roll of reporters, feature-requesters, testers and discussion contributors is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you, all of you. 🙏

## [2.17.4] - 2026-07-13

### Fixed

- **Electric VW ID.3 / ID.4 / ID.5 / ID.7 (and other MEB cars) show their driving range again over the EU Data Act portal.** These cars report the range in an anonymous field that only an internal id distinguishes, so the integration couldn't recognise it and the range stayed empty; it now resolves it correctly.
- **A bogus "service due in ~2.1 billion km" reading is gone.** A specific "no value" marker the service countdown sends slipped through the filter and got flipped into a huge positive distance; it's now dropped like the other no-reading markers.
- **No more pointless re-login loop when the data portal is briefly busy.** A "429 too many requests" or a "400 not ready yet" while fetching your data used to look like a failed login and kicked off a re-authentication loop; those are now treated as "no data this poll" and the next poll just tries again.

### Thanks

These EU Data Act read-path fixes (MEB/ID.x range, the "no reading" unit markers, transient-status handling) came out of benchmarking portal data quality across the wider EU Data Act community — thank you to everyone sharing real field data and edge cases, and to the reporters who flagged the missing ID.x range. 🙏

## [2.17.3] - 2026-07-13

### Fixed

- **VW EU passenger cars get their data flowing again.** The EU Data Act portal changed the format it expects for a data request, so the request the integration creates for you was being silently rejected — and status could stay "unavailable" with no obvious reason. It now sends what the portal expects, so the feed provisions correctly. This affects every VW EU car that reads over the portal.
- **Charging power and charge rate no longer read ten times too high** on EU Data Act cars. The portal reports these in tenths, so e.g. a real 7.4 kW showed up as 74 kW; they're now scaled correctly.
- **The diagnostics download no longer contains your account ID or VIN in the raw-fields section.** Those values are redacted now, while the field names stay visible so nothing is hidden.
- **Combustion VW (North America) cars are no longer wrongly told they need a subscription.** The "not entitled" check keyed off the EV-only charge/climate reads, which legitimately don't apply to a petrol car; it now keys off the main vehicle-status read instead.
- **The vw.de companion channel works on Car-Net (MBB) cars again** and stops forcing a repeated re-login. It was pinned to the wrong data-centre id for MBB cars, and it treated a "no data yet" reply as if your login had failed.
- **Clearer errors when a command can't run on a Car-Net (MBB) car.** Honk & Flash now tells you it isn't available on that channel instead of a misleading "GPS position needed"; a rejected Security PIN now says exactly that — check your S-PIN — instead of looking like an expired subscription; and remote wake explains that VW doesn't permit it on that channel. Thanks to the live diagnostic that pinned all three down.

### Thanks

These fixes exist because people filed clear reports and ran real cars: **@SparkyDan555** (charge power/rate reading 10× too high), **@Rizencip** and **@shaunadam** (combustion VW North America), **@dazj1990** (the VW EU portal feed going quiet), and **@torstentosh** and **@Mattheisen87** (the MBB command diagnostics). 🙏

## [2.17.2] - 2026-07-11

### Added

- **The integration now speaks four more languages: Italian, Norwegian (Bokmål), Danish and Finnish.** Full UI translations plus a translated README for each — twelve languages in total now.
- **You can switch on the two-way command channel for an existing VW or Audi account without deleting and re-adding it.** Open Settings → Devices & Services → Reconfigure and tick "enable MBB commands" — the QR confirmation runs and the command channel is attached to your existing entry (so your entity IDs, automations and dashboards stay intact). Still **experimental** and legacy Car-Net only, exactly as at first setup.

### Fixed

- **Reconfigure no longer wipes an existing command channel.** Updating your password (or any other setting) through Reconfigure used to silently drop a durable-MBB two-way channel you'd set up — you'd have had to add it again. Reconfigure now merges your changes on top of what's already there instead of replacing everything.
- **The manual "Create EU Data Act data request" button now works even if you turned automatic provisioning off.** Pressing it is an explicit request, so it now always creates the data request rather than doing nothing.
- **"No data → self-heal" now kicks in right away instead of waiting for the host's first six hours of uptime.** A clock comparison meant the runtime re-provisioning could stay dormant on a freshly booted Home Assistant; it now fires on the first cycle that needs it.
- **Bentley setup and reconfigure no longer crash** when building the entry title (Bentley isn't in the internal brand-name table — it now falls back to a plain label instead of erroring).
- **Lock / climate / charge toggles no longer snap back after you press them.** The control flipped to the new state immediately, but the very next data poll overwrote it with the car's still-pre-command state, so it looked like the command hadn't worked until you hit refresh. The optimistic state is now held until the car's backend actually reports the change (or a couple of minutes pass). Thanks @torstentosh for pinning this down on a PPE Q4 e-tron.

### Changed

- **Porsche login rebuild — groundwork only, nothing changes for users yet.** The experimental Porsche path targets the retired My-Porsche (Auth0) app; the live app is Porsche One (PingFederate device login). This release adds that device-login implementation (unit-tested against mocked endpoints) so the rewrite is ready, but it is **not wired in** and still needs a Porsche One owner to verify it end-to-end before Porsche can be switched back on. Porsche stays flagged experimental.

## [2.17.1] - 2026-07-10

### Fixed

- **"Configure your S-PIN" no longer appears when your S-PIN is already correct (#666).** On a setup that pairs EU-Data-Act reads with the legacy two-way command channel, the command connector grabbed your S-PIN once when it started up — so an S-PIN you added or changed *later* through the integration's Options never reached it, and every lock/climate/charge command failed asking you to configure a PIN you'd already configured. The connector now reads the S-PIN Options-first at start-up **and** picks up a changed PIN live, without a restart. Thanks @torstentosh for the report and the testing.
- **Clearer errors for S-PIN and SEAT/CUPRA attestation walls (#666).** A remote command that needs an S-PIN but has none configured now reports a clean "S-PIN required" instead of a raw traceback, and SEAT/CUPRA commands blocked by their AWS WAF are now correctly identified as a device-attestation wall (not a phantom subscription/renewal problem).
- **Reconfigure no longer aborts with "already configured" (#584).** Reconfiguring an existing account (Settings → Devices & Services → Reconfigure) immediately failed with "This account is already configured", because the check matched the very entry you were reconfiguring. It now only refuses if you switch to a *different* account that already has its own entry — reconfiguring the same account updates it in place. That means you no longer have to delete and re-add the integration (which would regenerate every entity_id from the default device name and break your automations and dashboards). Thanks @Mattheisen87 for the precise root-cause.
- **Legacy Car-Net remote lock/unlock now targets the correct backend URL (#666).** The MBB lock/unlock request was being sent to the wrong host and path shape (it dropped the brand/country and used the setter host), so on a real Car-Net car it would have 404'd. Corrected to the verified `{Brand}/{country}` form on the vehicle's home-region host — the same shape our other Car-Net calls already use. Grounded against the myAudi/We-Connect app internals.

- **The "open the brand app" button now uses each app's real link (#666).** Several brands' deep-link schemes were launcher guesses (`wecharge://`, `myseat://`, `mycupra://`, `myporsche://`, `vwapp://`) that didn't match the app; corrected to the schemes the shipping apps actually register (`weconnect://`, `seat://`, `cupra://`, `porsche-app://`, `myvw://`). Audi and Škoda were already correct.

### Changed

- **Porsche is now flagged experimental — its login may fail (#666).** The fresh app teardown showed Porsche moved from the old My-Porsche (Auth0) app to **Porsche One**, which uses a completely different login (PingFederate device-grant). Our current Porsche login targets the retired Auth0 app, so it's expected to fail on current accounts. Rather than quietly advertise it as working, Porsche is now labelled experimental in the brand picker. The rebuild path is documented and confirmed feasible — it just needs a Porsche owner to help verify it end-to-end before it's switched back on. (Testers with a Porsche account welcome.)

### Added

- **The EU Data Act data request is now set up for you automatically — no more "device with empty entities" (#584).** In portal mode the integration can only receive data once there's an *active continuous data request* on the VW EU Data Act portal. Until now you had to create that request yourself on the portal website first — and if you didn't (or it lapsed), you got a device full of empty entities and reasonably assumed the integration was broken. Now it **creates the request for you automatically** and, if data stops arriving, **re-provisions it on the fly** — so "no data coming in" self-heals. A one-time notification tells you when a request was created. You can turn automatic provisioning off under Configure, or trigger it yourself with the new **"Create EU Data Act data request"** button. (We're the only VW-EU Home Assistant integration that can create the request for you — the others require you to do it by hand.)
- **Audi Car-Net owners can now enable the two-way command channel too — experimental (#666).** The legacy command path (lock/climate/charge over the older Car-Net backend) was Volkswagen-only; it's now offered for Audi as well, since the underlying command catalog is identical and the brand routing is handled. This is **experimental** and applies only to older legacy Car-Net Audis (not the newer MEB/PPE e-tron generation) — it hasn't been confirmed end-to-end on a real car yet, so treat it as opt-in testing.
- **New sensors for EU-portal cars: cabin temperature, HV-battery min/max temperature, charge-target time and profile user count.** The latest round of Vehicle Data Scout reports (a VW ID.7 among them) carried a handful of signals we didn't map yet. If your car sends them in its portal data, they now appear as sensors. Everything else in those reports was already covered.

## [2.17.0] - 2026-07-10

### Added

- **Škoda now reports its heater source too (#682).** Škoda EVs expose a `heaterSource` value on the climate endpoint (e.g. "AUTOMATIC") — the same signal VW, Audi, SEAT and CUPRA already surface. It now feeds Škoda's **heater source** sensor as well (electric cars, where the field is present). Thanks @ra666ack for the Scout report.

### Fixed

- **Charging settings (target %, charge mode, min charge, max AC current) work on PPE Audis again (#666).** Same root cause as the v2.16.3 climate-temperature fix: these were sent as a POST where VW's backend expects a **PUT**, so on the stricter PPE/MEB Audis (Q4/Q6 e-tron) every charging-settings change came back **404** — @torstentosh confirmed the charge-target still 404'd on 2.16.3 right after the climate fix started working. All four charging setters now use the correct PUT (through a shared helper that also covers climate), keep the old POST as a no-regression fallback, and surface a clean error instead of a raw 404 traceback if a vehicle genuinely doesn't expose the write. The legacy MBB two-way charge path is unchanged.

## [2.16.4] - 2026-07-09

### Fixed

- **Repair prompts show correctly in six more languages.** Several of the integration's repair messages (two-factor needed, terms & conditions, marketing consent, rate-limited, auth failed) were missing the `{brand}` / `{username}` placeholders in the Czech, Spanish, French, Dutch, Polish and Swedish translations — so Home Assistant logged translation-validation warnings and could blank those messages out. All six now match the English source, with the account name and brand back where they belong. Thanks @shaarkys, whose debug log surfaced the Czech warnings.

## [2.16.3] - 2026-07-09

### Fixed

- **Setting the climate temperature works again on Audi Q4/Q6 e-tron and other PPE cars (#666).** The "set target temperature" action was going out as the wrong kind of request — a POST carrying the *read*-side field name (`targetTemperature_C`) — where VW's backend actually expects a **PUT** with `targetTemperature` + a unit. On the stricter PPE/MEB Audis the gateway answered that with a **404**, so every temperature change failed with an "unexpected error" (older models were more forgiving, which is why this went unnoticed). It now sends the correct PUT + body, keeps the old request as a fallback so nothing that worked before can break, and if a vehicle genuinely doesn't expose a standalone temperature-set it now says so cleanly instead of dumping a 404 traceback. The verb + field were cross-checked against four independent VW/Audi CARIAD clients.

### Thanks 🙏

Huge thanks to @torstentosh for the pin-sharp debug log + diagnostics that made this a five-minute root-cause instead of a guessing game. Exactly the kind of report that makes a fix like this possible.

## [2.16.2] - 2026-07-08

### Added

- **New diagnostic sensor: what triggered the last EU Data Act delivery (#636).** On EU Data Act cars there's now a "report trigger" sensor that tells you what kicked off the most recent data report — e.g. a remote request you made, or the car reporting on its own. It ships **disabled by default** (it's diagnostic detail most people won't need), so turn it on if you're curious. Thanks for the field spot.
- **New diagnostic sensor: which climate mode your car is set to (#671).** Audi and other CARIAD EU cars report a `climatisationMode` setting — "comfort" in the wild — that we already used when *sending* a climate command but never read *back*. There's now a "climate mode" sensor showing the current value. Like the trigger sensor above, it's **disabled by default** and only shows up on cars that actually send the field. Thanks @tsvyatkov for the Scout report.

### Fixed

- **VW: your car stays alive when the EU Data Act portal has a bad moment.** If you've got a VW EU car set up with the volkswagen.de website channel as a backup on top of the EU Data Act portal, and the portal times out for a poll, we now fall back to the website data for that cycle instead of freezing the entity on its last-known values. Before, a portal hiccup would quietly leave you looking at stale numbers even though volkswagen.de had fresh ones sitting right there. Single-source setups are completely unchanged. And if the website session itself has actually expired, you get a proper re-login prompt rather than silent staleness.

- **Škoda: warning lights no longer read "Problem" on a perfectly healthy car (#649).** Škoda's health endpoint always sends one entry per monitored category (engine, brakes, tyres, oil…) even when nothing's wrong — a healthy category just comes back with an empty defect list. We were treating "the list has entries" as "something's wrong", so on every Škoda all the warning sensors flipped to Problem while the MySkoda app calmly showed "All good". Now a category only counts as a warning when it actually carries a defect, so an all-clear car reads all-clear. Thanks @divanguz-alt for the report and the spot-on root-cause.

### Thanks 🙏

This release came straight from your field reports. Special thanks to @divanguz-alt (Škoda warning root-cause, #649), @chrischtili (the `trigger_type` field, #636) and @tsvyatkov (the `climatisationMode` field, #671). And to everyone who filed a Vehicle Data Scout report or bug this cycle — @bachjessen @BalooDK @datenhamster @Drachendiadem @fesch89 @fugazzy @gr6803 @heikone @IanNorthern @janez78 @joostbouten @kaufmannralf @KratosLionXD @Lagaff86 @littlecake @LouisFk @MaFi1504 @Manuel-Hanak @MaTi8383 @MichaelNeys @moltke69 @NevelSavage @Ola-Skallberg @PollenNor @Raymondgijzen @roeleert @Sacha72 @sebastianedse @sotiropoulos123 @Svenruotsi @tolnaiz @torstentosh @wfa001 — even the reports that turn out already-covered help confirm the field mapping is holding up. The full roster of everyone who's ever reported here is in [CONTRIBUTORS.md](CONTRIBUTORS.md).

## [2.16.1] - 2026-07-05

### Fixed

- **volkswagen.de proactive session-roll: the first roll no longer gets wrongly skipped on a freshly-booted host.** The debounce used `0.0` as the "never rolled yet" marker, but `time.monotonic()` can be a small number right after boot — so on a fresh start the very first proactive roll could be debounced away. Uses a proper `-inf` marker now, so the first roll always fires regardless of uptime. (CI caught this on a fresh runner; no user-visible impact, but the guard now behaves as intended.)
- **LICENSE is detected as AGPL-3.0 again (HACS validation).** The LICENSE file carried a short custom copyright/intro header above the licence text, which made GitHub's licence detector report "Other" and failed HACS's licence check. The canonical AGPL-3.0-or-later text now stands alone in LICENSE (so it's correctly detected), and the copyright notice + the AGPL §7 attribution/naming terms moved to a new NOTICE file (pointing at the existing ATTRIBUTION.md). **No change to the licence itself** — same AGPL-3.0-or-later, same attribution requirements.

## [2.16.0] - 2026-07-05

### Added

- **Service & oil-change now also show an absolute due-date on EU Data Act cars, not just "in N days."** The portal path already gave you the "next service in 155 days" counter, but the companion "due on <date>" sensors (`service_due_at` / `oil_service_at`) stayed empty on EU-Data-Act vehicles — they only filled in on the brand-native paths. Now the portal path feeds them too, so a dashboard can show the actual date. (No new entities — it populates the sensors that were already there.)
- **volkswagen.de channel: two new read signals + the car's nickname & plate (beta).** If you use the opt-in volkswagen.de read channel, it now also reports the **number of active dashboard warning lights** and your **last confirmed remote lock/unlock action + time**, and surfaces the vehicle's nickname and licence plate. These ship **disabled by default** — they're beta, hitting live endpoints we haven't broadly validated yet, so enable them if you'd like to help test — and they fail soft: if VW's backend doesn't answer, the sensors just stay "unknown" and never hold up the rest of your data. Want to help validate the channel? See #632.

### Fixed

- **The optional volkswagen.de read channel no longer quietly drops its session between polls.** That channel's sign-in lapses roughly 30 minutes after login and normal data reads don't keep it alive, while the poll runs every 15 minutes — so on a slow cycle the session could die silently, and the next read would fail (sometimes forcing a re-login with a fresh email code) with nothing to tell you why. The integration now proactively refreshes that session at the start of each cycle, well inside the expiry window, so it stays alive. Best-effort — a failed refresh just falls back to the existing on-demand re-login. (No effect unless you enabled the volkswagen.de channel.)

### Thanks 🙏

None of this happens without the people who file Vehicle Data Scout reports, open issues, send diagnostics + logs, and test on real cars — you're the reason the field coverage and reliability keep improving. Thanks to everyone who fed into this stretch of releases, including @brokkolo @MBrunk85 @PascalFlierman @normand198 @JosefAuer84 @jebeke65 @oh-supra @kotipalvelu @Carbolithos @jwmaas @saxmanio85 @danst0 @StefanSch84 @ravest @bachjessen @VanHynten @daydy16 @tsvyatkov @gudden @jamiegt10 for the recent field-Scout reports, and @CyberChris79 + @Ra72xx for the diagnostics and repros that drove the MBB command-cascade and the duration-parsing fixes. The full roster of everyone who's ever reported here lives in [CONTRIBUTORS.md](CONTRIBUTORS.md).

## [2.15.12] - 2026-07-04

### Fixed

- **A failed MBB command no longer knocks all your sensors offline (#584).** On the legacy Car-Net two-way alpha, reads and commands run through the same connection and shared one token-refresh budget. So when VW's backend kept 500ing a lock/climate command, the retries burned through that budget, tripped the "too many refreshes — pause" guard, and that guard then also blocked the normal data poll — every entity went unavailable with a red exclamation mark until a restart. Now a command failure stays contained to that command: it can't exhaust the poll's refresh budget or drag your reads down with it. On top of that, a transient MBB 5xx from VW is retried with a short backoff instead of failing instantly. Reads keep flowing even when a command can't get through. Thanks to CyberChris for the clean repro and logs.
- **Aux-heating (Standheizung) now fails cleanly on legacy Car-Net cars instead of leaking the wrong credentials (#584).** On an MBB car the engine pre-heater command was sending the MBB token to VW's newer backend, which rejected it with a `400 missing auth header`. There's no verified MBB route for the pre-heater yet, so rather than send the wrong credentials it now returns a clear "not available on the legacy two-way path yet" message. Non-MBB cars (the newer portal + Audi) are unaffected. Wiring up real MBB aux-heating is a separate future item.

## [2.15.11] - 2026-07-03

### Added

- **HV battery status sensor.** EU Data Act cars that report a high-voltage battery status flag now get a diagnostic sensor for it, separate from the state-of-charge reading. It's off by default and translated into all 8 supported languages — turn it on if you want it. Thanks to the reporter for surfacing the field.
- **Spoiler position sensor (#614).** On cars with a movable spoiler, the actual spoiler position as a percentage now shows up as a diagnostic sensor, alongside the open/closed state we already had — same as we did for the sunroof. It's off by default and translated into all 8 supported languages.

### Fixed

- **Charging-scenario and immediate-action sensors on more cars.** Some EU Data Act vehicles send these two charging status readings under a slightly different name than others, so they were showing up empty. They now fill in either way. Thanks to the CUPRA Tavascan reporter.

## [2.15.10] - 2026-07-02

### Added

- **Live push updates — experimental opt-in BETA (Audi, VW, Škoda, CUPRA, SEAT).** Instead of only polling on a timer, the integration can now listen for the car's own push notifications and refresh the moment something changes — a lock/unlock, charging kicking in, climate switching over. It's off by default; flip it on per brand in the integration options if you want to try it. Heads up: it's genuinely experimental and still needs testers with a live car to confirm it works end-to-end on each brand, so expect rough edges. If it can't connect it quietly backs off and falls back to normal polling — no log spam.
- **Set the AC charging current on Škoda.** Škoda EVs now get a "Max. Charging Current" dropdown so you can switch the car between drawing the full AC current and a reduced rate — handy if you want to go easy on a shared or older circuit. It reads back the car's current setting and is translated into all 8 supported languages. Only Škoda cars with a battery get it.

## [2.15.9] - 2026-07-02

### Added

- **Rear climate-zone on/off sensors for Audi (#597).** Cars with a rear climate zone now expose whether the rear-left and rear-right zones are switched on, matching the front-zone sensors we already had. They're diagnostic and off by default — turn them on if you want them. Cars without a rear zone won't get an empty entity. Thanks to @kaledii for the report.

### Fixed

- **VW North America dropouts got reported as errors (#593).** When the VW-NA backend was briefly slow or the connection dropped mid-poll, the timeout bubbled all the way up and showed in the Error Reporter as if the integration had broken — the same "backend temporarily unavailable" blip we already shrug off everywhere else. Now a connection drop or timeout on a VW-NA request is treated as exactly that: a transient hiccup, skipped for this poll, no error logged. A real 403 (entitlement/attestation) or any genuine server error still surfaces normally, so nothing real gets swallowed. Thanks to @dardares for the report.
- **Consent/terms prompts flooded the Error Reporter every poll (#596).** If your account was waiting on a one-time action in the brand app — a privacy-consent acceptance, updated terms, a 2FA confirmation, or a portal onboarding step — the integration correctly showed a Repair telling you to go accept it, but *also* logged an error to the Reporter on every single poll (dozens of duplicate entries). Those prompts are something only you can clear in the app, not a bug in the integration, so they no longer get recorded to the Error Reporter — you still get the clear Repair notice telling you what to do. Genuine problems are still reported as before. Thanks to @knalp for flagging it.
- **Charging-mode dropdown was stuck in German for everyone (#589).** The `Charging Mode` select baked the German option labels ("Manuell", "Bevorzugte Ladezeiten", …) straight into the entity, so a UK user (or anyone not on German) saw German verbatim — Home Assistant had nothing it could translate. The options are now stable canonical keys that HA localises per your language, with proper translations shipped for all 8 supported languages; the current value localises too, no matter which spelling the car's backend sends back. This is a display/localisation change only — it doesn't touch how a mode is sent, so command behaviour is unchanged on the brands that support switching it. Thanks to @ColinSainsbury for reporting.
- **Stopped a harmless "new field" report on Audi (#598).** When the Audi backend has a brief hiccup fetching your car's capabilities list, it tacks on a little error wrapper that the field scout hadn't seen before and flagged as new. It's just the same "backend was momentarily busy" placeholder we already ignore everywhere else — there's nothing to show for it, so it no longer gets reported. Thanks to @zapadee for the report.

## [2.15.8] - 2026-06-30

### Added

- **New "Charge Mode Changes Pending" sensor for Audi/VW (#583).** The portal now ships a little queue counter for charge-mode switches (e.g. flipping between manual and timer charging), right next to the charging-settings and charging-commands queues we already track. It's a diagnostic sensor, off by default — flip it on if you want to confirm a charge-mode change actually went through.

### Fixed

- **VW EU portal login that timed out got reported as an error (#576, #578).** When the EU Data Act portal was briefly slow or unreachable during sign-in, the timeout bubbled all the way up and showed up in the Error Reporter as if the integration had broken — same as the "backend temporarily unavailable" hiccups we already shrug off everywhere else. Now a connection drop or timeout during login is treated as exactly that: a transient blip, skipped for this poll, no error logged, no re-login churn. A genuinely wrong password (or a consent/2FA prompt) still surfaces normally, so nothing real gets swallowed.

## [2.15.7] - 2026-06-30

### Fixed

- **Electric and combustion ranges were swapped on plug-in hybrids (#555, #565).** On PHEVs like the Passat GTE 1.4 eHybrid and the Tiguan eHybrid, the "electric range" sensor showed the petrol range and the combustion sensor showed the electric one — battery and fuel levels read fine, only the two ranges were flipped. Turns out on these cars the *primary* engine is the combustion one (the opposite of an ID.x, where the primary engine is electric), and we were mapping the two ranges by position. Now we work out which range is which from the engine type, so electric and combustion line up with the VW app again. Pure EVs are unaffected. Thanks to the reporters of #555 and #565 for the clear write-ups.
- **VW EU login that ended in "check email and password" after a correct password (#527).** On accounts where VW shows a one-time consent/authorization page, the integration tried to accept it but submitted the form the wrong way, so VW rejected it with a blank `400` and login never finished. Two things were off: the consent form posts back to its own URL with the query string attached (where the security tokens live) and we were stripping that query off; and the form lists each granted scope as its own field, which we were collapsing down to one and dropping a required scope. Both are fixed now, so the consent step completes on its own and login goes through. Huge thanks to **@RaimondB**, who reproduced it offline, root-caused both defects, and verified the fix end-to-end on his own car. 🙏

### Added

- **New "Battery climate energy use" sensor.** Picks up the battery-climatisation (thermal-management) energy your car already reports on the EU Data Act portal — handy for the e-cars that pre-heat or cool the battery. It's a diagnostic sensor, off by default, so flip it on under the device if you want it.

## [2.15.6] - 2026-06-27

### Fixed

- **Honest message when a portal car can't take commands (#543).** If your car connects through VW's read-only EU Data Act portal and you try to send a command (lock, climate, charging), you used to get told to "disable read-only mode in the options" — but there's no switch that helps: the portal simply has no command path. The message now says that plainly, so you're not sent hunting for a setting that can't change anything. Cars where read-only really is just a toggle you flipped still get the old "disable it in the options" hint.
- **No more stray US/Canada dropdown for non-US cars (#465).** Setting up an EU car (or any brand before you'd picked one) showed a "country" field that only offered USA and Canada — confusing, since it never applied to you. That picker now only appears when you choose Volkswagen US/Canada, where it actually selects your region. Pick VW US/CA and the US↔Canada chooser is right there as before; everyone else never sees it.

## [2.15.5] - 2026-06-27

### Added

- **Optional ABRP (A Better Routeplanner) live telemetry push.** You can now feed your car's live data straight into ABRP so it plans routes around your real state of charge. It's off by default and opt-in: turn it on in the integration options, paste your ABRP token (and a developer api_key — see the README on how to get one), and a shipped blueprint uploads automatically whenever there's something new to send. There's a small diagnostic "ABRP data changed" sensor that makes sure the same snapshot never gets uploaded twice. Your location only ever leaves the house when an upload actually runs, and the token + key are never written to the log.
- **More mapped fields.** The "last update reason" — why the car last pushed a report to the backend (e.g. it started charging, ignition went on/off, climate ran) — now surfaces as a diagnostic sensor (disabled by default). One of the recurring VW-EU Scout fields, now off the list. Nothing hidden.
- **Bidirectional charging (V2G) limits (#541).** If your car reports them, the upper and lower charge-level limits it'll bidi-charge within now show up as two diagnostic sensors (disabled by default).
- **Sunroof position (#544).** On top of the open/closed state we already had, the actual sunroof position (as a percentage) now surfaces as a diagnostic sensor (disabled by default).

### Fixed

- **Aux-consumer consumption no longer shows a bogus 65535 (#544).** When the car had no reading, the average auxiliary-consumer consumption sensors were passing the "no data" placeholder through as if it were a real value. They now read empty in that case instead, so it can't poison your long-term stats.

- **VW US/CA: data reads work again on locked-down accounts with an S-PIN (#503).** Some US/Canada accounts could log in and list the garage but every per-vehicle read came back 403. If you've set your S-PIN, the integration now unlocks those reads the way the official app does — it asks for a short-lived per-car token and uses that for the data. It's done carefully: the token is cached and only refreshed when it expires (never on every poll), and if your S-PIN looks wrong or you're near the attempt limit it backs off immediately and falls back to the normal path, so it can't lock your S-PIN. Accounts without an S-PIN are unchanged. And a persistent 403 that used to stay silent now raises the repair notice after it keeps happening.
- **EU Data Act portal: "check email and password" with a correct password (#527).** After you typed the right login, the portal sometimes showed a one-time "authorize this app" consent screen instead of finishing — and the integration mistook that for a wrong password. It now accepts that consent for you automatically (you already entered your login and want it connected, exactly what the app does), so login just goes through. If for some reason it can't, you now get a clear "finish the consent in your browser" message instead of being told your password is wrong. A genuinely wrong password still says so.
- **Flash-lights button works again on VW/Audi (EU).** It was calling an endpoint that doesn't exist with the wrong body, so the car always answered "bad request" and nothing happened. It now sends the same request the official app does. If your car insists on a location for the flash, it retries with the car's last-known position automatically, and if there's no position yet you get a clear hint to wake the car first instead of a silent failure.
- **The US/Canada region setting is no longer saved on non-US/CA cars.** That dropdown only matters for Volkswagen US/Canada, but every brand was quietly getting "United States" stored in its config even when it was irrelevant — so a Swiss or EU car ended up looking like a US car in the diagnostics. It never affected your data (EU cars ignored it), but it was confusing and could have tripped up future code. Now it's only kept for Volkswagen US/Canada, where it actually does something; everyone else leaves it blank. Existing setups that already have the stray value keep working untouched.
- **Turning OFF read-only mode now actually re-enables commands (#543).** If your car was set up with read-only on, switching it off in the integration options had no effect — the old value still won and lock/climate/charge stayed blocked. Now your choice in the options always takes priority, so disabling read-only brings the command buttons back as expected.

## [2.15.4] - 2026-06-26

### Fixed

- **VW US/CA: clearer diagnosis when sensors stay empty (#503).** Login + the garage list now succeed (US/Canada selector), but if the per-vehicle data endpoints return 403, the integration classifies why — an inactive Car-Net / VW Connect subscription, a VW device-attestation lockdown, or a transient block — and raises a repair notice (with the cause in the debug log, no secrets) instead of silently showing nothing. Last-known data keeps showing.

- **Battery capacity / available energy were 10x too high (#534).** The EU-portal energy-content readings are in 0.1-kWh units but were passed through unscaled — an ID.4 showed 756 kWh instead of 75.6 (and 461 instead of 46.1 available). Now scaled correctly.

- **Clearer login errors (#527).** A portal login that fails for a non-password reason — terms/consent not yet accepted, a 2FA or onboarding step, a region/soft-block — no longer shows the misleading "check email and password". You now get the real reason and what to do (open the portal once in a browser, finish the prompt, retry), so users with correct credentials aren't sent chasing a password problem. Failure logging now records the landing page type/error code (no secrets) to pin the cause.

- **Charge-timer & slope-consumption now actually populate, and the Scout stops re-reporting them.** These EU-portal fields were only read under one payload shape and silently missed the realistic one — so they never showed AND recurred in the Vehicle Data Scout for every VW-EU user. Now read from either shape; uphill/downhill slope no longer collide; the Scout only lists genuine unmapped metadata.

- **VIN privacy.** Scout / error-report titles no longer expose the full VIN. For a car whose name was never changed (notably Audi, where CARIAD defaults the vehicle name to the VIN) the "model" fell back to the raw 17-char VIN — bypassing the last-6 masking the footer promises. The model is now omitted when it is (or contains) a VIN; the brand alone scopes the issue.

### Added

- **More EU Data Act portal fields mapped (#518).** Active charge target, charge-time display, charging power, and the dual charging-plug state set (plug 1 + 2: flap, flap-lock, lock, infrastructure, connection) now surface as diagnostic sensors. Nothing hidden — unmapped fields stay in the Scout.
- **More mapped fields (#521, #522).** Next-charging-timer schedule (start/finish/reachability), uphill/downhill slope consumption, the charging error code, and an outdoor-temperature alias. Diagnostic; low-confidence disabled by default; nothing hidden.
- **More mapped fields (#523).** Actual charge rate (folded into the charge-rate sensor), comfort settings (climatisation-at-unlock, mirror heating, front climate-zone enable) and the start/stop charging action. Diagnostic, disabled by default; nothing hidden.
- **More mapped fields (#528).** Start/stop modification, hood state, front tyre pressures, and the last-trip gas / range-gain / zero-emission aggregates (the short-term counterparts to the lifetime figures). Diagnostic, disabled by default; nothing hidden.
- **Audi next-charging-timer fallback (#530).** Some Audis report the charge-timer id + target-SoC-reachable under a different container than the integration was reading, so the sensor stayed empty. Now read as a fallback — the existing 'target SoC reachable' sensor populates. No new entities.
- **More mapped fields (#535).** App/master data-result status enums now surface as diagnostic sensors (disabled by default). With this, the recurring VW-EU Scout reports are down to genuine envelope metadata only.
- **More mapped fields (#537).** The next-charge-timer slot number (which of the profile timers is next) now surfaces as a diagnostic sensor (disabled by default).
- **More mapped fields (#538).** Rear + spare actual tyre pressures (the front pair shipped earlier) and the full target/required tyre-pressure set now surface as diagnostic sensors (disabled by default, unit ambiguous so unitless).
- **EU portal values could disagree with each other (#529).** Battery level, odometer and "last seen" were each read independently from the portal's multi-snapshot export, so they could come from different moments — wrong/uncorrelated readings and even a phantom "moved overnight". Now every field is taken from its latest sample so they stay in sync; the odometer's never-go-backwards guard now lives at the cross-poll layer where it belongs. (VW EU portal only; the BFF path was unaffected.)

## [2.15.3] - 2026-06-26

### Added

- **~28 more EU Data Act portal fields mapped (#465, #514, #515, #516).** Selected charge mode, max AC charge current, auto-unlock charge port, battery-care mode, bulk-charge threshold, door/closure safe-states + bonnet lock, sunroof / service-hatch / spoiler state, trip-odometer endpoints, fuel level + oil / AdBlue (SCR), per-corner tyre-pressure differentials, the instrument-cluster warning indicator, and more — now surface as (mostly diagnostic) sensors, named in all supported languages. Low-confidence fields are disabled by default; nothing is hidden — anything still unmapped stays visible in the Scout.
- **Vehicle model shown in the Scout / Error reports.** The auto-filed issue title and body now include the vehicle model (e.g. "…on volkswagen ID.4"), so reports are recognisable at a glance. Model name only — no VIN or other personal data.
- **More mapped fields + surfaced entities (#517).** `hv_soc` (folds into State of Charge), long/short-term auxiliary and gas consumption averages, range-gain and zero-emission distance, and the charger-update trigger; plus new sensors for battery available/capacity energy (kWh), Škoda trip costs, and oil level (%). Opaque/heartbeat fields (`scope_potential_total`, `echo`) stay Scout-only.
- **MBB durable-login setup translated** into French, Spanish, Dutch, Polish, Czech and Swedish (was English-only).

### Fixed

- **VW US/Canada EVs: battery, range and charged energy now populate (#503).** v2.15.2 read these from the wrong endpoint (`…/hvbattery` is only the departure-timer "use HV battery" toggle) and from guessed field names, so nothing filled. Verified against the dismantled MyVW app: the EV State of Charge, range and charged energy live on the charge-summary `batteryStatus` object (`currentSOCPct`, `cruisingRange.range`, `chargeEnergy`), and the charge-complete time field is `remainingChargingTimeToComplete` (the prior `_min` suffix never matched). All corrected.
- **Charging error code:** a `0.0` value is now treated as "no error" instead of surfacing a bogus code.
- **Charged energy is per-session, not lifetime (#511).** The portal's `charge_energy` (and the VW US/CA charge value) is a current-session gauge that reads 0 when idle — it was mislabelled onto the lifetime **Total Charged Energy**, and now feeds the per-session **Charged energy** sensor where it belongs. The lifetime total stays sourced only from genuinely cumulative fields (CUPRA/SEAT/Škoda).
- **Volkswagen EU login uses the current app version** (User-Agent We Connect 3.63.2; a stale 3.61.0 was still riding the login/data path while the command path already used 3.63.2).
- **Robustness (full-codebase audit).** The VW US/Canada vehicle model now appears in Scout/Error reports; the climate / on-board-electronics energy fields now populate (were mapped to non-existent keys); de-duplicated two sensor definitions; and a charging-state sentinel value can no longer hide an unrelated field from the Scout.

## [2.15.2] - 2026-06-25

### Added

- **More charger-detail fields (#513).** External power supply state, energy flow, charging reason, charging error code, remaining-time charge target, and the charge-port LED (colour + pattern, disabled by default) now surface as (mostly diagnostic) sensors. The keep-alive `echo` field and raw IDs stay Scout-only.

### Fixed

- **VW US/Canada EVs showed no battery or range (#503).** The EV traction State of Charge and electric range come from the dedicated `…/hvbattery` endpoint and `cruiseRangeFirst`, not the 12V `rvs.batteryStatus` / bare `cruiseRange` we read before. The integration now reads both (additive fallbacks), verified against the MyVW app. Confirmed against the dismantled MyVW APK.
- **Charging / climate remaining-time read as seconds (#511).** The EU Data Act portal sends these durations as seconds with a trailing `s` (e.g. `"2400s"` = 40 min, `"0s"` = 0); v2.15.1 read them as a plain number and left the sensors empty. They now convert `Ns` → minutes, and the climate-time read also accepts the `remaining_climate_time` key. A bare number is still treated as minutes (older firmwares). Thanks to @Ra72xx for the sample data.

## [2.15.1] - 2026-06-25

### Added

- **Volkswagen US/Canada: region selector.** Setup now asks US vs Canada, so Canadian accounts authenticate against the Canadian backend and client id instead of silently defaulting to the US one (which made Canadian logins fail). Existing entries keep working (default US). (#503)
- **~30 more vehicle-data fields mapped.** Many fields the Vehicle Data Scout surfaced now become proper sensors — charge type / scenario / reason, charged energy, battery-care target, available & maximal energy content, trip and lifetime consumption + recuperation, parking brake and lights, per-corner tire-pressure status, LPG/CNG, engine status and more (several diagnostic or disabled-by-default). Nothing is hidden — anything still unmapped stays visible in the Scout. (#504, #508, #509, #510)
- **EU Data Act portal: charged energy.** The older charger format also reports `battery_state_report.charge_energy`; it now maps to the cross-brand charged-energy sensor (`total_charged_energy_kwh`), the same one CUPRA/SEAT already populate.
- **volkswagen.de setup now states the prerequisite.** The opt-in Volkswagen.de website channel returns no data unless your Volkswagen ID is the vehicle's **primary user** — the setup screen now says so (complete "Confirm identity" once on volkswagen.de). Added in all supported languages.

### Fixed

- **Target SoC (and other repeated fields) could show a stale value (#465).** The EU Data Act portal ships a flat, ordered event-log where each snapshot's capture time arrives as its own `car_captured_time` data-point. When a field changed across snapshots (e.g. battery-care lowering the charge target from 100% to 80%), the parser tied on the dataset-level timestamp and kept the first-seen (stale) value. It now carries the running `car_captured_time` so the value from the latest snapshot wins. Thanks to @RaAdNe for the precise diagnosis and data.

### Docs

- Regenerated the 6 language READMEs (fr/es/nl/pl/cs/sv) from the current English README — localized the sponsor text (was English), corrected the install steps to HACS Default, fixed the language picker; removed the orphan `README.en.md`.
- `NOTICE.md`: corrected the copyright footer to GNU AGPL v3.0-or-later (was Apache-2.0); added Bentley to the trademark table; replaced placeholder reference URLs with plain-text credits.
- `ATTRIBUTION.md`: use the current display name "VW Group Connect" as the primary name (keeping "VAG Connect" in the protected-names list).
- `CONTRIBUTING.md`: added Bentley to the live-testers table.

## [2.15.0] - 2026-06-25

First stable release of the 2.15.0 line (consolidates the `2.15.0a*` / `2.15.0b*` betas). Highlights:

### Added

- **Command channel for portal-primary setups (opt-in).** Climate and charging commands now work for accounts whose data comes from the EU Data Act portal, via a second sign-in on a durable command backend. Opt-in per entry; existing read-only setups are unchanged.
- **Portal-safety / last-known-good cache.** Each vehicle's last good readout is cached locally and restored across restarts, so a momentary empty/failed portal fetch no longer blanks your dashboard — values carry forward (the odometer never goes backwards) until fresh data arrives, and the failed poll just feeds the staleness watchdog.
- **More fields surfaced.** The Vehicle Data Scout no longer hides any portal field, and the older VW EU charger format now maps its battery level to State of Charge.

### Fixed

- **VW US/Canada login (#503).** Two separate causes — an over-widened OAuth scope and a stale, separate sign-in client-id — both removed; the North-America flow now matches the live MyVW app end-to-end.
- **Duplicate / stale portal fields (#465, #504).** Reworked the portal field de-duplication so the freshest value wins and array-nested fields don't collapse onto the wrong key.
- **App-identity refreshed** to current builds (We Connect 3.63.2, myAudi 5.5.1) so the command/data endpoints stop rejecting stale versions.
- **Škoda lock/unlock** uses the current PIN field name.

### Changed

- **Honest CUPRA/SEAT command status.** Those brands' command backend is now gated server-side (App Check + WAF); the integration says so plainly instead of silently failing. Data continues via the EU Data Act portal.
- **MEB "commands unavailable" notice** surfaces as a Home Assistant repair when a newer MEB car can't use the legacy command channel.

## [2.15.0b14] - 2026-06-25

> **Beta / pre-release** — the actual fix for VW US/Canada login (#503).

### Fixed

- **VW US/Canada login (#503) — the real cause.** b13 reverted an over-widened OAuth scope, but sign-in still dead-ended at VW's North-America sign-in service with "no code in …/signin-service/v1/b680e751…". The real culprit was a stale, separate "browser" client-id (`b680e751…`) that was used *only* to build the NA sign-in URL — but the current MyVW app uses the same app client all the way through. Removed that stale override so the sign-in now uses the real per-country MyVW client; confirmed against the live MyVW app (its code has zero `b680e751` / `identity.na` literals) and an independent working US setup. (A live US/CA login confirms the close.)

## [2.15.0b13] - 2026-06-24

> **Beta / pre-release** — one car, reads *and* commands: the EU Data Act portal for data + a durable-MBB command channel on top. And a simpler 2-path setup.

### Added

- **The setup login is now two clear paths.** "Browser-Login (QR)" for Audi / Škoda / SEAT / CUPRA (passwordless, two-way native), and "Portal (E-Mail + Passwort)" for Volkswagen EU / Porsche. The standalone "MBB durable login" and "Volkswagen.de" menu entries are gone — MBB is now a toggle on the Portal path, and vw.de stays an options-only extra read channel.
- **MBB remote commands on a Volkswagen portal entry.** On the Portal login you can tick "Enable MBB remote commands"; after the email/password sign-in it adds one QR confirm and arms a durable-MBB command channel **alongside** the portal. Result on one device: reads come from the EU Data Act portal, and lock / climate / charge / target-SoC / window-heating commands go through MBB. The MBB bearer refreshes itself (survives restarts). If the car turns out to be MBB-ineligible (newer ID/MEB), the portal entry is still created — you just get reads without commands, instead of the whole setup failing.
- **Portal-safety: your recorded values now survive an outage *and* a restart.** The integration keeps a small local cache of each car's last-known telemetry. When a poll comes back empty or partial — a common thing on the EU Data Act portal — it no longer blanks the fields it didn't get this time: SoC, odometer, range, fuel, service intervals and the like stay visible at their last recorded value until real new data arrives. That cache is now written to disk, so after a Home Assistant restart your dashboard shows the recorded values immediately instead of "unknown" until the first poll finishes. Volatile states (locks, charging, doors) are deliberately *not* carried forward — a stale "unlocked" would be misleading — so those still reflect the latest poll.
- **A backwards odometer reading is rejected.** The portal occasionally serves a stale or zero mileage, so the "km" sensor would jump down and then back up. It now keeps the recorded value whenever a fresh reading is lower than what we already have, so the odometer only ever moves forward.
- **A clear notice when an MEB / ID car can't do remote commands.** If you enable MBB commands on the Portal login but the car turns out to be an MEB / ID-family model (ID.3/4/5/7, Enyaq, Born, Q4), commands aren't possible — VW's MEB backend doesn't speak the durable command path. Instead of silently missing the lock/climate/charge entities, the integration now creates the read-only entry **and** raises a clear repair explaining it's a known MEB limitation, not a setup error. The README also gained a "Known limitations" section spelling out MEB, the CUPRA/SEAT command block, and the portal's thin-and-growing data.

### Changed

- A Volkswagen portal entry that has the MBB command channel armed is no longer forced read-only — its command entities (lock/switch/climate/buttons) now appear. A portal entry without the command channel stays read-only as before.
- **The Vehicle Data Scout no longer hides any fields.** b10 had started filtering "plumbing" fields (request ids, envelope timestamps, and the like) out of the Scout report — that was the wrong call, because it also hid things worth mapping. The Scout now surfaces *everything* the portal sends, so nothing gets quietly dropped before it can be turned into a real sensor.
- **A device-attestation block on commands is now reported honestly.** VW is rolling Firebase App Check / Play Integrity across its backends (it already killed CUPRA/SEAT reads). If that ever reaches a command channel, the 403 used to be mislabeled as "not entitled" — sending you to chase a subscription renewal that wouldn't help. It's now recognised from the response body as an attestation lock and surfaced as exactly that: commands gone on that channel, reads continue. (No current channel is affected — this is so the day it happens, the message is the truth.)
- **VW EU command headers now track the current We Connect app version.** The app-identity the integration presents to VW's command endpoints was pinned at an old build (3.51.1); it's bumped to the live `com.volkswagen.weconnect` version (3.63.2, confirmed by dismantling the current APK). These endpoints can reject stale app versions, so tracking the real build keeps the command path healthy — and a regression test now pins it so it can't quietly drift stale again.
- **Audi app-identity refreshed to the current myAudi build, everywhere.** All four places the integration claimed to be the myAudi app were stale (4.31.0 / 4.24.0 / 4.18.0); they're now the live `de.myaudi.mobile.assistant` version 5.5.1 (versionCode 800344232, verified against the dismantled APK manifest) — the brand config, GraphQL headers, the MBB app-identity and the market-config fetch. Same rationale: stay indistinguishable from the real app so a future version check can't lock us out. Pinned by a regression test.
- **The CUPRA/SEAT "online services blocked" notice now names the real cause and is honest about it.** Reverse-engineering the current apps confirmed VW's block is **device attestation** (Firebase App Check / Play Integrity) plus a web-application firewall on the SEAT/CUPRA backend — not a header or app-version problem, and not something an open-source client can reproduce. The repair message (all 9 languages) now says exactly that and sets honest expectations: remote **commands** for these brands are unlikely to come back, while vehicle **data** keeps flowing through the EU Data Act portal. Also documented the dismantle-verified fallback OAuth client-ids (for the `client_id` override option) in case VW ever blocklists a primary. (#464)

### Fixed

- **Volkswagen US / Canada login was broken (#503).** A v2.11.0 change widened the North-America OAuth scope from `openid` to `openid profile cars vin` based on a source-read that was never live-tested against the NA backend — and it silently regressed sign-in: the authorize redirect stopped returning a code, so login failed with a misleading "email or password wrong". Reverted to bare `openid`, which is **confirmed against the live MyVW app** (the dismantled APK carries `openid` as its only OAuth scope; the wider chain appears nowhere) and matches the value an NA tester verified in #269. (Canada keeps its own app client-id, which the APK confirms is genuine — it wasn't the cause.)
- **Wrong value shown when VW sends duplicate data points (#465).** The EU Data Act portal sometimes returns several data points with the *same* name (e.g. multiple SoC or target-SoC candidates). We were resolving ties by array order, so a stale duplicate could win — one reporter's ID.5 showed 80% SoC while the car and app showed 90%. Now duplicates are resolved by each point's own capture time (a genuine timestamp beats the shared dataset floor; the newer of two real timestamps wins; with neither, the first is kept deterministically), and a field nested inside an array (like a charge profile) no longer collapses onto the active top-level value.
- **State of charge now shows for cars on the legacy charger format (#504).** Some VWs report the traction battery only as `battery_level_HV` (the old Car-Net charger report) instead of the standard field, so their SoC sensor was blank. It's now read as a last-resort source — cars that send the standard field are unaffected, and the duplicate-resolution above keeps the freshest reading.
- **Škoda unlock now sends the correct S-PIN field.** A reverse-engineering pass against the current MyŠkoda app showed its unlock body uses the wire key `currentSpin` (and never a bare `spin`) — our old `spin` key was being rejected by Škoda's backend, so unlock-with-PIN failed. Fixed to `currentSpin`. (Lock is unaffected — it needs no PIN.)

## [2.15.0b12] - 2026-06-23

> **Beta / pre-release** — the EU Data Act portal as a *supplementary* read channel now actually delivers data (e.g. portal reads alongside MBB commands).

### Fixed

- **Adding the EU Data Act portal as a read channel on a non-portal entry (e.g. an MBB command entry) returned no data — silently.** The portal only delivers while an active "continuous data request" exists for the car, and the request kickoff was only ever run for a portal-*primary* entry. So a portal *supplementary* never got a request → it logged in fine but every read came back empty, with nothing in the log to explain it. Now the kickoff also runs for a configured portal supplementary (it shares the signed-in session), and the "no active data request" notice is surfaced for the supplementary channel too, so it's no longer a silent dead end. **Note:** the kickoff is still opt-in — turn on "EU Data Act: automatically create a custom data request" in the options for the channel to populate (it starts a 1-month data subscription on your portal account).

> **Beta / pre-release** — keeps a durable-MBB entry alive (it was going stale ~an hour after setup).

### Fixed

- **Durable-MBB entries stopped working about an hour after setup.** The MBB bearer was only ever refreshed when a request came back with "expired" — but the main MBB reads deliberately don't trigger a refresh on a rejection (to avoid hammering the login endpoint when the car's data access is simply restricted). The result: once the bearer actually expired, every read failed with "token expired" until a restart. It's now refreshed proactively, just before it expires, so an MBB entry (and its remote commands) stays alive on its own. This is what makes the "commands via MBB + reads via the EU Data Act portal" combination usable unattended.

### Security

- **The EU Data Act portal password was stored in the clear in the diagnostics download.** The supplementary-channel credentials added in b8/b9 (portal email + password, and the vw.de session cookies, which carry the sign-in tokens) were never registered with the diagnostics redaction, so a downloaded diagnostics file exposed them in plaintext — the very file users attach to bug reports. They're now redacted like every other secret. **If you added a portal or vw.de read channel on an earlier 2.15.0 beta, change that portal password** and don't re-share any diagnostics you exported from those builds.

### Added

- **You can now remove a supplementary read channel.** Until now the vw.de and EU Data Act portal read-channel toggles could only ADD a channel — once added there was no way to turn one back off, so a redundant or no-longer-resuming channel kept retrying (and showing a "re-add" repair) on every restart. The options now show a "Remove …" toggle for each channel that's currently active; ticking it clears that channel and reloads, and any leftover "re-add" repair is cleared with it.

## [2.15.0b10] - 2026-06-23

> **Beta / pre-release** — EU Data Act portal: many more signals mapped, a lock-state bug fixed, and a tidier Scout. (Includes the b9 vw.de silent-resume fix.)

### Fixed

- **The "doors locked" sensor could read *unlocked* on a locked car.** The portal reports each door's lock state individually (and no single overall flag), which we weren't reading — so the lock sensor fell back to a stale/empty value and showed unlocked. It's now derived from the actual per-door lock states, so a fully-locked car reads locked.

### Added

- **Lots more from the EU Data Act portal, now as proper sensors.** Per-door open + lock states, the tailgate and bonnet, per-window open/closed + how far each window is down, last-trip distance & duration, lifetime average speed & driving time, average monthly mileage, an inspection-due warning, and remaining charge/climate time — all read from the portal and mapped onto the right entities (enum meanings + units taken from the official data dictionary).
- **The Vehicle Data Scout report now shows the official spec name** for each unknown field (it was blank before because the lookup didn't match the portal's field names).

### Changed

- **The Vehicle Data Scout is less noisy.** Pure plumbing / identity fields (request ids, hashed account id, VIN, envelope timestamps, measurement-quality flags) are no longer reported as "new fields" — only real vehicle signals are.

## [2.15.0b9] - 2026-06-23

> **Beta / pre-release** — the vw.de channel finally resumes silently (no more code-email on every restart).

### Fixed

- **vw.de no longer asks for a new email code on every reload.** The session now resumes through a silent re-authorization (it re-uses the long-lived sign-in cookie to mint a fresh session in the background), instead of probing a data endpoint and falling back to a full login when that probe failed. The data probe was the wrong test — the portal session quietly expires about half an hour after sign-in even while the underlying sign-in is still good, so it kept forcing a needless code-email. The silent resume only ever asks for a code when the sign-in itself has genuinely expired (a one-time re-add), never on a routine restart. Applies to both the vw.de primary mode and the vw.de supplementary read channel.
- **vw.de reads were silently coming back empty.** Every request now sends the CSRF token the portal expects (echoed from its cookie), which the reads require — without it the portal answered with empty data.

## [2.15.0b8] - 2026-06-23

> **Beta / pre-release** — the real two-way + reads combo: EU Data Act portal as a supplementary read channel.

### Added

- **Add the EU Data Act portal as a read channel on top of a command-capable entry (e.g. durable MBB).** MBB gives you remote commands and fuel but can't read SoC / charging / odometer / service; the portal can. Tick "Add an EU Data Act portal read channel" in the options, sign in with email + password (no one-time code), and the portal's reads are merged onto your primary channel — so you get commands *and* full data on one device. Read-only, email/pw with automatic re-login (reliable, unlike the OTP-bound vw.de channel), and it never touches command routing. The merged "Data source channel" sensor shows both channels contributing.

## [2.15.0b7] - 2026-06-23

> **Beta / pre-release** — event-loop hygiene.

### Fixed

- **No more "blocking call" warning from the data dictionary.** Once the Scout report started naming portal fields from the dictionary, the first lookup read the 288 KB spec file on the event loop. The cache is now warmed off-loop at setup, so the in-poll lookups never block.

## [2.15.0b6] - 2026-06-23

> **Beta / pre-release** — service-countdown sign fix, no more vw.de code-email storm, unmapped fields in the Scout.

### Fixed

- **Service & oil-change countdowns now read correctly.** They were showing as overdue (negative) when the car actually has them coming up — the portal reports these as a negative "remaining until due", so "due in 155 days / 14900 km" was landing as −155 / −14900. Now flipped: a positive countdown, and only genuinely-overdue cars go negative.
- **The vw.de channel no longer triggers a new code-email on every poll.** When its session couldn't be resumed it kept starting a fresh login, which made Volkswagen send a new one-time-code email each cycle. It now only probes (no email) and raises the re-login repair once — re-add it from the options when you're ready, no more code-email storm.

### Changed

- **Unmapped portal fields now also show up in the Vehicle Data Scout report**, not just on the raw-fields sensor — so the long tail of fields we haven't curated yet is visible and one-click reportable, which is how more of them become proper sensors over time.

## [2.15.0b5] - 2026-06-23

> **Beta / pre-release** — more service data straight from the portal + graceful vw.de re-login.

### Added

- **Service & maintenance intervals, lock status and window heating now come straight from the EU Data Act portal.** The raw-field discovery surfaced that the portal already sends inspection + oil-change intervals (distance and days), central-lock state and window-heating state for Golf-class cars — these are now mapped onto the proper sensors, so you get them without needing the separate vw.de channel.

### Fixed

- **The vw.de read channel now fails gracefully instead of silently.** When its session can't be resumed without a fresh one-time code, it raises a clear "Volkswagen.de read channel needs re-login" repair you can act on, rather than just logging "stale". The primary channel is unaffected, and the repair clears itself once the channel is back.

## [2.15.0b4] - 2026-06-23

> **Beta / pre-release** — supplementary-channel resume fix.

### Fixed

- **The supplementary vw.de channel now resumes from freshly-added cookies.** Even after re-adding the channel, it kept reporting "cookies stale" — the cheap resume probe returns a redirect for a valid session, and the supplementary path gave up on it instead of trying the full silent login (which a valid session completes without an OTP). It now falls back to that login exactly like the primary vw.de channel, so a freshly-added channel arms and merges. If the session is genuinely dead the log now says why (`login=otp_required` → re-add), and the primary channel is unaffected either way.

## [2.15.0b3] - 2026-06-23

> **Beta / pre-release** — declutter: hide entities without data.

### Added

- **Entities without data are now hidden by default, so a vehicle isn't flooded with dozens of "unknown" sensors.** Only sensors and binary sensors that actually have a value are created; an entity still appears automatically the moment its value first arrives (the dynamic spawner now re-evaluates every poll and tracks entities individually). Controls (lock, climate, buttons, …) are never affected. Untick **"Hide entities without data"** in the integration options if you'd rather see everything.

## [2.15.0b2] - 2026-06-23

> **Beta / pre-release** — hotfix for the b1 multi-channel live test.

### Fixed

- **The supplementary vw.de read channel now arms reliably alongside an EU Data Act portal entry.** In b1 the supplementary channel reused the shared session, and because vw.de and the portal share the same login host and cookie names, importing the vw.de cookies clobbered the portal's — the resume probe failed ("cookies stale") and the merge never ran. The vw.de channel now uses its own isolated session, so the two channels can't interfere; this also clears the duplicate-entity warnings that the cookie clash could trigger. Update and restart — the saved cookies should now resume directly (re-add the channel only if they've genuinely expired).

## [2.15.0b1] - 2026-06-23

> **Beta / pre-release** — bundles the unreleased a11–a13 work plus the EU Data Act read-path expansion, the official data dictionary + raw-field discovery, the multi-channel merge with a live vw.de opt-in, and reliability hardening. Install via the HACS beta channel to test.

### Added

- **Rich EU Data Act reads for legacy & PHEV cars, with miles→km auto-conversion.** Flat field names used by older Golf GTE and PHEV vehicles now map cleanly — fuel level, oil level, outside temperature, service intervals — instead of being silently skipped. Distance units are detected and converted (miles → km via the companion unit field) so readings land in the car's market unit. Drivetrain detection now infers electric/combustion/hybrid from the data present, fixing EVs shown as combustion-only and PHEVs as neither.
- **The official EU Data Act data dictionary (V5.0, 1142 fields).** The Vehicle Data Scout report now names an unmapped field from the official spec when its path is a known identifier — opaque UUIDs become human names for maintainers.
- **Raw field discovery — one diagnostic sensor for unmapped portal fields.** A single disabled-by-default sensor per car shows how many portal fields aren't curated yet, with the full value set in its attributes. Same detection that feeds the Scout, so you see every value the backend sent without waiting for a curated mapping — and without an entity per field. Available in all 8 languages.
- **Multi-channel data merge with provenance.** For cars whose data is split across channels (fuel on one, SoC on another, odometer on a third), a field-level union now gap-fills in priority order — the highest-trust channel is never overwritten — and records which channels contributed in a new "Data source channel" diagnostic sensor.
- **Live multi-channel polling: opt-in vw.de read channel.** A new "Add a Volkswagen.de read channel" option pulls VIN / odometer / service / master data from volkswagen.de in parallel and merges it onto your primary channel. Read-only, Volkswagen-only (email + email-OTP). Single-channel setups are byte-for-byte unchanged, and it fails gracefully if vw.de is unavailable.
- **MBB "two-way available" diagnostic sensor.** Tells you when the durable Car-Net backend grants a remote command (climate/charge) on a currently-licensed service — derived from the operation list, no extra request, icon-only.
- **Charge-rate and plug-connection mapping** from the EU Data Act portal, plus the energy-dashboard tip in the README (use the cumulative charged-energy sensor, not the per-100 km averages). Bentley added to the brand table.

### Fixed

- **Account rate-limit protection.** When the backend hard-limits (HTTP 430, or 429 after retries are spent), the integration now pauses all requests on that account for a cool-down (429 → 30 min, 430 → 2 h) instead of hammering and risking an IP ban. Self-clears on expiry.
- **Bogus "no reading" values no longer reach your dashboard.** Portal sentinel markers (65535 / 2147483647 / 4294967295, −1 charging-time, 0/1 tyre-pressure) are filtered out instead of poisoning SoC / range / odometer statistics. The odometer also never jumps backwards — monotonic fields keep the highest reading regardless of delivery order — and bare fields inherit the dataset capture time so the freshest snapshot wins.
- **Per-session/trip kWh deltas no longer carry the energy device-class** (HA 2026.6 rejects energy + measurement together).
- **No source-aliasing in the merge** — gap-filled list/dict fields are deep-copied so a merged result can't be corrupted by a later change to a source snapshot.

### Changed

- **VW enum labels shortened for display** (strip CHARGE_STATE_/CHARGING_MODE_/PLUG_STATE_… prefixes) so charging state reads cleanly — display only, logic unchanged.
- **Coordinator passes its config entry explicitly** (HA 2026.8 readiness).
- **Automatic discovery of unmapped portal fields** keeps logging the long tail so coverage grows from real payloads, not guesswork. Test suite modernized for Python 3.14.

## [2.15.0a10] - 2026-06-22

> **Alpha / pre-release** — reliability batch (from the failsafe audit + a tester log).

### Fixed

- **Vehicle entities keep their last values during a portal outage instead of going blank.** When the EU Data Act portal times out or is briefly down, the car's sensors used to flip to unknown for that cycle (and the "last updated" time falsely reset to now). The integration now recognises a no-data poll and keeps the previous values visible (marked stale) — so a portal hiccup no longer blanks your dashboard. A brand-new car with no data yet still appears and fills in as before.
- **MBB no longer hammers the login endpoint when a read is blocked.** On the durable-MBB path, a blocked status read could trigger a token refresh every poll, which tripped the safety guard ("pausing to prevent IP ban"). Those reads no longer refresh on a block, so the integration stops risking a rate-limit / IP ban while the read channel is unavailable. The scheduled refresh still keeps the session fresh.

## [2.15.0a9] - 2026-06-22

> **Alpha / pre-release** — small fix from a tester report (#442).

### Fixed

- **Climatisation no longer shows as "on" when the car can't actually start it.** On some Audi/VW cars the climatisation status comes back as `invalid` — a no-data state the car returns when climatisation can't run, e.g. at a low battery. The integration was treating anything that wasn't an explicit "off" as "running", so the climatisation binary sensor flipped on by mistake. It now treats those no-data states as off, so the sensor reflects reality.

## [2.15.0a8] - 2026-06-22

> **Alpha / pre-release** — small but important UX fix from a tester report (#498).

### Fixed

- **The MBB login now tells newer ID / MEB owners why it can't work, instead of looping the VIN screen.** If the durable MBB login returns `Unknown user`, that means the car is a newer ID.3/4/5 / MEB model that was never enrolled in the legacy Car-Net backend — so the durable login + remote commands genuinely can't reach it. Instead of bouncing you back to the VIN form with a cryptic error, the flow now stops with a clear message pointing you to the EU Data Act portal (or email + password) for those vehicles. The MBB login is for older Car-Net cars (most PHEV / combustion models).

## [2.15.0a7] - 2026-06-22

> **Alpha / pre-release — the "Endstufe" two-way test.** The deep dive settled what the durable VW login can and can't do, and this build ships the part that genuinely works durably: **remote commands**. No re-add needed — update and restart, then try a command.

### Added

- **Durable two-way commands over the MBB login: climate, charging and charge target.** The investigation proved the durable (password-free) VW login can't *read* live data — VW closed that path for this token type — but it CAN issue **commands** (the command path does an extra authorisation step that reads don't). So with the MBB login + your S-PIN you now get durable **climate start/stop, window heating, charging start/stop, and set charge target %** — and these keep working across restarts, no app-attestation, no ~1‑hour re-login.
- **Country-agnostic by design.** Commands are routed through the car's own service directory (the operationList), which hands over the right server per service per market — so this works for German, Austrian, Dutch, etc. VW EU vehicles, not just the Swiss car it was discovered on. Each command is only attempted if the directory says your car+subscription actually allows it (so you don't waste S-PIN tries on a 403).

> ⚠️ **Live-test the commands deliberately.** The command bodies are grounded against the classic Car-Net app + the car's own directory but haven't been actuated on every model — try one (e.g. start climate) and check it acts. A wrong S‑PIN counts toward the 3‑try lock, so the integration refuses to act when the car reports you're down to your last attempt. Reads still come from your other channel (EU Data Act / the existing login) — the MBB login is login + licence + commands.

## [2.15.0a6] - 2026-06-21

> **Alpha / pre-release** — the diagnostics paid off. Live probing revealed the durable VW login works perfectly *and* reads data — the empty status on the test car was simply an **expired We Connect subscription** (every paid service was off). This build reads the car's service directory so it knows that, and tells you instead of failing silently. No re-add needed — update and restart.

### Added

- **The MBB integration now reads your vehicle's "service directory" (operationList).** This is the authoritative list of which connected services your car has and whether they're licensed/active. From it the integration now:
  - **tells you when your We Connect / connect subscription is expired or inactive** — the `subscription_active` / subscription-expiry / days-remaining sensors are populated, and the log says "renew it in the app" instead of dumping cryptic 403 errors;
  - **skips the status read entirely when the subscription is inactive** (it would only 403), so the log stays clean and the poll is faster;
  - lays the groundwork for the full command set later (the directory hands over the exact per-service hosts and the granted remote-commands for climate, charging and timers).

> ℹ️ If your car shows everything "unknown" and `subscription_active` is off, that's the cause — renew We Connect for that vehicle (or test on a car with an active subscription) and the data flows. The durable login itself is working.

## [2.15.0a5] - 2026-06-21

> **Alpha / pre-release** — diagnostics build. a4 got the car to appear via the VIN; now the status read returns nothing, so this surfaces exactly why. No re-add needed — just update and restart.

### Changed

- **MBB status read now logs exactly what the server returns.** Your Golf GTE shows up but all sensors are "unknown" — to pin down whether the status endpoint rejects the token, returns an empty body, or returns data in a shape we don't yet map, the read now logs the host/country it used and, on an empty result, the exact field IDs (or envelope keys) the car returned. This is the same diagnostic approach that pinned the garage issue in one step.

## [2.15.0a4] - 2026-06-21

> **Alpha / pre-release** — second live-test follow-up. The diagnostics from a3 pinned the exact blocker, and this fixes it.

### Fixed

- **MBB: you now enter your VIN directly, and the car finally appears.** The a3 diagnostics showed the durable VW token is allowed to read your *car* but not to list your *account's garage* (the server replied `403 — no permission for systemId XID_APP_VW`). That's expected for this token type — so the MBB login now has a **VIN field**: enter your 17-character VIN (windscreen / registration; comma-separate multiple cars) and the integration uses it directly. Everything car-level — status, and lock/unlock with your S-PIN — works with this token; only the garage *listing* didn't, and the VIN field replaces it.

> ℹ️ **If you already added the MBB login on a2/a3:** delete that entry and add it again with the new "Volkswagen EU — Durable Login (MBB)" option so you can enter the VIN. The browser confirm is quick.

## [2.15.0a3] - 2026-06-21

> **Alpha / pre-release** — follow-up to a2 from the first live test. The MBB durable login itself worked end-to-end (browser confirm → durable token); the only blocker was finding your cars afterwards.

### Fixed

- **MBB: the car list is now looked up with the right country and headers.** On the first live test the durable VW login succeeded but the integration found no vehicles, because the account-list call was hardcoded to Germany (`DE`) and was missing the app-identification headers the VW servers expect. It now reads your account's country from the login token (e.g. `CH` for Switzerland), sends the `Volkswagen`/`myAudi` app headers on every MBB call, and tries the known server/country combinations until your cars appear.
- **Better diagnostics:** if the car list still comes back empty, the log now shows the exact HTTP status for each server/country it tried (instead of a vague "APIError"), so the endpoint can be pinned down quickly.

## [2.15.0a2] - 2026-06-21

> **Alpha / pre-release** — please live-test and report back. Expect rough edges.

### Added

- **Volkswagen EU durable login (MBB) — now a real option in the integration, not just a test script.** There's a new sign-in choice "Volkswagen EU — Durable Login (MBB)": you confirm once in your browser (no password stored in Home Assistant) and the integration keeps a long-lived, self-refreshing session that survives restarts — unlike the read-only portal. Add your S-PIN in the options to also get **two-way lock/unlock**. VW-only, alpha — the status read works best for combustion/PHEV (fuel level, range, AdBlue) for now; EV battery fields via this path come later.
- **Remote lock/unlock over the MBB path**, using the classic security-PIN handshake. The S-PIN is checked locally before anything is sent so a typo can't burn one of your three tries, and the integration refuses to act if the car reports you're down to your last attempt (3 wrong PINs locks it until you reset in the car/app).

> ⚠️ The durable VW path needs a confirmation from your account to fully verify end-to-end on real cars — that's exactly what this alpha is for. If lock/unlock reports a failure with the doors open or the key inside the car, that's the car refusing, not a bug.

### Internal (MBB hardening, pre-release review)

- The MBB session now auto-refreshes when its token expires (previously the durable token could go stale after a restart and the car would show "unknown" until you re-confirmed in the browser — the whole point of "durable" is that it shouldn't).
- Tightened token isolation: several background calls (capability/trip-stats prefetch, the field-probe pass, wake, charging-station lookup) are now skipped for MBB sessions so the MBB token is only ever sent to the MBB servers, never to the (dead, for VW) app backend.

## [2.15.0a1] - 2026-06-20

> **Alpha / pre-release** — ships the latest reverse-engineering findings for live testing. Expect rough edges; please report what you see.

### Added

- **Bentley is now a selectable brand (login + read).** My Bentley runs on the same backend as Audi, so it slots straight in. Two-way (commands) for Bentley is a follow-up.
- **Login resilience for Škoda, SEAT and CUPRA.** If the app's login key ever gets rotated by the manufacturer, the integration now has spare keys to fall back to automatically — so a rotation doesn't lock you out.
- **VW Group app-atlas research** in `docs/research/` — a catalogue of every brand app's login scheme, plus the discovery of a durable, refreshable login path for Volkswagen that gets past the new app-attestation wall. A local test tool (`scripts/mbb_dag_test.py`) lets you verify the VW path against your own account via a confirmation link (your credentials stay in your browser; it never prints tokens).

### Changed

- **Project relicensed to GNU AGPL v3.0-or-later** (was Apache-2.0). Forks must stay open-source under the same license. See [`ATTRIBUTION.md`](ATTRIBUTION.md) for the attribution + naming terms, and consider supporting the project via GitHub Sponsors.

### Fixed

- The advanced OLA User-Agent override for SEAT/CUPRA is no longer silently overwritten, so it actually applies now.

## [2.14.10] - 2026-06-18

### Fixed

- **volkswagen.de website login (beta): the email code is finally accepted instead of looping with a new code every time.** Entering the emailed code kept failing as a "credential issue", and a fresh code was sent after each attempt. The login page's code box isn't always named the same thing internally, and the integration was filling in the wrong one — so the identity service saw an empty code, rejected it, and emailed a new one, over and over. It now fills whichever code box the page actually shows (and ticks "remember this browser" when offered, so the saved session lasts longer). (Opt-in beta channel only.)

## [2.14.9] - 2026-06-17

### Fixed

- **volkswagen.de website login (beta): a restart now actually resumes the session instead of looping / asking for a new email code.** This was the real root cause behind the redirect loop on resume. The single-sign-on cookie that keeps you logged in lives only on the identity host and has no domain attached, so the old code quietly dropped it when saving and never restored it — which meant a restart had no valid session to resume and bounced back to the login page. The login cookies (the SSO one included) are now captured and restored across both hosts, so a restart silently reuses your session. A stale session reported as `412`/`428` (not just `401`/`403`) now also correctly triggers a clean re-login. (Opt-in beta channel only.)

## [2.14.8] - 2026-06-17

### Fixed

- **EU Data Act portal: a slow/unreachable portal no longer errors the whole poll — it just means "no data this poll".** When the portal was sluggish, the request could time out at the network layer (before any response), and that timeout slipped past the retry logic and surfaced as an error (the spike of auto-reported `TimeoutError`s on June 16). Now a timeout or dropped connection is retried with the same short backoff as a transient server error, and if it keeps failing the poll quietly skips and tries again next cycle — instead of erroring or, worse, forcing a pointless re-login. Affects both the data-listing and the dataset-download steps.

## [2.14.7] - 2026-06-15

### Added

- **volkswagen.de website login (beta): redirect-chain debug logging, so a stuck login can finally be diagnosed.** When the website login bounces in a loop, the error message is redacted (it can carry tokens), which made the root cause invisible from a normal log. This adds a `DEBUG`-level, hostname-only trace of the redirect chain (and the resume-probe result) — e.g. `volkswagen.de → identity.vwgroup.io → volkswagen.de → …`. Only hostnames are logged; paths and query strings (where the OAuth `state`/tokens live) are never written. Turn on debug logging for `custom_components.vag_connect` to capture it. No functional change — purely diagnostics for the beta channel.

## [2.14.6] - 2026-06-15

### Fixed

- **volkswagen.de website login (beta) now actually resumes a saved session instead of re-logging-in every time.** v2.14.5 stopped the redirect-loop crash, but it still kicked you back to a fresh email-OTP whenever the resume wobbled. Now, when the integration comes back up it does a quick, redirect-free check against the data endpoint with your saved cookies: if the session is still good it's adopted straight away — no login dance, no OTP — and only a genuinely expired session falls back to a fresh login. As a belt-and-suspenders extra, the credential step also can't get stuck in a redirect loop anymore. (Opt-in beta channel only; no change for any other brand or mode.)

## [2.14.5] - 2026-06-15

### Fixed

- **volkswagen.de website login (beta) no longer crashes with a redirect loop when resuming a saved session.** When the integration came back up and reused the saved login cookies, the website login could bounce in a redirect loop (`TooManyRedirects`) and surface as a bogus "invalid credentials". It now caps the redirects and handles the two real cases cleanly: an already-logged-in session is recognised straight away (no re-login, no OTP), and a stale-cookie loop is reported as a normal "please re-authenticate" instead of a crash. (Opt-in beta channel only.)

## [2.14.4] - 2026-06-15

### Fixed

- **The "Email 2FA required" repair notice stops throwing translation errors for good.** v2.14.3 supplied the missing `{brand}` value, but a notice already sitting in the repairs list from an older version had no value and kept spamming `MISSING_VALUE` in the logs. The notice title no longer depends on a placeholder at all (all 8 languages), so old and new notices both render cleanly, and the repair description now also gets its `{username}` value supplied. Purely a cosmetics/log-noise fix.

## [2.14.3] - 2026-06-14

### Fixed

- **volkswagen.de website login (beta): you only enter the email code once now, not on every restart.** The beta channel logged you in (code and all) when you set it up, but then threw all that away and started fresh every time Home Assistant restarted — which meant it asked for a new email code on every single restart, and if you weren't there to type it in, the integration just got stuck. It now remembers the login session from setup and reuses it, so a restart picks up where it left off instead of pestering you for another code. If the saved session has genuinely gone stale, it falls back to asking you to sign in again, same as before. The session keeps itself fresh in the background after each successful login. (Opt-in beta channel only; still read-only.)
- **Repair notifications show the brand name properly instead of a literal `{brand}`.** A couple of the "please sign in again" repair prompts (including the email-code one) had a `{brand}` placeholder that wasn't being filled in, so the title could read awkwardly. It now drops in the actual brand (or a sensible fallback) so the message reads cleanly.

## [2.14.2] - 2026-06-14

### Fixed

- **volkswagen.de website login (beta): the email code now submits correctly.** The OTP step was posting just the code + state, but the VW identity email-challenge page is a form with hidden fields (`_csrf` / `relayState` / …) that have to come along — without them the code didn't go through cleanly. It now parses the challenge form exactly like the password step does and submits the code inside the real form, so email-OTP logins complete. (Opt-in beta channel only.)

## [2.14.1] - 2026-06-14

### Fixed

- **System Health no longer falsely reports the VW/Audi backend as unreachable.** The connectivity check pinged an old discovery URL (`/login/v1/idk/openid-configuration`) that VW has started answering with a `403` before you even log in — so Home Assistant's System Health card showed the CARIAD backend as "failed" even when everything was working. It now pings the current endpoint (the same one the login already uses), which answers normally.

## [2.14.0] - 2026-06-14

### Added

- **New opt-in beta way to connect a Volkswagen: the volkswagen.de website (read-only).** There's now a third sign-in option when you add a Volkswagen — "Volkswagen.de website (beta)" — that logs in the same way the volkswagen.de "myVolkswagen" web area does and reads your car through it. The point: that website uses its own server-side login, so it goes around the app-attestation wall that's been killing the normal token logins for VW. You sign in with your Volkswagen ID email + password (and an emailed code if your account asks for one), and you get charge level, range, charging state and power, charge target, plus odometer and service-due info. It's **read-only** — no lock/climate/charge commands — and **opt-in**: you have to pick it on purpose. Nothing changes for anyone who doesn't, every existing setup (app login, browser login, EU Data Act portal) behaves exactly as before. It's a beta and hasn't been verified end-to-end against a live VW account yet, so treat it as experimental.

## [2.13.1] - 2026-06-14

### Fixed

- **Fewer dropped polls when the EU Data Act portal is having a moment.** The portal throws transient server errors (500/502/503/504) that come and go within seconds — and until now a single blip meant skipping the whole poll and waiting 15 minutes for the next one. The integration now backs off briefly and retries (a couple of times, a few seconds apart) before giving up as "no data this poll", so a short hiccup no longer costs you a full cycle of data. The "you haven't enabled the data request yet" case (404) still returns instantly with no added delay, and a real auth failure still re-authenticates as before.

## [2.13.0] - 2026-06-13

The EU Data Act portal becomes the **universal read-only safety net**: as VW keeps closing native API access brand by brand (VW EU's token logins are gone, CUPRA/SEAT's online services are now behind a device-attestation wall), each affected brand now degrades gracefully to the read-only portal instead of going dark.

### Fixed

- **CUPRA, SEAT and Škoda now route their data reads through the EU Data Act portal when the portal fallback is active** — not just their login. Until now, when a brand's native backend went dark (e.g. CUPRA/SEAT's online services getting blocked by VW), the login correctly fell back to the read-only portal, but the very next data poll still hit the dead native endpoint — so you'd get a successful login and then no data. These brands now follow the same portal-routing path VW EU already used, both for the vehicle list and the status read. It's the EU Data Act portal becoming the universal read-only safety net: as VW keeps closing native access brand by brand, each one degrades gracefully to the portal instead of going dark. Non-breaking — the native path is completely unchanged whenever the portal fallback isn't engaged.
- **CUPRA/SEAT now actually reach that fallback.** There was a catch: the portal fallback only ever armed when the *login* failed — but for CUPRA/SEAT the login still succeeds and it's only the data call that gets blocked (the 403 device-attestation wall). So the fallback never fired and the previous fix couldn't help. Now, when the native garage call comes back 403 despite a valid login, the integration arms the read-only EU Data Act portal on the spot and serves the vehicle list from there. This is what makes the portal safety net real for the brands that are blocked *today*.
- **Quieter logs in EU Data Act portal mode.** When a car is running on the read-only portal, the integration was still trying the manufacturer-backend "capabilities" call on every setup — which can't work there (the portal session isn't a real backend token) and just logged a `400` every time. It now skips that call in portal mode. Cars on a normal (non-portal) connection are unaffected, including when you've turned on read-only mode yourself.

## [2.12.6] - 2026-06-13

An honesty fix for the CUPRA/SEAT repair notice.

### Changed

- **The CUPRA/SEAT "OLA 403" repair notice now tells the truth.** It used to suggest the app-identifying headers might be outdated and told you to check for an update or try an app-version override — but those 403s are a VW server-side access revocation for SEAT/CUPRA, not anything a header bump or a reconfigure can fix. The notice now says that plainly (in all eight languages), drops the dead-end advice, and notes the integration falls back to the read-only EU Data Act portal where it can (#432, #444, #456, #392).

## [2.12.5] - 2026-06-13

A data-quality patch for the EU Data Act portal, plus a scout-noise fix for Audi.

### Fixed

- **Jumping SoC / odometer on the EU Data Act portal.** The portal ships an unordered event-log, and we were keeping the first value we happened to see for each field (often the oldest), so battery level and mileage bounced around. We now keep the newest value per field by timestamp — the same data-quality problem the whole portal ecosystem hit. Empty / no-content / corrupt portal ZIPs are also handled as "no data this poll" instead of being mistaken for a login failure (which used to trigger a pointless re-login).
- **Audi scout noise on deeper charging timer/profile fields** (#446, #448). The selectivestatus backend started nesting `chargingTimers` / `chargingProfiles` one level deeper (4 segments, e.g. `…Status.value.timers`); registered the deeper wildcards so the Vehicle Data Scout stops re-flagging fields we already read.

### Changed

- Housekeeping: removed an orphaned repair-notice translation key (`data_act_wake_needed`) that was superseded by the "no vehicle data" notice and is never shown. No user-facing change.

## [2.12.4] - 2026-06-09

A resilience release for the ongoing VW-side backend outage: the integration now rides out transient server errors quietly instead of treating them like a broken login.

### Fixed

- **VW portal outage no longer spams errors or triggers needless re-logins** (#428, #429, #430, #431). While VW's EU Data Act portal is in its ongoing outage, the data endpoints keep returning HTTP 500. We were treating that 500 as an authentication failure — so it logged an error every poll and kicked off pointless re-login attempts. A 500 is the portal having a bad moment, not a dead session, so it's now handled as "no data this poll" (the existing "no vehicle data" notice already explains the outage). A genuine 401/403 still re-authenticates exactly as before.
- **Token-refresh hiccups no longer look like a wrong password** (#438). When the VW token server returns a transient gateway error (HTTP 502/503/504) on an otherwise-valid login — common while their backend is flaky — the integration was treating it as an authentication failure: it popped up a "please reconfigure" reauth prompt and filed error reports for what is purely a VW-side blip. Now a 5xx on the token endpoint is treated as "VW backend temporarily unavailable": your entities keep their last value, the integration retries on the next poll, and nothing prompts you to re-enter credentials. A genuinely rejected refresh token (HTTP 400) still triggers a real re-login. Applies to every brand (Audi, VW, Škoda, SEAT, CUPRA).
- **Quieter during outages** (#435, #436, #437, #438, #439). Transient VW-backend 5xx errors — the kind above — no longer get escalated to the in-app Error Reporter. They're a server-side outage symptom, not an actionable bug, and were generating a stream of noise reports. Your entities stay available through the normal failure-tolerance window in the meantime.

## [2.12.3] - 2026-06-08

### Changed

- **Everything's translated now — all eight languages, end to end.** We went through every string the integration shows and filled in the gaps: the newer entity names (battery temperature, climate zones, navigation charge target, parking-map links, plug LED colour, the "command pending" sensors and friends), the little help texts under the login and options fields, the "open the brand app" service, and the repair notices (wake the car, portal session expired, optional browser package missing, OLA headers outdated). Until now anything we hadn't translated quietly fell back to English, so non-English users saw a mix. EN, DE, NL, SV, FR, ES, PL and CS are now complete — with everyday wording for the car terms instead of literal tech-speak.

## [2.12.2] - 2026-06-08

### Added

- **"No vehicle data" hint when the portal is empty.** When the VW EU Data Act portal logs in but returns no data, the integration now raises a clear Home Assistant repair notice instead of staying silent. It explains the likely causes — most often the VW-side portal outage that's been running since late May 2026 (which hits every tool, not just us), or a data request that isn't set up yet — and tells you the quickest check: open the VW data portal in a browser and see whether *you* can see your car's data there. If it's empty there too, it's on VW's side. The notice clears by itself once data starts flowing. Fully translated across all eight bundled languages (EN, DE, NL, SV, FR, ES, PL, CS).

Quick follow-up to the v2.12.0 VW EU portal beta, from the first round of live testing.

### Fixed

- **VW EU portal broke after a Home Assistant restart** (#393). The portal saves a cookie-session placeholder token, and on restart the integration reused it and skipped the login — so the portal session was never rebuilt and the next call hit the old (dead) endpoint with a useless token, ending in "No vehicles found". Now a fresh portal login runs on every restart, so the session is always re-established.
- **"No data request" no longer spams errors** (#393, #424). Until you manually create a continuous data request for your car in the VW data portal, the data endpoint returns 404/500 — that's expected, not a failure. The integration now treats it as "no data yet" (the car still appears, data fills in once the request goes live) instead of logging an error every poll.
- **Scout noise on Audi charging timers/profiles** (#423). Registered the deeper `chargingTimers` / `chargingProfiles` sub-paths and the DC auto-unlock setting the Scout kept flagging.

## [2.12.0] - 2026-06-07

The big one for VW EU. We confirmed live that VW has closed every token-based login route for passenger cars — the hybrid trick another project used now gets a hard 403 from Auth0, the code-flow needs a client secret we can't have, and device-login isn't enabled for the VW client. The only door VW has to keep open under the EU Data Act is the read-only data portal, so that's the path we built.

### Added

- **VW EU Data Act portal connector (read-only, BETA).** A brand-new cookie-based login + data path for VW passenger cars, using the EU Data Act portal. It logs in, pulls the vehicle's data export, and surfaces the high-value bits (charge level, odometer, range, charging state, doors, window heating, temperatures). Trade-offs: it's read-only (no remote climate/charge commands), updates on roughly a 15-minute cadence, and you have to switch on a one-time "continuous data request" on the VW portal first. Kicks in automatically once the old token logins fail. Marked beta — the live login is being validated on #388/#393 before we lean on it.
- **Brand-aware portal config.** The portal connector is wired as a fallback in every brand's login chain, so it now picks the right OAuth client + brand selector per brand (VW, CUPRA, SEAT verified; others fall back gracefully) instead of always using VW's. Foundation for offering the read-only portal path to more brands later.
- **Skoda trip cost.** Total / fuel / electricity / CNG cost for the trip overview, with the currency, when Skoda ships it.

### Fixed

- **Cars stuck showing "online" forever.** Some vehicles report a capture timestamp years in the future (a known broken-clock quirk on certain control units), which pinned the connection state to "online" with a nonsense last-seen time. We now ignore timestamps beyond a 5-minute window. Applies to every brand.
- **Scout noise.** Registered the climatisation sub-blocks (CUPRA/SEAT) and the battery-support / charging-profiles / charging-timers blocks (VW/Audi) the Data Scout kept flagging, so it stops re-reporting fields we already read. Closes the scout reports behind #411, #414, #415, #416, #417, #419.

### Legal

- Added `LEGAL.md` documenting the statutory basis (EU Software Directive Art. 6, §69e UrhG, Art. 21 URG, DMCA §1201(f), EU Data Act Arts. 4–6) and attribution for the open-source projects the portal connector's mechanics were adapted from.

## [2.11.4] - 2026-06-05

Bundle release covering the v2.11.3 fallout. After v2.11.3 unblocked the Auth0 state-token wall, the next bottleneck surfaced: the VW EU signin-service flow is a TWO-step submit (POST email first to get a fresh hmac for the password page, then POST password to a different URL). Plus a handful of upstream-sync fixes for Skoda + small parser additions from the latest scout reports.

### Fixed

- **VW EU signin-service 2-step SPA login** (#388 swebachus, #393 SniperWCW). v2.11.3 extracted hmac + postAction from the templateModel JSON literal correctly but then POSTed the password straight to the identifier URL — got HTTP 405 every time, because the email-page hmac is bound to the identifier session only. v2.11.4 does the full upstream-canonical flow: POST email + identifier-hmac → identifier URL, regex-extract the FRESH hmac out of the response (the password page), swap "identifier" → "authenticate" in the URL path, POST email + password + fresh-hmac + relayState → authenticate URL. Pattern lifted from the audi_services.py implementation.
- **Skoda charging-statistics timezone header**. The upstream charging-statistics replacement endpoint (which we adopted preemptively in v2.11.0) tightened its server-side parser to require `X-Device-Timezone: GMT` instead of accepting any Olson zone. Switched from `Europe/Berlin` to `GMT` so the endpoint stops 400'ing on accounts where the server got picky.
- **SEAT / CUPRA climatisation field-layout for newer firmware** (#411 heidle78 scout). The scout caught two new top-level keys in the climatisation response: `climatisationStatus` (state / remaining-time / outside-temp moved here) and `windowHeatingStatus` (front/rear states moved here). Parser now checks the new sub-blocks first and falls back to the legacy `status`-wrapped layout for older firmwares.
- **Auto-reporter empty-body issues** (#409, #412 — empty bodies). Some browsers silently drop the `body` query param when the final encoded URL crosses 8KB. URL-encoded markdown inflates ~1.5x, so the 6500-char budget we shipped overflowed in some cases. Dropped to 4000 raw → ~6000 encoded so even chatty error reports survive the round-trip.

## [2.11.3] - 2026-06-04

Bundle release. Five fixes spanning SEAT / CUPRA endpoint corrections, VW EU signin-service SPA auth, and Audi token refresh defense. Built from a fresh round of upstream-lib source-walks (pycupra const.py + connection.py, audi_connect_ha audi_services.py, volkswagencarnet vw_connection.py) plus the live diags from #392 (heidle78) and #388 (swebachus).

### Fixed

- **SEAT / CUPRA climatisation read endpoint** (#392 heidle78 v2.11.1 trace). We were hitting `/v2/vehicles/{vin}/climatisation` for the read which 404s — that path is the command prefix only (the start / stop / settings / window-heating POSTs hang off it). The actual read endpoint is `/v1/vehicles/{vin}/climatisation/status`. Restores `climatisation_state`, `target_temperature`, `outside_temp`, `aux_heating_*` etc. on every CUPRA / SEAT that's been silently null for these fields.
- **SEAT / CUPRA door-lock parser presence check** (same trace). The "sub-job absent" failure in `parser_stats.door_lock` was a stats-misclassification — the parser actually populates `doors_locked` + `doors_individual` correctly from `/v2/vehicles/{vin}/status`, but the presence check only looked at `mycar.access.accessStatus.value` which is empty on newer firmware. Check now accepts either source so cars don't show false-positive parser failures in the diag.
- **SEAT / CUPRA `permission_*` + `capabilities_count` plumbing**. The `/v1/vehicles/{vin}/permissions` URL we polled for the `permission_is_owner` / `permission_can_command` entities consistently 404'd in production — the canonical endpoint is `/v1/users/{userId}/vehicles/{vin}/relation-status`. Also added a `capabilities_count` diagnostic sensor for SEAT / CUPRA (already exists for VW EU and VW NA), cached for 24h so we don't hammer the capabilities endpoint on every scan_interval tick.
- **VW EU SPA login on the signin-service flow** (#388 swebachus, Volkswagen ID.7 Sweden). The Auth0 SPA branch we shipped in v2.10.x was Auth0-specific — it hunted for `state=hKFo...` tokens which only exist on the universal-login path, then POSTed to `/u/login`. Users routed through the legacy `signin-service/v1/<client>` flow with a SPA-rendered password page (zero hidden inputs) hit a hard "no Auth0 state token found" error. Now: when the page embeds the `templateModel: { hmac, postAction, relayState, ... }` JSON literal (the SPA shell does), we pull those three fields and POST to the signin-service authenticate URL with the proper body shape. Same approach pycupra and audi_connect_ha use. Also covers a softer fallback (relayState alone via URL / JSON / escaped-JSON) for SPA shells that don't ship a full templateModel.
- **Audi / VW refresh-token defense** (audi_connect_ha upstream PR #749 pattern). When the IDK token endpoint returns a fresh `access_token` but omits the `refresh_token`, we used to hard-fail with `AuthenticationError` and force a full re-login. Some IDK refresh responses do exactly that — the existing refresh-token stays valid for the rotation lifetime. Now: we keep the previously-known refresh-token when the response omits it, instead of throwing the user back to the config flow.

## [2.11.2] - 2026-06-04

### Fixed

- **SEAT / CUPRA trip stats + aux-heating status** (#392 heidle78 v2.11.0/v2.11.1 trace). The trip endpoints we'd used since v1.x (`/trips/shortTerm`, `/trips/longTerm`, `/trips/lastrefuel`) and the standalone aux-heating status endpoint (`/api/auxiliary-heating/v1/{vin}/status`) all 404 on Formentor PHEV firmware — they're not the canonical OLA paths. Replaced with the actual ones the app uses: a single `driving-data/SHORT` for last-trip + lifetime totals + `recent_trips` list, `driving-data/CYCLIC` for per-tank / per-charge refuel events, and the aux-heating sub-block that already comes back inside the existing `/v2/vehicles/{vin}/climatisation` payload (no extra request). Should unblock `last_trip_*`, `lifetime_*`, `refuel_trip_*`, `recent_trips`, `aux_heating_*` on Formentor PHEV and likely every other CUPRA / SEAT that's been silently null since v1.0.

## [2.11.1] - 2026-06-04

### Fixed

- **SEAT / CUPRA `max_charge_current` enum → amperage** (#392 heidle78 v2.11.0 trace regression). v2.11.0's pycupra-verified `settings.maxChargeCurrentAc` reader now correctly hits the canonical key on Formentor PHEV MJ22-23 firmware, but that firmware returns the enum string `"maximum"` / `"reduced"` instead of an integer amperage. The HA `sensor.cupra_max_ladestrom` is registered as `device_class=current, unit=A, numeric` and blew up with `ValueError: could not convert string to float: 'maximum'`. Now: prefer the explicit integer field when present, otherwise map the enum to the canonical amperage values verified against zackcornelius's VW NA APK decompile (`maximum`/`max` → 32 A, `reduced`/`min`/`minimum` → 10 A). Leaves the field `None` when neither path produces a usable value.

## [2.11.0] - 2026-06-04

Cross-brand parser audit against upstream lib source code. Five parallel deep diffs (pycupra, myskoda, volkswagencarnet, audi_connect_ha + CarConnectivity-VW, CarConnectivity-connector-volkswagen-na) surfaced field-name and parsing bugs that have been silently returning null on every car for some time. Bundled into one PR rather than the per-brand hotfix chain pattern.

### Fixed (cross-brand)

- **Skoda driving range fields** (myskoda source-verified). `electricRange.distanceInKm` / `combustionRange.distanceInKm` / `secondaryEngineRange.distanceInKm` are scout-derived paths that myskoda's DrivingRange model does NOT include. Canonical keys are `primaryEngineRange.remainingRangeInKm` + `secondaryEngineRange.remainingRangeInKm` plus an `engineType` enum to decide which is electric vs combustion. Old paths kept as fallback for any firmware that genuinely ships them. `adBlueRange` is a flat int upstream, not a dict.
- **Skoda doors_open / windows_open** were reading from `access.doorsOpenedCount` / `windowsOpenedCount` which do not exist on Skoda mysmob vehicle-status (no `access` subobject). For years these sensors silently reported false. Now reads `overall.doors == "OPEN"` / `overall.windows == "OPEN"` per myskoda Status.Overall model.
- **Skoda driving_score** was reading non-existent top-level `score` / `drivingScoreClass`. Upstream DrivingScore model is per-period (`daily/weekly/monthly/quarterlyScore.main`). Now prefers `weeklyScore.main` then falls back through the other periods.
- **SEAT / CUPRA charging path-prefix** (pycupra source-verified). The canonical path is `charging.status.charging.*` and `charging.status.battery.chargeEnergyInKwh` on Born MY24+. Pre-v2.11.0 we only tried `charging.charging.*` (direct) so `charging_power_kw`, `charging_rate_kmh`, `charging_type`, `total_charged_energy_kwh` were silently null on newer firmwares. Now adds the `.status.` segment as the canonical primary, keeps direct as fallback.
- **SEAT / CUPRA `battery_care_target_soc_pct`** field name. pycupra reads `targetSocPercentage` (no underscores); we previously tried `targetSOC_pct` and other variants only.
- **VW EU / Audi `plug_led_color` double-write bug**. A second unconditional assignment at the end of the charging block overwrote a valid PPE-firmware value (`plugLedColor` on access or chargingStatus) with `None` from `plugStatus.value.ledColor`. Now consolidated into a single defensive chain ordered upstream-canonical-first.
- **VW EU / Audi `battery_care` parent block order**. Volkswagencarnet's `vw_const` puts the canonical path under `batteryChargingCare.chargingCareSettings.*`; we previously tried `charging.chargingCareSettings.*` FIRST and the dedicated batteryChargingCare block was a fallback. Flipped so the canonical wins.

### Added

- **SEAT / CUPRA min_soc** read at `settings.minBatteryStateOfChargeInPercent` on `/v1/charging/info` (pycupra `get_min_charge_level`). Sensor previously stayed null.
- **SEAT / CUPRA climate_remaining_time_min + climate_ready_at** wired. The OLA climate payload already shipped `status.remainingClimatisationTime_min`; we just never read it. Derived `climate_ready_at` ISO timestamp lets HA show a "ready by" clock.
- **VW EU missing selectivestatus jobs**: `activeVentilation`, `batterySupport`, `chargingProfiles`, `chargingTimers`. Without these requested, parsers that read from those blocks (active ventilation state at v2.10.0 Group A, next-charging-timer at #173) returned null on any car whose data didn't happen to ship inside a sibling block.
- **VW EU `measurements.rangeStatus.value.electricRange`** added as a third fallback in the electric range chain. Some pure-EV ID.x firmware ships only this leaf.
- **VW EU / Audi aux-heating legacy fallback** at `climatisation.auxiliaryHeatingStatus.value.*`. Older Audi A4 B9 / MIB3 cars ship aux-heating state under the climatisation parent, NOT under top-level auxiliaryHeating. audi_connect_ha references this legacy path; we missed it pre-v2.11.0.

### Added (cont. - new endpoint integrations)

- **Skoda dedicated warning-lights health endpoint** (`/api/v1/vehicle-health-report/warning-lights/{vin}`, myskoda Health model). Canonical source for dashboard warning lamps with per-category breakdown (engine / brakes / tyre / oil / fluid) and human-readable defect text. Previously the warning_* fields relied on data piggybacking inside other responses.
- **Skoda trip statistics endpoint** (`/api/v1/trip-statistics/{vin}`, myskoda TripStatistics model). Populates `lifetime_distance_km`, `lifetime_avg_fuel_consumption_l_100km`, `lifetime_avg_electric_consumption_kwh_100km` from the overview block plus `last_trip_*` fields from `detailedStatistics[0]`.
- **SEAT / CUPRA aux-heating status read** (`/api/auxiliary-heating/v1/{vin}/status`). We have used this host for start/stop commands since v1.x; the status read now fills in `auxiliary_heating_status`, `aux_heating_active`, `auxiliary_heating_remaining_min`, and `heater_source` which were null on every car before.
- **SEAT / CUPRA trip statistics** via three OLA endpoints (`/v1/vehicles/{vin}/trips/{shortTerm,longTerm,lastrefuel}`, pycupra references). Populates `last_trip_*`, `lifetime_*`, and `refuel_trip_*` with defensive field-name variants for both legacy MBB-suffixed and CARIAD-suffixed shapes.

### Fixed (VW NA - in-place corrections, full rewrite still scheduled)

- **VW NA SPIN flow algorithm + token field** (zackcornelius source-verified). The canonical hash is `SHA-512("{challenge}.{spin}")` (challenge first, period, then spin); pre-v2.11.0 used `SHA-1(spin + nonce)` which fails on modern Cox firmware. SHA-512 is now the primary attempt; the legacy SHA-1 stays as fallback on 4xx so users on older firmware are not regressed. The session token field is `carnetVehicleToken` (NOT `sessionToken`); both are tried.
- **VW NA Canada client_id** at `69eb3c39-d2be-4006-8197-37cc4971e8fe_MYVW_ANDROID`. CA accounts that authenticated with the shared US client_id were rejected on newer firmware.
- **VW NA OAuth scope** now `openid profile cars vin` (was bare `openid`). The NA IDP returns reduced consent + missing claims when only `openid` is requested.
- **VW NA field-name corrections**: `data.location` (not `vehicleLocation`), `data.readiness.readinessStatus.value.connectionState.isOnline` (boolean) as primary online signal, `chargingStatus.currentChargeState` (not `chargingState`), `chargingStatus.chargePower` (not `chargePower_kW`), `chargeSettings.targetSOCPercentage` (not `chargingSettings.targetSOC_pct`), `chargingStatus.currentSOCPct` for battery_soc (was on wrong endpoint), `climateStatusReport.climateStatusInd` (not `climateState`), `data.timestamp` (epoch-ms) as canonical last-seen. `cruiseRangeUnits == "MI"` now converts to km (was silently treated as km, miles users had ~38% underreported range).

### Added (cont. - post-audit upstream sync)

- **Skoda charging statistics endpoint** (myskoda PR #586 source-verified). POSTs to `prod.emea.mobile.charging.cariad.digital/charging_statistics` with a VIN-filtered date range and Skoda-brand headers (`X-Brand: skoda`, `X-Device-Timezone: Europe/Berlin`, `X-Api-Version: 1`). The legacy `/v1/charging/{vin}/history` endpoint started returning HTTP 500 for many users after the Skoda app update on 2026-05-15 (upstream issue #585). The replacement uses `monthSections[].entries[].{primaryValue.value, secondaryValue.value, sessionDetails.startedAt, sessionDetails.currentType}` to populate `total_charged_energy_kwh` (sum across all entries), `last_charging_session_kwh`, `last_charging_session_duration_min`, `last_charging_session_start`, `last_charging_session_current_type`, and a compact `recent_charging_sessions` list. Adopted preemptively because PR #586 has not yet landed upstream but the broken state affects every Skoda user on current firmware.
- **VW EU / Audi `chargeMode` selectivestatus sub-job** (volkswagencarnet PR #328 source-verified, merged 2026-06-01). CARIAD-BFF now exposes a dedicated `charging.chargeMode.value` block carrying `preferredChargeMode` + `availableChargeModes`. Independent of the auth crisis - this is a real additive backend change. Now populates `charging_preferred_mode` and `available_charge_modes` for VW EU / Audi vehicles (CUPRA / SEAT have already shipped these from OLA endpoints since v2.10.0).

### Verified aligned with upstream (no action required)

- **SEAT / CUPRA `app-market: android` header** already set in `_ola_headers.py` for both brands since v2.1.x. Aligned with pycupra v0.2.30 403 fix.
- **`tokentype: IDK_TECHNICAL` header** is not set anywhere in our codebase. Aligned with volkswagencarnet v5.4.7 removal.
- **VW NA OAuth scope** confirmed `openid profile cars vin` against zackcornelius HEAD source — both repo source and live API behavior verified.
- **VW EU auth situation**: refresh tokens dead, Play Integrity X-Assertion required, Python cannot bypass. Confirmed wide community consensus (volkswagencarnet pinned #989, o11e's APK Frida writeup, evcc-io). Our Data Act portal fallback is the realistic ceiling.
- **Skoda mysmob charging-history /v1/charging/{vin}/history**: upstream broken with HTTP 500 since 2026-05-15 (myskoda issue #585). We adopt the in-progress fix from myskoda PR #586 (rsa-wusel APK reverse-engineered) preemptively because the upstream-broken state hits every Skoda user on 2026-05-15+ firmware.

### Still pending (separate PRs scheduled)

- **VW NA write-side full rewrite** (lock/unlock HTTP verbs, set-target-SOC method + body shape, climate-settings PUT shape, departure-timer shape). zackcornelius HEAD now has the APK-decompiled reference: `GET /ss/v1/user/{userId}/challenge` → `POST /ss/v1/user/{userId}/vehicle/{uuid}/session` body `{idToken, spinHash, tsp:"WCT"}` → carnetVehicleToken as Bearer (not X-Spin-Session). Lock = PUT body `{"lock":bool}`. Verbatim port scheduled v2.11.1.
- **VW NA subscription/privileges** parser shape (zackcornelius reads `data.services[*].operations[*].capabilityStatus`, not a top-level `subscription` block) - v2.11.1.
- **Audi refresh_token KeyError defense** (audi_connect_ha PR #749 source-verified) - backend now intermittently omits refresh_token. Our refresh path needs same `if "refresh_token" in resp` guard - v2.11.1.
- **Audi IDK discovery URL preference** (audi_connect_ha PR #738) - verify `_audi_market_config.py` reads `idkLoginServiceConfigurationURLProduction` with fallback to `/auth/v1/idk/oidc/openid-configuration` - v2.11.1.
- **Skoda TripStatistics OverallCost/FuelCost fields** (myskoda v2.11.1 additive). Needs new VehicleData attributes + sensor.py registrations + 9-lang translations + currency-aware unit handling - v2.11.1.

## [2.10.12] - 2026-06-04

### Fixed

- **SEAT / CUPRA field-name corrections cross-referenced against pycupra source** (#392 heidle78 v2.10.10 follow-up - still-null trace). v2.10.10's static-info fix guessed top-level field names on the garage response that don't exist; the actual data lives in nested sub-blocks. Deep-diff against pycupra (the established Python lib for OLA backend) surfaced four concrete bugs:

  - **model**: now reads `specifications.factoryModel.vehicleModel` (was guessing top-level `model`/`modelName`), optionally concatenated with `specifications.carBody` for the full display name.
  - **model_year**: now reads `specifications.factoryModel.modYear` (was guessing `modelYear` - note the missing `el`).
  - **manufacturer**: now reads `specifications.factoryModel.vehicleBrand` (was guessing top-level `brand`).
  - **odometer_km**: added `mileageKm` as the FIRST field-name variant on `/v1/mileage` (pycupra's canonical key, was missing from our chain so offline-state Formentor PHEVs came out with odometer null).
  - **target_soc** + **max_charge_current** + **auto_unlock_charge**: now read from the `settings` sub-dict on `/v1/charging/info` (pycupra: `settings.targetSoc` / `settings.maxChargeCurrentAcInAmperes` / `settings.maxChargeCurrentAc` / `settings.autoUnlockPlugWhenCharged`). Pre-v2.10.12 read top-level only and silently missed the nested data on most CUPRA/SEAT firmwares.

## [2.10.11] - 2026-06-04

### Fixed

- **Data Act portal SPA: 3 new state-extraction patterns + 2-source forensic dump** (#388 swebachus v2.10.10 trace). swebachus's v2.10.10 warning log showed the portal returns a pure-SPA shell as the password page: `password_html.contains '<input'=False, contains 'state'=True, contains '__STORE__'=False`. Three new extraction patterns target the actual shapes this means: (a) Auth0 native state signature `hKFo...` regex (state tokens always start with that msgpack 2-key map marker so they are catchable even when minified into a bare string literal); (b) escaped JSON `\"state\":\"...\"` for double-encoded inline payloads; (c) URL-encoded state inside the HTML body for `window.location = "...state=X..."` patterns. The warning log now also covers `landing_html` (not just `password_html`), prints the raw URL strings, and dumps the 110-char context window around any `"state"` substring so the next failing trace pinpoints exactly where the token lives or proves the page is purely JS-rendered post-bundle.

## [2.10.10] - 2026-06-04

### Fixed

- **SEAT / CUPRA static vehicle info from garage** (#392 heidle78 v2.10.8 follow-up diag). Pre-v2.10.10 the parser never read `model`, `model_year`, `manufacturer`, or `firmware_version` from the OLA garage response, so every SEAT / CUPRA vehicle showed "Unbekannt" / `None` for those device-card fields even when the data was clearly present in the API. Now extracts them in `get_vehicles` with defensive multi-variant lookup (`model`/`modelName`, `modelYear`/`year`, `brand`/`manufacturer`/`brandName`, `firmwareVersion`/`softwareVersion`, plus a `specifications` / `vehicleSpecification` sub-block) and caches per-VIN like the existing licensePlate + nickname pattern.

## [2.10.9] - 2026-06-04

### Fixed

- **Data Act portal SPA: attribute-order-agnostic state extraction + forensic logs** (#388 Arno-MA-73 v2.10.8 trace). v2.10.7's HTML hidden-input regex required `name` to appear before `value` in the markup; some Auth0 SPA bundles ship the attributes in the opposite order and the v2.10.7 regex silently missed those. Now walks every `<input ...>` tag, captures `name` and `value` as two independent regex matches the way `idk.py:_parse_csrf_robust` already does for the main BFF flow. Adds `data-state="..."` attribute as a third extraction path. Plus full DEBUG forensic logs at every step in the SPA branch (landing/identifier/password URLs, HTML lengths, parser field key sets, state extraction source and first 12 chars on success, first-200-char dump of password HTML when nothing works) so the next failing trace surfaces what shape the portal actually returns.

## [2.10.8] - 2026-06-03

### Fixed

- **CUPRA / SEAT PHEV classification** (#392 heidle78 Formentor diag). Some OLA firmware versions ship `engines.primary.fuelType="gasoline"` but DO NOT populate a combustion range in the `ranges` block on the same response. Pre-v2.10.8 the integration derived `has_combustion` purely from the ranges block, so a Formentor PHEV came out classified as `is_hybrid=False` and `has_combustion=False`, suppressing the fuel-tank / combustion-range sensors downstream. Now also treats any non-electric `primary_engine_type` (gasoline / diesel / cng) as combustion so the PHEV flag flips correctly regardless of which response branch carries the range data on a given poll.

## [2.10.7] - 2026-06-03

### Fixed

- **Data Act portal SPA: state token extraction from HTML** (#388 Arno-MA-73 post-restart trace). v2.10.6 fixed the 405 but then failed with "no Auth0 state parameter in URL" because aiohttp's redirect-following strips the state from the final response URL on some SPA flows. Now mirrors `idk.py`'s extraction order: HTML hidden input first (most reliable, Auth0 always embeds `<input type="hidden" name="state" value="...">` in the page body even on SPA), regex over hidden inputs as fallback, JSON-embed pattern as third option, then the URL query strings as last resort. Both `password_html` (most recent) and `landing_html` (original GET) get checked.

## [2.10.6] - 2026-06-03

### Fixed

- **Data Act portal SPA password POST 405** (#388 xeonixo + Arno-MA-73). v2.10.3 POSTed the SPA password to the parsed identifier-form action URL, which returned HTTP 405 Method Not Allowed for several users. Auth0 Universal Login actually routes the SPA password submission through the SAME `/u/login?state=<x>` URL as the identifier step; differentiation happens via the body's `action` field. Now mirrors `idk.py`'s SPA fallback exactly: form-encoded POST first, JSON-content-type fallback when that lands on 4xx or back on the IDP host, follow the redirect chain. State is pulled from the password-page URL with a fallback to the original landing URL.

## [2.10.5] - 2026-06-03

EU Data Act portal: no more manual click-through. When the integration is in read-only portal mode and you opt in via the new toggle, it kicks off the Custom Data Request on its own.

### Added

- **EU Data Act portal Custom Data Request auto-kickoff** (live-trace based). At startup in read-only `data_act_portal` mode, the coordinator checks each VIN for an existing 15-min Custom Request and creates one when none exists. Uses the verified `/proxy_api/euda-apim/` endpoints captured 2026-06-03: GET `metadata/partial` to detect, CSRF + POST `requests/partial` to kick off, GET `datadelivery/{Identifier}/list` to pick up the ZIPs. The portal accepts at most one active custom request per VIN at a time so the check-then-create order is critical; we adopt an existing request if one is already running instead of double-kicking. New toggle `eu_data_act_auto_kickoff` in OptionsFlow defaults to OFF because the kickoff implies a 1-month data subscription on the user's account at the portal.
- **Repairs issue on portal session expiry**. HTTP 401 on any portal API call now opens a guided `data_act_session_expired` Repairs issue pointing the user at the Reconfigure flow. Portal sessions are cookie-bound and not refreshable, so we surface the prompt instead of silently looping.

## [2.10.4] - 2026-06-03

Two power-user tools for keeping the auth chain alive when VW rotates client_ids.

### Added

- **APK watcher: auto-issue on new OAuth client_id**. The daily atlas builder already polled VW Group APKs and extracted client_ids; now there is a diff step that compares the latest extraction against everything wired into source. When a brand-new id appears, a labeled issue gets opened so the maintainer (or anyone) can promote it into the alternates list without waiting for someone to notice manually.
- **OAuth client_id override in OptionsFlow** (power-user). When the community spots a fresh client_id in a new APK before the daily watcher catches it, paste the full `UUID@apps_vw-dilab_com` into the new field and the resolver tries it first. All existing fallbacks stay in the chain. Empty / malformed values are silently ignored.

## [2.10.3] - 2026-06-03

VW EU users finally get a working read-only path again.

### Fixed

- **Data Act portal SPA password completion** (#388 caraar12345's trace). When the portal's password page is SPA-rendered, v2.10.2 detected it but bailed out telling the user the fallback in idk.py was the route - except that route is for the BFF client, not the portal client, so users on VW EU had nowhere to land. The Data Act portal flow now finishes the SPA-rendered password page itself with a form-encoded POST that includes `action=default` and the state lifted out of the page URL, then runs the standard token exchange. The portal client_id passes the Azure WAF where the main VW Android client_id is blocked, so this is the one path most affected VW EU users can actually use for read-only data.

## [2.10.2] - 2026-06-03

EU Data Act portal flow rebuilt against a verified live trace.

### Fixed

- **Data Act portal OAuth flow** (#388, #393). The portal client uses plain authorization-code flow with `prompt=login`, not the hybrid response_type we were sending. That mismatch was the source of the "unexpected landing URL - IDP may have rejected client_id" error several users hit when the live BFF strategies all failed and the integration tried the read-only fallback. Now switched to standard code flow plus PKCE-S256 plus a token exchange against `identity.vwgroup.io/oidc/v1/token`. Hybrid fragment delivery is kept as a defensive fallback so accounts that happened to work on the old path are not regressed.
- **Data Act portal state-string order**. Was `{country}__{language}__{BRAND}`, now `{language}__{country}__{BRAND}` per the live trace. DE/DE users worked by coincidence; non-matching country/language combinations were routed to the wrong portal locale.

### Added

- **EU Data Act portal usership-verification scaffolding**. New `check_verification_state()` and `submit_usership_verification()` on the scraper detect whether the one-time EU Data Act declaration is on file per VIN and can submit it on behalf of the user when an opt-in config flag is set. The Repairs / OptionsFlow wire-up lands in v2.10.3; the methods are usable from external code today.
- **Data request submission scaffolding**. New `submit_data_request()` and `poll_for_dataset_url()` for the async ZIP delivery flow. Endpoint shapes are best-effort against the documented form fields; verified shapes ship in v2.10.3 once a live trace captures the AJAX call that populates "Ihre Dateien".

## [2.10.1] - 2026-06-03

VW EU login hotfix. The v2.10.0 SPA fix unblocked one path, but several users still hit HTTP 403 on the authorize endpoint itself - the Azure WAF in front of `identity.vwgroup.io` started rejecting the Android user-agent some time on 2026-05-31. Same finding the wider HA-VAG community converged on this week.

### Fixed

- **VW EU 403 on authorize endpoint** (#388, #393). When the initial GET to `/oidc/v1/authorize` comes back 401 or 403, retry once with a plain mobile-browser user-agent. Picks up users blocked at the WAF without affecting accounts that already work on the Android UA.
- **VW user-agent bumped** to `Volkswagen/3.61.0-android/14` to match the current shipping APK. The old `3.51.1` string is what the WAF presumably flagged.

## [2.10.0] - 2026-06-02

The biggest single release so far. VW EU login is unblocked again after the 2026-05-31 backend change, parked cars no longer show all-Unknown, and SEAT/CUPRA gets its Energy-Dashboard story plus settable battery-care.

### Added

- **One service for every vehicle command**. Pick from a dropdown of 14 actions (lock, unlock, climate, charge, lights, window heating, wake, aux heating, ventilation) on any vehicle device. The individual services still work too, no automations break.
- **Wake your car before polling it** (opt-in). When the previous poll said the car was OFFLINE, send a wake first, then poll. Trades one extra API call for getting actual data back. Off by default.
- **See in-flight commands**. New pending-action sensors tell you when a lock/unlock/climate request the app sent is still being processed by the car, so automations can wait for real ack instead of guessing with sleeps. Closes #389.
- **Trip stats per tank or charge session**. 9 new sensors for distance, time, average speed, fuel and electric consumption, plus totals you can feed into the Energy Dashboard. Filled the long-standing gap in HA-VAG land.
- **Real warning-light data on SEAT/CUPRA** from a dedicated backend endpoint, with per-category booleans (engine, brakes, tyre, oil) plus a readable message list.
- **Set the battery-care preservation mode and target SoC** directly from HA on SEAT/CUPRA. Read-side was added in v2.8.1, this completes the write side.
- **Audi plug LED colour** wired up for Q6/A6 e-tron PPE. Older Audis keep the sensor hidden.
- **Real-time charging rate** on Audi + VW EU where the firmware reports it separately from the averaged rate.
- **Rich climate-start service** that lets you set per-seat heating, glass heating, eco-vs-comfort mode, continue-while-unlocked and target temperature in one call. Audi + VW EU only.
- **Charging history with power-curve points** for SEAT/CUPRA, so the DC-fast-charge kW-vs-SoC story finally works there. Diagnostic sensor exposes the curve in attributes, ready for Lovelace charts.
- **Group B: 7 more SEAT/CUPRA endpoints**. App notifications (count + last subject + severity), permissions (owner / can-command), engine + coolant temperature, charging profiles (same shape as Skoda already had), charging modes, a service to push charging settings to the car, and the public charging-station catalog now works on SEAT/CUPRA too.

#### VW EU field parity (Group A) — 10 new sensors

- HV battery min/max temperature (separate from the average) — useful for thermal-runaway alarms on long DC charges.
- Max AC charging current split into "what you set" vs "what the wallbox actually delivers".
- Born MY24+ AC connector auto-release flag + state.
- Optimised battery use toggle (longevity vs performance, distinct from battery-care).
- Active ventilation status + countdown to end.
- Rear sunroof + Cabrio roof-cover position.
- 12V battery health bucket (low / normal / high), distinct from the existing voltage sensor.
- Last-trip absolute fuel + electric consumption totals.

#### VW NA endpoint parity (Group C)

- Subscription + capabilities sensors on VW NA (Cox-backend). Pre-v2.10.0 SEAT/CUPRA + VW EU only.
- Modern Cox two-step SPIN flow for privileged actions. The old in-body SPIN still works as fallback.
- Modern lock/unlock endpoint, falls back to the legacy one on 404.
- NA-specific climate + window-heating endpoints, falls back to EU-style on 404.

### Fixed

- **VW NA "everything Unknown" on ID.4 US 2023** (#322 roberttco). Cox migrated the response shape; we now read both old and new shapes so accounts on either firmware get real values.
- **Scout stops shouting** about warning-light error envelopes and pending-action requests. Both are bff-internal wrappers, not real new data. Closes #389.
- **VW EU login broken after 2026-05-31** (#388 BalooDK + swebachus). VW migrated the password page to a JS-rendered shape and our form POST started getting "wrong credentials" even when they were right; the Data-Act fallback then mistook the SPA's `consent.js` asset for a real consent wall. Retry the same login URL with JSON content-type, and tightened the consent-wall detection so it doesn't trip on `consent.js`. VW EU users can log in again.
- **Tire pressure on newer PPC firmware**. Same data, new branch in the response; the parser now checks both branches.

### Documented

- Active-ventilation TODO from v2.4.x is cleared — Group A above shipped the parser and entities.
- Deeplink scheme TODOs are cleared. The smali extractions don't carry URI scheme strings (they live in AndroidManifest.xml + iOS Info.plist), so the shipped schemes stay sourced from each brand's launcher metadata.

## [2.9.0] - 2026-06-02

Hardening bundle: provenance canaries + weekly watcher, SPDX license headers across all Python files, and VW account-lock detection with a guided Repair issue.

### Added

- **VW account-lock detection**. After the 2026-05-31 ecosystem-wide VW Auth chaos surfaced a new failure mode (oliverrahner on volkswagencarnet#332 reporting his brand account getting locked for ~24h after too many failed token-refresh attempts), the coordinator now tracks HTTP 423 (Locked) and HTTP 403 with throttling-marker bodies on the token endpoint. Three such responses inside a 30-minute sliding window surface a Repair issue (`account_locked`) explaining the lock + next steps (wait, raise scan_interval, optionally switch to read-only Data Act portal mode). Auto-clears on the next successful auth. Native DE translation, EN parity for the other 7 supported languages.
- **Provenance canaries + weekly watcher**. New `custom_components/vag_connect/_canaries.py` declares 5 uniquely-spelled identifier strings, one per strategic module (auth resolver, Data Act scraper, DAG flow, Scout, watchdog). Each canary is also referenced from the module it watermarks so it travels with any port. Weekly cron in `.github/workflows/canary-watch.yml` queries GitHub Code Search for the canaries outside the `its-me-prash` namespace and opens a triage issue tagged `provenance` when a foreign hit appears. Apache 2.0 permits the port; the canaries make stripping the LICENSE + NOTICE observable.

### Changed

- **SPDX-License-Identifier headers** added to all 158 Python files. Files already carried the copyright + Apache 2.0 line; this adds the machine-readable SPDX identifier on the line below so REUSE / FOSSA / SCANCODE-class license scanners pick them up without parsing free-text. Mechanical change, no behaviour impact.

## [2.8.2] - 2026-06-02

### Fixed

- Scout no longer auto-fires on the 6-key `.error.*` envelope the Cariad BFF returns when the `vehicleHealthWarnings.warningLights` job hits a 5xx upstream. Same shape as the v2.7.4 fix for `oilLevel.error` / `tyrePressure.error` / `auxiliaryHeating.error`, one branch deeper. Closes #384 (moltke69 Audi scout).

## [2.8.1] - 2026-06-01

Closes 11 SEAT/CUPRA OLA-field parser gaps surfaced via side-by-side comparison with the pycupra reference, after the v2.5.3 OLA v1/v5 fallback chain did not fix DanielBie's offline-Leon entity coverage (issue #306).

### Added

- 11 new sensors backed by OLA fields that the seat_cupra parser was not reading: `adblue_level_pct` (% tank level for diesel SCR, separate from the existing `adblue_range_km`), `cng_level_pct` + `cng_range_km` (CNG variants like Polo TGI, Mii Ecofuel, Leon TGI), `primary_engine_range_km` (PHEV / dual-fuel parity with the existing `secondary_engine_range_km`), `charging_preferred_mode` (user-selected mode mirror), `seat_heating` (any-seat-on aggregate), `parking_light`, `external_power` (charger is actually energising the cable, distinct from `plug_connected`), `battery_care` (preservation mode flag), `energy_flow` (any HV-battery exchange happening), `area_alarm` (geofence event). All entries phantom-protected via `_DATA_PRESENT_REQUIRED` so vehicles without the underlying field stay clean.
- Translations for the 11 new entities mirrored across all 9 supported languages (DE + EN canonical, the other 7 carry the EN labels until per-language polish; cross-lang parity test pinned).

## [2.8.0] - 2026-06-01

Stable cut of the v2.8.0 series. Promotes 2.8.0rc1 + 2.8.0rc2 from release-candidate to stable with no further code changes; the rc cycle ran under 24 hours and the only reported field issue (#378 from jwaeles) was fixed in rc2.

### What is new vs v2.7.4

- Five action items from the 2026-05-30 competitive scan: MFA / Email-OTP handler, coordinator auto-reload watchdog, headless EU Data Act portal zip scraper, FCM push live activation for Audi and VW, Repairs flow for DAG-to-hybrid_full degradation.
- Five v3.0 quick wins pulled forward: auxiliary-heating entities (switch + 2 numbers + sensors) for Audi and VW, `vag_connect.open_app` service with per-brand deeplinks, brake-service plus preferred-workshop sensors for all 4 Cariad brands, per-job parser-health telemetry in diagnostics, per-brand declared-vs-observed capability snapshot in diagnostics.
- 30-day device-bound IDP cookie persistence across HA restarts to skip the email-OTP challenge.
- Roadmap consolidation: five overlapping roadmap docs reduced to one canonical top-level `ROADMAP.md` with a new "Won't do" block listing 11 explicit exclusions.
- Dead-weight cleanup: Pydantic dual-write scaffold removed (blocking-IO warning gone), `euda.py` shim retired, 6 stale v1.x docs + 12 dead probe scripts deleted.
- README rewritten for all nine languages: DE + EN canonical, the other seven mechanically synchronised. Drops the v2.0 Big-Bang highlights and adds honest "Where we lead" + "Where the limits are" blocks.

### What changed during the rc cycle (rc2 hotfixes folded in)

- VW EU re-auth after the 2h token expiry was crashing in the Data Act portal fallback because the IDP migrated the `hmac` and `_csrf` fields out of plain `<input type="hidden">` markup into a SPA-rendered JSON block. The portal-side form parser now mirrors the multi-fallback strategy already in `idk.py:_parse_csrf_robust` (HTMLParser, regex over hidden inputs, form-action regex, and JSON/script-block extraction). Reported in #378.
- Two-way auth recovery for VW EU and Audi hybrid_full. After the hybrid flow succeeds, the integration now opportunistically exchanges the auth_code that Auth0 also delivers in the callback URL for a token set that may include a real refresh_token. Strictly additive: when the standard token endpoint is still Play-Integrity-walled the exchange fails silently and the hybrid-only TokenSet is kept (v2.6.0 behaviour preserved); when the wall has been loosened (as observed across the ecosystem around 2026-05-31) the upgraded TokenSet replaces the hybrid one and the next 2h boundary refreshes against `/auth/v1/idk/oidc/token` instead of triggering a full relogin.

## [2.8.0rc2] - 2026-06-01

Two-way VW EU re-auth recovery + hotfix for the 2026-05-31 IDP markup migration that broke the Data Act portal fallback. Same feature set as 2.8.0rc1 plus the two fixes below.

### Fixed

- VW EU re-auth after the 2h token expiry was crashing in the Data Act portal fallback because the IDP migrated the `hmac` and `_csrf` fields out of plain `<input type="hidden">` markup into a SPA-rendered JSON block. The portal-side form parser now mirrors the multi-fallback strategy already in `idk.py:_parse_csrf_robust` (HTMLParser, regex over hidden inputs, form-action regex, and JSON/script-block extraction), so a markup migration on either side fails loudly in the regression tests instead of in production. Reported in #378.

### Changed

- Two-way auth recovery for VW EU and Audi hybrid_full strategy. After the hybrid flow succeeds, the integration now opportunistically exchanges the auth_code that Auth0 also delivers in the callback URL for a token set that may include a real refresh_token. Strictly additive: when the standard token endpoint is still Play-Integrity-walled the exchange fails silently and the hybrid-only TokenSet is kept (v2.6.0 behaviour preserved). When the wall has been loosened (as observed across the ecosystem around 2026-05-31) the upgraded TokenSet replaces the hybrid one and the next 2h boundary refreshes against `/auth/v1/idk/oidc/token` instead of triggering a full relogin. Combined with the form-parser fix above this gives two independent recovery paths (refresh + full relogin via portal fallback) so a single endpoint flap on either side does not break re-auth.

## [2.8.0rc1] - 2026-05-31

First release candidate for v2.8.0. Bundles the five action items from the 2026-05-30 competitive scan with five v3.0 quick wins pulled forward, plus a dead-weight cleanup pass and a roadmap consolidation. README rewritten across all nine supported languages for v2.7.x reality (DAG MVP positioning + honest VW EU Play-Integrity limits).

### Action items

- MFA / Email-OTP config_flow handler (#1). The VW IDP can challenge for a 6-digit code on first sign-in; the flow now captures it cleanly instead of failing with a generic `cannot_connect`.
- Coordinator auto-reload watchdog (#2). When all VINs on the hybrid_full strategy show `failure_count >= 2` and `last_good_at` is older than 2x the scan interval, the coordinator silently re-authenticates without dropping entities. Mirrors the upstream community automation pattern but internalised so users do not have to wire it themselves.
- Headless EU Data Act portal zip scraper (#3). New `cariad/auth/_data_act_scraper.py` wired as Tier 3.5 (activates only when the active strategy is `data_act_portal`). Route A probes a research-confirmed JSON endpoint; Route B is fully scaffolded behind a new `CONF_ENABLE_DATA_ACT_BROWSER` OptionsFlow toggle that drives a headless Chromium via the optional `playwright` package (NOT in `manifest.json` — 100 MB Chromium download stays opt-in). Missing-dep surfaces a `data_act_browser_missing` Repair issue.
- FCM push channel for Audi and VW now ships live activation (#4). Decoded payloads (lockState, chargingState, climateState, alarm) are fired onto the HA event bus as `vag_connect_push_event` and trigger a coordinator refresh. The Cariad Firebase sender_id / api_key / app_id are still tester-gated behind a `NotImplementedError` in `_resolve_fcm_credentials` until the live APK extraction lands; the OptionsFlow toggle label moves from "EXPERIMENTAL" to "Live (beta)".
- Repairs flow when DAG degrades to hybrid_full (#5). New `auth_strategy_degraded` issue surfaces in the HA UI after 3 consecutive successful polls confirm the resolver has silently fallen back, with two guided remediations: re-run the browser-login setup, or pin the read-only Data Act portal mode (via the new `CONF_PREFERRED_AUTH_STRATEGY` option).
- MFA / 30-day device-bound IDP cookie persistence. The VW IDP issues a cookie after a successful email-OTP that suppresses the OTP for around 30 days; until now we discarded it on every restart, reload, and 2h re-login. `TokenSet`, `TokenStorage`, and `IDKAuth` all extended to round-trip the cookie. Latent bug-fix included: the storage layer never persisted `strategy` or `auth_cookies`, so the watchdog never saw the active strategy after a restart.

### Quick wins from the v3.0 roadmap (pulled forward)

- Standheizung / auxiliary-heating surface (quick win A): switch + duration number (5–60 min) + target-temp number (16–30 °C) + new `auxiliary_heating_status` + `aux_heating_active` + `auxiliary_heating_remaining_min` sensors. Audi + VW EU only; SEAT/CUPRA flow continues to require S-PIN. Capability map declares `auxiliaryHeating` for the two new brands.
- `vag_connect.open_app` service (quick win B). Fires `vag_connect_open_app` on the HA event bus with `{vin, brand, deeplink_url, action}` so a Lovelace card can open the brand's native mobile app on the calling device via `window.location.href`. Deeplink schemes are defined in `const.DEEPLINK_SCHEMES`; the per-brand scheme strings are marked `TODO(2.8.1)` for device-side re-verification once the v2.8.1 IPA/smali pass lands.
- Brake-service + preferred-workshop sensors (quick win C). Six new sensors: `brake_fluid_change_due_at`, `brake_pads_front_inspection_due_at`, `brake_pads_rear_inspection_due_at`, `preferred_workshop_name`, `preferred_workshop_address`, `preferred_workshop_phone`. Populated for VW EU + Audi (CARIAD-BFF `serviceCare`), Skoda mysmob `maintenanceReport`, and SEAT/CUPRA OLA `maintenance` when the dealer has wired up the service plan. Phantom-protected via `_DATA_PRESENT_REQUIRED`.
- Parser-health telemetry in diagnostics (quick win D). Each brand client's `parser_stats` dict records `{success, fail, last_error[:200]}` per named job (`oil_level`, `charging`, `climatisation`, `tyre_pressure`, `auxiliary_heating`, `trip_statistics`, `service_care`, etc.) and is exported in the diagnostics dump, so a silent parser regression on one job is visible while the rest of the poll succeeds. PII redaction reuses the existing JWT/VIN/email scrubber.
- Per-brand capability advertisement in diagnostics (quick win E). New `cariad/_capabilities.py` declares the expected per-brand capability matrix; `coordinator.capabilities_snapshot()` adds the observed-this-poll view and a `drift` list flagging declared-True-but-observed-False. Lets a missing entity be triaged as "brand never supported it" vs "parser dropped a field" without reading source code.

### Housekeeping

- Dead-weight cleanup pass. Removed the v2.2.0 Pydantic dual-write scaffold (one model, return value discarded everywhere, plus a blocking-IO warning on every fresh HA startup), retired the `euda.py` v2.0 shim that had zero callers, deleted 6 stale v1.x docs and 12 dead probe scripts from the v1.27 research era.
- Roadmap consolidation. Five overlapping roadmap docs reduced to one canonical top-level `ROADMAP.md`. New "Won't do" block records the 11 things we have explicitly ruled out (MBB direct-data path, Lamborghini/Bentley/Bugatti commands, VW China, etc.) so future feature requests can point at it.
- README rewritten for all nine languages. Drops the v2.0 Big-Bang highlights and adds honest "Where we lead" + "Where the limits are" blocks. DE + EN canonical, the other seven languages mechanically synchronised.

## [2.2.0-rc1] — 2026-05-16 — "Legen — wait for it — dary" (Release Candidate)


## [2.2.0] — 2026-05-17 — "Legen — wait for it — dary" (Final)


## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion

- Cross-Brand App Atlas
- OLA watcher gains upstream as 3rd consensus source
- App Atlas covers all 7 brands

## [2.7.4] - 2026-05-31

### Fixed
- Scout no longer auto-fires on the 6-key `.error.*` envelope the Cariad BFF returns when `oilLevel` / `tyrePressure` / `auxiliaryHeating` jobs hit a 5xx upstream. v2.7.1 silenced the parent path but the single-level `.*` wildcard did not cover the 4-component child paths. Closes #371 and #373.

## [2.7.3] - 2026-05-31

### Changed
- Data Act portal auth: when the password form is missing in the response, scan the returned HTML for EU Data Act consent signals (`data act`, `consent`, `einwilligung`, `zustimmung`, `shape the future`, `datenverarbeitung`) before falling back to the generic credentials-rejected message. Surfaces a clearer instruction for users who hit the consent wall on `myvolkswagen.*` (issue #372).

## [2.7.2] - 2026-05-31

### Security
- Coordinator setup-failure log no longer prints the raw exception message at ERROR level. An aiohttp `InvalidURL` raised on the OAuth callback path could surface the full redirect URL including `access_token`, `id_token`, and `code` JWTs, all of which base64-decode to the user's email and a working access token. Log type only at ERROR; message at DEBUG.

### Fixed
- Multi-strategy auth resolver in `base.py` now also catches non-`AuthenticationError` exceptions (e.g. `aiohttp.InvalidURL`), converts them to a clean `AuthenticationError`, and falls through to the next strategy. Prevents the raw URL from leaking up to the coordinator's catch-all.

## [2.7.1] - 2026-05-31

### Fixed
- Vehicle Data Scout no longer auto-fires on `oilLevel` / `tyrePressure` / `auxiliaryHeating` branches we just promoted in v2.7.0. Closes scout-report issues #366 and #367.

## [2.7.0] - 2026-05-31

### Added
- Browser-Login (OAuth Device Authorization Grant) for Audi, Škoda, SEAT, CUPRA. Open a QR code on your phone, sign in to your Brand ID account, confirm a short code. No password stored in Home Assistant, real refresh_token from the IDP.
- Trip statistics: `last_trip_*` and `lifetime_*` sensors populate from `/tripstatistics?type=shortTerm|longTerm`.
- `warning_messages` sensor surfaces every backend warning the manufacturer app would show (Audi STO / towing-bracket alerts etc), not just the hardcoded oil/engine/brake/tyre family.
- `oilLevel` and `tyrePressure` jobs added to the selectivestatus request. Populates `oil_level_warning` binary_sensor and the existing `tire_pressure_*_bar` sensors.

### Fixed
- Per-door, per-window, sun-roof, trunk-lock state now populate on locked cars (was only on unlocked).
- Outside temperature parser tries multiple backend key variants for Audi MY24+ compatibility.
- Window heating front/back parser tries multiple JSON shape variants.
- `wake_count_today` defaults to 0 instead of Unknown.
- TIMESTAMP sensors parse ISO 8601 strings to tz-aware datetime (cures entity-add failure on subscription_expiry_at).
- Cross-language translation parity. All 8 supported languages now ship the full config_flow translation set (browser_login, browser_login_approve, menu_options, progress, errors).

### Notes
- If field labels in the config dialog render as raw keys (`brand`, `spin`, etc) after upgrade, do a hard browser refresh (Ctrl+Shift+R). Home Assistant caches translations client-side and may not pick up the new keys until the browser cache clears.

## [2.7.0b11] - 2026-05-31

### Added
- Trip statistics endpoint wired. `last_trip_*` and `lifetime_*` sensors now populate from `/vehicle/v1/vehicles/{vin}/tripstatistics?type=shortTerm|longTerm`. Closes Unbekannt on Lifetime Distance, Last Trip Distance / Avg Speed / Avg Fuel Consumption, Lifetime Avg Fuel Consumption.
- `warning_messages` text sensor showing every backend warning as `type: text`, comma-joined. Surfaces brand-specific warnings the hardcoded oil/engine/brake/tyre binary sensors miss (e.g. Audi STO / towing-bracket alerts that come through in the myAudi email notifications).
- `wake_count_today` defaults to 0 on first data load instead of None / Unbekannt. The counter only increments when the user uses the wake button; users who never wake the car now see 0 instead of "Unknown".

### Fixed
- Outside temperature parser tries multiple backend key variants (`outsideTemperature_K`, `temperatureOutside_K` under `outsideTemperatureStatus` and `temperatureOutsideStatus`). Closes Unbekannt on Audi MY24+ models where the key differs from the canonical Cariad name.
- Window heating front / back parser tries multiple JSON shape variants (`windowHeatingStatus` / `statusList` / `windowHeatingStatusList` / direct array under value). Closes Unbekannt on brands shipping the data under a non-canonical key.

## [2.7.0b10] - 2026-05-31

### Added
- `oilLevel` job in the CARIAD-BFF selectivestatus request. New binary_sensor `oil_level_warning` (Oil Level / Ölstand). Closes "Oil Level" Unbekannt gap vs upstream.
- `tyrePressure` job in the same request. Populates the existing `tire_pressure_*_bar` sensors and `tire_pressure_warning` binary_sensor. Closes per-wheel pressure Unbekannt gap.
- `auxiliaryHeating` job for future Webasto / standheizung parity.

### Fixed
- Per-door and per-window state was only populated when the car was unlocked (`overallStatus == "UNSAFE"`). On a locked car the parser left `doors_individual` / `windows_individual` empty and all per-position entities (Left Front Door, Sun Roof, etc) rendered as Unbekannt. Now always iterate the doors and windows arrays regardless of overall status.
- Trunk lock state was never extracted from the access response. Pulled from the doors array entry with name "trunk", populating the existing `trunk_locked` binary_sensor.

## [2.7.0b9] - 2026-05-31

### Changed
- DAG browser-login Phase 2: URL and user_code now live inside the form schema as pre-filled fields, not just in the description. Description rendering kept failing on real installs (translation-loader miss or HA frontend quirk). Schema fields render reliably.
- Added a QR code selector showing the verification URL. Scan with phone camera to open the login page in one tap.
- Field labels chosen so the raw-key fallback ("verification_url", "user_code", "approved_in_browser") stays readable when translations miss.
- Persistent notification and WARNING log line from b8 kept as belt-and-suspenders.

## [2.7.0b8] - 2026-05-31

### Fixed
- DAG browser-login: URL and user_code now surface through three independent paths so at least one always renders even when the others fail. (1) form description (was already in b7), (2) persistent_notification fired on form first entry, (3) WARNING log line with both values. Defense against the empty-dialog-body symptom seen on b7 even after full HA restart.
- DAG browser-login form: switched from empty `vol.Schema({})` to a single optional confirm boolean. Empty schemas caused HA's frontend to skip description rendering on at least one install.

## [2.7.0b7] — 2026-05-31 — "DAG spinner-forever fix #3 — form-based URL display (beta)"

- After b4 and b6 both failed to reliably surface the verification URL + user_code in the show_progress dialog (HA frontend cached the progress description per flow id and didn't always pick up `description_placeholders` even when the show_progress task and step_id changed), Phase 2 is now rendered as a normal config_flow form. Forms substitute placeholders via the standard text-rendering pipeline which works reliably.
- New UX:
  - URL + 6-digit code shown as plain markdown text — fully visible and copyable
  - Submit button visible from the start
  - User opens URL in their browser (any device), signs in, approves
  - When done, clicks Submit
  - Background poll task validates with VW backend
  - If poll done + tokens → advance to entry creation
  - If poll done + error → drop back to brand picker (retry)
  - If user clicked Submit before approval was complete → re-renders form with a "still waiting for browser approval" hint
- Trade-off vs show_progress: lost auto-advance (user has to click Submit once they've approved), but gained guaranteed visibility of the URL + code. Worth it.
- Translation key added: `still_waiting_browser` (DE + EN).

## [2.7.0b6] — 2026-05-31 — "DAG spinner-forever fix #2 — split phases into distinct step_ids (beta)"

- Browser-login progress dialog now reliably shows the verification URL + user_code after the device_code is acquired. The b4 attempt at a single-step two-phase flow ran into HA's frontend caching the progress description per step_id — when the same step_id returned a second `show_progress` with a different `progress_action` and new `description_placeholders`, the dialog often kept showing the first (empty) description and the spinner appeared to spin forever.
- Refactored into two distinct step_ids:
  - `browser_login_pending` — Phase 1 only (request /device_authorization). Shows "Requesting login code…".
  - `browser_login_approve` — Phase 2 only (poll /token). Shows "Open {url}, enter {code}, sign in".
- HA tears down the first dialog cleanly between phases and renders a fresh one for Phase 2, so the placeholders apply correctly the first time.

## [2.7.0b5] — 2026-05-31 — "TIMESTAMP sensors fix (beta)"

- subscription_expiry_at (and any other ISO-string sensors with TIMESTAMP device class) now parse to timezone-aware datetime in native_value. Pre-fix HA rejected the entity at add-time with 'str has no attribute tzinfo'.

## [2.7.0b4] — 2026-05-31 — "Menu + DAG progress UX fix (beta)"

- Browser-Login / Email+Password menu now passes labels in the code instead of relying on the HA translation lookup — cures empty-chevron rendering when the integration is updated without an HA restart.
- Browser-Login progress: split into two phases so the URL + user_code populate in the progress text BEFORE the long poll begins. Previously the progress UI showed only "Waiting for browser approval…" with the URL/code never appearing.

## [2.7.0b3] — 2026-05-31 — "Hassfest + test contract fixes (beta)"

- Translations: moved progress key from inside step to top-level config.progress per HA schema.
- Tests aligned with v2.7.0b1 menu split and v2.7.0b2 5-header default.

## [2.7.0b2] — 2026-05-31 — "Audi token-headers fix (beta)"

- Audi email+password login: dropped the dummy x-assertion / x-platform / x-android-package-name trio from token requests — VW backend now rejects the dummy value and lets through requests that omit the headers entirely. Matches upstream v1.19.2+ behaviour.

## [2.7.0b1] — 2026-05-31 — "Browser-Login UI (beta)"

- New config_flow menu: choose between Browser-Login (recommended) and Email + Password (legacy).
- Browser-Login wires the v2.6.0 OAuth Device Authorization Grant module into HA's show_progress flow — open a URL, enter a short code, no password stored in HA.
- Available for Audi, Škoda, SEAT, CUPRA. VW EU + Porsche stay on the email + password path.

## [2.6.0] — 2026-05-31 — "Multi-Strategy Auth (Hybrid + DAG + Data Act)"

- VW EU now logs in via OIDC hybrid flow (response_type=code id_token token) — bypasses Play Integrity wall.
- OAuth Device Authorization Grant (RFC 8628) module for Audi/Skoda/SEAT/CUPRA — browser-based, password-less, refresh-token-friendly. UI wiring lands in v2.7.0.
- Per-brand strategy resolver with automatic fallback (up to 3 tiers per brand).
- In-house EU Data Act portal auth as last-resort read-only fallback strategy.

## [2.5.13] — 2026-05-30 — "Play Integrity Wall Decoded"

- Discovered: Play Integrity attestation

## [2.5.12] — 2026-05-30 — "Market-Config Activation + Atlas Pipeline Audit"

- `refresh_audi_market_config()` was never called in v2.5.11
- Atlas-builder APK extraction pipeline broken since 2026-05-25
- Strategic update on #336 (VW GIS Migration)

## [2.5.11] — 2026-05-30 — "Field-tested Auth Hardening"

- VW EU was silently impersonating the Audi app via the `x-android-package-name` token
- Audi market-config dynamic discovery
- evcc-derived alternate OAuth `client_id` for Audi

## [2.5.10] — 2026-05-29 — "VW NA Polish (roberttco bundle, 2 of 5)"

- #323 — "Last Update value does not reflect last time data was updated"
- #325 — "Controls become disabled after using them"
- #322 — "Sensors are unknown or incorrect"

## [2.5.9] — 2026-05-29 — "Scout-Policy T1 — Parse What We Silenced"

- NEW `binary_sensor.camping_mode`
- CUPRA `battery.chargeEnergyInKwh` → `sensor.total_charged_energy_kwh`

## [2.5.8] — 2026-05-29 — "Silencer Sweep (campingMode + CUPRA charging rename)"

- Silenced 11 scout-reports in one sweep
- Why a single silencer-sweep release

## [2.5.7] — 2026-05-29 — "502 Resilience + OIDC Discovery + qmauth Fallback Chain"

- Stop misdiagnosing VW server outages as credentials failures
- OIDC discovery for token URL
- qmauth fallback chain

## [2.5.6] — 2026-05-28 — "APK-Primary Auth-Config with OAuth Client-ID Fallback Chain"

- NEW
- New module: `cariad/auth/_auth_config_resolver.py`
- OAuth client_id fallback chain

## [2.5.5] — 2026-05-28 — "App Atlas Phase A.5: Auth-Config Shield"

- App Atlas APK extraction now mines auth-config secrets too
- New `auth_secrets` bucket
- Audi

## [2.5.4] — 2026-05-28 — "VW Azure WAF Migration Emergency Hotfix (#313)"

- Audi and Volkswagen EU login failed with HTTP 403
- The fix (ported from evcc PR #30277 + PR #30292, MIT-licensed, merged hours earlier on
- Cross-reference (independent confirmations of the same migration)

## [2.5.3] — 2026-05-28 — "OLA v1↔v5 Fallback Chain (#306 Mii/Tavascan/Leon FR-KL Fix)"

- SEAT + CUPRA users on older vehicle generations (SEAT Mii Electric, CUPRA Tavascan VZ,
- `doors_locked` vs `doors_open` contradiction resolved
- Offline vehicle?

## [2.5.2] — 2026-05-28 — "Scout Pipeline Expansion"

- Vehicle Data Scout coverage widened across all 7 brands
- What this means for you
- Public framing

## [2.5.1] — 2026-05-28 — "Consent Wall Auto-Skip Hotfix"

- Audi/VW/Škoda/SEAT/CUPRA login regression — consent wall now auto-skipped
- Better error message for "Login redirect missing after password submission"
- Affected users

## [2.5.0] — 2026-05-27 — "Have You Met Mii?" (PyCupra Parity Sprint Part 1)

- 4 new binary_sensors
- Hints toward v3.0 — "Suit Up: The Push Tech Edition" 🎩

## [2.4.2] — 2026-05-27 — "Retro-Silencer Sweep + ActiveVentilation Interim"

- VW EU + Audi
- Silenced by code (3)
- Already-fixed in v2.4.1 — reporters on stale versions (4)

## [2.4.1] — 2026-05-25 — "OLA Defense + VW NA Garage + Scout Policy"

- OLA authentication — defense-in-depth
- Scout Policy

## [2.4.0] — 2026-05-23 — "Marketing-Rename: VAG Connect → VW Group Connect (Community Tribute)"

- 🪪 Marketing-Rename: "VAG Connect" → "VW Group Connect"

## [2.3.0] — 2026-05-23 — "VW North America Login Fix + Audi Route-aware Charging"

- #269 (roberttco VW NA, 2026-05-21) — VW North America Login (US/CA) endlich funktional
- #264 (moltke69 Audi, 2026-05-19) — Route-aware Smart Charging Sensoren

## [2.2.3] — 2026-05-23 — "Easter Egg + Sprint A Quick-wins"

- 🥚 Easter-Egg Service `vag_connect.show_vag` (Community Tribute)
- #270 (roberttco VW NA, 2026-05-21) — Config-flow Brand-Selection
  bleibt nach
- Scout #268 + #271 (VW EU arvcer, 2026-05-21/22) —
  `charging.chargingStatus.requests`

## [2.2.2] — 2026-05-18 — "Silencer Catch-up + Laien-friendly Names + Diesel Dashboards"

- Scout #260 silencer-fix + cross-language entity-name laien-cleanup
- Bubble Card ready-made templates für VAG Connect (`docs/lovelace/bubble-card/`)
- Bubble Card diesel variant `02b-vehicle-popup-diesel.yaml` (Audi
  S6 TDI tailored)

## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion (continued)

- Phase 8 PR #5 — `car_type` cross-brand derivation helper
- Phase 8 PR #4 — VW EU/Audi `primary_engine_fuel_level_pct` mirror
- Phase 8 PR #3 — Porsche electric/combustion range split

## [2.1.0] - 2026-05-15 ✨🌍 Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools / Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools

- Skoda Climate-Ready-At Sensor
- `scripts/verify_my_vin.py` — User-facing pre-flight diagnostic
- `docs/recipes/browser-mod.md` — Cookbook für browser_mod ↔ VAG Connect

## [2.0.1] - 2026-05-15 🚨🔒 Safety-Fix: `doors_locked` False-Negative Cross-Brand / Safety-Fix: `doors_locked` False-Negative Cross-Brand

- Critical Safety-Fix: `doors_locked` zeigte fälschlich "Unlocked" für tatsächlich
- CUPRA Born MY26 `charging.rateInKmph` Parser-Fallback (closes Scout #192)

## [2.0.0] - 2026-05-15 🎯🚀 Big-Bang Release — 19 PRs in einem Schlag / Big-Bang Release — 19 PRs in one shot

- `quality_scale: platinum`
- DeviceInfo `configuration_url` + `suggested_area="Garage"`
- System Health Panel

## [1.27.2] - 2026-05-11 ⚡🔌 Scout-Felder Power-Patch + Plug-Diagnose / Scout-Felder Power-Patch + Plug Diagnostics

- ✨ Neue Entities
- 🎯 Scout Issues Closed
- 📋 Scout-Pipeline-Policy

## [1.27.1] - 2026-05-11 🚨🔧 Hotfix: device_tracker GPS-Daten / Hotfix: device_tracker GPS data

- 🐛 Root cause
- 🔧 Fix
- ✅ Was jetzt funktioniert

## [1.27.0] - 2026-05-11 🔬📋 Pre-Cariad PHEV Research + Strategic Roadmap / Pre-Cariad PHEV Research + Strategic Roadmap

- `_private/research-archive/2026-05_pre-cariad-mbb-and-golf-7-gte-audit.md`
- `_private/research-archive/2026-05_strategic-roadmap-v1.27-to-v2.0.md`
- `ROADMAP.md`

## [1.26.2] - 2026-05-09 🚨🔧 Hotfix-2: Root cause `zip_release` revertet — HACS install path / Hotfix-2: Root cause `zip_release` reverted — HACS install path

- `hacs.json`
- 🔍 Root cause
- 🔄 Reverted

## [1.26.1] - 2026-05-09 🚨 Hotfix: Integration lädt nicht in v1.25.x / Hotfix: integration won't load in v1.25.x

- `manifest.json`
- `entity_base.py:device_info`
- 🔄 Reverted

## [1.26.0] - 2026-05-09 🎯 Welle-6 Feature Backlog (#173) — 7 neue Entitäten + Cross-Brand Parity / Welle-6 Feature Backlog (#173) — 7 new entities + Cross-Brand Parity

- `sensor.<vin>_secondary_engine_range_km`
- `sensor.<vin>_next_charging_timer_id`
- `sensor.<vin>_next_charging_timer_target_soc_reachable`

## [1.25.0] - 2026-05-09 🚀 Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank) / Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank)

- Cross-brand parity wins
- `_normalize.py`
- Porsche HTTP hardening

## [1.24.2] - 2026-05-08 🧪 Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration / Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration

- Echter Production-Bug gefunden + gefixt
- 🧪 Property-Tests via hypothesis / Property-Tests via hypothesis
- 🧪 Porsche + VW NA Parser Parity / Porsche + VW NA Parser Parity

## [1.24.1] - 2026-05-08 🛠️ v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening / v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening

- Ruff `E741` Ambiguous variable name `l`
- 🐛 Bugfix / Bugfix
- 🔒 Security / Security

## [1.24.0] - 2026-05-08 🚗 Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle) / Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle)

- Post-Fix
- 🐛 Bugfix — CUPRA/SEAT Silent Bug (seit OLA-Support live) / Bugfix — CUPRA/SEAT Silent Bug
- 🚀 Neu — Skoda mysmob Multi-Angle Wire-In / New — Skoda mysmob Multi-Angle Wire-In

## [1.23.0] - 2026-05-07 🚀 Audi/VW Push Foundation (Cariad FCM channel) / Audi/VW Push Foundation (Cariad FCM channel)

- Neues Modul
- Neuer Config-Flow Toggle
- Bilingual translations

## [1.22.0] - 2026-05-07 🖼️ Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic) / Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic)

- Neue Image-Entity
- `VagSkodaWidgetImageEntity` Klasse
- `_cache_all_images` Erweiterung

## [1.21.0] - 2026-05-07 🔄 Audi/VW MBB Legacy-Path Migration Phase 1 / Audi/VW MBB Legacy-Path Migration Phase 1

- MBB für andere Commands
- SPIN secure-token flow
- Country-detection

## [1.20.3] - 2026-05-07 🚨 Cariad-wrapper-404 Detection + Switch Hasattr-Gate (Audi/VW user-report) / Cariad-wrapper-404 Detection + Switch Hasattr-Gate

- Audi App-Push "Fahrzeug derzeit nicht erreichbar"
- Wake/Climate/Charging 404
- Single info-log per command

## [1.20.2] - 2026-05-07 🧹 Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle / Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle

- 3 Scaffolding-Module mit `# SCAFFOLDING — NOT WIRED` Header
- ROADMAP "Standalone enhancements" Cleanup
- ROADMAP "Last updated" Header

## [1.20.1] - 2026-05-07 🔓📚 BinarySensor LOCK-class fix (#131) + Doc refresh / BinarySensor LOCK-class fix (#131) + Doc refresh

- README.md "Was noch in Arbeit ist"
- FAQ.md
- #131

## [1.20.0] - 2026-05-06 🚗 Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment / Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment

- `GET /api/v2/widgets/vehicle-status/{vin}`
- `GET /api/v1/vehicle-information/{vin}`
- `GET /api/v1/vehicle-information/{vin}/equipment`

## [1.19.4] - 2026-05-06 🔧📊 Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue / Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue

- Quota auto-pause polling
- `is_fixable=True` mit handler
- Per-VIN quota tracking

## [1.19.3] - 2026-05-06 🛰️ Scout-Welle 6: 5 Reports, 19 truly new paths silenced / Scout Wave 6: 5 reports, 19 truly new paths silenced

- `charging` endpoint
- `air-conditioning` endpoint
- `readiness` endpoint

## [1.19.2] - 2026-05-05 🔐 Token-Persistence über HACS-Updates (#118 fix) / Token Persistence across HACS Updates (#118 fix)

- Neues Modul
- `CariadBaseClient` Erweiterungen
- Coordinator Wire-Up

## [1.19.1] - 2026-05-04 📊 Pycupra-style API Quota Sensor / Pycupra-style API Quota Sensor

- `base.py:_capture_rate_limit_headers(headers)`
- `models.py`
- `coordinator.py:_enrich`

## [1.19.0] - 2026-05-04 🚀 CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.) / CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.)

- Neues Push-Module
- Neuer Config-Flow Toggle
- Bilingual Translations

## [1.18.0] - 2026-05-04 🚀 Skoda MQTT Push Foundation (#57 Phase 1) / Skoda MQTT Push Foundation (#57 Phase 1)

- Neues Push-Package
- Neuer Config-Flow Toggle
- Lazy-Import-Strategie

## [1.17.7] - 2026-05-04 🌡️🔧 Skoda outside_temperature + preferred_workshop attrs / Skoda outside_temperature + preferred_workshop attrs

- Kein neuer Sensor, kein neuer Translation-Key, kein neues HACS-Manifest-Field
- `extra_state_attributes` auf bestehendem `service_due_in_days` Sensor
- Kein neuer Sensor, kein neuer Entity-ID

## [1.17.6] - 2026-05-04 🌍 HomeRegion-Helper Scaffolding (evcc port) / HomeRegion Helper Scaffolding (evcc port)

- `custom_components/vag_connect/cariad/_home_region.py`
- `tests/bruno/cariad_bff/22_GET_homeRegion.bru`
- `tests/test_v1176_homeregion.py`

## [1.17.5] - 2026-05-04 🛰️ Scout-Welle 5: 4 Community-Reports an einem Tag + 4 Verification-Pings / Scout Wave 5: 4 community reports in one day + 4 verification pings

- #118 eismarkt
- #51 Audi RS e-tron GT 404
- #48 all-actions-fail

## [1.17.4] - 2026-05-03 🎯 Bruno-CI Stufe 2 COMPLETE — Full Strict Coverage / Bruno-CI Stufe 2 Complete (Skoda + CARIAD-BFF strict)

- Skoda: +17 neue .bru files
- CARIAD-BFF: +11 neue .bru files
- `{path_suffix}` placeholder expansion

## [1.17.3] - 2026-05-03 🤖🛡️📚 Bruno-CI Stufe 2 + Lovelace Cards + 3 Research Docs

- Drift-check: 35/35 match, 0 drift, strict mode AKTIV in CI
- flex-table-card
- vehicle-info-card

## [1.17.2] - 2026-05-03 🧹🤖 Stale-Cleanup + Bruno-CI Stufe 1 / Stale-Reference Cleanup + Bruno-CI Foundation

- `tests/bruno/seat_cupra/`
- `tests/bruno/{skoda,cariad_bff}/`
- `scripts/check_bruno_url_drift.py`

## [1.17.1] - 2026-05-02 🚙🌬️🔥 Bruno Quick-Wins Bundle / Bruno Quick-Wins (Window heating fix + Ventilation + Aux Heating + Battery Care + Navigation #36 + 2× A/B-fallback)

- `Timwun/Cupra-WeConnect-Bruno-Collection`
- `upstream/pycupra`
- 🐛 Bug-Fixes / Bug-Fixes

## [1.17.0] - 2026-05-02 🛡️📚 Operational Hardening Bundle / Operational Hardening (Quota-protective polling + FAQ + HACS Checklist + Year-rollover Tests + Deactivated Notification)

- `vag-ha-integration-research.md`
- 🔄 Geändert / Changed
- ✨ Neu / Added

## [1.16.1] - 2026-05-02 🐛 SEAT/CUPRA Climate Fix + #122 Scout-Paths / SEAT/CUPRA Climate 404 Fix + SEAT scout-path registration

- #53 Climate
- #53 Phase 3 Phantom-Button
- 🐛 Bug-Fixes / Bug-Fixes

## [1.16.0] - 2026-05-02 ⏰📍 Cross-Brand UX + Skoda Charging Profiles / Cross-Brand UX + Skoda Charging Profiles (HA time platform #26 + #25/#31 read-only via charging-profiles + OTA Probe planning)

- Neue `entity.time` Sektion
- Skoda Vehicle-Information Bundle
- Charging Profile Write-Side

## [1.15.0] - 2026-05-02 🛰️🔋 Skoda Modernization Bundle / Skoda Modernization (Charging History #35 + OTA + 8 cap-ids + capability tolerance + anonymize hardening)

- #75 Skoda Kodiaq Mk2 403
- #26 Klima-Timer / Departure-Timer datetime UI
- #25 Standort-spezifischer Ladeziel + #31 Ladeprofile pro Standort

## [1.14.0] - 2026-05-02 🚗 Audi Feature Pack Bundle / Audi Feature Pack (Trip Stats + Engine Start ICE + PPC Climate Body) + Skoda Scout-Pfade #116

- #35 Ladehistorie LTS
- #51 RS e-tron GT Facelift
- PPE Auto-Detection

## [1.13.0] - 2026-05-02 🛡️ Production Hardening Bundle / Production Hardening (Capability Phase 3 + Read-only Phase 2 + Diagnostics-Polish + Process)

- ✨ Neu / Added
- 🔄 Geändert / Changed
- 🌐 Übersetzungen / Translations

## [1.12.3] - 2026-05-01 🛰️ Scout-Pfade #111 + #113 + #114 / Scout paths bundled with wildcard strategy

- fuelStatus
- vehicleHealthInspection
- departureProfiles

## [1.12.2] - 2026-05-01 🌟🛰️ Erstes Community-Scout-Report (Skoda #107 von tritanium73) / First community Scout report

- 4 unexpected findings sind bereits durch v1
- 2 Error-Reporter Findings sind transiente 502 Bad Gateway → v1

## [1.12.1] - 2026-04-30 🛰️📚 Scout-Pfade #105/#106 + Gerhard's Born Fixture + FAQ #47 / Scout paths + Born fixture + Subscription FAQ

- Wildcards
- Komplett anonymisiert
- Zweck

## [1.12.0] - 2026-04-30 🔋💡⚡🧯🔒 5-in-1 Feature-Sprint / Five features in one MINOR

- 📋 Doc-only — User-Data Handling + `[Inference]` Marker

## [1.11.1] - 2026-04-30 🐛💨 Golf 7 GTE Fuel-Range Fix (#96) + Optimistic UI (3B-Part-3)

- 🔧 **Drivetrain-Detection** liest jetzt aus 4 Quellen (statt 2): zusätzlich measurements
- 🔧 **carType="hybrid" flag** explizit erkannt → setzt has_battery=True UND
- 🔧 **Total range fallback** aus measurements

## [1.11.0] - 2026-04-30 🔆🔧 Issue #91 Closure: Light-Status, Service-Days, Max-Charge-Current

- Lichter-Status war nirgends zugänglich
- Service-Tage konnte man nur als Datum sehen, nicht als "noch X Tage"
- Max-Ladestrom war als Field da aber kein Sensor

## [1.10.2] - 2026-04-30 🚗 CUPRA Born 2026 Firmware-Shapes (Gerhard's #53 Live-Test)

- 🔋 battery
- 🔒 status
- 🚪 status

## [1.10.1] - 2026-04-30 🛡️ Defensive Coding Phase 2 (Issue #58)

- Skoda Parser
- VW EU/Audi Parser
- SEAT/CUPRA Parser

## [1.10.0] - 2026-04-29 🔋⛽ PHEV-Range-Triple + Audi-Diesel-Range (Issue #94)

- 🔋 **electric_range_km** ("Elektrische Reichweite")
- ⛽ **combustion_range_km** ("Kraftstoff-Reichweite")
- 🛣️ **total_range_km** ("Gesamtreichweite")

## [1.9.1] - 2026-04-29 🔧 Audi/VW Lock + Wake Hotfix + Capability-Filter Phase 2

- Audi S6 (Diesel)
- VW Golf 7 GTE

## [1.9.0] - 2026-04-29 🔬 Vehicle Data Scout + Error Reporter

- 📚 Documentation refresh

## [1.8.12] - 2026-04-29 🌐 Multi-Brand Connection-State (MVP-Move)

- 🟢🟡⚫ **connection_state Sensor** funktioniert jetzt nicht nur für Škoda (v1
- 🏆 **Erste VAG-Integration mit centralisiertem Multi-Brand Connection-State

## [1.8.11] - 2026-04-29 🚙 Škoda Online/Standby/Offline + Live-API-Erkenntnisse

- 🟢🟡⚫ **Verbindungsstatus-Sensor**
- 🚪 **Schiebedach, Kofferraum, Motorhaube** funktionieren jetzt
- 🔒 **Bessere Türschloss-Erkennung** auf neueren Modellen (Kodiaq 2026+) durch

## [1.8.10] - 2026-04-29 🩹 Hotfix


## [1.8.9] - 2026-04-29 🚗 CUPRA Born Bug-Fix-Bündel

- 🚪 **Türen, Fenster, Kofferraum, Motorhaube, Schiebedach** werden jetzt
- 🚗 **"Auto fährt gerade"** funktioniert wieder
- ⚡ **Lade-Power und Restzeit** werden korrekt angezeigt

## [1.8.8] - 2026-04-29 🔓 Lock / Climate / Charging für Audi 2025+ und Passat B9

- 🔒 **Lock/Unlock** funktioniert auf neuen Audi-Modellen (war vorher 404)
- ❄️ **Klimatisierung Start/Stop** funktioniert auf neuen Modellen
- ⚡ **Laden Start/Stop** funktioniert auf neuen Modellen

## [1.8.7] - 2026-04-29 🛡️ Stabilität — kein "Unavailable"-Flackern mehr

- 🌐 **Wochenend-Backend-Probleme** werden jetzt ausgesessen
- 🔁 **Einzelne fehlgeschlagene Polls** lösen kein "Unavailable" mehr aus
- 🐢 **Gateway-Timeouts (504)** werden automatisch nochmal versucht statt zu

## [1.8.6] - 2026-04-29 📚 Docs-Truthfulness Hotfix

- 🏆 **Multi-Brand-Successor-Position:** README sagt jetzt klar dass VAG Connect
- 🏷️ **Dynamic CI-Badge:** Statt hardcoded Test-Counts (die schnell veraltet
- 📝 **Aktuelle Stand & ehrliche Limits Section** in allen 8 README-Sprachen

## [1.8.5] - 2026-04-27

- `CommandProfile` enum
- Coordinator helpers `get_command_profile(vin)` /
  `set_command_profile(vin, profile)`
- VWEUClient `_post_command(vin, suffix)` helper

## [1.8.4] - 2026-04-27

- SEAT/CUPRA `command_lock` and `command_unlock` now use the SecToken
  flow
- `coordinator.async_lock` now requires S-PIN for SEAT/CUPRA brands
- `SpinError`

## [1.8.3] - 2026-04-27

- `vehicle_supports_capability(vin, capability_id)`
- `button.py` reads from the helper
- No effect on Audi / VW EU / Škoda / Porsche / VW NA

## [1.8.2] - 2026-04-27

- `CommandFailureReason` enum + `classify_command_failure()` helper
- Three-state feature model
- Capabilities cache

## [1.8.1] - 2026-04-27

- VIN masking in logs and diagnostics
- Diagnostics now redact more PII fields by default
- Issue templates

## [1.8.0] - 2026-04-26

- Per-VIN availability
- S-PIN fail-fast
- Fake writable entities removed

## [1.7.0] - 2026-04-25

- Škoda: Complete API rewrite
- Car-friendly entity names
- Škoda parking v3

## [1.6.1] - 2026-04-25

- Škoda
- GraphQL
- Bootstrap

## [1.6.0] - 2026-04-24

- SEAT/CUPRA
- SEAT/CUPRA vehicle renders
- SEAT/CUPRA window heating

## [1.5.13] - 2026-04-24

- Škoda camelCase tokens

## [1.5.12] - 2026-04-23

- Entity translations
- Škoda token exchange
- SEAT token exchange

## [1.5.11] - 2026-04-23

- Brand-specific token endpoints
- Token refresh

## [1.5.10] - 2026-04-22

- CUPRA/SEAT user_id
- Lock platform
- Nightly polling reduction

## [1.5.9] - 2026-04-22

- CUPRA auth
- CUPRA/SEAT scope
- SEAT/CUPRA/Škoda token endpoint

## [1.5.8] - 2026-04-22

- SEAT/CUPRA/Škoda auth
- English entity labels
- CUPRA/SEAT OAuth scope

## [1.5.6] - 2026-04-18

- Sicherheits- und Performance-Audit
- Sicherheit
- Performance

## [1.5.5] - 2026-04-18

- Behoben — IDK Auth-Logs erschienen als "Fehler" in HA

## [1.5.4] - 2026-04-13

- Bereinigung — README, Issues, letzter toter Sensor
- `connection_state` Sensor entfernt
- README komplett neu geschrieben

## [1.5.3] - 2026-04-13

- Audi Images
- GDC Filter
- Behoben — Log-Auswertung

## [1.5.3] - 2026-04-13

- Behoben — Log-Rauschen
- AZS Token / Audi Images funktioniert ✅

## [1.5.2] - 2026-04-13

- Behoben — Kompletter Entity-Audit: API-Realität vs. Erwartungen
- Entfernte Dead Entities
- API-Wahrheit: Was CARIAD BFF wirklich liefert

## [1.5.2] - 2026-04-13

- Behoben — Binary Sensor Audit
- 5 tote Binary-Sensor-Entities entfernt

## [1.5.1] - 2026-04-13

- Behoben — Sensor-Audit
- 11 tote Sensoren entfernt
- Abfahrtstimer-Sensoren repariert

## [1.5.1] - 2026-04-13

- Behoben — Sensor-Qualität
- 11 tote Sensoren entfernt
- Abfahrtstimer Zeitanzeige repariert

## [1.5.0] - 2026-04-13

- v1.5.0 — Bugs & Stabilität
- Bug #32 — `is_charging` stuck nach Ladeende
- #34 — Warnleuchten als binary_sensor

## [1.4.1] - 2026-04-13

- Docs

## [1.4.1] - 2026-04-13

- Docs

## [1.4.0] - 2026-04-13

- manifest.json
- strings.json + 8 Übersetzungen
- hacs.json

## [1.3.8] - 2026-04-13

- Behoben
- CI mypy `no-any-return` Fehler

## [1.3.7] - 2026-04-13

- Behoben
- Nicht-unterstützte Fahrzeugplattformen überspringen — Issue #709

## [1.3.6] - 2026-04-13

- Behoben
- Audi Render Images — AZS Token Exchange
- `graphql.py` — `graphql_url` Override-Parameter

## [1.3.5] - 2026-04-13

- Behoben
- GraphQL 403 Audi — korrekter Portal-Client
- VW EU GraphQL 404 — korrigierte Domain

## [1.3.4] - 2026-04-13

- Behoben
- Sensor-Crash: Inspektionsdatum + Ölwechseldatum
- Kilometerangaben ohne Dezimalstellen — Issue #17

## [1.3.3] - 2026-04-13

- Auf der Geräteseite
- Auf jeder Entity
- Behoben + Hinzugefügt

## [1.3.2] - 2026-04-12

- Hinzugefügt
- Render Images für alle EU-Marken
- Code-Refactoring

## [1.3.1] - 2026-04-12

- Geändert
- 7 Image-Entities statt 1 pro Fahrzeug
- Lokales Caching

## [1.3.0] - 2026-04-12

- Hinzugefügt
- Vehicle Render Images — Issue #15

## [1.2.0] - 2026-04-12

- Hinzugefügt
- Lademodus-Steuerung — Issue #891
- Mindest-Akkustand (Min SoC) — Issue #889

## [1.1.1] - 2026-04-12

- Behoben
- #917 — Ladegeschwindigkeit/Ladeleistung zeigt "unavailable" wenn nicht geladen wird
- #927 — Options-Flow triggert kompletten Integration-Neustart

## [1.1.0] - 2026-04-12

- Hinzugefügt
- Universelle Felder für alle Marken — `coordinator._enrich()`
- Code-Qualität

## [1.0.0] - 2026-04-12

- Erstes stabiles Release

## [0.14.25] - 2026-04-12

- Hinzugefügt
- Neue Marken: Porsche + VW North America
- Config Flow

## [0.14.23] - 2026-04-12

- Alle Entities standardmäßig sichtbar
- Geändert

## [0.14.22] - 2026-04-12

- Bug: `window_heating` mapped auf `command_start_climate`
- 7 neue Entities
- `iot_class`: `cloud_polling` → `cloud_push`

## [0.14.10] - 2026-04-12

- VW EU Scope
- BRAND_AUDI client_id
- Research-Ergebnis

## [0.14.9] - 2026-04-12

- Fixed — basierend auf volkswagencarnet (MIT) Analyse

## [0.14.8] - 2026-04-12

- Auth0 400: login_url direkt verwenden
- Kombinierter POST
- Fallback

## [0.14.7] - 2026-04-12

- Auth0 UL v2: 400 Bad Request behoben

## [0.14.6] - 2026-04-12

- Auth0 Universal Login v2
- 2FA-Unterstützung

## [0.14.5] - 2026-04-12

- Auth0 Universal Login

## [0.14.4] - 2026-04-12

- Abfahrtstimer schreiben

## [0.14.3] - 2026-04-12

- IDK Login: robusteres CSRF-Parsing
- Detailliertes Schritt-Logging

## [0.14.2] - 2026-04-12

- Audi/VW Login
- AZS Token Exchange (Audi)
- VW US/CA aus Brand-Liste entfernt

## [0.14.1] - 2026-04-12

- Semver retroaktiv korrigiert: 0
- iot_class: cloud_push → cloud_polling (wir pollen, kein Push-Protokoll)
- CI: CarConnectivity-Dependencies entfernt, mypy + coverage-threshold hinzugefügt

## [0.11.0] - 2026-04-12

- Platinum Quality Scale

## [0.10.1] - 2026-04-12

- CarConnectivity und alle 5 Brand-Connectors aus manifest
- manifest

## [0.10.0] - 2026-04-12

- cariad/
- cariad/auth/idk
- cariad/api/vw_eu

## [0.9.0] - 2026-04-12

- Lizenz: MIT → **Apache 2
- Copyright: Prash Balan (@its-me-prash) in allen Dateien
- strict-typing Platinum-Regel: 0 mypy-Fehler (--disallow-untyped-defs

## [0.8.2] - 2026-04-12

- Automatische Erkennung des requests-Versionskonflikts (HA 2026
- repairs
- Stabiler Betrieb auch bei requests-Konflikt

## [0.8.1] - 2026-04-11

- Python 3

## [0.8.0] - 2026-04-11

- diagnostics
- Stale-Device-Bereinigung bei Fahrzeugwechsel
- Gold Quality Scale vollständig: runtime_data, reauth, reconfigure,

## [0.7.0] - 2026-04-09

- Abfahrtstimer (Timer 1–3): set_departure_timer Service
- number
- Gold Quality Scale: runtime_data, reauth-Flow, reconfigure-Flow

## [0.6.0] - 2026-04-08

- EntityCategory für diagnostische Sensoren
- Sensoren: Ladeleistung kW, Ladegeschwindigkeit km/h, Akkutemperatur, Ölstand

## [0.5.0] - 2026-04-06

- Abfahrtstimer-Sensor (read-only): zeigt nächsten aktiven Timer

## [0.4.6] - 2026-04-05

- Coordinator-Crash wenn GPS-Daten None zurückgeben

## [0.4.5] - 2026-04-04

- Fensterheizung: is_on nach manuellem Toggle korrekt

## [0.4.4] - 2026-04-04

- SEAT/CUPRA: fehlende user_id → 404 auf Garage-Endpoint

## [0.4.3] - 2026-04-03

- Klimatisierungstemperatur: Kelvin→Celsius für alle Marken

## [0.4.2] - 2026-04-03

- Ladeende-ETA: negativer Wert wenn Fahrzeug voll geladen

## [0.4.1] - 2026-04-02

- Config Flow reconfigure verlor Scan-Intervall nach Speichern

## [0.4.0] - 2026-04-01

- Standort-Adresse als Sensor (OpenStreetMap Geocoding)
- Fahrtrichtung (Heading) als Sensor
- Ladesäulen-Informationen: Name, Betreiber, Adresse, Leistung

## [0.3.4] - 2026-03-31

- Škoda: Mehrfache Initialisierung des MQTT-Listeners

## [0.3.3] - 2026-03-30

- Audi: AZS-Token-Refresh nach 1h zuverlässig

## [0.3.2] - 2026-03-29

- VW EU: doors_individual leer wenn overallStatus == SAFE

## [0.3.1] - 2026-03-28

- CUPRA: command_wake 405 bei manchen Modellen ignoriert

## [0.3.0] - 2026-03-27

- Individuelle Tür-Sensoren (Fahrertür, Beifahrertür, Fond, Kofferraum)
- Fensterstatus-Sensoren

## [0.2.2] - 2026-03-25

- Mehrfache Fehlerlog-Einträge bei dauerhafter Nichterreichbarkeit

## [0.2.1] - 2026-03-24

- GPS: None statt 0

## [0.2.0] - 2026-03-23

- Ladeleistung-Sensor kW
- Ladegeschwindigkeit-Sensor km/h
- Ladeende-ETA-Sensor

## [0.1.1] - 2026-03-21

- HA 2024

## [0.1.0] - 2026-03-20

- Erste Version: VW EU, Audi, Škoda, SEAT, CUPRA
- Sensoren: Akkustand, Reichweite, Kilometerstand, GPS, Türen, Fenster, Klimatisierung,
- Services: lock, unlock, start/stop Klimatisierung, flash, wake, refresh

