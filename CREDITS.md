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

## Gradings

The verdicts in `english.grades` are attributed to the scholars named in each record — among them Al-Albani, Zubair Ali Zai, Shuaib Al Arnaut, Ahmad Muhammad Shakir, Muhammad Fouad Abd al-Baqi, Abu Ghuddah, Bashar Awad Maarouf, Salim al-Hilali, and the Darussalam editorial team.

This repository **transmits** those gradings. It does not compute, infer, adjudicate, or rank them. Where scholars differ, every verdict is kept with its attribution.

## Downstream

Built for and used by **Al-Islam | Islamic Pillars**:

- **Author:** Abubakr Elmallah (أبوبكر الملاح)
- **Project:** <https://github.com/TheAbubakrAbu/Al-Islam-Islamic-Pillars>
- **App Store:** <https://apps.apple.com/us/app/al-islam-islamic-pillars/id6449729655>
- **Website:** <https://abubakrelmallah.com/>

The pack format (`.hpk`), the search-fold logic, and the daily-card policy are shared with that app; `HadithFold.swift` is a verbatim copy kept in sync by fingerprint.

Companion projects by the same author:

- [**Quran Tajweed Engine**](https://github.com/TheAbubakrAbu/Quran-Tajweed-Engine) — the same idea, for the Quran
- [**Al-Adhan | Prayer Times**](https://github.com/TheAbubakrAbu/Al-Adhan-Prayer-Times)
- [**Al-Quran | Beginner Quran**](https://github.com/TheAbubakrAbu/Al-Quran-Beginner-Quran)

## The one who reported it

None of this work would have happened without the user of Al-Islam who noticed that Forty Hadith Qudsi 24 said the opposite of what it should, and took the trouble to report it. A bug that had been silently deleting sentences across sixteen collections was found because one reader paid attention and spoke up.

> *"Whoever guides someone to goodness will have a reward like the one who did it."* — Prophet Muhammad ﷺ (Sahih Muslim)

## License

The tooling and documentation in this repository are MIT — see [LICENSE](LICENSE).

**The hadith text is not this repository's to license.** It belongs to the tradition, and its English rendering to the translators and publishers whom sunnah.com credits. Use it with care, preserve the chain of attribution above, and keep the text accurate.
