# Changelog

All notable changes to the data and tooling. The corpus is 50,884 hadiths across 17 collections throughout; entries below describe what changed *about* those records.

## [Unreleased]

### Added

- **Pack verification gate** — [`tools/verify_packs.py`](tools/verify_packs.py) re-derives every string, id, citation, chapter range, daily flag, and search fold from `db/by_book` and compares it against the shipped packs, then asserts every section of `conformance/vectors.json` and the manifest checksums: **666,816 assertions** on an LZFSE build, 768,584 when the search payload is LZMA (`HPK_SEARCH=2`). Standard library only, so a port can use it as its own acceptance test. `tools/pack/build.sh` now runs it and fails the build on any mismatch. Packing successfully was never the same as packing *correctly* — a stale rebuild, an edited JSON that was never repacked, or a packer bug all produce files that decode perfectly and ship the wrong text; nothing caught those before.
- **The search fold, portable** — [`tools/fold.py`](tools/fold.py) is `HadithFold.swift` with no Apple frameworks and nothing outside the standard library: the Swift original leans on `CharacterSet`, this one spells out the Unicode categories it means. It reproduces the packer's fold fingerprint (`87ae980f6662910b`) and, verified across the whole corpus, every one of the 101,768 per-row search folds character for character. This is the file to translate when porting the engine — the fold is the one part a port can get wrong *silently*, since a mismatched fold returns no results rather than an error.
- **Collection catalog** — [`db/catalog.json`](db/catalog.json): the 17 collections as data rather than as someone's UI code — titles in both scripts (Arabic vocalized), compiler and era, short and long descriptions, and the 102 name aliases needed to resolve a reference like `"nasa'i 5"`. Held apart from `db/by_book/` so the book files stay pure upstream schema, and cross-checked against the corpus — and against the consuming app's compiled copy — by the verifier, so the two can no longer drift. [docs/01-data-schema.md](docs/01-data-schema.md#the-catalog--dbcatalogjson)

- **Standard citation numbers** — `citation` on **47,476 records (93.3%)**: the sunnah.com number readers actually cite ("2950", "8a"), which upstream's `idInBook` drifts from progressively (Jami` at-Tirmidhi 2950 sat at `idInBook` 3033 — a user report). Content-matched from two independent donors with a structural guard against anthology-duplicate mispairs; cross-confirmed on 24,479 records with 100% final agreement, after adjudicating seven scrape-era sunnah.com typos by local sequence (all seven confirmed by the second donor). Absence means *no standard number exists* (all of Muwatta Malik, most of Bulugh al-Maram — sunnah.com numbers neither), never "unknown". [`tools/add_citations.py`](tools/add_citations.py) · [docs/01-data-schema.md](docs/01-data-schema.md#citation)
- **HPK format v3** — the per-row record grew from 15 to 20 bytes to carry the citation (u32 base + u8 suffix). Spec, reference decoder, and conformance vectors updated; v2 readers reject v3 packs by design. [docs/04-hpk-format.md](docs/04-hpk-format.md)
- **HPK format v4** — the display payload grew from three to four strings per hadith: the scholar gradings (`name U+001F grade` records joined by `U+001E`), so apps can finally show sahih/hasan/da'if without carrying the JSON. The gradings had been in `db/by_book/` since `add_grades.py` ran; the packs simply dropped them. +0.2 MB across all 17 packs. [docs/04-hpk-format.md](docs/04-hpk-format.md)

- **Scholar gradings** — `english.grades` on **21,455 records (42.2%)**, from 10+ named scholars (Zubair Ali Zai, Al-Albani, Darussalam, Shuaib Al Arnaut, and others). Matched by content, never by hadith number. Nothing computed or adjudicated; where scholars differ, every verdict is kept. [`tools/add_grades.py`](tools/add_grades.py) · [docs/03-gradings.md](docs/03-gradings.md)
- **Documentation suite** — `docs/` with getting-started, architecture, data schema, repair pipeline, gradings, the byte-level pack format, porting guide, glossary, and FAQ.
- **Portable pack specification** — [docs/04-hpk-format.md](docs/04-hpk-format.md) documents `.hpk` completely, so the format is no longer readable only from the Swift source.
- **Reference pack decoder** — [`tools/read_pack.py`](tools/read_pack.py), ~200 lines of standard-library Python written from the spec alone. Verifies all 7,277 Bukhari rows.
- **Conformance vectors** — [`conformance/vectors.json`](conformance/vectors.json), behavioural truth any port can assert against.
- **Data dictionary** — [`db/README.md`](db/README.md).

