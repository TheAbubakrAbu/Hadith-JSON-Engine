#!/usr/bin/env python3
"""Build db/vocabulary.txt: every English word the corpus uses, for correcting a typed one.

    python3 tools/build_vocabulary.py [--apply] [--check <list>]

A search that only ever byte-compares finds nothing for "intetion", and telling a reader their
query returned no results when the corpus is full of "intention" is a bug with a friendly face.
Correcting a typo needs one thing the corpus can give and a dictionary cannot: the set of words
that are actually IN it. A general English dictionary would happily "correct" a narrator's name
into an ordinary word.

The rule (docs/06-ranked-search.md): every 4 to 24 letter run of lowercase ASCII in the English
search fold of every hadith, deduplicated and sorted. Derived here from db/by_book/ through the
same two transforms the packer applies -- `cleaned_hadith_text` then `fold.english` over
`text + "\\n" + narrator` -- so the list a consumer ships and the folds it searches can never
disagree.

    --check <list>   compare against another list (an app's shipped copy, say) and report the
                     symmetric difference instead of writing anything.

The result is 32,555 words, 274 KB. It is committed because deriving it costs a pass over the
whole corpus and every consumer needs the same answer; `--apply` re-derives it. Al-Islam's shipped
copy, exported by the app's own walk over the packs rather than from the JSON, is the same list
word for word (`--check` on it reports no difference either way), which is the point of deriving
it from the same two transforms.
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
OUT = ROOT / "db" / "vocabulary.txt"

MIN_LENGTH = 4
MAX_LENGTH = 24


def words_of(text):
    """The 4 to 24 letter lowercase-ASCII runs of a folded string. Any other byte ends a run and
    disqualifies it, so a digit, an apostrophe or an Arabic letter inside a run drops the run."""
    out = []
    for run in text.split():
        if MIN_LENGTH <= len(run) <= MAX_LENGTH and all("a" <= c <= "z" for c in run):
            out.append(run)
    return out


def collect(books=None):
    vocabulary = set()
    for path in sorted(BOOKS.rglob("*.json")):
        book = json.loads(path.read_text(encoding="utf-8"))
        if books is not None and path.stem not in books:
            continue
        for hadith in book["hadiths"]:
            english = hadith.get("english") or {}
            text = cleaned_hadith_text(english.get("text") or "")
            narrator = cleaned_hadith_text(english.get("narrator") or "")
            vocabulary.update(words_of(fold.english(text + "\n" + narrator)))
    return sorted(vocabulary)


def read_list(path):
    """A word list, with or without the `#shelf <fingerprint>` header a consuming app may stamp on
    its own copy, and xz-compressed or plain."""
    raw = path.read_bytes()
    if path.suffix == ".xz":
        import lzma
        raw = lzma.decompress(raw)
    lines = [line for line in raw.decode("utf-8").split("\n") if line]
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write db/vocabulary.txt")
    parser.add_argument("--check", type=pathlib.Path, help="compare against another list")
    args = parser.parse_args()

    words = collect()
    print(f"{len(words):,} words, {sum(len(w) + 1 for w in words):,} bytes")

    if args.check:
        other = read_list(args.check)
        mine, theirs = set(words), set(other)
        missing = sorted(theirs - mine)
        extra = sorted(mine - theirs)
        print(f"{args.check}: {len(other):,} words; "
              f"{len(missing)} not derived here, {len(extra)} not in that list")
        for label, items in (("only there", missing), ("only here", extra)):
            if items:
                print(f"  {label}: {', '.join(items[:15])}{' ...' if len(items) > 15 else ''}")
        return 1 if (missing or extra) else 0

    if not args.apply:
        print("dry run; pass --apply to write db/vocabulary.txt")
        return 0
    OUT.write_text("\n".join(words) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
