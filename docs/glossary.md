# Glossary

Terms you will meet in this repository and in the data. Written for developers, not scholars — enough to build correctly and to know when you are out of your depth.

## The text

**Hadith** (حديث, pl. *ahadith*) — a report of something the Prophet Muhammad ﷺ said, did, or tacitly approved. Not the Quran; a separate body of transmitted narration.

**Isnad** (إسناد) — the chain of transmission: "A told me, from B, from C, who heard the Prophet ﷺ say…". Authentication is largely the study of these chains. In this data it is the `english.narrator` field, though the split between chain and content is not always clean.

**Matn** (متن) — the content of the report, as opposed to its chain. Roughly `english.text`.

**ﷺ** (U+FDFA) — *salla Allahu alayhi wa sallam*, "may Allah's blessings and peace be upon him", said after the Prophet's name. Rendered variously in sources as `(pbuh)`, `(saw)`, or the Arabic written out; the corpus normalises to the single ligature. **Note:** 4,148 occurrences were converted from Arabic script to the ligature. Identical words, different glyphs.

**(ra)** / **رضي الله عنه** — *radiya Allahu anhu*, "may Allah be pleased with him", said after a Companion's name. Left as each source has it, because rendering it in English forces a choice of gender and number.

**Hadith Qudsi** (حديث قدسي) — a hadith in which the Prophet ﷺ relates words of Allah, distinct from the Quran in wording and status. The `qudsi40` collection.

**Sadaqah jariyah** — a continuing charity whose reward persists after death. The stated intent behind this repository and the apps it serves.

## Authentication

These appear as values in `english.grades[].grade`. **Do not collapse them to a scale** — see [03-gradings](03-gradings.md).

**Sahih** (صحيح) — sound. The chain is continuous and every narrator is reliable.

**Hasan** (حسن) — good. Sound but with a narrator of slightly lesser precision; still acceptable as evidence.

**Hasan Sahih** — Tirmidhi's characteristic composite verdict, roughly "good, indeed sound", often meaning it is sound through more than one chain.

**Da'if** (ضعيف, also written *Daif*) — weak. Some defect in the chain or the narrators.

**Mawdu'** (موضوع) — fabricated. Not a genuine narration.

**Isnaad Sahih / Isnaad Hasan** — the *chain* is sound or good. A narrower claim than grading the report itself: a sound chain does not by itself settle the content.

**Sahih Lighairihi** (صحيح لغيره) — sound *by virtue of something else*: weak on its own but raised by corroborating narrations.

**Muttafaqun alayh / "Agreed Upon"** — reported by both Bukhari and Muslim. The strongest common attribution.

**Marfu' / Mawquf / Maqtu'** — attributed to the Prophet ﷺ / stopped at a Companion / stopped at a Successor. You will see `Sahih Maqtu'` and similar composites.

## Collection types

**Sahih** (as a book title) — a collection whose compiler admitted only what he judged sound. `bukhari`, `muslim`.

**Sunan** (سنن) — organised by legal topic, mixing grades. `abudawud`, `tirmidhi`, `nasai`, `ibnmajah`, `darimi`.

**Musnad** (مسند) — organised by *narrator* rather than topic. `ahmed` (Musnad Ahmad).

**Muwatta** (موطأ) — Malik's early compilation, mixing hadith with the practice of Madinah. `malik`.

**The Nine Books** — the conventional core set. Here: Bukhari, Muslim, Abu Dawud, Tirmidhi, Nasa'i, Ibn Majah, Malik, Ahmad, Darimi.

**Arba'in** (أربعون, "forty") — a genre of forty selected hadiths. `nawawi40` (an-Nawawi's, the most studied), `qudsi40`, `shahwaliullah40`.

**Riyad as-Salihin** — an-Nawawi's topical anthology of ~1,900 narrations on character and worship.

**Bulugh al-Maram** — Ibn Hajar's collection of hadiths used in legal rulings, each with its attribution.

**Mishkat al-Masabih** — a large topical expansion of an earlier collection.

**Al-Adab al-Mufrad** — Bukhari's separate collection on manners and character.

**Shama'il Muhammadiyah** — Tirmidhi's collection on the Prophet's ﷺ appearance, character and daily conduct.

## Structure in this data

**Book** — one collection, one JSON file. Identified by `slug` (`bukhari`) and grouped by folder (`the_9_books`).

**Chapter** — `chapters[]`, a topical division (*kitab* or *bab*). Chapter ids can be **fractional**; see [01-data-schema](01-data-schema.md).

**`idInBook`** — position within a collection. **Drifts** relative to sunnah.com; not a citation key.

**Row** — a hadith's zero-based index in `hadiths[]`. The pack's internal addressing unit. Not the same as `idInBook`.

## Engine terms

**Fold** — a search-normalised form of a string: diacritics stripped, letter forms unified, case flattened, so a query byte-compares against it without normalising per keystroke. Computed at pack time. Arabic and English fold by different rules.

**Fold fingerprint** — a hash of the folding logic, stamped into every pack. If the app's own folding has drifted, prebuilt folds cannot be trusted.

**Blocked-word fingerprint** — a hash of the daily-card word list. If it has drifted, the app rechecks the words itself rather than trusting precomputed flags — costing speed, never correctness.

**Block** — a run of hadiths (~256 KB of raw text) compressed as one unit, so reading a chapter decompresses one or two blocks instead of a book.

**Eager section** — the part of a pack read when a book opens: titles, chapters, and the id table. Under 100 KB compressed even for Bukhari.

**Scar** — the surface signature of a deletion (a doubled space mid-sentence, whitespace welded onto punctuation). A **prefilter, not evidence** — it over-fires roughly 130 to 1.

**Proof gate** — the rule that a repair is written only if re-simulating the upstream bug on it reproduces the damaged record exactly. See [02-repair-pipeline](02-repair-pipeline.md).

**Narrator folded** — a repair where no split point between chain and content satisfied the proof, so the narrator was merged into the body and `english.narrator` left empty. Flagged in the logs.
