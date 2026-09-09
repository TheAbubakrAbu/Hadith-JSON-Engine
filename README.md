# Hadith JSON Engine

**An open-source, offline-first, framework-agnostic hadith engine.** The complete text of 17 collections — 50,884 hadiths in Arabic and English — *repaired* from a scraper bug that had been silently deleting sentences for years, graded by named scholars, and shipped as **portable data + a documented binary pack format + precise specifications**, so anyone can build a hadith app in any language on any platform. No network required; everything ships in the box.

> The data originates from [AhmedBaset/hadith-json](https://github.com/AhmedBaset/hadith-json), which scraped [sunnah.com](https://sunnah.com). This repository repairs it, grades it, documents it, and packages it for offline apps. It is the data layer behind **[Al-Islam | Islamic Pillars](https://github.com/TheAbubakrAbu/Al-Islam-iOS)**. See [CREDITS.md](CREDITS.md).

<a href="https://apps.apple.com/us/app/al-islam-islamic-pillars/id6449729655?platform=iphone">
  <img src="Logo.png" alt="Logo" width="120" style="border-radius:10px;"/>
</a>

## At a glance

| | |
|---|---|
| **50,884** hadiths | **17** collections |
| **607** chapters | Arabic + English |
| **4,477** repaired records | **2** independent proof-gated passes |
| **22,764** graded records | **10+** named scholars |
| **47,476** cited records | standard sunnah.com numbering |
| **2,328** explained narrations | a second, independent corpus |
| **331** curated entries | 21 subjects across 4 collections |
| **32,555** vocabulary words | typo correction from the corpus itself |
| **79 MB** JSON → **25 MB** packs | **3.15x**, block-lazy |
| **0** network calls at runtime | 100% offline |

---

## Why this exists

**Every hadith app is built on the same handful of scraped datasets, and the most widely used one is quietly broken.**

`AhmedBaset/hadith-json` strips sunnah.com's editorial square brackets with a **greedy** regex ([`scrapeData.ts:70`](https://github.com/AhmedBaset/hadith-json/blob/main/src/helpers/scrapeData.ts#L70)):

```ts
.replace(/\[.*\]/g, "")
```

`.*` is greedy, so in any hadith containing two or more bracket pairs on one line, the match runs from the **first `[`** to the **last `]`** and everything between them is deleted. With one pair you lose `[of His]`. With two, whole sentences vanish and the surviving fragments weld together.

In Forty Hadith Qudsi 24, both halves of the narration contain `a servant [of His]`, so the match spans them:

> If Allah has loved a servant, He calls Gabriel and says: I **abhor** So-and-so, therefore abhor him.

The hadith is made to say that Allah abhors the servant He loves. The Arabic in the same record is complete — the record contradicts itself. This was reported by a user of Al-Islam, which is how the work began.

This repository fixes that, proves every fix, and documents everything precisely enough to rebuild from scratch.

**New here? → [docs/00-getting-started.md](docs/00-getting-started.md).** New to the terms (isnad, matn, sahih, musnad…)? → the [glossary](docs/glossary.md).

## What's inside

```
Hadith-JSON-Engine/
├── db/                         ← canonical data (language-agnostic; the core deliverable)
│   ├── by_book/
│   │   ├── the_9_books/        bukhari · muslim · nasai · abudawud · tirmidhi
│   │   │                       ibnmajah · malik · ahmed · darimi
│   │   ├── forties/            qudsi40 · nawawi40 · shahwaliullah40
│   │   └── other_books/        riyad_assalihin · bulugh_almaram · mishkat_almasabih
│   │                           aladab_almufrad · shamail_muhammadiyah
│   ├── catalog.json            how each collection is titled, attributed, and named
│   ├── hadeethenc/             the Hadith Encyclopedia: 2,328 explained narrations, 452 topics
│   ├── topics.json             a curated subject index: 331 narrations, 21 subjects, 7 lanes
│   └── vocabulary.txt          the corpus's own English words, for correcting a typed one
├── logs/                       ← per-hadith before/after for all 4,477 repairs
├── docs/                       ← comprehensive documentation
│   ├── 00-getting-started · architecture · glossary · faq
│   ├── 01-data-schema          the JSON contract
│   ├── 02-repair-pipeline      the bug, the proof, both passes
│   ├── 03-gradings             sahih/hasan/da'if, and what is refused
│   ├── 04-hpk-format           the binary pack format, portable spec
│   ├── 05-hadeethenc           the encyclopedia corpus and the .henc container
│   ├── 06-ranked-search        scoring by where a word landed; typo correction
│   ├── 07-topics               the curated subject index
│   ├── 08-semantic-search      meaning search, and the .svec vector pack
│   └── PORTING.md              read the packs from any language
├── tools/                      ← the pipeline
│   ├── final_repair.py         pass 1 · whole-string greedy proof
│   ├── repair_line_aware.py    pass 2 · per-line grouping proof
│   ├── fix_leading_punctuation.py
│   ├── add_grades.py           scholar gradings, content-matched
│   ├── add_citations.py        standard sunnah.com numbers, content-matched
│   ├── read_pack.py            reference decoder · the executable spec
│   ├── read_henc.py            the same for the encyclopedia container
│   ├── fold.py                 the search fold, portable · the file to translate
│   ├── ranked_search.py        ranked search, portable · the other file to translate
│   ├── semantic.py             meaning search and the .svec pack, portable
│   ├── build_hadeethenc.py     the encyclopedia corpus, structure-only normalisation
│   ├── build_topics.py         the subject index · every citation must resolve
│   ├── build_vocabulary.py     the search vocabulary, derived from the corpus
│   ├── verify_packs.py         the gate · proves a pack IS its JSON
│   ├── verify_corpora.py       the gate for everything in db/ that is not by_book/
│   └── pack/                   build.sh · pack-hadith.swift · pack_hadeethenc.py
└── conformance/vectors.json    ← behavioural truth any port can assert against
```

## Engine modules

Each module is data first and stands alone — take the text and ignore the rest, or adopt all of it:

| Module | What it does | This engine |
|---|---|---|
| Hadith text | 50,884 hadiths, Arabic + English + narrator | ✓ |
| Repair | proof-gated recovery of scraper-deleted text | 4,477 |
| Gradings | sahih / hasan / da'if by named scholars | 21,455 |
| Citations | the standard sunnah.com numbers ("2950", "8a") | 47,476 |
| Chapters | 607 chapters, contiguous row ranges | ✓ |
| Search folds | precomputed Arabic + English normalisation | ✓ |
| Packing | 3.15x block-compressed binary, lazy reads | ✓ |
| Daily selection | precomputed length + editorial flags | 12,039 |
| Encyclopedia | explained narrations, benefits, glosses, takhrij | 2,328 |
| Subject index | curated topics across collections | 331 |
| Ranked search | word-independent scoring, stems, typo correction | ✓ |
| Meaning search | word-vector MaxSim, model-agnostic | ✓ |
| Framework-agnostic | plain JSON, plus a documented binary | ✓ |

Specifications, in reading order:

1. **[Data schema](docs/01-data-schema.md)** — the JSON contract, field by field
2. **[Repair pipeline](docs/02-repair-pipeline.md)** — the bug, the proof gate, both passes
3. **[Gradings](docs/03-gradings.md)** — what is attached, and what is deliberately refused
4. **[HPK format](docs/04-hpk-format.md)** — the binary pack, byte by byte
5. **[The Hadith Encyclopedia](docs/05-hadeethenc.md)**: the second corpus, and the `.henc` container
6. **[Ranked search](docs/06-ranked-search.md)**: scoring by where a word landed, and typo correction
7. **[The subject index](docs/07-topics.md)**: 331 narrations by subject, citations only
8. **[Meaning search](docs/08-semantic-search.md)**: word-vector MaxSim, and the `.svec` pack
9. **[Porting](docs/PORTING.md)** — read the data or the packs from any language

## Two ways to consume this

**Plain JSON** — the canonical product. Any language reads it; nothing is hidden.

```python
import json
book = json.load(open("db/by_book/forties/qudsi40.json"))
book["hadiths"][23]["english"]["text"]   # Hadith Qudsi 24, intact
```

**Packed `.hpk`** — a build artifact for apps that need speed and size. 79 MB of JSON becomes 25 MB, opening a chapter decompresses one ~256 KB block instead of parsing a book, and search folds are precomputed so a keystroke is a byte compare. The format is fully specified in [docs/04-hpk-format.md](docs/04-hpk-format.md) — it is not a private format.

```bash
tools/pack/build.sh /path/to/your-app
```

The JSON is the source of truth. The packs are reproducible from it, and nothing is in a pack that is not in the JSON — and that is **checked, not asserted**. `build.sh` finishes by re-deriving every string, id, citation, chapter range, flag, and search fold from `db/by_book` and comparing it against what it just wrote:

```bash
python3 tools/verify_packs.py <packs-dir>     # ~670,000 assertions, standard library only
```

Packing successfully is not the same as packing correctly: a stale rebuild, an edited JSON that was never repacked, or a packer bug all produce files that decode perfectly and ship the wrong text. This is the gate that catches them. The build is also deterministic — the same JSON produces byte-identical packs, so a checksum is enough to tell whether a shipped pack is current.

## The repair, in short

A record is treated as damaged **if and only if** a clean candidate exists such that

```
simulate_bug(clean) == damaged      # provably the same hadith
clean               != damaged      # text was provably lost
```

Re-running the upstream bug on the candidate must reproduce the damaged record exactly. If it doesn't reproduce, nothing is written — a mis-attributed repair is structurally impossible, because the wrong hadith would not reproduce the damage. Matching is **by content, never by hadith number**, since upstream's `idInBook` has [known drift](https://github.com/AhmedBaset/hadith-json/issues/11).

Two passes were needed, because the first simulation was subtly wrong. Full detail: **[docs/02-repair-pipeline.md](docs/02-repair-pipeline.md)**.

| Book | Hadiths | Pass 1 | Pass 2 | Repaired | % |
|---|---:|---:|---:|---:|---:|
| `other_books/riyad_assalihin` | 1,896 | 1,885 | 3 | 1,888 | 99.6% |
| `other_books/bulugh_almaram` | 1,767 | 756 | 43 | 799 | 45.2% |
| `the_9_books/tirmidhi` | 4,053 | 626 | 101 | 727 | 17.9% |
| `the_9_books/nasai` | 5,768 | 194 | 64 | 258 | 4.5% |
| `the_9_books/ahmed` | 1,374 | 209 | 9 | 218 | 15.9% |
| `other_books/mishkat_almasabih` | 4,428 | 189 | 5 | 194 | 4.4% |
| `the_9_books/ibnmajah` | 4,345 | 107 | 17 | 124 | 2.9% |
| `the_9_books/muslim` | 7,459 | 71 | 17 | 88 | 1.2% |
| `other_books/shamail_muhammadiyah` | 402 | 80 | 4 | 84 | 20.9% |
| `forties/nawawi40` | 42 | 18 | 20 | 38 | 90.5% |
| `forties/qudsi40` | 40 | 22 | 0 | 22 | 55.0% |
| `the_9_books/bukhari` | 7,277 | 9 | 6 | 15 | 0.2% |
| `the_9_books/abudawud` | 5,276 | 13 | 0 | 13 | 0.2% |
| `other_books/aladab_almufrad` | 1,326 | 7 | 1 | 8 | 0.6% |
| `the_9_books/malik` | 1,985 | 1 | 0 | 1 | 0.1% |
| `forties/shahwaliullah40` | 40 | 0 | 0 | 0 | 0.0% |
| `the_9_books/darimi` | 3,406 | 0 | 0 | 0 | 0.0% |
| **Total** | **50,884** | **4,187** | **290** | **4,477** | **8.8%** |

`logs/` holds a `before`/`after` record for every single change, so any repair can be audited without re-running anything.

## Gradings

Upstream carries **no grading field at all**, so a reader cannot tell sahih from da'if. [`tools/add_grades.py`](tools/add_grades.py) attaches `english.grades` — **22,764 records (44.7%)** from 10+ named scholars. Nothing is computed or adjudicated; where scholars differ, every verdict is kept.

| Grader | Records | | Verdict | Records |
|---|---:|---|---|---:|
| Al-Albani | 18,590 | | Sahih | 41,053 |
| Zubair Ali Zai | 17,563 | | Hasan | 7,640 |
| Darussalam | 14,059 | | Daif | 7,201 |
| Shuaib Al Arnaut | 5,783 | | Hasan Sahih | 3,298 |

Full detail, including the three categories of grading this deliberately **refuses** to write: **[docs/03-gradings.md](docs/03-gradings.md)**.

## Performance

Indicative figures, Apple Silicon. Packing decides everything decidable ahead of time, once, so no device repeats it:

- **Storage:** 79 MB JSON → **25 MB** packed (3.15x). Whitespace cleanup, search folds, chapter ranges, and daily-card flags are all precomputed.
- **Opening a book:** the eager section only — titles, chapters, and the id table, under 100 KB compressed for the largest book. The 12 MB of text behind it stays on disk.
- **Opening a chapter:** 1–3 LZMA blocks, a few milliseconds. Not a scan of the book.
- **Search:** a byte compare against precomputed folds, with no String allocated and no normalisation pass per keystroke.
- **Memory:** packs are memory-mapped, so untouched text is never resident and touched pages are clean and evictable.

## Known limitations

Read [docs/faq.md](docs/faq.md#what-is-still-wrong) before assuming the data is perfect. In brief:

- **19 records are still provably truncated**, plus 22 undecidable. Both clean donors share the same gaps.
- **115 repairs rest on a single donor** with no independent confirmation (`confirmed_by` in the logs says which).
- **16 Ibn Majah records were refused as ambiguous** and left damaged rather than guessed at.
- **2,562 records look scarred but lost nothing** — the scar heuristic over-fires roughly 130 to 1. Do not read a scar count as a damage count.
- **Darimi has no English at all** (3,406 records) — sunnah.com has no English translation for it.
- **Upstream's other problems are inherited**: missing hadiths and chapter gaps. `idInBook` drift is answered by the `citation` field (93.3% coverage; the rest have no standard number to carry), but the row index itself still drifts.
- **The proof is structural, not scholarly.** It proves a repair restored the *same hadith*; it cannot prove a translation is accurate.
- **Nothing joins the encyclopedia to the books.** `db/hadeethenc/` carries a takhrij reference in Arabic prose, not a machine key, so the two corpora are neighbours rather than one joined table. A partial mapping presented as a complete one would be worse than none, so none is attempted.
- **The subject index is 331 narrations, not a survey.** It is a curated entry point over four collections, and 218 of its entries are from Bukhari.
- **Meaning search ships no model and no vectors.** The lane is specified and implemented; the embedding is yours, and a `.svec` pack built against one model or one revision of the text must be rejected by any reader running against another.

## Regenerating

```bash
python3 tools/runall.py                                    # pass 1
python3 tools/repair_line_aware.py --donors <dir> --apply  # pass 2
python3 tools/fix_leading_punctuation.py --apply           # narrator-tail cleanup
python3 tools/add_grades.py --donors <dir> --apply         # scholar gradings
python3 tools/add_citations.py --donors <dir> --apply      # standard citation numbers
tools/pack/build.sh /path/to/your-app                      # build the .hpk packs

python3 tools/build_hadeethenc.py --source <dir> --apply   # the encyclopedia corpus
python3 tools/build_topics.py --source <ts> --apply        # the subject index
python3 tools/build_vocabulary.py --apply                  # the search vocabulary
python3 tools/pack/pack_hadeethenc.py /path/to/your-app    # build HadeethEnc.henc
python3 tools/verify_corpora.py --pack <pack>.henc         # the gate for all of the above
python3 tools/verify_corpora.py --pack <pack>.henc --softened-dashes   # ... for a pack whose
                                                           # English commentary was re-punctuated
```

See [docs/00-getting-started.md](docs/00-getting-started.md) for what `<dir>` must contain.

## Sources

| Role | Repo | License |
|---|---|---|
| Base data & schema | [AhmedBaset/hadith-json](https://github.com/AhmedBaset/hadith-json) | none stated |
| Clean text & grades | [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api) | Unlicense |
| Clean text & grades | [CheeseWithSauce/HadithsJSONFormat](https://github.com/CheeseWithSauce/HadithsJSONFormat) | MIT |
| The encyclopedia corpus | [hadeethenc.com](https://hadeethenc.com) | reuse permitted: **no modification**, credit required |
| Subject curation & search weights | Tilawa (Jamil Hammoudeh) | used with permission |

The first three ultimately derive from [sunnah.com](https://sunnah.com); `db/hadeethenc/` does not, which is the point of it. Please respect sunnah.com's terms for the underlying translations; this repo claims no ownership of them. Full provenance: [CREDITS.md](CREDITS.md).

> **Note on upstream licensing:** AhmedBaset/hadith-json states no license. This repo redistributes its schema and Arabic text on the same basis the upstream project redistributes sunnah.com's. If the upstream author objects, open an issue and it will be taken down.

## The Al-Islamic Apps

Five repositories by the same author: three apps, and the two engines the apps are built on. Everything is free, offline-first, and open source.

**Apps**

- [**Al-Islam | Islamic Pillars**](https://github.com/TheAbubakrAbu/Al-Islam-iOS) — prayer times, the Quran, hadith, tafsir, and the Islamic essentials in one app
- [**Al-Adhan | Prayer Times**](https://github.com/TheAbubakrAbu/Al-Adhan-iOS) — prayer times, adhan notifications, and the Qibla
- [**Al-Quran | Beginner Quran**](https://github.com/TheAbubakrAbu/Al-Quran-iOS) — the Quran for beginners and Arabic learners

**Engines** — the data layers behind those apps, extracted so anyone can build on them in any language

- [**Hadith JSON Engine**](https://github.com/TheAbubakrAbu/Hadith-JSON-Engine) — *this repository*. 50,884 hadiths across 17 collections: repaired, graded, cited, and packed
- [**Quran Tajweed Engine**](https://github.com/TheAbubakrAbu/Quran-Tajweed-Engine) — the same idea for the Quran: 6,236 ayahs with pre-computed tajweed, qiraat, and recitations

## License & attribution

The tooling, documentation, and specifications here are MIT — see [LICENSE](LICENSE). Use, modify, and redistribute them freely, **with attribution**, and preserve the provenance in [CREDITS.md](CREDITS.md).

**The hadith text is not this repository's to license.** It belongs to the tradition, and its English rendering to the translators and publishers whom [sunnah.com](https://sunnah.com) credits. These are the words of the Prophet ﷺ — keep them accurate, and keep the chain of attribution intact.

## Contributing

Better sources, closed gaps, new language ports of the pack reader, and scholarly review of the repairs are all welcome — especially the last one. See [CONTRIBUTING.md](CONTRIBUTING.md).

## A note on intent

This project — like **[Al-Islam](https://github.com/TheAbubakrAbu/Al-Islam-iOS)**, **[Al-Adhan](https://github.com/TheAbubakrAbu/Al-Adhan-iOS)**, **[Al-Quran](https://github.com/TheAbubakrAbu/Al-Quran-iOS)**, and the **[Quran Tajweed Engine](https://github.com/TheAbubakrAbu/Quran-Tajweed-Engine)** — is offered as *sadaqah jariyah*. These are the words of the Prophet ﷺ; they deserve to be transmitted accurately. If a hadith in your app is wrong, someone may act on it. That is the whole reason this repository exists, and why every repair here is gated by a proof rather than a guess.

If it helps you, keep the chain of attribution intact and contribute improvements back.

> *"When a person dies, all their deeds end except three: a continuing charity (sadaqah jariyah), beneficial knowledge, or a righteous child who prays for them."* — Prophet Muhammad ﷺ (Sahih Muslim)
