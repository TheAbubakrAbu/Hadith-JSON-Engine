# Data schema

One JSON file per collection, under [`db/by_book/`](../db/by_book). Plain UTF-8, no BOM, no trailing newline. The schema is upstream's, unchanged, with exactly two additions: `english.grades` and `citation`.

## File shape

```jsonc
{
  "id": 5,
  "metadata": {
    "id": 5,
    "length": 4053,                       // hadith count
    "arabic":  { "title": "…", "author": "…", "introduction": "" },
    "english": { "title": "…", "author": "…", "introduction": "" }
  },
  "chapters": [ /* Chapter */ ],
  "hadiths":  [ /* Hadith  */ ]
}
```

`introduction` is empty for every book in the corpus. It is preserved for schema compatibility and dropped during packing.

## Chapter

```jsonc
{
  "id": 1,
  "bookId": 5,
  "arabic": "كتاب الطهارة عن رسول الله صلى الله عليه وسلم",
  "english": "The Book on Purification"
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | number | Usually an integer. **Can be fractional**: Shama'il Muhammadiyah has `8.2`. |
| `bookId` | number | The owning book. Redundant with the file; dropped during packing. |
| `arabic` | string | Chapter name. May be empty. |
| `english` | string | Chapter name. May be empty, fall back to the book title. |

**Fractional chapter ids.** Truncating `8.2` collides with chapter `8`. If you need integer keys, use the same mapping the packer does:

```
id == floor(id)  →  int(id)
otherwise        →  1000 + round(id * 10)      # 8.2 → 1082
```

## Hadith

```jsonc
{
  "id": 40946,
  "idInBook": 3,
  "chapterId": 0,
  "bookId": 10,
  "citation": "3",
  "arabic": "عَنْ أَبِي عَبْدِ الرَّحْمَنِ …",
  "english": {
    "narrator": "On the authority of Abdullah, the son of Umar ibn al-Khattab (ra), who said:",
    "text": "I heard the Messenger of Allah (ﷺ) say, \"Islam has been built on five [pillars]: …\"",
    "grades": [ { "name": "Al-Albani", "grade": "Sahih" } ]
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | number | Global id across the corpus. |
| `idInBook` | number | Position within the book. **Has known drift**: see below. |
| `chapterId` | number | Matches a `chapters[].id`. Same fractional caveat. |
| `bookId` | number | Redundant; dropped during packing. |
| `citation` | string | **Added by this repo.** The standard sunnah.com citation, `<digits>[a-z]?`, see below. Absent when no standard number exists. |
| `arabic` | string | The Arabic text. **Never modified by this repository.** May be empty (125 records in Malik). |
| `english.narrator` | string | The isnad line. May be empty. |
| `english.text` | string | The matn. **May be empty**: all 3,406 Darimi records, plus a few elsewhere. |
| `english.grades` | array | **Added by this repo.** Absent when no grading could be matched. |

### `citation`

The number readers actually cite and search with, sunnah.com's, which follows the Dar-us-Salam prints. `"2950"`, or `"8a"` where one base number covers several narrations (Sahih Muslim numbers variant chains as 8a/8b/…; 6,187 of its 7,459 records carry a letter). Attached by [`tools/add_citations.py`](../tools/add_citations.py) via content matching against two independent donors; never by row position, which is exactly what cannot be trusted.

Present on **47,476 of 50,884 records (93.3%)**. **Absent means "no standard number exists for this row", never "unknown":**

- **Muwatta Malik (all 1,985)**: sunnah.com has no collection-level number for it, and its Arabic-edition numbers are non-unique and incomplete.
- **Bulugh al-Maram (1,389 of 1,767)**: sunnah.com numbers only some of its books.
- Sahih Muslim's 13 unnumbered muqaddimah rows, 15 in Musnad Ahmad, 2 in an-Nasa'i, 2 in Shama'il, 2 in Mishkat.

Citations are **not unique** (every Muslim variant letter shares its base) and **not monotonic** (a repeated narration keeps its original number, "Sahih Muslim 33c" genuinely sits in Book 5). Display them and search by them; do not use them as keys. `idInBook` remains the stable row key.

### `english.grades`

```jsonc
"grades": [
  { "name": "Ahmad Muhammad Shakir", "grade": "Sahih" },
  { "name": "Al-Albani",             "grade": "Sahih" },
  { "name": "Zubair Ali Zai",        "grade": "Sahih - Bukhari And Muslim" }
]
```

Sorted by `(name, grade)`. `name` may be an empty string when the source gave a verdict without attribution. Present on 21,455 records; **absent means "not known", never "ungraded by scholars"**. See [03-gradings.md](03-gradings.md) for exactly what is and is not attached, and why Bukhari and Muslim carry none.

Do not parse `grade` into a scale. There are 2,358 distinct strings and they carry real nuance, `Sahih`, `Hasan Sahih`, `Isnaad Sahih`, `Sahih Lighairihi`, `Da'if in chain` are not points on one axis. Display them; do not rank them.

## Things that will bite you

**`idInBook` drift.** Upstream's numbering does not reliably match sunnah.com's ([upstream #11](https://github.com/AhmedBaset/hadith-json/issues/11)), Jami` at-Tirmidhi 2950 sits at `idInBook` 3033. It is fine as an index *within this dataset*. It is **not** a citation key (`citation` is), and it is not safe for matching against another dataset, match on text instead. Every tool in this repo does.

**Empty English.** Darimi has none at all; sunnah.com has no English translation for it. Malik has 12 more, Ahmed 15. Render the Arabic and omit the English block; do not show an empty field.

**Empty Arabic.** 125 records in Malik. Same treatment in reverse.

**Whitespace.** The corpus carries hard-wrapped lines, doubled spaces, tabs, and no-break spaces. Deliberate paragraph breaks (blank lines) are meaningful; other whitespace runs are not. The packer collapses them; if you read the JSON directly, do the same:

```
\r\n | \r        → \n
\t   | U+00A0    → space
[ ]*\n[ ]*       → \n
\n{2,}           → paragraph break (keep)
remaining \n     → space
[ ]{2,}          → space
then trim
```

**A doubled space is not evidence of damage.** 2,562 records look scarred but lost nothing: the source translations simply contain doubled spaces. See [faq.md](faq.md#is-a-double-space-a-sign-of-damage).

**The Arabic is untouched.** Every repair in this repository modifies `english.text`, and in one case `english.narrator`. The Arabic is byte-identical to upstream and has never been verified against sunnah.com, treat it as inherited, not validated.

## Books

| Folder | Slug | Hadiths | Chapters |
|---|---|---:|---:|
| `the_9_books` | `bukhari` | 7,277 | 97 |
| `the_9_books` | `muslim` | 7,459 | 57 |
| `the_9_books` | `nasai` | 5,768 | 52 |
| `the_9_books` | `abudawud` | 5,276 | 43 |
| `the_9_books` | `tirmidhi` | 4,053 | 49 |
| `the_9_books` | `ibnmajah` | 4,345 | 38 |
| `the_9_books` | `malik` | 1,985 | 61 |
| `the_9_books` | `ahmed` | 1,374 | 8 |
| `the_9_books` | `darimi` | 3,406 | 24 |
| `forties` | `qudsi40` | 40 | 1 |
| `forties` | `nawawi40` | 42 | 1 |
| `forties` | `shahwaliullah40` | 40 | 1 |
| `other_books` | `aladab_almufrad` | 1,326 | 57 |
| `other_books` | `shamail_muhammadiyah` | 402 | 57 |
| `other_books` | `riyad_assalihin` | 1,896 | 20 |
| `other_books` | `mishkat_almasabih` | 4,428 | 25 |
| `other_books` | `bulugh_almaram` | 1,767 | 16 |
| | **Total** | **50,884** | **607** |

## The catalog, `db/catalog.json`

A separate, single file describing the **collections** rather than their text: how each is titled in both scripts, who compiled it and when, what it is in a line and in a paragraph, and the name forms a reference lookup should accept.

It is kept out of the book files deliberately. `db/by_book/*.json` carries upstream's schema and the text, and nothing else belongs in there; a reader that only wants hadiths never has to skip past editorial prose. The two are checked against each other by `tools/verify_packs.py`, so the counts and the book order cannot drift apart.

**Which side is authoritative, for this file only.** Everything else here flows outward: the corpus is repaired in this repository and an app's packs are built from it, so when the two disagree about hadith text the app is stale. The catalog's *prose* is the exception. The titles, author names and descriptions are not scraped or derived from anything; they were written for the consuming app's own shelf, in its voice, and `verify_packs.py` cross-checks them against `HadithCatalogBook.all` precisely because the same facts then exist in two places. For those nine fields the app is upstream and this file follows it, which is what `tools/sync_app_catalog.py` does:

```bash
python3 tools/sync_app_catalog.py --app /path/to/Al-Islam-iOS            # dry run
python3 tools/sync_app_catalog.py --app /path/to/Al-Islam-iOS --apply
```

It refuses the whole run rather than carry a bad rewrite across: a vocalization pass may add and remove marks, so every Arabic change must leave the consonantal skeleton identical, and no incoming text may contain a sukoon. That is what separates a cosmetic refresh from a corrected name hiding inside one.

```jsonc
{
  "version": 1,
  "groups": [ { "key": "six", "title": "THE SIX BOOKS" }, … ],
  "books": [
    {
      "slug": "bukhari",                  // matches the file name and the pack name
      "number": 1,                        // 1-based position in the corpus order
      "folder": "the_9_books",            // which db/by_book/ directory holds it
      "group": "six",                     // one of the keys in `groups`
      "groupTitle": "THE SIX BOOKS",
      "englishTitle": "Sahih al-Bukhari",
      "arabicTitle": "صَحِيح البُخارِي",     // vocalized; no sukoon, final letters left bare
      "authorEnglish": "Imam Muhammad ibn Ismail al-Bukhari",
      "authorArabic": "الإِمَامُ مُحَمَّدُ بنُ إِسمَاعِيلَ البُخَارِيُّ",
      "era": "d. 256 AH / 870 CE",        // the classical way these books are dated
      "shortDescription": "…",            // one or two lines, for a list row
      "longDescription": "…",             // the fuller story; "\n\n" separates paragraphs
      "aliases": ["bukhari", "bukharee", "bokhari", …],
      "chapters": 97,
      "hadiths": 7277
    }
  ]
}
```

| Field | Notes |
|---|---|
| `slug` | The join key for everything: `db/by_book/<folder>/<slug>.json`, `<slug>.hpk`, the manifest. |
| `number` | Corpus order, the six canonical collections, the three early ones, the forties, then the rest. Chronological by compiler within each group. |
| `arabicTitle`, `authorArabic` | **Vocalized**, unlike the book file's `metadata.arabic.title`, which is bare. Both are correct; these are meant to be displayed. Tashkeel on every letter *except* that a sukoon is never written: a letter that would carry one carries nothing. The Arabic inside `longDescription` follows the same rule. |
| `aliases` | Lowercase alphanumeric name forms, apostrophes and hyphens removed, for resolving `"bukhari 5"`. Unique across the corpus, no alias names two books. |
| `chapters`, `hadiths` | The real shape, asserted against the data by `tools/verify_packs.py`. |

**Resolving a reference like `"nasa'i 5"`.** Lowercase the name, drop apostrophes, split on non-alphanumerics, and discard the words that name no collection on their own: the articles (`al`, `an`, `as`, `ad`, `at`, `the`, `of`, `imam`) and the generic words that appear across half the shelf (`sahih`, `sunan`, `jami`, `musnad`, `hadith`, `forty`, `book`, `collection`). What is left is matched against `aliases`. This is what makes `"Hadith 24"` resolve to nothing, correctly: it names no book: while `"Qudsi 24"` resolves to one. A name that fits more than one collection should resolve to **nothing** rather than a guess.

## Writing the files back

If you modify a book, serialise it the way the repo does, or every file will show as fully rewritten:

```python
open(path, "w", encoding="utf-8").write(json.dumps(book, ensure_ascii=False))
```

Default separators, no indent, no trailing newline. This round-trips the committed files byte for byte.
