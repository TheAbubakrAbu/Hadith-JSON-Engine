# Data dictionary

Canonical, language-agnostic hadith data. Plain UTF-8 JSON — load it from any language. Full schema and usage live in [`../docs`](../docs); this is the quick reference.

```
db/
├── by_book/
│   ├── the_9_books/   bukhari · muslim · nasai · abudawud · tirmidhi
│   │                  ibnmajah · malik · ahmed · darimi
│   ├── forties/       qudsi40 · nawawi40 · shahwaliullah40
│   └── other_books/   riyad_assalihin · bulugh_almaram · mishkat_almasabih
│                      aladab_almufrad · shamail_muhammadiyah
└── catalog.json       the 17 collections: titles, compilers, eras, descriptions, name aliases
```

`by_book/` holds the text. [`catalog.json`](catalog.json) holds everything *about* the collections — how to title and attribute them, and which name forms a `"bukhari 5"` lookup should accept — kept separate so the book files stay pure upstream schema. See [docs/01-data-schema.md](../docs/01-data-schema.md#the-catalog--dbcatalogjson).

| File | Hadiths | Chapters | English? | Graded | Repaired |
|---|---:|---:|:---:|---:|---:|
| `the_9_books/bukhari.json` | 7,277 | 97 | ✓ | — | 15 |
| `the_9_books/muslim.json` | 7,459 | 57 | ✓ | — | 88 |
| `the_9_books/nasai.json` | 5,768 | 52 | ✓ | 5,646 | 258 |
| `the_9_books/abudawud.json` | 5,276 | 43 | ✓ | 4,176 | 13 |
| `the_9_books/tirmidhi.json` | 4,053 | 49 | ✓ | 3,948 | 727 |
| `the_9_books/ibnmajah.json` | 4,345 | 38 | ✓ | 4,313 | 124 |
| `the_9_books/malik.json` | 1,985 | 61 | ✓ | 1,705 | 1 |
| `the_9_books/ahmed.json` | 1,374 | 8 | ✓ | 1,239 | 218 |
| `the_9_books/darimi.json` | 3,406 | 24 | **none** | — | 0 |
| `forties/qudsi40.json` | 40 | 1 | ✓ | — | 22 |
| `forties/nawawi40.json` | 42 | 1 | ✓ | — | 38 |
| `forties/shahwaliullah40.json` | 40 | 1 | ✓ | — | 0 |
| `other_books/aladab_almufrad.json` | 1,326 | 57 | ✓ | — | 8 |
| `other_books/shamail_muhammadiyah.json` | 402 | 57 | ✓ | 394 | 84 |
| `other_books/riyad_assalihin.json` | 1,896 | 20 | ✓ | — | 1,888 |
| `other_books/mishkat_almasabih.json` | 4,428 | 25 | ✓ | 32 | 194 |
| `other_books/bulugh_almaram.json` | 1,767 | 16 | ✓ | 2 | 799 |
| **Total** | **50,884** | **607** | | **21,455** | **4,477** |

Bukhari and Muslim show no gradings **on purpose** — sunnah.com does not grade them hadith by hadith. See [docs/03-gradings.md](../docs/03-gradings.md).

## Record shape

```jsonc
{
  "id": 40946,           // global id across the corpus
  "idInBook": 3,         // position in this book — HAS KNOWN DRIFT, not a citation key
  "chapterId": 0,        // matches chapters[].id — can be fractional
  "bookId": 10,          // redundant with the file; dropped when packing
  "citation": "3",       // ADDED BY THIS REPO; the standard sunnah.com number ("2950", "8a");
                         // absent when no standard number exists (Malik, most of Bulugh)
  "arabic": "…",         // never modified by this repository
  "english": {
    "narrator": "…",     // the isnad line; may be empty
    "text": "…",         // the matn; may be empty (all of Darimi)
    "grades": [          // ADDED BY THIS REPO; absent when unknown
      { "name": "Al-Albani", "grade": "Sahih" }
    ]
  }
}
```

Full field notes, gotchas, and the whitespace-normalisation sequence: [docs/01-data-schema.md](../docs/01-data-schema.md).

## Provenance

The schema and Arabic text come from [AhmedBaset/hadith-json](https://github.com/AhmedBaset/hadith-json). This repository changes **only** `english.text` (and, in one Muslim record, `english.narrator`), plus the added `english.grades` and `citation`.

Recovered English text and all gradings come from two independent clean scrapes — [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api) and [CheeseWithSauce/HadithsJSONFormat](https://github.com/CheeseWithSauce/HadithsJSONFormat). All three ultimately derive from [sunnah.com](https://sunnah.com).

**The Arabic has never been verified against sunnah.com.** It is byte-identical to upstream. Treat it as inherited, not validated.

Full attribution: [../CREDITS.md](../CREDITS.md).

## Audit trail

Every change is recorded in [`../logs/<book>.repairlog.json`](../logs) with the exact `before` and `after`, so any repair can be checked without re-running the pipeline:

```jsonc
{
  "idInBook": 3,
  "before": "…built on five : testifying…",
  "after":  "…built on five [pillars]: testifying…",
  "narrator_folded": false,
  "confirmed_by": 2,      // independent donors that agreed (pass 2 only)
  "pass": "line_aware"    // absent on pass-1 entries
}
```

`confirmed_by: 1` marks the 115 repairs resting on a single source — the ones most worth a human read.

## Writing files back

Serialise the way the pipeline does, or every file shows as fully rewritten:

```python
open(path, "w", encoding="utf-8").write(json.dumps(book, ensure_ascii=False))
```

Default separators, no indent, no trailing newline. Round-trips byte for byte.

## A note on the text

These are the words of the Prophet ﷺ. If you change something here, prove it — the standard this repository holds itself to is in [docs/02-repair-pipeline.md](../docs/02-repair-pipeline.md), and a gap left honestly is better than a guess written confidently.
