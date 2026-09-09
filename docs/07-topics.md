# 07 · The subject index

331 narrations, given plain-English titles and filed under 21 subjects in 7 lanes, so one subject can be read as Bukhari words it, next to Muslim, next to at-Tirmidhi.

[`db/topics.json`](../db/topics.json) · built by [`tools/build_topics.py`](../tools/build_topics.py)

## Why a second index

The 17 collections are organised the way their compilers organised them: by chapter, in the order each compiler chose. That is the right structure for the books, and it is the wrong one for a reader who wants to know what the Prophet ﷺ said about anger, or about a neighbour. The answer is spread across four books under four different chapter headings, and 14 of the 21 subjects here draw on more than one collection.

Chapter browsing serves the corpus. This serves the question.

It is small on purpose. 331 narrations is not a survey of the corpus and does not pretend to be one: it is a curated entry point, and everything past it is the search lanes ([`docs/06`](06-ranked-search.md)) and the books themselves.

## No text is copied

Every entry is a `slug` + `citation` pair:

```jsonc
{
  "id": "bukhari-1",
  "title": "Actions Are By Intentions",   // the curator's title, not the hadith's words
  "topic": "intention",
  "lane": "popular",
  "slug": "bukhari",
  "citation": "1",
  "tags": ["popular", "featured", "intention", "bukhari"],
  "rank": 0
}
```

Resolve `slug` + `citation` against `db/by_book/` and you get **this** repository's text, with its repairs and its gradings. That is the point of storing a citation and not a string: a curated row can never drift from the corpus behind it, and a repair made next month reaches every curated row for free.

The build enforces it. A citation that is not on the shelf **fails the build** rather than shipping a row that opens onto nothing:

```bash
python3 tools/build_topics.py --source <hadithDatabase.ts>
# 331 entries, 21 topics, 7 lanes; 23 carry a grading in this corpus
#   abudawud 13, bukhari 218, muslim 90, tirmidhi 10
```

`citation`, never `idInBook`: the standard number is the stable key, and the row index drifts ([`docs/01`](01-data-schema.md#citation)). A curation outlives an index.

## The shape

```jsonc
{
  "version": 1,
  "curation": { "by": "Jamil Hammoudeh", "project": "Tilawa", "importedOn": "2026-05-24" },
  "lanes":  [{ "id": "adhkar", "label": "Adhkar & Dua", "subtitle": "Morning, evening, salah, dhikr, and protection" }],
  "topics": [{ "id": "dhikr", "label": "Dhikr", "subtitle": "…", "lane": "adhkar" }],
  "entries": [ … ]
}
```

| Lane | Topics | Entries |
|---|---|---:|
| `foundations` | Intentions · Faith · Taqwa · Knowledge · Hope · Hereafter | 92 |
| `worship` | Purification · Prayer · Quran · Fasting · Hajj & Umrah | 73 |
| `akhlaq` | Character · Mercy · Community | 62 |
| `adhkar` | Dhikr · Dua · Protection | 48 |
| `daily-life` | Family · Charity · Trade | 43 |
| `qudsi` | Hadith Qudsi | 13 |
| `popular` | *(none)* | 26 |

## The one modelling trap

**An entry's `lane` is not its topic's `lane`.** They look like the same field and they are not.

Six lanes own topics. The seventh, `popular`, owns none: it cuts across the others, and the 26 entries carrying it are filed under topics that live in `foundations`, `worship` and the rest. Hadith 1 of Bukhari is `"topic": "intention"` (a `foundations` topic) and `"lane": "popular"` at the same time.

So there are two legitimate groupings and they answer different questions:

- **by `entry.lane`** gives 7 lanes and a Popular row: what to show on a landing screen.
- **by `topics[entry.topic].lane`** gives 6 lanes and no Popular row: where a narration belongs in the taxonomy.

Pick one deliberately. Grouping by the topic's lane silently loses the Popular lane; grouping by the entry's lane makes Popular look like a peer of Worship when it is a cross-cut. Both are correct answers to their own question and neither is a correct answer to the other.

## Ordering

`rank` is a total order over the whole index (0 to 1330, sparse, unique). It is the curator's ordering, not a computed score, and it is the order to present entries in within any grouping. Sorting alphabetically instead throws away the one editorial judgement the index carries.

`tags` are free-form and mostly redundant with `topic`, `lane` and `slug`. 32 distinct values. Treat them as search hints, not as structure.

## Gradings

23 of the 331 carry a grading in this corpus. That is not a quality signal about the curation: Bukhari supplies 218 of the entries, and sunnah.com grades neither Bukhari nor Muslim hadith by hadith, so the corpus has no grading to attach ([`docs/03`](03-gradings.md)). The gradings the index can show are the ones its Abu Dawud and at-Tirmidhi entries carry.

Every narration here is drawn from Bukhari, Muslim, Abu Dawud or at-Tirmidhi.

## Credit

The curation, the titles, the topics and the lanes are Tilawa's work (Jamil Hammoudeh), used with permission. This repository contributes the resolution to its own text and the guarantee that every row lands somewhere real. See [CREDITS.md](../CREDITS.md).
