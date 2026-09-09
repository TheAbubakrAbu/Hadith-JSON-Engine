# Getting started

Everything here is offline. There is no API, no key, and no network call — you read files.

## Pick your path

| I want to… | Go to |
|---|---|
| Read hadith text in any language | [Use the JSON](#use-the-json) |
| Ship a fast, small offline app | [Use the packs](#use-the-packs) |
| Understand the repair and trust it | [02-repair-pipeline](02-repair-pipeline.md) |
| Show sahih / hasan / da'if | [03-gradings](03-gradings.md) |
| Write a pack reader for my language | [04-hpk-format](04-hpk-format.md) · [PORTING](PORTING.md) |
| Know what's still wrong | [faq](faq.md#what-is-still-wrong) |
| Not know what "isnad" means | [glossary](glossary.md) |

## Use the JSON

One file per collection under [`db/by_book/`](../db/by_book), grouped into `the_9_books/`, `forties/`, and `other_books/`. Plain UTF-8, no compression, no tricks.

```python
import json

book = json.load(open("db/by_book/forties/qudsi40.json"))

print(book["metadata"]["english"]["title"])       # Forty Hadith Qudsi
print(len(book["hadiths"]))                       # 40

h = book["hadiths"][23]                           # Hadith Qudsi 24
print(h["english"]["narrator"])
print(h["english"]["text"])                       # intact — this is the repaired record
```

```javascript
const book = JSON.parse(await fs.readFile("db/by_book/the_9_books/bukhari.json", "utf8"));
const chapter = book.chapters.find(c => c.id === 1);
const hadiths = book.hadiths.filter(h => h.chapterId === chapter.id);
```

Full field reference: **[01-data-schema.md](01-data-schema.md)**.

Two things to know before you build on it:

- **`idInBook` has known drift** ([upstream #11](https://github.com/AhmedBaset/hadith-json/issues/11)). Do not treat it as a stable citation key across datasets. Match by content when you cross datasets.
- **Darimi has no English** — all 3,406 records are Arabic-only, because sunnah.com has no English translation for it. Render the Arabic and omit the English block rather than showing a blank.

## Use the packs

If you are shipping an app, the JSON is the wrong thing to bundle: 79 MB of it, parsed on device. Build the packs instead.

```bash
tools/pack/build.sh /path/to/your-app
```

That compiles the packer, writes 17 `.hpk` files plus `manifest.json` into `<app>/Resources/Data/Hadith/`, and copies `HadithFold.swift` into the app so build-time and run-time folding cannot drift.

25 MB instead of 79 MB, memory-mapped, one ~256 KB block decompressed per chapter read, with search folds and chapter ranges already computed. The format is fully specified in **[04-hpk-format.md](04-hpk-format.md)** and there is a working Python decoder at [`tools/read_pack.py`](../tools/read_pack.py):

```bash
python3 tools/read_pack.py path/to/nawawi40.hpk --hadith 3
python3 tools/read_pack.py path/to/bukhari.hpk --verify
```

## Rebuild the data from scratch

Only needed if you want to re-derive the repairs rather than trust the committed result. You need the two clean donor sources laid out like this:

```
<donors>/
├── fawaz/
│   ├── eng-bukhari.json  eng-muslim.json  eng-nasai.json  eng-abudawud.json
│   └── eng-tirmidhi.json eng-ibnmajah.json eng-malik.json eng-nawawi.json
└── HadithsJSONFormat-main/
    └── Sunnah/{bukhari,muslim,nasai,abudawud,tirmidhi,ibnmajah,malik,
                ahmad,darimi,forty,adab,shamail,riyadussalihin,mishkat,bulugh}/*.json
```

```bash
# fawazahmed0 editions
for e in eng-bukhari eng-muslim eng-nasai eng-abudawud eng-tirmidhi \
         eng-ibnmajah eng-malik eng-nawawi; do
  curl -sLo "fawaz/$e.json" \
    "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/$e.json"
done

# CheeseWithSauce, whole repo
curl -sLo cws.tar.gz \
  "https://codeload.github.com/CheeseWithSauce/HadithsJSONFormat/tar.gz/refs/heads/main"
tar xzf cws.tar.gz
```

Then:

```bash
python3 tools/runall.py                                     # pass 1
python3 tools/repair_line_aware.py --donors <donors> --apply  # pass 2  (~4 min)
python3 tools/fix_leading_punctuation.py --apply
python3 tools/add_grades.py --donors <donors> --apply
python3 tools/add_citations.py --donors <donors> --apply
tools/pack/build.sh /path/to/your-app
```

Every step is a dry run by default. Drop `--apply` to see what it would change without writing.

> The CheeseWithSauce files carry a UTF-8 BOM. Read them with `utf-8-sig`, or `json.load` throws on the first character. Silently swallowing that leaves books with only one donor and quietly halves their confirmation — the tools report unreadable donor files rather than skipping them.

## The rest of `db/`

Three corpora sit beside the books and need none of the above. They are already built; the commands below only re-derive them.

```bash
python3 tools/build_hadeethenc.py --source <dump> --apply   # db/hadeethenc/, needs the site's dump
python3 tools/build_topics.py --source <ts> --apply         # db/topics.json, needs the curation
python3 tools/build_vocabulary.py --apply                   # db/vocabulary.txt, from db/by_book alone
python3 tools/pack/pack_hadeethenc.py /path/to/your-app     # HadeethEnc.henc
```

Only `vocabulary.txt` is derivable from this repository alone; the other two need their upstream source, which is why both are committed rather than generated on demand. What each one is: [05](05-hadeethenc.md), [07](07-topics.md), [06](06-ranked-search.md).

## Verify what you have

```bash
python3 tools/read_pack.py <pack>.hpk --verify   # every row decodes, chapters cover all rows
python3 tools/read_henc.py <pack>.henc --verify  # the same, for the encyclopedia container
python3 tools/verify_corpora.py                  # db/ beyond by_book, against the conformance vectors
```

`manifest.json` beside the packs carries a sha256 per pack, plus both fingerprints and the shapes. Check against it before trusting a pack you did not build yourself.
