# What's new

Every release, newest first. Each one is tagged on GitHub; the [releases page](https://github.com/TheAbubakrAbu/Hadith-JSON-Engine/releases) carries the same notes.

Version numbers describe the **data and the specifications**, not a library API: there is no package to install here, so a new version means the corpus grew, the packs changed shape, or a document now says something it did not say before. Anything that changes a `.hpk` or `.henc` byte layout is called out explicitly, because a reader built against the old one will need to know.

---

## 1.1 (9 September 2026)

The release that added a second corpus beside the nine books, and the search that reaches into it.

- **The Hadith Encyclopedia.** 2,328 narrations under 452 categories, in Arabic and English, each with a scholarly explanation, a benefits list, word glosses and a full takhrij reference. It is the only corpus here that does not descend from sunnah.com, and it carries [its own terms](05-hadeethenc.md#licence-attribution-is-a-condition-not-a-courtesy): reuse is permitted on two conditions, no modification and clear credit. Ships as `db/hadeethenc/` and as the `.henc` container. → [docs/05](05-hadeethenc.md)
- **Ranked search**, with typo correction derived from the corpus itself and both British and American spellings treated as one word (the corpus genuinely mixes `neighbour` and `neighbor`). Scoring is by *where* a word landed: a chapter title outranks a collection name, which outranks the body. → [docs/06](06-ranked-search.md)
- **A curated subject index**: 331 narrations across 21 subjects, citations only, no text. → [docs/07](07-topics.md)
- **Gradings expanded to 22,764 records**, attributed to the scholar who gave them. → [docs/03](03-gradings.md)
- **Meaning search tooling**: the `.svec` word-vector format and the MaxSim scoring over it. No model and no vectors ship; bring your own embeddings. → [docs/08](08-semantic-search.md)
- **Documentation and verification**: `tools/verify_packs.py` (666,816 assertions, every pack against the JSON it was built from) and `tools/verify_corpora.py` (everything in `db/` that is not `by_book`).

## 1.0 (10 August 2026)

The first release: the repair, and the data.

- **17 collections, 50,884 hadiths, 607 chapters**, Arabic and English.
- **4,477 repaired records.** Upstream's scraper stripped sunnah.com's editorial square brackets with a greedy regex, so in any hadith with two or more bracket pairs on one line everything between the first `[` and the last `]` was deleted. Whole sentences vanished and the surviving fragments welded together; in Forty Hadith Qudsi 24 the result made the narration say the opposite of what it says. Every fix is proof-gated by two independent passes and logged per hadith. → [docs/02](02-repair-pipeline.md)
- **Citations** in standard sunnah.com numbering, on 47,476 records.
- **The `.hpk` pack format**, fully specified: 79 MB of JSON becomes 25 MB, a chapter read decompresses one ~256 KB block, and search folds are precomputed. → [docs/04](04-hpk-format.md)
