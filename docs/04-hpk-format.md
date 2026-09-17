# The HPK pack format

`.hpk` is the binary the apps ship. This document specifies it completely (every byte, every offset), so any language can read a pack without consulting the Swift source. A working reference decoder in ~200 lines of Python is at [`tools/read_pack.py`](../tools/read_pack.py).

**The JSON in [`db/by_book/`](../db/by_book) is the source of truth. Packs are a reproducible build artifact.** Nothing is in a pack that is not in the JSON.

## Why a binary at all

The 17 books are 79 MB of JSON. Bundled as-is that is 79 MB of install footprint, and opening one book means decoding megabytes of UTF-8 into strings on the device; the whole shelf resident once a launch prewarm has run.

The packs are 25 MB total, and reading is: map the file (no resident cost), decompress **one** ~256 KB block, hand back the strings inside it.

The deeper point is that **anything decidable ahead of time is decided once, at build time**, instead of on every device on every launch:

| Precomputed at pack time | What it replaces on the device |
|---|---|
| Whitespace cleanup (hard wraps, doubled spaces, tabs, NBSP) | A regex pass over every string, on every decode |
| Arabic + English search folds, per hadith and per chapter | Normalising text per keystroke, or holding a folded copy of the library in RAM |
| Each chapter's row range | `filter { $0.chapterId == … }` over the whole book, every time a chapter opens |
| Daily-card flags (short enough; free of the blocked words) | Reading a whole book's text to choose Hadith of the Day |
| Block layout + compression | Decoding megabytes of JSON to read one chapter |
| Chapter and hadith counts | A hand-maintained table in the app that could drift from the data |

Fields the app never reads (`bookId`, the book-level `id`, chapter `bookId`, the universally empty metadata introductions), are dropped.

## Conventions

- **Little-endian** throughout.
- **String** = `u32` byte length, then that many bytes of UTF-8. Not NUL-terminated.
- Offsets are absolute from the start of the file.
- Records are 20 and 28 bytes wide, so **nothing is guaranteed to be naturally aligned**. Read integers byte by byte, or use unaligned loads.

## Header: 48 bytes at offset 0

| Offset | Type | Field |
|---:|---|---|
| 0 | `u32` | magic, `0x4B504448`, `"HDPK"` |
| 4 | `u16` | format version, currently **4** |
| 6 | `u8` | eager codec |
| 7 | `u8` | text codec |
| 8 | `u8` | search codec |
| 9 | `u8` | reserved, 0 |
| 10 | `u16` | block count |
| 12 | `u32` | chapter count |
| 16 | `u32` | hadith count |
| 20 | `u32` | eager section offset |
| 24 | `u32` | eager compressed length |
| 28 | `u32` | eager raw length |
| 32 | `u64` | fold fingerprint |
| 40 | `u64` | blocked-word fingerprint |

**Codec values:** `1` = LZFSE, `2` = LZMA. Both are Apple `Compression` framework buffer codecs; LZMA interoperates with standard XZ decoders. Current builds use LZMA for the eager section and display text, LZFSE for search folds.

**Reject the file** if the magic or version does not match. Chapter and hadith counts are repeated inside the eager section; treat the header copies as a hint and bound any allocation by what the buffer could actually hold: a truncated file otherwise hands you a reserve count read out of garbage.

## Block table: 28 bytes per block, starting at offset 48

| Offset | Type | Field |
|---:|---|---|
| 0 | `u32` | first row in this block |
| 4 | `u32` | text offset |
| 8 | `u32` | text compressed length |
| 12 | `u32` | text raw length |
| 16 | `u32` | search offset |
| 20 | `u32` | search compressed length |
| 24 | `u32` | search raw length |

## Eager section

Compressed with the eager codec; read whole when a book opens, because it is small (under 100 KB compressed for the largest book). Decompressed layout:

```
String   arabic title
String   arabic author
String   english title
String   english author
u32      chapter count
  per chapter:
    i32     chapter id          (signed; see "Chapter ids" below)
    u32     first row
    u32     row count
    String  arabic name
    String  english name
    String  arabic fold
    String  english fold
u32      hadith count
  per hadith (20 bytes, fixed):
    u32     id
    u32     idInBook
    i32     chapterId
    u32     citation base       (0 = no standard citation exists for this row)
    u8      citation suffix     (0 = none, 1...26 = "a"..."z")
    u16     block index
    u8      flags
```

The per-hadith id table is what lets a book open instantly with none of its text loaded: 50,884 of these is about 1 MB for the entire library.

### Citation

