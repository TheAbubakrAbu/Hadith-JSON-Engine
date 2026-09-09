#!/usr/bin/env python3
"""Meaning-based ("AI") search over the corpus, and the `.svec` vector pack. Portable Python.

    python3 tools/semantic.py --texts                    # what the corpus looks like as items
    python3 tools/semantic.py --describe <pack>.svec     # a vector pack's header and shape
    python3 tools/semantic.py --verify <pack>.svec       # the whole pack parses and is well formed

"Controlling anger" should reach the narration about the man who restrains himself, and
tools/ranked_search.py finds it only because "anger" happens to appear in it. A question phrased in
none of the corpus's words needs a different lane, and this is it.

THIS ENGINE SHIPS NO MODEL, and no vectors either. Word vectors are tens of megabytes, and every
platform already has an embedding worth using: Apple's `NLEmbedding.wordEmbedding`, Android's ML
Kit, a GloVe file in Node or Python. Hand `SemanticIndex` a function from a lowercased word to its
vector (or None when it has none) and this module does the rest.

WORD VECTORS AND MaxSim, NOT A SENTENCE EMBEDDING. Measured, not assumed: scoring a narration by
the cosine between a SENTENCE embedding of the query and one of the narration ranks this corpus
close to randomly. Hadith are dense, and one vector for a whole narration washes out the single
idea a query asks about. Scoring word by word fixes it. Embed every word; score a text as the MEAN
over the query's words of the BEST matching word in that text. It also degrades gracefully: a query
word the model has never seen contributes nothing rather than poisoning a vector.

The floor matters as much as the score. An absolute 0.38, tightened to 0.85 x the best hit, so a
strong result set sheds its weak tail and a query with no real answer returns nothing instead of
its least bad guess.
"""
import argparse
import json
import math
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from verify_packs import cleaned_hadith_text  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOKS = ROOT / "db" / "by_book"
CATALOG = ROOT / "db" / "catalog.json"

ABSOLUTE_FLOOR = 0.38
RELATIVE_FLOOR = 0.85
MAGIC = 0x53454D34   # "SEM4", little-endian


# --- The corpus as items -----------------------------------------------------------------------

def corpus_texts(slugs=None):
    """(texts, keys) for the whole shelf. One item per hadith, its narrator line joined to its
    text, keyed "<slug>|<idInBook>".

    A record with no English is kept, not skipped, so an item's position is its row's position and
    a caller can index either way. It embeds to an empty word row and scores nothing, which the
    floor discards anyway; skipping it would silently renumber every item after it. All 3,406
    Darimi records land here, plus 43 others.
    """
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    texts, keys = [], []
    for row in catalog["books"]:
        if slugs and row["slug"] not in slugs:
            continue
        book = json.loads((BOOKS / row["folder"] / f"{row['slug']}.json").read_text(encoding="utf-8"))
        for hadith in book["hadiths"]:
            english = hadith.get("english") or {}
            text = cleaned_hadith_text(english.get("text") or "")
            narrator = cleaned_hadith_text(english.get("narrator") or "")
            texts.append(f"{narrator} {text}".strip())
            keys.append(f"{row['slug']}|{hadith.get('idInBook')}")
    return texts, keys


def words_of(text):
    """The lowercased word run of one item. Any non-letter, non-digit ends a word."""
    out, current = [], []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


# --- The index ---------------------------------------------------------------------------------

