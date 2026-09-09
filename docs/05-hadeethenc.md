# 05 · The Hadith Encyclopedia

2,328 narrations with a scholarly explanation, a benefits list, Arabic word glosses, a grading and a full takhrij reference, in Arabic and English, filed under 452 categories.

> This is the one corpus in the repository that is **not** descended from sunnah.com.

## Why it is here

Everything under [`db/by_book/`](../db/by_book) traces back to a single scrape of sunnah.com. The two donor projects used to repair and grade it ([`docs/02`](02-repair-pipeline.md)) are scrapes of the same site. That is a real weakness and it is worth naming: a mistake upstream of all three reaches a reader through every path this engine offers, and no amount of cross-checking between the donors can see it, because they are not independent.

hadeethenc.com (الموسوعة الحديثية, the Hadith Encyclopedia), prepared under the supervision of the Dawah and Guidance Association and the Association for Serving Islamic Content in Languages, is an independent translation effort. It is also the only source here that carries, for every narration:

| | |
|---|---|
| **explanation** (`شرح`) | what the narration means, in the site's own scholarly prose. 2,328 of 2,328. |
| **benefits** (`فوائد`) | the lessons drawn from it, as a list. 2,328 in Arabic, **854** in English. |
| **words** (`معاني المفردات`) | glosses for the hard words: `{"w": …, "m": …}`. **1,479** narrations. Arabic only. |
| **reference** (`تخريج`) | the full takhrij: where the narration is found, edition and number. 2,328. |
| **grade** + **attribution** | e.g. `"Authentic hadith"` and `"Narrated by Al-Bukhari and Muslim"`. 2,328. |

`db/by_book` gives you the corpus. This gives you a curated, explained subset of it.

## Licence: attribution is a condition, not a courtesy

hadeethenc.com permits reuse on **two conditions**: no modification, addition or deletion of the content, and the source clearly credited.

So, precisely:

- **The text in `db/hadeethenc/` is not edited.** [`tools/build_hadeethenc.py`](../tools/build_hadeethenc.py) normalises structure only. The one text touch is CRLF to LF plus trimming outer whitespace, which changes no content.
- **Every screen that renders this text must render the credit.** Not a line in an About page: the credit belongs where the words are.
- **Do not add a wording pass.** Al-Islam re-punctuates em dashes in the English commentary for its own typography. That filter lives in the app, deliberately not in this repository, and it is worth knowing that it *is* a modification: if you redistribute the result, you are redistributing something these terms do not cover. The canonical data here is pristine, which is the state anyone building on it should start from.

If you do run such a filter, hold it to structure and wording, not to taste. `verify_corpora.py --pack <pack> --softened-dashes` does exactly that: the same paragraph blocks, every dash-free block character for character, the same words in the same order in the rest, and no em dash left behind. The check is not academic. Al-Islam's filter split the text into sentences and rejoined them with a single space, so every blank line in a dash-bearing explanation was silently flattened: 86 paragraph breaks across 12 narrations, turning long explanations into one wall of text. Punctuation was the licensed liberty; paragraphs were not.

Full provenance: [CREDITS.md](../CREDITS.md).

## The data

```
db/hadeethenc/
├── categories.json    452 nodes: id, parent, labels (en + ar), direct and subtree counts
└── narrations.json    2,328 narrations, Arabic and English, ascending numeric id order
```

One narration:

```jsonc
{
  "id": "1751",
  "categories": ["493"],          // ids into categories.json; a narration can sit under several
  "arabic": {
    "title": "…",                 // the site's own headline for the narration
    "intro": "…",                 // the isnad line
    "body": "…",                  // the narration, vowelled
    "explanation": "…",
    "benefits": ["…", "…"],
    "words": [{"w": "حجة الوداع", "m": "سُمِّيَتْ حَجَّة الْوَدَاع؛ …"}],
    "attribution": "متفق عليه",
    "grade": "صحيح",
    "reference": "صحيح البخاري (2/ 74) (1258 - 1259).\n…"
  },
  "english": {
    "title": "…", "intro": "…", "body": "…",
    "explanation": "…", "benefits": ["…"],
    "attribution": "…", "grade": "…"
  }
}
```

Arabic is canonical and carries three fields English has none of: `words`, `reference`, and a `benefits` list that is complete where the English one is not. English is a translation layer over it, which is why `body` in both languages tells the same narration and only the Arabic one is vowelled.

### The category tree

Seven roots, 452 nodes, five levels deep:

| Depth | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| Nodes | 7 | 39 | 232 | 136 | 38 |

```jsonc
{"id": "4", "parent": null,
 "labels": {"en": "Jurisprudence and Juristic Principles", "ar": "الفقه وأصوله"},
 "direct": 2, "total": 1311}
```

`direct` counts the narrations filed on the node itself, `total` the whole subtree.

