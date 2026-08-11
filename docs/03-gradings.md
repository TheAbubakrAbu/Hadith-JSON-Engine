# Gradings

Upstream's schema is `arabic` + `english{narrator, text}` and carries **no authentication grading at all**. A reader cannot tell a sahih narration from a da'if one. For Tirmidhi and Ibn Majah especially that is not cosmetic — those collections contain graded-weak material *by design*, and presenting it undifferentiated misrepresents it.

[`tools/add_grades.py`](../tools/add_grades.py) adds `english.grades`. **21,455 of 50,884 records (42.2%)** carry at least one verdict.

## What you get

```jsonc
"grades": [
  { "name": "Ahmad Muhammad Shakir", "grade": "Sahih" },
  { "name": "Al-Albani",             "grade": "Sahih" },
  { "name": "Darussalam",            "grade": "Sahih" },
  { "name": "Zubair Ali Zai",        "grade": "Sahih - Bukhari And Muslim" }
]
```

| Grader | Records | | Verdict | Records |
|---|---:|---|---|---:|
| Zubair Ali Zai | 17,563 | | Sahih | 40,862 |
| Al-Albani | 17,492 | | Hasan | 7,606 |
| Darussalam | 13,848 | | Daif | 7,201 |
| Shuaib Al Arnaut | 5,783 | | Hasan Sahih | 3,298 |
| Abu Ghuddah | 5,437 | | Sahih - Agreed Upon | 1,950 |
| Muhammad Fouad Abd al-Baqi | 4,267 | | Isnaad Sahih | 1,806 |
| Muhammad Muhyi Al-Din Abdul Hamid | 4,056 | | Isnaad Hasan | 1,750 |
| Ahmad Muhammad Shakir | 3,541 | | Sahih Muslim | 1,531 |

Coverage by book:

| Book | Graded | % |
|---|---:|---:|
| `abudawud` | 4,176 | 79.2% |
| `ibnmajah` | 4,313 | 99.3% |
| `shamail_muhammadiyah` | 394 | 98.0% |
| `nasai` | 5,646 | 97.9% |
| `tirmidhi` | 3,948 | 97.4% |
| `ahmed` | 1,239 | 90.2% |
| `malik` | 1,705 | 85.9% |
| everything else | ~34 | — |

## What it does not do

**Nothing is computed, inferred, or adjudicated.** These are sunnah.com's gradings, which are themselves quoting the named scholars. This tool matches and attaches them.

**Where graders disagree, every verdict is kept.** Reconciling `Al-Albani: Da'if` against `Shuaib Al Arnaut: Hasan` is a scholarly judgement, not a data-processing one, and this repository is not qualified to make it. Show all of them with attribution.

**Do not rank the strings.** There are 2,358 distinct verdicts and they carry real nuance. `Sahih`, `Isnaad Sahih` (the *chain* is sound, which is a narrower claim), `Sahih Lighairihi` (sound *by external corroboration*), and `Da'if in chain` are not points on a single axis. Collapsing them to a green/yellow/red badge will misrepresent them. Display the text and the grader.

**Absent means "not known", never "ungraded by scholars".**

## What is deliberately refused

Three categories, each caught by inspection before writing.

### 1. Bukhari and Muslim get nothing — on purpose

sunnah.com does not grade those two collections hadith by hadith; they are sahih by definition of the collections. CheeseWithSauce's `grade` column for them holds the **reference** instead:

```
bukhari  grade = "Sahih al-Bukhari 1"
muslim   grade = "Sahih Muslim 8 a"
tirmidhi grade = "Grade : Sahih (Darussalam)"     ← the real format
```

A first implementation that accepted those stamped **14,736 fake gradings** that were really just hadith numbers, each one unique. The parser now **requires the literal `Grade :` prefix**, which reference strings do not have.

If your UI wants to say something about Bukhari and Muslim, say it at the collection level. Do not synthesise per-hadith verdicts.

### 2. Contradictory attribution — 1,252 records

Where the two sources attribute **different verdicts to the same named grader**, neither is written:

```
nasai #15  Zubair Ali Zai:  "Hasan"  vs  "Sahih - Agreed Upon"
nasai #59  Zubair Ali Zai:  "Isnaad Sahih"  vs  "Sahih"
```

Mostly `abudawud` (1,097), then `nasai` (115). Some of these are not true contradictions — `Sahih` and `Sahih - Agreed Upon` are compatible — but picking one would mean deciding which source is right about what a scholar said. Refusing is cheap; being wrong is not.

### 3. Misaligned source columns — whole books

In `riyadussalihin`, `adab`, `forty`, `mishkat` and `malik`, CheeseWithSauce's `grade` column contains **the entire hadith text**, English and Arabic both. Their scraper misaligned the field for those books. That data is unusable and is rejected wholesale, which is why those collections show near-zero coverage.

One further cleanup: many entries repeat the verdict in Arabic after the English one —

```
"Grade : Sahih (Al-Albani) صحيح (الألباني) حكم :"
```

Both halves say the same thing. The English half is kept and everything from the first Arabic letter is cut, otherwise the grader's name is buried behind the Arabic and never parses out.

## How matching works

By content, never by hadith number. A grading is written only when the donor record is provably the same hadith:

- **exact** — `norm(donor) == norm(ours)`, or
- **clean twin** — some line-grouping of the donor reproduces ours, i.e. the donor is the undamaged version of a record still carrying greedy-bracket damage (see [02-repair-pipeline](02-repair-pipeline.md))

Anything else is left ungraded. If two donor records with *different* gradings both match, neither is written.

The tool is **idempotent**: it clears `grades` before each run, so a re-run cannot leave a stale verdict on a record that no longer matches.

## In the packs

Since pack format v4 the gradings ride in the packs as each hadith's fourth display string — `name U+001F grade` records joined by `U+001E`, empty when ungraded. See [04-hpk-format.md](04-hpk-format.md#display) for the encoding.
