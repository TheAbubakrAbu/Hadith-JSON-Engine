# Porting

How to consume this engine from a language that has no reader yet. Two levels: read the JSON (trivial, works everywhere) or read the packs (a day's work, worth it for a shipped app).

## Level 1 — read the JSON

There is nothing to port. The files are plain UTF-8 JSON with no compression and no custom encoding. Follow [01-data-schema](01-data-schema.md) and you are done.

[`db/catalog.json`](../db/catalog.json) comes with it and needs no reader at all: how each of the 17 collections is titled in both scripts, who compiled it and when, what it is, and the name forms a reference lookup like `"bukhari 5"` should accept. It is presentation data, kept out of the book files on purpose so the text stays pure — take it or ignore it.

The only subtleties are data ones, and they apply in every language:

- **Chapter ids can be fractional.** `8.2` in Shama'il Muhammadiyah. If your model uses integers, apply the mapping in the schema doc rather than truncating — truncation collides with chapter 8.
- **`english.text` can be empty.** All 3,406 Darimi records. Omit the block; do not render a blank.
- **`idInBook` is not a citation key.** Index within this dataset only.
- **Normalise whitespace at read time** unless you are packing (the packer does it once for you). The exact sequence is in the schema doc.

## Level 2 — read the packs

The complete byte-level specification is [04-hpk-format](04-hpk-format.md). [`tools/read_pack.py`](../tools/read_pack.py) is a working decoder in ~200 lines of standard-library Python, written from that spec alone — treat it as the executable version of the document. If a port and the spec disagree, one of them is a bug.

### What you need from your language

| Requirement | Notes |
|---|---|
| Little-endian integer reads | `u8`, `u16`, `u32`, `i32`, `u64`. **Unaligned** — records are 20 and 28 bytes wide. |
| UTF-8 decoding | Strings are `u32` length + bytes, not NUL-terminated. |
| LZMA / XZ decompression | For the eager section and display text. Apple's LZMA output reads as standard XZ. |
| LZFSE decompression | **Only** for the search payload. Skip it if you do not need search. |
| Memory mapping | Optional but the whole point — it keeps untouched text out of your footprint. |

If LZFSE is unavailable in your language, either skip search or rebuild with `HPK_SEARCH=2` to make the search payload LZMA. That costs scan speed and about 2.4 MB, and it is a legitimate trade if it makes a platform reachable. `tools/verify_packs.py` verifies the per-row search folds on such a build too — the chapter folds ride in the LZMA eager section and are always checked, whichever codec search uses.

### Order of work

1. Header — validate magic `0x4B504448` and version `4`. Reject otherwise.
2. Block table — 28 bytes each, from offset 48.
3. Eager section — decompress whole; parse titles, chapters, row table.
4. Display text — decompress a block on demand; split into strings; index `(row - firstRow) * 4`.
5. Search — fold the query, byte-compare inside the block's search payload.

### Rules a port must follow

**Bound every count before you allocate against it.** The header's block count, and the eager section's chapter and hadith counts, come out of the file. A truncated or corrupt pack hands you a number read from garbage, and a four-billion-element reserve is an allocation failure rather than a bad read. Clamp each against what the remaining buffer could actually hold — 28 bytes per block-table entry, 28 per chapter minimum, 20 per row.

**Clamp chapter ranges.** A corrupt eager section can leave a chapter pointing outside the row table. Clamp once at load, so no call site has to bounds-check a slice it was handed.

**Key your block cache by book slug plus block index — never by object identity.** A released pack's address can be handed straight back to the next allocation, and an identity key then serves the old book's block to the new book. This was a real bug: the pack verifier read books in order and got Hadith Qudsi's text out of an-Nawawi's Forty.

**Check the fold fingerprint before trusting prebuilt search text.** If your folding differs from the packer's, the folds are meaningless. Fail loudly and rebuild.

**Treat the blocked-word fingerprint as advisory.** If it differs, recheck the words yourself for the few rows that pass the objective length gate. Out of sync should cost speed, never correctness.

**Do not straddle records when searching.** Each fold is NUL-terminated for exactly this reason. Search within a record's byte range, never across the block.

## Conformance

[`conformance/vectors.json`](../conformance/vectors.json) is the single source of behavioural truth. Every port should assert against it, so a behaviour is specified **once** there instead of re-asserted in N hand-written test files. Add a case there and every port picks it up.

It covers:

- corpus shape — book, chapter, and hadith counts
- known texts — including the records this repository repaired, so a port that reads stale data fails
- chapter row ranges — contiguity and full coverage
- pack invariants — magic, version, fingerprints
- fractional chapter id mapping
- the encyclopedia's counts, tree shape, and known records
- the subject index's counts per lane and per book, and that every citation resolves
- the vocabulary's size, hash, and bounds
- ranked-search weights, stopwords, and seven query probes with their top hits

Two tools run against it, and they answer different questions:

```bash
python3 tools/read_pack.py <pack>.hpk --verify   # does this pack DECODE? per-book counts
python3 tools/verify_packs.py <packs-dir>        # does it say what the JSON says? every vector asserted
python3 tools/verify_corpora.py                  # the same, for everything in db/ that is not by_book/
```

`read_pack.py --verify` is a decode check: every row reachable, chapter ranges covering the corpus, and the counts printed for a human to read. It does **not** assert the vectors.

[`tools/verify_packs.py`](../tools/verify_packs.py) is the acceptance test. It re-derives every string, id, citation, chapter range, daily flag, and search fold from `db/by_book` and compares it against the pack, then asserts every section of `vectors.json` and the manifest checksums — around 670,000 assertions, standard library only. **A port should be able to pass the same checks**; if your reader and this tool disagree about a book, one of you is wrong, and the JSON says which.

## The fold is the part ports get wrong

Everything else in a pack is bytes you either read correctly or don't. The search fold is different: it is a *transformation*, it happened at build time, and a port that folds queries even slightly differently gets silence rather than an error — the query simply never matches text that is sitting right there.

[`tools/fold.py`](../tools/fold.py) is the fold in portable Python, with no Apple frameworks and nothing outside the standard library. **It is the file to translate**, not `HadithFold.swift`, because the Swift original leans on `CharacterSet` and the Python one spells out the Unicode categories it means.

Prove your port before trusting it. The fold's own fingerprint is stamped into every pack header:

```bash
python3 tools/fold.py                 # 87ae980f6662910b — must equal the header's value
python3 tools/fold.py "الصلاة خير من النوم"
```

Run the same probes (`fold.PROBES`) through your implementation, hash the results the same way, and compare. They are chosen so that changing any single rule changes the fingerprint — hamza carriers, dagger alif, alif maqsurah, teh marbuta, tashkeel, Quranic signs, the salawat ligature, punctuation, case, and whitespace collapsing. If it matches, your fold agrees with the packer everywhere. If it doesn't, refuse the prebuilt search text and fold at runtime instead of shipping a search that quietly finds nothing.

## Level 3: the rest of `db/`

Three more corpora sit beside the books, and none of them needs the pack reader.

| What | Read it as | Spec |
|---|---|---|
| [`db/hadeethenc/`](../db/hadeethenc) | plain JSON, or the `.henc` container | [05](05-hadeethenc.md) |
| [`db/topics.json`](../db/topics.json) | plain JSON; resolve `slug` + `citation` against `db/by_book/` | [07](07-topics.md) |
| [`db/vocabulary.txt`](../db/vocabulary.txt) | one word per line, UTF-8 | [06](06-ranked-search.md) |

`.henc` is a second container with its own layout, simpler than `.hpk`: a header holding the category tree and a light row per narration, then xz blocks of full narrations. The same three rules apply to it and for the same reasons. Bound every count from the file before allocating against it, check each inflated size against the length recorded for it, and key a block cache by block index rather than by object identity. [`tools/read_henc.py`](../tools/read_henc.py) is the reference decoder, written from the spec rather than from the packer.

## The two files to translate

The fold is the first ([below](#the-fold-is-the-part-ports-get-wrong)). The second is [`tools/ranked_search.py`](../tools/ranked_search.py), and it is worth translating for the same reason: it is a *transformation*, it decides what a reader sees, and a port that gets it subtly wrong returns plausible results in the wrong order rather than an error.

Everything it does is a byte compare against the folds a pack already carries, so a port needs nothing new from its language. What it needs is care with the details that look incidental and are not:

- **A row can match through its chapter alone.** Chapter and collection scores are computed once per chapter and added to every row of it, so a block whose folds contain no word of the query can still hold rows that count. A reader that skips blocks by content must exempt the blocks holding a matched chapter's rows, or those rows disappear from the results with nothing to indicate they were dropped.
- **A stem matches at a word start only**, never mid-word, and is discounted. The other spelling (`neighbour` / `neighbor`) is charged at full price, because the corpus genuinely contains both.
- **A word already in the vocabulary as a substring is never "corrected".** A half-typed word is a prefix, not a mistake, and correcting it takes the search away from what the reader is about to type.
- **Ties break on `(-score, slug, row)`.** Without a total order, two correct ports produce different lists and neither can be checked against the other.

[`conformance/vectors.json`](../conformance/vectors.json) pins seven probes under `rankedSearch`, with the hit count, the corrections, the relaxed flag and the top five for each. Assert against those.

## A note on scope

A port does **not** need to reimplement the repair pipeline. That is a build-time concern producing the data in `db/by_book/`; a consuming app reads the result. Unless you are re-deriving the corpus from the donor sources, ignore `tools/*.py` entirely and port only the reader.