class SemanticIndex:
    """Words embedded once, items stored as the word rows they use.

    A corpus of 50,884 hadiths uses on the order of 15,000 distinct words, so embedding by word and
    storing an item as indices into that vocabulary is what makes this fit in memory at all: the
    vectors are 15,000 x dim, not 50,884 x dim, and an item costs one small integer per word.
    """

    def __init__(self, embed, keys=None):
        self.embed = embed
        self.keys = keys
        self.vocabulary = []          # word, by index
        self.index = {}               # word -> index
        self.vectors = []             # unit-length, parallel to `vocabulary`
        self.items = []               # list of word-index lists

    @staticmethod
    def normalized(vector):
        norm = math.sqrt(sum(v * v for v in vector))
        return None if norm == 0 else [v / norm for v in vector]

    def _word_index(self, word):
        if word in self.index:
            return self.index[word]
        vector = self.embed(word)
        if vector is None:
            self.index[word] = None
            return None
        unit = self.normalized(vector)
        if unit is None:
            self.index[word] = None
            return None
        self.index[word] = len(self.vocabulary)
        self.vocabulary.append(word)
        self.vectors.append(unit)
        return self.index[word]

    def add(self, text):
        row = []
        for word in words_of(text):
            position = self._word_index(word)
            if position is not None and position not in row:
                row.append(position)
        self.items.append(row)

    def build(self, texts):
        for text in texts:
            self.add(text)
        return self

    def search(self, query, limit=20):
        """[(item index, score)], best first. Mean over the query's known words of the best cosine
        among the item's words, then the calibrated floor."""
        query_vectors = []
        for word in words_of(query):
            vector = self.embed(word)
            unit = self.normalized(vector) if vector is not None else None
            if unit is not None:
                query_vectors.append(unit)
        if not query_vectors:
            return []
        # One similarity table per query word: its cosine against every vocabulary word, once.
        tables = [[sum(a * b for a, b in zip(q, v)) for v in self.vectors] for q in query_vectors]

        scored, best = [], 0.0
        for position, row in enumerate(self.items):
            if not row:
                continue
            total = 0.0
            for table in tables:
                total += max(table[word] for word in row)
            score = total / len(tables)
            if score > best:
                best = score
            if score >= 0.30:   # coarse pre-filter; the floor below does the real gating
                scored.append((position, score))
        floor = max(ABSOLUTE_FLOOR, best * RELATIVE_FLOOR)
        scored = [row for row in scored if row[1] >= floor]
        scored.sort(key=lambda row: -row[1])
        return scored[:limit]


# --- The `.svec` vector pack -------------------------------------------------------------------
#
# A first build costs one embedder call per distinct word and a pass over the corpus, which on a
# phone is minutes. A pack is that work, done once, shipped:
#
#   u32 magic "SEM4" | u32 dimension | u32 embeddingRevision
#   u32 fingerprintLength | fingerprint (UTF-8)
#   u32 vocabCount | u32 itemCount
#   u32 wordsLength | vocabulary, "\n"-joined (UTF-8)
#   u32 keysLength  | keys, "\n"-joined (0 when the pack carries none)
#   u32 indexWidth (2 or 4)
#   vectors: vocabCount x dimension IEEE half floats, unit length, row major
#   items:   itemCount x (u32 count, count x index of that width)
#
# GUARDED, NEVER TRUSTED. `embeddingRevision` names the model build the vectors came from and
# `fingerprint` names the source texts. A reader that finds either different from what it is
# running MUST reject the pack and build on device: vectors from last month's model, or from text
# that has since been corrected, answer confidently and wrongly. Half precision is deliberate and
# measured: the largest cosine change a half-precision round trip made on this corpus was 1.4e-4,
# against a floor of 0.38.


