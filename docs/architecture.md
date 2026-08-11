# Architecture

How this repository is put together, and why. Read this once and the rest makes sense.

## Design principles

1. **Data-first.** The canonical product is the JSON in [`db/by_book/`](../db/by_book). Code is replaceable; the data is the asset. Any language reads JSON, so the engine is automatically cross-platform.
2. **Proof, not heuristic.** Nothing is written to a hadith unless re-simulating the upstream bug on the replacement reproduces the damaged record exactly. A heuristic that is right 99% of the time is wrong about 500 hadiths, and these are the words of the Prophet ﷺ.
3. **Refuse rather than guess.** Ambiguity, donor disagreement, and unprovable candidates all result in the record being left exactly as upstream has it. A gap is honest; an invention is not.
4. **Match by content, never by number.** Upstream's `idInBook` drifts, so every cross-dataset match is on text.
5. **Decide once, at build time.** Anything a device would otherwise recompute on every launch — folding, chapter ranges, whitespace, daily-card eligibility — is computed here and stamped into the pack.
6. **Fingerprint what must agree.** Where two repositories hold copies of the same logic, each pack carries a fingerprint of both, so drift is detected instead of silently corrupting behaviour.

## Layers

```
        ┌──────────────────────────────────────────────────────────────┐
        │  YOUR APP  (SwiftUI / Compose / React / Flutter / CLI / …)    │
        └──────────────────────────────┬───────────────────────────────┘
                                       │  reads JSON, or maps a .hpk
        ┌──────────────────────────────▼───────────────────────────────┐
        │  PACKS  (build artifact — optional)                           │
        │  17 × .hpk + manifest.json · 25 MB · block-lazy, mmapped      │
        │  spec: docs/04-hpk-format.md · reader: tools/read_pack.py     │
        └──────────────────────────────┬───────────────────────────────┘
                                       │  tools/pack/build.sh
        ┌──────────────────────────────▼───────────────────────────────┐
        │  DATA  (db/by_book/**.json)  ← THE SOURCE OF TRUTH            │
        │  17 books · 50,884 hadiths · 607 chapters · repaired + graded │
        └──────────────────────────────▲───────────────────────────────┘
                                       │  tools/*.py, each proof-gated
        ┌──────────────────────────────┴───────────────────────────────┐
        │  SOURCES                                                      │
        │  AhmedBaset/hadith-json  (base, damaged)                      │
        │  fawazahmed0/hadith-api  ·  CheeseWithSauce/HadithsJSONFormat │
        │  all three ultimately scraped from sunnah.com                 │
        └──────────────────────────────────────────────────────────────┘
```

## The pipeline

Each stage is idempotent and dry-run by default. Each writes an audit trail.

| Stage | Tool | What it does |
|---|---|---|
| 1 | [`final_repair.py`](../tools/final_repair.py) + [`runall.py`](../tools/runall.py) | Whole-string greedy proof. 4,187 repairs. |
| 2 | [`repair_line_aware.py`](../tools/repair_line_aware.py) | Per-line grouping proof — the records pass 1 could not model. 290 repairs. |
| 3 | [`fix_leading_punctuation.py`](../tools/fix_leading_punctuation.py) | Trims narrator tails (`"): Two men…"`) left by pass 1. 646 records. |
| 4 | [`add_grades.py`](../tools/add_grades.py) | Attaches scholar gradings, content-matched. 21,455 records. |
| 5 | [`add_citations.py`](../tools/add_citations.py) | Attaches the standard sunnah.com citation numbers, content-matched. 47,476 records. |
| 6 | [`pack/build.sh`](../tools/pack/build.sh) | Builds the 17 `.hpk` packs + manifest. |

Stages 1–5 mutate `db/by_book/`; stages 1–3 append to `logs/`. Stage 6 reads `db/by_book/` and writes only into the target app.

Why two repair passes exist, and why the first one's simulation was subtly wrong, is the single most important thing to understand about this repo: **[02-repair-pipeline.md](02-repair-pipeline.md)**.

## Two repositories, kept honest

The packer and the app each hold a copy of logic that must agree exactly. Copies drift. So each pack carries a fingerprint of both, and the app checks its own against them:

| Shared thing | Copy A | Copy B | If they drift |
|---|---|---|---|
| Search folding | `tools/pack/HadithFold.swift` | `<app>/iPhone/Hadith/HadithFold.swift` | Caught immediately; packs must be rebuilt, because prebuilt folds cannot be trusted. |
| Daily blocked words | `tools/pack/daily-blocked-words.txt` | the app's `Settings.dailyCardBlockedWords` | Nothing breaks. The app rechecks the words itself for the few hadiths that pass the objective length gate. |

The asymmetry is deliberate. A drifted fold is a **correctness** problem, so it fails loudly. A drifted word list is a **policy** problem, so it degrades to recomputation. Being out of sync costs speed, never correctness.

`build.sh` copies `HadithFold.swift` into the app on every build, so drift is not something you have to remember to avoid.

## What is derived, and from what

| Artifact | Derived? | Reproducible by |
|---|---|---|
| `db/by_book/**.json` | repaired + graded from upstream | the pipeline above, given the donors |
| `logs/*.repairlog.json` | audit trail | written by stages 1–3 |
| `*.hpk`, `manifest.json` | build artifact | `tools/pack/build.sh` |
| Search folds, chapter ranges, daily flags | computed at pack time | inside the packs only; never stored in the JSON |

Note the last row: the JSON is deliberately kept as close to the upstream schema as possible, with `english.grades` and `citation` the only additions. Everything else the app needs is computed during packing rather than baked into the canonical data — so the JSON stays a clean, portable hadith corpus rather than an app-specific format.

## Why chapters are ranges

Every book lays its hadiths out in chapter order, one unbroken run per chapter. That makes a chapter a *slice* of the row table instead of a filter over it, which is the difference between opening a chapter in constant time and scanning 7,277 records.

This is an **invariant the packer verifies**, not an assumption it makes. Packing fails loudly if a chapter's rows are not contiguous, if a chapter has no hadiths, or if the ranges do not cover every row. If a future data update breaks the property, the build stops rather than shipping a book that shows readers the wrong hadiths.

## Auditing without re-running

`logs/<book>.repairlog.json` holds one entry per change:

```jsonc
{
  "idInBook": 3,
  "before": "…built on five : testifying…",     // exactly what upstream shipped
  "after":  "…built on five [pillars]: testifying…",
  "narrator_folded": false,
  "confirmed_by": 2,        // how many independent donors agreed (pass 2 only)
  "pass": "line_aware"      // absent on pass-1 entries
}
```

`confirmed_by: 1` marks the 115 repairs that rest on a single source. Those are the ones worth a human read.
