# 06 · Ranked search

Matching the query's words independently, scoring each hadith by **where** they landed, and correcting a typo against the corpus's own vocabulary.

Reference implementation: [`tools/ranked_search.py`](../tools/ranked_search.py). Like [`tools/fold.py`](../tools/fold.py), it is standard-library Python with nothing platform-specific in it, and it is **the file to translate**.

## What is wrong with a byte scan

A `.hpk` stores every hadith's search fold precomputed ([`docs/04`](04-hpk-format.md)), so scanning the corpus for a query is a `memmem` over decompressed blocks. That is exact, exhaustive, allocates nothing, and is the right primitive. It is also blind, and measurably so. Over all 50,884 records:

| Query | Contiguous byte scan | Ranked |
|---|---:|---:|
| `controlling anger` | **0** | 4 |
| `rights of the neighbour` | **0** | 47 |
| `intetion` | **0** | 333 |

The three failures are three different problems:

1. **The words do not touch.** Al-Adab Al-Mufrad 1317 is about the person who controls himself in anger. The scan wants those two words adjacent.
2. **The word is inflected, and spelled the other way.** The corpus has 125 records saying `neighbour` and 138 saying `neighbor`: the translations come from several hands and the corpus mixes them. `rights` never reaches `the right of the neighbour`.
3. **The query has a typo.** Silence is the worst possible answer, because it reads as "this corpus has nothing about intention" when the corpus has 333 records about it.

And a fourth, which the scan gets wrong rather than misses: a query word landing in a **chapter title** (what the narration is *about*) counts for exactly as much as the same word buried in a four-hundred-word narration.

## The scoring

Where a word landed decides what it is worth.

| Landed in | Weight | Why |
|---|---:|---|
| **PRIMARY** the chapter title | 12 | the compiler's own statement of what these narrations are about |
| **CITATION** the collection title | 7 | "bukhari fasting" should favour Bukhari |
| **BODY** the narration and its narrator line | 3 | the text itself |

and then:

| Adjustment | Value |
|---|---:|
| whole-word hit, over a substring | +6 |
| the query's words together as the typed phrase, in a chapter title | +60 |
| the same, in the body | +25 |
| a stemmed hit (`rights` reaching `right`) | -2 |
| the other spelling (`neighbour` / `neighbor`) | 0, full price |
| a corrected typo (`intetion` reaching `intention`) | -5 |
| per matched word, when the relaxed pass is the one shown | +40 |

A hit is never worth less than 1, so a discount cannot cancel a match. The direction of every adjustment is the same rule stated once: **an exact match always outranks a guess.**

The weights come from Tilawa's `hadithSearchEngine.ts` (Jamil Hammoudeh, used with permission), applied here to this engine's precomputed folds.

### Chapter and citation are scored once per chapter

Every row of a chapter shares its chapter title and its collection title, so those two buckets are computed once per chapter and added to each of its rows. On Bukhari that is 97 evaluations instead of 7,277.

A consequence worth stating: **a row can match through its chapter alone.** A block whose folds contain no word of the query can still hold rows that count, so a reader that skips blocks by content must exempt the blocks holding a matched chapter's rows, or those rows vanish.

### Strict, then relaxed

The strict pass keeps only rows carrying **every** word of the query. If a multi-word query returns nothing at all that way, the relaxed pass keeps the rows carrying the **most** of it, and adds 40 per matched word so that a row carrying more of the query outranks a row that merely scored well on less of it.

Single-word queries never relax: there is nothing to relax to.

## Building a query

```python
query = ranked_search.parse("controlling anger", vocabulary)
hits, relaxed = ranked_search.search(query)
```

1. **Trim.** Under two characters, there is no query.
2. **Pick the script.** `fold.is_arabic_script` decides, and the Arabic and English lanes never mix: an Arabic query is matched against Arabic folds only.
3. **Fold**, with the same [`tools/fold.py`](../tools/fold.py) rules the packer used. If your fold differs from the packer's, everything below finds nothing and reports no error. Check the fingerprint.
4. **Split and drop stopwords** (English only): `a an and are as at be by for from he his in is it of on or that the to was who with`. A query that is *nothing but* stopwords keeps them, because an empty query finds an empty screen.
5. **Derive the three alternative forms** per word, English only: the stem, the transatlantic spelling, and the correction.

### The stem is deliberately not a stemmer

```
suffixes: ing, ed, es, s, ly
guards:   the word is at least 5 letters, lowercase ASCII only,
          and at least 4 letters remain after the suffix comes off
```