def read_svec(path):
    """A `.svec` as a dict. Bounds every count against the buffer before allocating: the numbers
    come out of the file, and a truncated pack hands a reader a count read from garbage."""
    data = path.read_bytes()
    offset = 0

    def u32():
        nonlocal offset
        if offset + 4 > len(data):
            sys.exit(f"{path}: truncated at byte {offset}")
        value = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        return value

    def blob(length):
        nonlocal offset
        if offset + length > len(data):
            sys.exit(f"{path}: a {length}-byte field runs past the end")
        chunk = data[offset:offset + length]
        offset += length
        return chunk

    if u32() != MAGIC:
        sys.exit(f"{path}: not a SEM4 vector pack")
    dimension = u32()
    revision = u32()
    fingerprint = blob(u32()).decode("utf-8")
    vocab_count = u32()
    item_count = u32()
    words = blob(u32()).decode("utf-8").split("\n")
    keys_length = u32()
    keys = blob(keys_length).decode("utf-8").split("\n") if keys_length else None
    width = u32()
    if width not in (2, 4):
        sys.exit(f"{path}: index width {width}, expected 2 or 4")
    if len(words) != vocab_count:
        sys.exit(f"{path}: {len(words)} words, the header says {vocab_count}")
    if keys is not None and len(keys) != item_count:
        sys.exit(f"{path}: {len(keys)} keys, the header says {item_count}")
    if vocab_count * dimension * 2 > len(data) - offset:
        sys.exit(f"{path}: {vocab_count} x {dimension} half floats do not fit in what is left")
    vectors = blob(vocab_count * dimension * 2)

    items = []
    fmt = "<H" if width == 2 else "<I"
    for _ in range(item_count):
        count = u32()
        if count * width > len(data) - offset:
            sys.exit(f"{path}: an item claims {count} words, the buffer cannot hold them")
        row = list(struct.unpack_from(f"<{count}{fmt[1]}", data, offset)) if count else []
        offset += count * width
        items.append(row)
    return {"dimension": dimension, "embeddingRevision": revision, "fingerprint": fingerprint,
            "vocabulary": words, "keys": keys, "indexWidth": width, "items": items,
            "vectorBytes": vectors, "trailing": len(data) - offset}


def verify(pack, path):
    problems = []
    vocab = len(pack["vocabulary"])
    for position, row in enumerate(pack["items"]):
        for word in row:
            if word >= vocab:
                problems.append(f"item {position}: word index {word} of {vocab}")
                break
    if pack["trailing"]:
        problems.append(f"{pack['trailing']} trailing byte(s) after the last item")
    if any(not word for word in pack["vocabulary"]):
        problems.append("the vocabulary contains an empty word")
    empty = sum(1 for row in pack["items"] if not row)
    lengths = [len(row) for row in pack["items"]]
    print(f"{path.name}: dimension {pack['dimension']}, revision {pack['embeddingRevision']}, "
          f"{vocab:,} words, {len(pack['items']):,} items, {pack['indexWidth']}-byte indices")
    print(f"  fingerprint: {pack['fingerprint'][:110]}{'...' if len(pack['fingerprint']) > 110 else ''}")
    print(f"  keys: {'yes, ' + format(len(pack['keys']), ',') if pack['keys'] else 'none'}"
          f"{'  e.g. ' + pack['keys'][0] if pack['keys'] else ''}")
    if lengths:
        print(f"  words per item: min {min(lengths)}, mean {sum(lengths) / len(lengths):.1f}, "
              f"max {max(lengths)}; {empty} empty")
    if problems:
        print(f"\nFAILED: {len(problems)} problem(s)", file=sys.stderr)
        for line in problems[:20]:
            print("  " + line, file=sys.stderr)
        return 1
    print("\nOK")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--texts", action="store_true", help="report the corpus as items")
    parser.add_argument("--describe", type=pathlib.Path, help="a .svec pack's header and shape")
    parser.add_argument("--verify", type=pathlib.Path, help="parse a .svec pack whole")
    args = parser.parse_args()

    if args.texts:
        texts, keys = corpus_texts()
        vocabulary = set()
        for text in texts:
            vocabulary.update(words_of(text))
        total = sum(len(words_of(text)) for text in texts)
        print(f"{len(texts):,} items, {len(vocabulary):,} distinct words, {total:,} word "
              f"occurrences; keys like {keys[0]!r}")
        print(f"an embedder is called {len(vocabulary):,} times to build this corpus, "
              f"not {total:,}")
        return 0
    path = args.describe or args.verify
    if not path:
        parser.error("one of --texts, --describe, --verify")
    return verify(read_svec(path), path)


if __name__ == "__main__":
    sys.exit(main())