### Fixed

- **[docs/PORTING.md](docs/PORTING.md) claimed `read_pack.py --verify` asserts the conformance vectors.** It does not, and never did — it is a decode check that prints per-book counts. A port following that instruction would have believed it had passed a conformance suite it never ran. The two tools and what each actually proves are now spelled out.
- **290 further hadiths repaired** by a second, line-aware pass. Pass 1's simulation used a single greedy strip over the whole string, but the upstream regex is per-line and both donors ship the text flattened — so any hadith with a bracketed insertion *and* a bracketed citation could never satisfy the proof. Those records were **unprovable, not undamaged**. [`tools/repair_line_aware.py`](tools/repair_line_aware.py) · [docs/02-repair-pipeline.md](docs/02-repair-pipeline.md)
  - Nawawi's Forty went from 19 damaged records to **zero**, including #3 (`[pillars]`) and #9 (`[to do]`, an entire missing clause).
  - 174 of the 290 are confirmed by two independent donors; 116 rest on one.
- **646 pass-1 repairs opened with a narrator fragment** — `"): Two men set out…"`. The proof compares with `norm`, which discards punctuation, so a split before the `):` closing a narrator and one after it were indistinguishable to it. Proof-neutral to fix. [`tools/fix_leading_punctuation.py`](tools/fix_leading_punctuation.py)
- **Donor loading silently failed on most books.** The CheeseWithSauce files carry a UTF-8 BOM; `json.load` threw and the error was swallowed, leaving books with one donor instead of two. Now read as `utf-8-sig`, and unreadable files are reported rather than skipped.

### Changed

- README restructured around what the engine *is* and what is still wrong with it.
- **Corrected the residual-damage figure.** The previous "~2,750 further records carry the signature of a deletion" reads as a damage count and is not one. Measured against the nearest clean donor: **2,562 lost nothing** (the scar regex over-fires ~130:1), **19 are genuinely damaged**, **22 undecidable**. The honest residual is 19 + 22, not ~2,750.

### Known issues

- 19 records still provably truncated; 22 undecidable; 16 Ibn Majah records refused as ambiguous. All need a third source.
- 115 repairs rest on a single donor (`confirmed_by: 1` in the logs).
- 1,252 gradings refused for contradictory attribution to the same scholar.
- Darimi has no English translation at all (3,406 records); sunnah.com has none either.
- Missing hadiths and chapter gaps are inherited from upstream. `idInBook` drift is answered by the `citation` field, but the row index itself still drifts and remains a row key, not a citation.

## [1.0.0]

### Added

- **4,187 hadiths repaired** from the greedy-bracket bug in `AhmedBaset/hadith-json`, using two independent clean scrapes and a proof gate: re-simulating the bug on a candidate must reproduce the damaged record exactly, so a mis-attributed repair is structurally impossible. Matching by content, never by hadith number. [`tools/final_repair.py`](tools/final_repair.py)
  - Reported upstream as [issue #17](https://github.com/AhmedBaset/hadith-json/issues/17).
  - Worked example: Forty Hadith Qudsi 24, where the deletion inverted the meaning so the hadith read *"If Allah has loved a servant … I abhor So-and-so"*.
- **Full audit trail** — `logs/<book>.repairlog.json` holds `before`/`after` for every change.
- **The `.hpk` pack format and packer** — 79 MB of JSON to 25 MB, memory-mapped, block-lazy, with whitespace cleanup, search folds, chapter row ranges, and daily-card flags all precomputed at build time. Fold and blocked-word fingerprints stamped into every pack so the two repositories cannot silently drift. [`tools/pack/`](tools/pack)
- Honorific rendering normalised to the `ﷺ` ligature (4,148 occurrences).