Base and suffix render as the standard sunnah.com citation, `2950`, or `8a` where one base covers several narrations (see [01-data-schema.md](01-data-schema.md#citation)). This is the number to print beside a hadith and to resolve reference lookups against; `idInBook` is the row key, not the citation. Base 0 means sunnah.com has no collection-level number for the row (all of Muwatta Malik, most of Bulugh al-Maram), fall back to `idInBook` for display. Version 2 packs carried 15-byte records without these two fields; version 4 added the fourth display string (gradings) per hadith.

### Row flags

| Bit | Name | Meaning |
|---:|---|---|
| `1 << 0` | `dailyLength` | Short enough for a daily card in both scripts, and English text is present. **Objective**, derived from the data alone. |
| `1 << 1` | `dailyGentle` | Free of the daily-card blocked words. **Policy**: trust only when the fingerprints agree. |

### Chapters are row ranges, not filters

Every book lays its hadiths out in chapter order, one unbroken run per chapter, so a chapter is a *slice* of the row table. This is an **invariant the packer checks**, not an assumption: packing fails loudly if a chapter's rows are not contiguous, if a chapter has no hadiths, or if the ranges do not cover every row. Silently shipping a book that broke the assumption would show readers the wrong hadiths.

Readers should still clamp: a corrupt or truncated eager section can leave a chapter pointing outside the row table.

### Chapter ids

`chapterId` is signed because Shama'il Muhammadiyah squeezes a sub-chapter in as the float id `8.2`. Truncating collides with chapter 8, so fractional ids map to a stable synthetic integer:

```
id == floor(id)  →  int(id)
otherwise        →  1000 + round(id * 10)      # 8.2 → 1082
```

## Per-block payloads

For each block, the display payload immediately followed by the search payload.

### Display

The block's strings back to back, length-prefixed, **four per hadith in row order**, `arabic`, `narrator`, `text`, `grades`. Hadith `row` lives at slot `(row - block.firstRow) * 4`. `grades` encodes the scholar gradings as `name U+001F grade` records joined by `U+001E`, empty when ungraded, display them verbatim ([03-gradings.md](03-gradings.md)); they are not part of the search payload. The reader splits the block once and indexes it; there is no per-hadith offset table because the split is done once and cached.

### Search

```
u32           record count
u32           arabic section length in bytes
u32 * count   arabic fold lengths
u32 * count   english fold lengths
              arabic folds, each followed by a NUL byte
              english folds, each followed by a NUL byte
```

Lengths up front give offset → row without a scan. Each record is **NUL-terminated so a match can never straddle two hadiths**. The English fold covers the narration *and* its narrator.

## The two fingerprints

Two independent repositories have to stay honest with each other, and both fingerprints are stamped into every pack.

**Fold fingerprint**: of `HadithFold.swift`, which is copied verbatim into the app. Search only works if build-time and run-time folding agree scalar for scalar. If the app's own fingerprint differs, the prebuilt search text cannot be trusted and the packs must be rebuilt. A drifted copy is caught immediately instead of quietly breaking search.

**Blocked-word fingerprint**: of the daily-card word list the flags were computed from. If it differs, nothing breaks: `dailyLength` is still objective, and the app simply rechecks the words itself for the few hadiths that pass the length gate. **Being out of sync costs speed, never correctness.**

## Reading a pack: the minimum path

1. Read and validate the 48-byte header.
2. Read the block table.
3. Decompress the eager section → titles, chapters, row table.
4. To read hadith `row`: take `rows[row].block`, decompress that block's display payload, split into strings, index `(row - firstRow) * 4`.
5. To open chapter `c`: rows `c.firstRow ..< c.firstRow + c.rowCount`. Usually 1–3 blocks.
6. To search: fold the query the same way, then byte-compare inside each block's search payload.

Cache decompressed blocks, key them by **book slug plus block index**, never by object identity. A released pack's address can be handed straight back to the next one allocated, and an identity key then serves the old book's block to the new book. (This was a real bug, found by the pack verifier reading books in order and getting Hadith Qudsi's text out of an-Nawawi's Forty.)

## Manifest

`manifest.json` is written beside the packs and records exactly what shipped: format version, both fingerprints, codecs, block target size, and per book the sha256, byte size, chapter and hadith counts, and how many hadiths qualify for a daily card. Verify against it before trusting a pack you did not build.

## Tuning

Block size is 256 KB of raw display text by default (`HPK_BLOCK` env var, in KB). Measured across 64K/128K/256K/512K/1M, the compression ratio keeps improving with size (the compressor gets a longer window), but so does the cost of touching one hadith. 256K is the knee: it gives up ~1.5 MB against 1 MB blocks and keeps a single block's LZMA decode near a millisecond, so opening a chapter is 1–3 blocks and a few milliseconds.

The codec split is deliberate and asymmetric:

- **Display text takes LZMA.** It is decompressed a block at a time and the reader caches it, so LZMA's extra saving (12.8 MB vs ~19 MB for the same text) is worth its ~170 MB/s decode: a read touches one block.
- **Search folds take LZFSE.** A query scans *every* block of *every* book, 48 MB of it, so it wants ~1.6 GB/s and pays 2.4 MB for the privilege.

Override with `HPK_TEXT` / `HPK_SEARCH` (`1` = LZFSE, `2` = LZMA).