**Never present the sum of the roots as a corpus size.** A narration can sit under several categories (1.36 on average, up to 7), so the seven roots total **3,160** against a corpus of 2,328. Deduplicate when you walk a subtree; [`tools/read_henc.py`](../tools/read_henc.py)'s `under()` shows the shape of it.

## The `.henc` container

14.8 MB of JSON is not something to parse at the door for a list of titles. `.henc` is the same trade `.hpk` makes for the books ([`docs/04`](04-hpk-format.md)): a header every screen needs, and blocks nothing reads until a narration is opened.

```bash
python3 tools/pack/pack_hadeethenc.py <out-dir>          # db/hadeethenc/ -> HadeethEnc.henc
python3 tools/read_henc.py <pack>.henc --verify          # the reference decoder
python3 tools/read_henc.py <pack>.henc --id 1751
python3 tools/read_henc.py <pack>.henc --category 493
```

14.8 MB becomes **2.9 MB**: a 145 KB header, and 19 blocks of 128 narrations each.

### Layout, version 2

All integers are little-endian and **unaligned**. Offsets in the block table are relative to the payload start, which is the first byte after the header.

```
u8[4]  magic            "HENC" (0x434E4548 read as u32 little-endian)
u16    version          2
u16    entriesPerBlock  128
u32    headerCompressed bytes of the xz header
u32    headerRaw        its inflated size
u32    blocks
u32    entries          narrations
u32    tree             categories

block table: `blocks` x 16 bytes, from offset 24
  u32 firstEntry        the index of this block's first narration
  u32 offset            from the payload start
  u32 compressed
  u32 raw

header       xz, `headerCompressed` bytes: two string tables, the tree then the light rows
payload      one xz string table per block, in block-table order
```

A **string table** is `u32 records`, then each record as `u32 fields` followed by fields of `u32 length` + UTF-8 bytes. Nothing is NUL-terminated.

**Tree record**, six fields: `id`, `parent` (empty string for a root), English label, Arabic label, `direct`, `total`. The two counts are decimal strings, not integers: the table holds strings and a reader parses them.

**Light record**, six fields: `id`, categories as a comma-joined list, English title, English intro, English grade, English attribution. This is everything a list, a category screen and a search need, so browsing the whole encyclopedia touches no block at all.

**Full record**, seventeen fields, in this order:

```
0  id                      9  arabic.reference
1  categories (comma)     10  english.title
2  arabic.title           11  english.intro
3  arabic.intro           12  english.body
4  arabic.body            13  english.explanation
5  arabic.explanation     14  english.benefits   (U+001F joined)
6  arabic.benefits        15  english.attribution
7  arabic.attribution     16  english.grade
8  arabic.grade
```

A reader indexes into that order, so **appending to it is a format change**. `benefits` is a list flattened with U+001F (unit separator); an empty field is an empty list, not a list of one empty string. `arabic.words` is **not in the pack**: the glosses are 1.9 MB for a screen most apps do not build. Keep `db/hadeethenc/narrations.json` if you want them.

### Rules a reader must follow

**Bound every count before allocating against it.** `blocks`, `entries`, `tree`, and every `u32 records` and `u32 length` inside a string table come out of the file. A truncated pack hands you a number read from garbage, and a four-billion-element reserve is an allocation failure rather than a bad read. Clamp each against what the remaining buffer could actually hold.

**Check the inflated sizes.** Both the header and every block record their raw length. A block that inflates to a different size is a corrupt pack, not a short read.

**Do not hold the payload.** The point of the container is that a reader keeps the header (145 KB) and touches a block only when a narration inside it opens. Caching decompressed blocks is fine and worth doing; caching all nineteen is the same as having parsed the JSON.

**Key a block cache by block index, not by object identity.** The same bug that bit the book packs ([`docs/PORTING`](PORTING.md)) bites here: a released pack's address can be handed straight back to the next allocation.

## Consuming it

**Plain JSON.** `db/hadeethenc/narrations.json` is 14.8 MB of ordinary UTF-8. Load it, index by `id`, done.

**Packed.** Build once with `pack_hadeethenc.py`, then read the header at launch and a block per narration. [`tools/read_henc.py`](../tools/read_henc.py) is a complete reader in ~200 lines of standard-library Python, written from this document rather than from the packer. If the two disagree, one of them is a bug.

The pack is deterministic: the same JSON produces byte-identical output, so a checksum is enough to tell whether a shipped pack is current.

## Cross-referencing the books

There is no id that joins this corpus to `db/by_book/`. The link, where you want one, is `arabic.reference`: it names the collection, the edition and the number, in Arabic, as a takhrij line rather than as a machine key. Parsing it into a `(slug, citation)` pair is possible for the common cases and is not attempted here, because a partial mapping presented as a complete one is worse than none. Treat the two corpora as neighbours, not as one joined table.