Then the doubled consonant English adds before `-ing` and `-ed` comes off again, so the stem is a prefix of the word's other forms: `controlling` and `controls` both reach `control`, `stopped` reaches `stop`. Short stems keep the double (`falling` stays `fall`, `passed` stays `pass`), and `s` and `z` never collapse, because the doubled letter there is the word itself (`bless`, `buzz`).

A stemmed hit matches at a **word start** only, never mid-word, and is discounted. Porter or Snowball would be more aggressive and would also turn `sunnah` into something that matches nothing. The point is not linguistic correctness; it is to reach the same word's other forms without reaching different words.

### The other spelling

```
6+ letters ending -our  ->  -or      (neighbour -> neighbor)
5+ letters ending -or   ->  -our
6+ letters ending -ise  ->  -ize
6+ letters ending -ize  ->  -ise
```

Length guards keep it away from the short words that merely end the same way: `four`, `hour`, `your`, `for`, `nor`. This one is charged at **full price**, not discounted, because it is not a guess about what the reader meant: the corpus contains both spellings of the same word.

## Typo correction

[`db/vocabulary.txt`](../db/vocabulary.txt): every 4 to 24 letter run of lowercase ASCII in the English search fold of every hadith, deduplicated and sorted. **32,555 words, 274 KB.** Regenerate it with [`tools/build_vocabulary.py`](../tools/build_vocabulary.py).

It has to be the corpus's own words, not a dictionary. A general English word list would happily "correct" a narrator's name into an ordinary word, and would offer corrections toward words the corpus does not contain, which finds nothing after all that work.

The rule:

```
1.  fewer than 4 letters, or not lowercase ASCII      ->  leave it alone
2.  it occurs anywhere in the vocabulary as a SUBSTRING ->  leave it alone
3.  budget = 2 edits from 7 letters up, else 1
4.  candidates: vocabulary words within `budget` of its length
5.  prefilter on the letter mask, then bounded Levenshtein
6.  first distance-1 candidate wins outright; otherwise the best under budget
```

Step 2 is the one that is easy to leave out and expensive to leave out. Someone typing `intent` is half way through `intention`, not making a mistake, and "correcting" a prefix to a different word takes the search away from what they are about to type.

Step 5 is what makes it fast enough to run per keystroke. Every letter of the query the candidate lacks costs at least one edit, and the other way round, so a word within `n` edits shares all but `n` of its letters. One 32-bit mask per word and two `popcount`s reject almost every candidate before the edit distance runs. Levenshtein itself is the single-row form, abandoned as soon as every cell in a row exceeds the budget.

The result is offered, never imposed: the corrected word is searched **and** discounted, and the correction is surfaced (`query.corrections`) so a reader can see that `intetion` was read as `intention` and say otherwise.

## Deriving the vocabulary, and proving it

The list must be derived from exactly the text the search will scan, or it will offer corrections toward words that are not in the folds:

```
cleaned_hadith_text(english.text) + "\n" + cleaned_hadith_text(english.narrator)
        |> fold.english
        |> every 4-24 letter lowercase-ASCII run
```

That is the same pair of transforms the packer applies, which is what makes the list and the folds agree by construction rather than by luck. It is checkable: Al-Islam ships a copy exported by the app's own walk over its built packs, and

```bash
python3 tools/build_vocabulary.py --check <that list>
# 32,555 words; 0 not derived here, 0 not in that list
```

Two independent derivations, one from the JSON and one from the binary packs, on different sides of the build, agreeing word for word.

## Conformance

`tools/ranked_search.py --probes` runs six queries chosen so that removing any single rule changes an answer: a chapter-title hit outranking a body hit, the phrase bonus, the stem, the transatlantic spelling, the typo correction, a stopword-only query, and the relaxed fallback. [`conformance/vectors.json`](../conformance/vectors.json) pins their results under `rankedSearch`, so a port asserts against them rather than against hand-written expectations.

Ties are broken by `(-score, slug, row)` so the order is total and a port's list can be compared element by element.

## Where it fits

This is one lane of three, and they answer different questions:

| Lane | Finds | Cost |
|---|---|---|
| **Contiguous scan** ([`docs/04`](04-hpk-format.md)) | the exact string, everywhere it occurs | a `memmem` per block |
| **Ranked** (this document) | the query's words, weighted by where they landed | a few `memmem`s per row |
| **Meaning** ([`docs/08`](08-semantic-search.md)) | the topic, whether or not the words appear | an embedding model, and vectors |

Ranked search is the default one to build first. It needs nothing the packs do not already contain, it fixes the three failures at the top of this page, and it cannot return something unrelated: every hit provably contains a word the reader typed, or a form of one.
