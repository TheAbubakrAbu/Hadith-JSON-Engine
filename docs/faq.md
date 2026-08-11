# FAQ

## Is the data correct now?

**No — not entirely, and you should not ship it believing otherwise.**

What is solid: the reported bug is fixed, 4,477 repairs are in, 4,476 of them re-verify against the shipped text, all 50,884 hadiths verify byte-for-byte between JSON and packs, and 99.6% of the shipped English matches an independent second scrape exactly.

What is not: see below.

## What is still wrong

- **19 records are still provably truncated**, plus **22 undecidable**. Both clean donors share the same gaps, so nothing available can close them.
- **16 Ibn Majah records were refused as ambiguous** — two candidates both reproduced the damage, so neither was written. They remain damaged.
- **115 repairs rest on a single donor** with no independent confirmation. `confirmed_by: 1` in the logs marks them. These are the ones most worth a human read.
- **173 records are corroborated by no second source at all.**
- **1,252 gradings were refused** because two sources attributed contradictory verdicts to the same named scholar.
- **Bukhari and Muslim carry no gradings** — deliberately; see [03-gradings](03-gradings.md).
- **Darimi has no English translation** (3,406 records). sunnah.com has none either. Malik has 12 more empty, Ahmed 15; Malik has 125 records with no Arabic.
- **Upstream's other problems are inherited**: missing hadiths and chapter gaps. `idInBook` drift is no longer user-facing — `citation` carries the standard number on 47,476 records (93.3%) — but the row index itself still drifts and still must not be used as a citation key.
- **The Arabic has never been verified.** It is byte-identical to upstream and was never checked against sunnah.com. Treat it as inherited, not validated.

## Is a double space a sign of damage?

**Usually not.** This is the single most misleading signal in the corpus.

2,603 records carry the "scar" pattern — a doubled space welded mid-sentence, or whitespace against punctuation. Compared against the nearest clean donor:

| | Records |
|---|---:|
| Donor identical — nothing was lost | 2,562 |
| Donor holds more text — real damage | 19 |
| No close match — undecidable | 22 |

The regex over-fires roughly **130 to 1**. The source translations simply contain doubled spaces. `final_repair.py`'s docstring warns it "both over- and under-fires"; that is what it looks like measured.

If you build a damage detector, do not ship its raw count as a damage count.

## Why can't the last few be fixed?

They need a third independent source, and there isn't one available:

| Route | Result |
|---|---|
| sunnah.com directly | 403 — Cloudflare blocks scripted clients |
| `sunnah-com/data` (official) | empty — README and `.gitignore` only |
| `sunnah-com/api` | has a DB dump, but it is a **590-row Bukhari sample** |
| Wayback Machine | 429 rate-limited |
| Other public scrapes | nothing substantial beyond the two already used |

The real path is an [api.sunnah.com key](https://github.com/sunnah-com/api) — free on request. That is sunnah.com's own database: authoritative text, gradings, **and the original line structure both scrapes flattened**, which is exactly what the repair proof depends on.

One caveat if you go that route: their API runs `strip_shortcodes` to remove BBCode like `[b]`, and the pattern cannot distinguish a formatting tag from a genuine one-word insertion. `[pillars]`, `[truly]`, `[seizing]` and `[something]` are stripped; `[of His]`, `[He said:]`, `[to do]`, `[1]` survive. **134 records in this corpus hold a bracket their API would delete.** Ask for a raw dump, pre-transform, or keep the community scrapes as a fallback for those.

## Can I trust a repair?

Structurally, yes. A repair is written only if re-simulating the upstream bug on it reproduces the damaged record **exactly**. The pipeline cannot match the wrong hadith, because the wrong hadith would not reproduce the damage.

Scholarly, that is a different question. The proof shows the *same hadith* was restored; it says nothing about whether the translation is accurate or whether the donor carried its own error. A wrong translation that reproduces the damage passes the gate.

Every change is in `logs/<book>.repairlog.json` with `before` and `after`. If you are shipping this to readers, have someone qualified read the 290 second-pass diffs, starting with the 115 marked `confirmed_by: 1`.

## Why not just use sunnah.com directly at runtime?

Because the apps this serves are offline-first. A reader on a plane, in a masjid basement, or without data should still be able to read hadith. Everything ships in the box; there are no runtime network calls for hadith at all.

## Why is `idInBook` unreliable?

Upstream's numbering does not consistently match sunnah.com's ([upstream #11](https://github.com/AhmedBaset/hadith-json/issues/11)) — Jami` at-Tirmidhi 2950 sits at `idInBook` 3033. It is a fine index *within this dataset*. It is not a citation key, and it is not safe for matching against another dataset. Every tool here matches on content instead.

The number a reader should ever see is the `citation` field ([schema](01-data-schema.md#citation)), attached by [`add_citations.py`](../tools/add_citations.py): the standard sunnah.com number, content-matched from two independent donors, cross-confirmed on 24,479 records with 100% agreement after seven scrape-era site typos were adjudicated by local sequence.

## Should I use the JSON or the packs?

JSON if you are analysing, porting, or building anything that is not a shipped app. Packs if you are shipping an app and care about install size, launch time, or memory.

The JSON is the source of truth; packs are a reproducible build artifact. Nothing is in a pack that is not in the JSON.

## Do I need Swift to read a pack?

No. The format is fully specified in [04-hpk-format](04-hpk-format.md), and [`tools/read_pack.py`](../tools/read_pack.py) is a working decoder in ~200 lines of standard-library Python, written from the spec alone.

One caveat: the search payload is LZFSE, which Python's standard library cannot decompress. Display text and the eager section are LZMA, which reads as standard XZ. Repack with `HPK_SEARCH=2` to make search LZMA too, at a cost in scan speed.

## Why LZMA for text but LZFSE for search?

Opposite access patterns. Display text is read one block at a time and cached, so LZMA's better ratio (12.8 MB vs ~19 MB) is worth its ~170 MB/s decode. Search scans *every* block of *every* book — 48 MB — so it needs ~1.6 GB/s and pays 2.4 MB for it.

## Can I use this commercially? What about attribution?

The tooling here is MIT. The **text is not this repository's to license** — it originates from sunnah.com's published translations by way of three community scrapes. Respect sunnah.com's terms for the underlying translations, and preserve the provenance in [CREDITS.md](../CREDITS.md).

The upstream base dataset states no license; see the note in the README.

## How do I report a wrong hadith?

Open an issue with the book slug, `idInBook`, and what you believe the correct text is. If it is a repair this repository made, the `logs/` entry showing `before`/`after` makes it quick to check.

If the error is in sunnah.com's own text rather than in the scrape, that belongs upstream at [sunnah-com/corrections](https://github.com/sunnah-com/corrections).
