This is the rest-of-world My Porsche build — the one EU owners install.
North America runs `com.porsche.one`, tracked on [`porsche.md`](porsche.md).

At **20.26.37** (versionCode 188460) the two are the same code: the DEX
string-pool diff is empty apart from the package-name strings and one
Porsche-Card product-availability path, and the Firebase config is identical.
Both are polled anyway, so a future divergence shows up as two different
version rows rather than as nothing at all.

The build string names the flavour. When this package was last fetched and
opened it read `20.26.36-row+186611`, where the North-American APK read
`20.26.37-pcna+188460` — those are APK readings, and they are older than the
`21.26.39` the version table carries, which came from a mirror listing. The
atlas records only the dotted part of such a string: a suffixed one does not
compare against a plain one, and that comparison is what stops a lagging
reading from walking the brand backwards.

**Source: none, as of 2026-10-17.** Google Play publishes no version for
either Porsche package — not "Varies with device", simply absent — and Play is
now the only source this pipeline uses. Whatever version-name the table below
shows is therefore a retained reading, not a current one: it came from a mirror
that is no longer polled, and it had stopped being re-confirmed before that:
the cache records `last_confirmed_at` of 2026-10-05 against a
`last_checked_at` of 2026-10-09 and `last_status: stale`, so no run after the
5th confirmed it. Read the number as "last known", which is what the Reading
row says.
Re-measure before treating the gap as permanent — VW-NA sat in the same group
and now answers.
