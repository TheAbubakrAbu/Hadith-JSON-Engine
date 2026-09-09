# Credits & data provenance

This engine would not exist without the people and projects below. Please preserve this attribution in any redistribution.

## The translations

Every English translation in this corpus originates from **[sunnah.com](https://sunnah.com)**, which publishes the standard printed translations of these collections. The three datasets below are all scrapes of sunnah.com; none of them, and not this repository, holds any ownership of the underlying translations.

**Please respect [sunnah.com's terms](https://sunnah.com/about) for the translations.** If sunnah.com objects to any part of this redistribution, open an issue and it will be taken down.

## Data sources

| Role | Project | License |
|---|---|---|
| Base data, schema, and all Arabic text | [AhmedBaset/hadith-json](https://github.com/AhmedBaset/hadith-json) | none stated |
| Clean English text + gradings + citation cross-check | [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api) | Unlicense |
| Clean English text + gradings + citation numbers | [CheeseWithSauce/HadithsJSONFormat](https://github.com/CheeseWithSauce/HadithsJSONFormat) | MIT |

**AhmedBaset/hadith-json** provides the structure this repository is built on — the book/chapter/hadith schema, the global ids, and the complete Arabic text, which is redistributed here **byte-identical and unmodified**. The greedy-regex bug this repository repairs is a bug in a generous piece of open-source work that many apps depend on, and the correction is offered back upstream ([issue #17](https://github.com/AhmedBaset/hadith-json/issues/17)).

**fawazahmed0/hadith-api** and **CheeseWithSauce/HadithsJSONFormat** are independent scrapes of the same sunnah.com translations. They are the reason the repair was possible at all: recovering deleted text required a clean copy of the same translation, and having *two* is what allowed 174 of the second-pass repairs to be confirmed by more than one source. They also carry the scholar gradings that upstream's schema omits entirely.

They are likewise the source of the `citation` field — the standard sunnah.com numbering ("Jami` at-Tirmidhi 2950", "Sahih Muslim 8a") that upstream's `idInBook` drifts from. CheeseWithSauce preserves sunnah.com's literal reference line on every row, which was content-matched onto this corpus; fawazahmed0's independent `hadithnumber` confirms 24,479 of the assignments, and adjudicated seven scrape-era typos on sunnah.com's own pages.

**sunnah.com** additionally publishes [`sunnah-com/api`](https://github.com/sunnah-com/api), whose OpenAPI specification and `text_transform.py` informed the documentation here.

## The Hadith Encyclopedia

`db/hadeethenc/` comes from **[hadeethenc.com](https://hadeethenc.com)** (الموسوعة الحديثية, the Hadith Encyclopedia), prepared under the supervision of the **Dawah and Guidance Association** and the **Association for Serving Islamic Content in Languages**. It is the only corpus here that does not descend from sunnah.com, and the only one carrying a scholarly explanation, a benefits list, word glosses and a full takhrij reference with each narration.

**hadeethenc.com permits reuse on two conditions: no modification, addition or deletion of the content, and the source clearly credited.** Both are binding on anyone redistributing this data, not just on this repository:

- The text in `db/hadeethenc/` is **not edited**. [`tools/build_hadeethenc.py`](tools/build_hadeethenc.py) normalises structure only; its one text touch is CRLF to LF plus trimming outer whitespace, which changes no content.
- **Every screen rendering this text must render the credit**, where the words are and not in an About page.
- A typographic or wording pass over it is a modification. If you apply one, you are no longer redistributing under these terms. See [docs/05-hadeethenc.md](docs/05-hadeethenc.md#licence-attribution-is-a-condition-not-a-courtesy).

The Arabic and English layers reached this repository through **Tilawa**'s build of the site's own API (see below).

## The subject index

`db/topics.json` is the curation of **Jamil Hammoudeh**, from the **Tilawa** project, used with permission: the 331 titles, the 21 subjects and the 7 lanes are his editorial work. The ranked-search weights in [`tools/ranked_search.py`](tools/ranked_search.py) are ported from Tilawa's `hadithSearchEngine.ts`, likewise with permission.

No hadith text is copied from that curation. Every entry is a citation resolved against `db/by_book/`, so what a reader sees is this repository's own text.

## Gradings

The verdicts in `english.grades` are attributed to the scholars named in each record — among them Al-Albani, Zubair Ali Zai, Shuaib Al Arnaut, Ahmad Muhammad Shakir, Muhammad Fouad Abd al-Baqi, Abu Ghuddah, Bashar Awad Maarouf, Salim al-Hilali, and the Darussalam editorial team.

This repository **transmits** those gradings. It does not compute, infer, adjudicate, or rank them. Where scholars differ, every verdict is kept with its attribution.

## Downstream

Built for and used by **Al-Islam | Islamic Pillars**:

- **Author:** Abubakr Elmallah (أبوبكر الملاح)
- **Project:** <https://github.com/TheAbubakrAbu/Al-Islam-iOS>
- **App Store:** <https://apps.apple.com/us/app/al-islam-islamic-pillars/id6449729655>
- **Website:** <https://abubakrelmallah.com/>

The pack format (`.hpk`), the `.henc` container, the search-fold logic, the ranked-search weights and the daily-card policy are shared with that app; `HadithFold.swift` is a verbatim copy kept in sync by fingerprint, and `db/vocabulary.txt` is cross-checked against the copy that app exports from its own built packs.

Companion projects by the same author:

- [**Quran Tajweed Engine**](https://github.com/TheAbubakrAbu/Quran-Tajweed-Engine) — the same idea, for the Quran
- [**Al-Adhan | Prayer Times**](https://github.com/TheAbubakrAbu/Al-Adhan-iOS)
- [**Al-Quran | Beginner Quran**](https://github.com/TheAbubakrAbu/Al-Quran-iOS)

## The one who reported it

None of this work would have happened without the user of Al-Islam who noticed that Forty Hadith Qudsi 24 said the opposite of what it should, and took the trouble to report it. A bug that had been silently deleting sentences across sixteen collections was found because one reader paid attention and spoke up.

> *"Whoever guides someone to goodness will have a reward like the one who did it."* — Prophet Muhammad ﷺ (Sahih Muslim)

## License

The tooling and documentation in this repository are MIT — see [LICENSE](LICENSE).

**The hadith text is not this repository's to license.** It belongs to the tradition, and its English rendering to the translators and publishers whom sunnah.com credits. Use it with care, preserve the chain of attribution above, and keep the text accurate.
