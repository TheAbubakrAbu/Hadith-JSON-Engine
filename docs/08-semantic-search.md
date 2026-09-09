# 08 · Meaning search

Finding the narrations about a topic whether or not they use its words, on device, with no network and no keys.

Reference implementation: [`tools/semantic.py`](../tools/semantic.py).

> **This ships no model and no vectors.** It ships the part a model cannot give you: how to turn this corpus into something an embedding can search well, the scoring that works on it, and the format for keeping the result.

## Where ranked search runs out

[Ranked search](06-ranked-search.md) finds `controlling anger` because the word "anger" happens to be in the narration. Every one of its hits provably contains a word the reader typed, or a form of one, and that guarantee is exactly its ceiling: a question phrased in none of the corpus's words returns nothing, correctly and unhelpfully. "What did the Prophet ﷺ say about looking after elderly parents" is a reasonable question with no reliable keyword in it.

That needs a different lane, and the two are complements. Ranked search is precise and cheap; this is recall at the cost of an embedding model.

## Word vectors and MaxSim, not a sentence embedding

This was measured, not assumed, and the obvious approach loses badly.

Embedding a whole narration as one vector and scoring it by cosine against a sentence embedding of the query ranks this corpus close to randomly. Hadith are dense: a single narration can carry a chain of transmission, a question, an answer and a ruling, and one vector for all of that washes out the single idea the query asks about.

Scoring word by word fixes it:

```
embed every distinct word of the corpus
score(text) = mean over the query's words of ( max over the text's words of cosine )
```

On real narrations that separates related (0.42 to 0.70) from unrelated (0.27 to 0.41) cleanly. It also degrades gracefully: a query word the model has never seen contributes nothing, where a sentence embedding lets one unknown word poison the whole vector.

The floor matters as much as the score:

```
floor = max(0.38, 0.85 * best score in this result set)
```

The absolute term says nothing below 0.38 is a real match. The relative term makes a strong result set shed its weak tail. Together they let a query with no real answer return **nothing**, which is the behaviour that makes the lane trustworthy: without the floor it always returns its twenty least-bad guesses, and a reader cannot tell those from answers.

## Building an index over this corpus

```python
texts, keys = semantic.corpus_texts()      # 50,884 items, keyed "bukhari|1"
index = semantic.SemanticIndex(embed).build(texts)
index.search("looking after elderly parents", limit=20)
```

One item per hadith: the narrator line joined to the English text.

**Keep the empty ones.** A record with no English (all 3,406 of Darimi, plus 43 others) embeds to an empty word row and scores nothing, which the floor discards anyway. Skipping it instead silently renumbers every item after it, and an index whose positions no longer match the corpus is worse than one with 3,449 dead rows in it.

**Embed by word, store items as word indices.** The corpus has 3,762,645 word occurrences and **30,828** distinct words, so this is the difference between 30,828 embedder calls and 3.7 million, and between 30,828 vectors resident and 50,884. An item then costs one small integer per distinct word it uses.

Not every word has a vector. Against Apple's English word embedding, 14,700 of the 30,828 do; the rest are transliterations, names and archaisms the model has never seen. They are dropped from the vocabulary rather than zero-filled, which is why the vocabulary in a shipped pack is smaller than the corpus's word count and not a sign of a truncated build.

**The embedder is yours.** `SemanticIndex` takes a function from a lowercased word to its vector, or None. Apple's `NLEmbedding.wordEmbedding`, Android's ML Kit, a GloVe file in Node or Python: whatever your platform already has. Word vectors are tens of megabytes and there is no reason for this repository to ship a copy of one.

## The `.svec` vector pack

A first build costs one embedder call per distinct word plus a pass over the corpus, which on a phone is minutes on first launch. A pack is that work done once, at build time.

```
u32  magic "SEM4"        0x53454D34
u32  dimension           300 in practice
u32  embeddingRevision   which build of the model produced these vectors
u32  fingerprintLength
     fingerprint         UTF-8; names the source texts
u32  vocabCount
u32  itemCount
u32  wordsLength
     vocabulary          "\n"-joined UTF-8, vocabCount words
u32  keysLength          0 when the pack carries no keys
     keys                "\n"-joined UTF-8, itemCount keys
u32  indexWidth          2 or 4
     vectors             vocabCount x dimension IEEE half floats, unit length, row major
     items               itemCount x ( u32 count, count x index of indexWidth bytes )
```

All integers little-endian and unaligned.

**Half precision is deliberate and measured.** The largest cosine change a half-precision round trip produced on this corpus was 1.4e-4, against a floor of 0.38. The vectors are stored unit length so a cosine is a dot product and nothing normalises at query time.

**Two-byte indices while the vocabulary fits.** Under 65,536 words the item rows are `u16`; the writer widens to `u32` past that. `indexWidth` says which, so a reader never guesses.

### The two guards, which exist to be believed

`embeddingRevision` and `fingerprint` are not metadata. **A reader that finds either different from what it is running must reject the pack and rebuild on device.**

- The model can change between OS releases. Vectors from last month's model, scored against today's query vectors, produce confident nonsense rather than an error.
- The source texts can change. A repair landed in `db/by_book/` after a pack was built means the pack answers for text that is no longer there.

Both failures are silent in every other way. This is the only place they can be caught, so a reader that skips the check has no second chance. The fingerprint should name what the vectors were built from without reading it: Al-Islam uses every pack's slug and byte size, which changes whenever the text does.

```bash
python3 tools/semantic.py --verify <pack>.svec
python3 tools/semantic.py --texts
```

`--verify` bounds every count in the file against the buffer before allocating against it, which is the same rule the other readers here follow and for the same reason: those numbers come out of the file.

## What this lane is not

It does not answer questions, and it must not be presented as if it did. It returns narrations, ranked by how close their words sit to the question's words in a vector space that knows nothing about Islam, hadith authenticity or context. A high score is a hint about relevance and is not a scholarly judgement of any kind.

Show the grading with the result ([`docs/03`](03-gradings.md)). Show the citation. Let the reader see what they were handed and where it came from.
