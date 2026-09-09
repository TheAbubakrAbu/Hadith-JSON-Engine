#!/usr/bin/env python3
"""Ranked hadith search, in portable Python -- the file to translate. See docs/06-ranked-search.md.

    python3 tools/ranked_search.py "controlling anger"
    python3 tools/ranked_search.py "the rights of a neighbour" --limit 10
    python3 tools/ranked_search.py "intetion" --books bukhari,muslim
    python3 tools/ranked_search.py --probes          # the conformance probes, as vectors.json has them

A byte scan for the query as one contiguous run is exact, exhaustive, and blind to everything else:
"controlling anger" finds nothing unless the two words touch, "rights" never reaches "the right of
the neighbour", "intetion" returns silence, and a word landing in a CHAPTER TITLE counts for no
more than the same word buried in a four-hundred-word narration. That scan is the right primitive
and the wrong ranking.

This matches the query's words independently and scores each hadith by WHERE they landed:

    PRIMARY   the chapter title, what the narration is about        12 per word
    CITATION  the collection it is in                                7
    BODY      the narration itself, its narrator line included       3

with a bonus for a whole word over a substring, a bonus for the words sitting together as the typed
phrase, a discount for a stemmed hit ("rights" -> "right"), the other spelling ("neighbour" /
"neighbor") at full price, and a corrected typo at a heavier discount, so an exact match always
outranks a guess. Strict pass first, where every word has to land somewhere; only if that comes
back empty on a multi-word query does a relaxed pass rank the rows carrying the most of it.

Everything here is a byte compare against folds produced by tools/fold.py, which is what makes it
portable to the packs: a `.hpk` stores those same folds precomputed, so a port scans the block
instead of the JSON and the scores come out identical. This module reads db/by_book/ so that the
algorithm can be checked with nothing but the standard library.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fold                                   # noqa: E402
from verify_packs import cleaned_hadith_text  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOKS = ROOT / "db" / "by_book"
CATALOG = ROOT / "db" / "catalog.json"
VOCABULARY = ROOT / "db" / "vocabulary.txt"

# --- Weights -----------------------------------------------------------------------------------
# Where a word landed decides what it is worth. Ported from Tilawa's hadithSearchEngine.ts
# (Jamil Hammoudeh, used with permission) onto this engine's folds.
PRIMARY_WEIGHT = 12
CITATION_WEIGHT = 7
BODY_WEIGHT = 3
PHRASE_BONUS_PRIMARY = 60
PHRASE_BONUS_BODY = 25
WHOLE_WORD_BONUS = 6
STEM_PENALTY = 2
FUZZY_PENALTY = 5
RELAXED_TOKEN_WEIGHT = 40

# Dropped from an English query: they land everywhere and rank nothing. A query that is nothing but
# stopwords keeps them, because an empty query finds an empty screen.
STOPWORDS = frozenset(
    "a an and are as at be by for from he his in is it of on or that the to was who with".split())

MIN_FUZZY_LENGTH = 4    # shorter than this and a correction is a coin toss
LONG_WORD = 7           # from here up, two edits are allowed instead of one
BOUNDARY = frozenset(" \n\t\r")


# --- Stemming and spelling ---------------------------------------------------------------------

SUFFIXES = ("ing", "ed", "es", "s", "ly")


def is_latin_word(word):
    return bool(word) and all("a" <= c <= "z" for c in word)


def undoubled(stem):
    """The consonant English doubles before -ing/-ed comes off again, so the stem is a prefix of
    the word's other forms: "controlling" and "controls" both reach "control", "stopped" reaches
    "stop". A short stem keeps its double ("falling" stays "fall", "passed" stays "pass"), and s/z
    never collapse: the doubled letter there is the word itself ("bless", "buzz")."""
    if len(stem) < 2 or stem[-1] != stem[-2] or stem[-1] not in "bdgmnprtl":
        return stem
    if stem[-1] == "l":
        # "controll", "compell", "travell" lose an l; "fall", "spell", "dwell" keep both.
        return stem[:-1] if len(stem) >= 7 else stem
    return stem[:-1] if len(stem) >= 4 else stem


def stem_word(word):
    """Deliberately not a real stemmer: ASCII only, length-guarded so a short word is never
    truncated into noise, and always discounted so an exact match outranks it."""
    if len(word) < 5 or not is_latin_word(word):
        return None
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return undoubled(word[:-len(suffix)])
    return None


def variant_spelling(word):
    """The other side of the Atlantic. The translations come from several hands, so the corpus
    itself mixes "neighbour" and "neighbor". Length-guarded away from the short words that merely
    end the same way ("four", "hour", "your")."""
    if not is_latin_word(word):
        return None
    if len(word) >= 6 and word.endswith("our"):
        return word[:-3] + "or"
    if len(word) >= 5 and word.endswith("or"):
        return word[:-2] + "our"
    if len(word) >= 6 and word.endswith("ise"):
        return word[:-3] + "ize"
    if len(word) >= 6 and word.endswith("ize"):
        return word[:-3] + "ise"
    return None


# --- Typo correction ---------------------------------------------------------------------------

def letter_mask(word):
    """One bit per lowercase ASCII letter, for the exact pre-test that spares the edit distance
    most of its candidates: every letter of the query the candidate lacks (and the other way round)
    costs at least one edit, so a word within `max` edits shares all but `max` of them."""
    mask = 0
    for char in word:
        if "a" <= char <= "z":
            mask |= 1 << (ord(char) - 97)
    return mask


def bounded_edit_distance(a, b, limit):
    """Levenshtein, abandoned as soon as every cell in a row exceeds the budget."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    if not a:
        return limit + 1 if len(b) > limit else len(b)
    if not b:
        return limit + 1 if len(a) > limit else len(a)
    row = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        diagonal = row[0]
        row[0] = i
        best = i
        for j in range(1, len(b) + 1):
            above = row[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            value = min(above + 1, row[j - 1] + 1, diagonal + cost)
            row[j] = value
            diagonal = above
            if value < best:
                best = value
        if best > limit:
            return limit + 1
    return row[len(b)]


class Vocabulary:
    """db/vocabulary.txt, indexed for correction. `blob` is the whole list space-joined, so the
    substring test that leaves a half-typed word alone is one find."""

    def __init__(self, words):
        self.words = words
        self.blob = " " + " ".join(words) + " "
        self.by_length = {}
        for word in words:
            self.by_length.setdefault(len(word), []).append((word, letter_mask(word)))

    @classmethod
    def load(cls, path=VOCABULARY):
        return cls([line for line in path.read_text(encoding="utf-8").split("\n") if line])

    def nearest_word(self, token):
        """The corpus word a mistyped one most likely meant, or None to leave it be. Anything the
        corpus already uses ANYWHERE as a substring is left alone: a half-typed "intent" is a
        prefix, not a typo."""
        if len(token) < MIN_FUZZY_LENGTH or not is_latin_word(token):
            return None
        if token in self.blob:
            return None
        limit = 2 if len(token) >= LONG_WORD else 1
        mask = letter_mask(token)
        best, best_distance = None, limit + 1
        for length in range(len(token) - limit, len(token) + limit + 1):
            for candidate, candidate_mask in self.by_length.get(length, ()):
                if (bin(mask & ~candidate_mask).count("1") > limit
                        or bin(candidate_mask & ~mask).count("1") > limit):
                    continue
                distance = bounded_edit_distance(token, candidate, limit)
                if distance < best_distance:
                    best_distance, best = distance, candidate
                    if distance == 1:
                        return candidate
        return best


# --- The query ---------------------------------------------------------------------------------

class Token:
    __slots__ = ("text", "stem", "variant", "fuzzy")

    def __init__(self, text, stem=None, variant=None, fuzzy=None):
        self.text, self.stem, self.variant, self.fuzzy = text, stem, variant, fuzzy


class Query:
    def __init__(self, is_arabic, phrase, tokens, corrections):
        self.is_arabic = is_arabic
        self.phrase = phrase
        self.tokens = tokens
        self.corrections = corrections

    def __bool__(self):
        return bool(self.tokens)


def parse(raw, vocabulary=None):
    """A raw query into folded tokens. Returns None for anything under two characters."""
    trimmed = raw.strip()
    if len(trimmed) < 2:
        return None
    is_arabic = fold.is_arabic_script(trimmed)
    folded = fold.arabic(trimmed) if is_arabic else fold.english(trimmed)
    words = [w for w in folded.split() if w]
    if not words:
        return None
    meaningful = words if is_arabic else [w for w in words if w not in STOPWORDS]
    used = meaningful or words

    tokens, corrections = [], []
    for word in used:
        if is_arabic:
            tokens.append(Token(word))
            continue
        fuzzy = vocabulary.nearest_word(word) if vocabulary else None
        if fuzzy:
            corrections.append((word, fuzzy))
        tokens.append(Token(word, stem_word(word), variant_spelling(word), fuzzy))
    return Query(is_arabic, " ".join(used), tokens, corrections)


# --- Matching ----------------------------------------------------------------------------------

def find(needle, haystack, whole_word, word_start):
    """(found, whole): whether `needle` occurs in `haystack`, and whether one occurrence stands
    alone as a word. A word-START hit (what a stem is allowed) needs only the leading boundary."""
    if not needle or len(haystack) < len(needle):
        return (False, False)
    found = False
    offset = 0
    while True:
        start = haystack.find(needle, offset)
        if start < 0:
            return (found, False)
        found = True
        leading = start == 0 or haystack[start - 1] in BOUNDARY
        end = start + len(needle)
        trailing = end >= len(haystack) or haystack[end] in BOUNDARY
        if word_start and leading:
            return (True, True)
        if whole_word and leading and trailing:
            return (True, True)
        if not whole_word and not word_start:
            return (True, False)
        offset = start + 1


def token_hit(token, text, weight):
    """What one query word is worth against one fold, or 0."""
    found, whole = find(token.text, text, True, False)
    if found:
        return weight + (WHOLE_WORD_BONUS if whole else 0)
    if token.variant:
        found, whole = find(token.variant, text, True, False)
        if found:
            return weight + (WHOLE_WORD_BONUS if whole else 0)
    if token.stem and find(token.stem, text, False, True)[0]:
        return max(1, weight - STEM_PENALTY)
    if token.fuzzy and find(token.fuzzy, text, False, True)[0]:
        return max(1, weight - FUZZY_PENALTY)
    return 0


class Hit:
    __slots__ = ("slug", "row", "score", "matched")

    def __init__(self, slug, row, score, matched):
        self.slug, self.row, self.score, self.matched = slug, row, score, matched


_books = {}


def load_book(slug, catalog_row):
    """db/by_book/<folder>/<slug>.json, kept once. The reference tool re-reads nothing; a shipped
    app reads a pack instead and never holds the JSON at all."""
    if slug not in _books:
        path = BOOKS / catalog_row["folder"] / f"{slug}.json"
        _books[slug] = json.loads(path.read_text(encoding="utf-8"))
    return _books[slug]


def rank_book(query, slug, book, catalog_row):
    """Every hadith of one book carrying at least one word of the query, with how many words it
    carries and its score before the relaxed bonus. The chapter and citation buckets are the same
    for every row of a chapter, so they are scored once per chapter, never once per narration."""
    title = catalog_row["arabicTitle"] if query.is_arabic else catalog_row["englishTitle"]
    book_fold = fold.arabic(title) if query.is_arabic else fold.english(title)
    citation_hits = {}
    for index, token in enumerate(query.tokens):
        hit = token_hit(token, book_fold, CITATION_WEIGHT)
        if hit:
            citation_hits[index] = hit

    buckets = {}
    for chapter in book["chapters"]:
        raw = chapter.get("arabic" if query.is_arabic else "english") or ""
        text = cleaned_hadith_text(raw)
        chapter_fold = fold.arabic(text) if query.is_arabic else fold.english(text)
        score, matched = 0, set()
        for index, token in enumerate(query.tokens):
            best = max(token_hit(token, chapter_fold, PRIMARY_WEIGHT), citation_hits.get(index, 0))
            if best:
                score += best
                matched.add(index)
        if len(query.tokens) > 1 and query.phrase in chapter_fold:
            score += PHRASE_BONUS_PRIMARY
        buckets[chapter.get("id")] = (score, matched)

    hits = []
    for row, hadith in enumerate(book["hadiths"]):
        if query.is_arabic:
            row_fold = fold.arabic(cleaned_hadith_text(hadith.get("arabic") or ""))
        else:
            english = hadith.get("english") or {}
            text = cleaned_hadith_text(english.get("text") or "")
            narrator = cleaned_hadith_text(english.get("narrator") or "")
            row_fold = fold.english(text + "\n" + narrator)
        bucket_score, bucket_matched = buckets.get(hadith.get("chapterId"), (0, set()))
        score, matched = 0, 0
        for index, token in enumerate(query.tokens):
            body = token_hit(token, row_fold, BODY_WEIGHT)
            if body == 0 and index not in bucket_matched:
                continue
            matched += 1
            score += body
        if not matched:
            continue
        score += bucket_score
        if len(query.tokens) > 1 and query.phrase in row_fold:
            score += PHRASE_BONUS_BODY
        hits.append(Hit(slug, row, score, matched))
    return hits


def search(query, slugs=None, catalog=None):
    """The whole shelf, ranked. Strict first: only if no row carries every word of a multi-word
    query do the rows carrying the most of it stand in, with `RELAXED_TOKEN_WEIGHT` per word so a
    row that carries more of the query outranks a row that merely scored well on less of it."""
    catalog = catalog or json.loads(CATALOG.read_text(encoding="utf-8"))
    rows = {row["slug"]: row for row in catalog["books"]}
    hits = []
    for slug in (slugs or [row["slug"] for row in catalog["books"]]):
        row = rows[slug]
        hits.extend(rank_book(query, slug, load_book(slug, row), row))

    strict = [hit for hit in hits if hit.matched == len(query.tokens)]
    relaxed = False
    if not strict and len(query.tokens) > 1:
        best = max((hit.matched for hit in hits), default=0)
        strict = [hit for hit in hits if hit.matched == best]
        relaxed = True
        for hit in strict:
            hit.score += RELAXED_TOKEN_WEIGHT * hit.matched
    strict.sort(key=lambda hit: (-hit.score, hit.slug, hit.row))
    return strict, relaxed


# --- Conformance probes ------------------------------------------------------------------------

# Chosen so that removing any single rule of the ranking changes an answer: a chapter-title hit
# outranking a body hit, the phrase bonus, the stem, the transatlantic spelling, the typo
# correction, a stopword-only query, and (the last probe) the relaxed fallback, where no record
# carries all three words and the two carrying two of them stand in.
PROBES = ("controlling anger", "rights of the neighbour", "intetion", "fasting ramadan",
          "the", "prayer of a traveller in the rain", "sunrise camel silk")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--books", help="comma-separated slugs, default the whole shelf")
    parser.add_argument("--probes", action="store_true", help="print the conformance probes")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    rows = {row["slug"]: row for row in catalog["books"]}
    vocabulary = Vocabulary.load()
    slugs = args.books.split(",") if args.books else None

    for raw in (PROBES if args.probes else [args.query]):
        if raw is None:
            parser.error("a query, or --probes")
        query = parse(raw, vocabulary)
        if query is None:
            print(f"{raw!r}: too short to search")
            continue
        hits, relaxed = search(query, slugs, catalog)
        note = " (relaxed)" if relaxed else ""
        corrected = "".join(f"  [{a} -> {b}]" for a, b in query.corrections)
        print(f"\n{raw!r}: {len(hits)} hit(s){note}{corrected}")
        for hit in hits[:args.limit]:
            row = rows[hit.slug]
            hadith = load_book(hit.slug, row)["hadiths"][hit.row]
            citation = hadith.get("citation") or f"row {hit.row}"
            text = cleaned_hadith_text((hadith.get("english") or {}).get("text") or "")
            print(f"  {hit.score:>4}  {row['englishTitle']} {citation}: {text[:110]}")


if __name__ == "__main__":
    main()
