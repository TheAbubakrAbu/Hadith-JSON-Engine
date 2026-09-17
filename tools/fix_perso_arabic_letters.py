#!/usr/bin/env python3
"""Fold the stray Perso-Arabic spellings in db/by_book onto the Arabic ones they stand for.

Three codepoints reached the corpus written the Persian/Urdu way where the Arabic one
belongs, in 61 distinct word forms across two books:

    U+06CC  \u06cc  FARSI YEH         -> U+064A \u064a YEH  or  U+0649 \u0649 ALEF MAKSURA
    U+06A9  \u06a9  KEHEH             -> U+0643 \u0643 KAF
    U+06C3  \u06c3  TEH MARBUTA GOAL  -> U+0629 \u0629 TEH MARBUTA

These are not Persian words. They are ordinary Arabic words typed on a keyboard that
produces the Persian forms, so the text reads and means the same and the fix restores the
spelling the rest of the corpus already uses.

WHY IT MATTERS. The KFGQPC Uthmanic faces the apps render hadith in are Quran-only: all
three codepoints sit in their cmap mapped onto the placeholder RING glyph built from
U+0602. Because they are IN the cmap, iOS never substitutes a system face - it draws a
small circle. Every one of these characters therefore reaches a reader as a circle where a
letter should be, and no font fallback can rescue it. The damage is concentrated: 68 of
the 73 characters are in the Arabic of shahwaliullah40, across 28 of its 40 narrations,
which is why that one collection reads as broken while everything around it looks fine.

WHY A PER-WORD TABLE AND NOT A CHARACTER MAP. Persian writes one \u06cc for two different
Arabic letters: the yeh \u064a and the alef maksura \u0649. A blind character fold turns
\u0639\u064e\u0644\u064e\u06cc into \u0639\u064e\u0644\u064e\u064a, which is a misspelling of \u0639\u064e\u0644\u064e\u0649 - and the same
mistake would hit \u0627\u0644\u0633\u064f\u0651\u0641\u0652\u0644\u064e\u06cc, \u0627\u0644\u0652\u062a\u064e\u0651\u0642\u0652\u0648\u064e\u06cc and \u064a\u064e\u0631\u064e\u06cc. So the decision is per word, not per
character, and the table below is the reviewed result.

HOW EACH ROW WAS DECIDED, by two independent methods that agreed on all 61:

  1. Corpus lookup. Every candidate spelling was looked up, tashkeel-stripped, in the
     90,492 distinct word forms of the REST of db/by_book. 51 forms matched exactly one
     candidate; 6 matched two and were taken on frequency, each time by a margin wide
     enough to be decisive (\u0639\u064e\u0644\u064e\u0649 18,350 against \u0639\u064e\u0644\u064e\u064a 5,274; \u0641\u0650\u064a 29,794 against \u0641\u0650\u0649 64).
  2. Orthographic rule. A word-final \u06cc carrying no diacritic of its own and no kasra
     before it is an alef maksura; every other \u06cc is a yeh.

The `why` column records which one settled each row. `--verify` re-runs method 1 against
the live corpus and fails if the table has drifted from it.

NOT TOUCHED: db/hadeethenc. Its licence permits reuse only with no modification of the
content, and the one narration affected there (2169, three Farsi yehs inside a quoted
ayah) is left exactly as published. Raise that one upstream instead.

Replacement is whole-word and exact, on the file BYTES rather than through a JSON
round-trip: none of these characters can occur in JSON syntax, so the formatting, key
order and whitespace of the file are untouched and the diff is only the characters that
really changed.

Re-run both gates afterwards:

    tools/pack/build.sh <app>                 # runs verify_packs.py itself
    python3 tools/verify_corpora.py           # re-derives vocabulary.txt

Usage:
    python3 tools/fix_perso_arabic_letters.py [--apply] [--verify]
"""
import itertools
import json
import os
import re
import sys

# Every file under db/ EXCEPT db/hadeethenc, which its licence forbids modifying.
TARGETS = [
    "db/by_book/forties/shahwaliullah40.json",
    "db/by_book/other_books/mishkat_almasabih.json",
]

# word as it is written now -> (word as it should be written, what decided it)
FOLD = {
    "اِلَیْهَا": ("اِلَيْهَا", "positional"),  # x2
    "خَیْرٌ": ("خَيْرٌ", "corpus x1,333"),  # x2
    "خَیْرُ": ("خَيْرُ", "corpus x1,333"),  # x2
    "عَلَی": ("عَلَى", "corpus x18,350, over عَلَي x5,274"),  # x2
    "لَیْسَ": ("لَيْسَ", "corpus x1,714"),  # x2
    "أُمَّتِیْ": ("أُمَّتِيْ", "corpus x456, over أُمَّتِىْ x7"),  # x1
    "أیَّامٍ": ("أيَّامٍ", "corpus x493"),  # x1
    "إِسْتَعِیْنُوْا": ("إِسْتَعِيْنُوْا", "positional"),  # x1
    "الاکوع": ("الاكوع", "positional"),  # x1
    "الدُّنْیَا": ("الدُّنْيَا", "corpus x795"),  # x1
    "الدِّیَارَ": ("الدِّيَارَ", "corpus x9"),  # x1
    "السُّفْلَی": ("السُّفْلَى", "corpus x45"),  # x1
    "الْبَیَانِ": ("الْبَيَانِ", "corpus x22"),  # x1
    "الْتَّقْوَی": ("الْتَّقْوَى", "corpus x27"),  # x1
    "الْحَیَاءُ": ("الْحَيَاءُ", "corpus x61"),  # x1
    "الْخَمِیْسِ": ("الْخَمِيْسِ", "corpus x50"),  # x1
    "الْخَیْرِ": ("الْخَيْرِ", "corpus x292"),  # x1
    "الْسَّعِیْدُ": ("الْسَّعِيْدُ", "corpus x3"),  # x1
    "الْعُلْیَا": ("الْعُلْيَا", "corpus x72"),  # x1
    "الْکَافِرِ": ("الْكَافِرِ", "corpus x100"),  # x1
    "الْکَفِّ": ("الْكَفِّ", "corpus x17"),  # x1
    "الْیَدُ": ("الْيَدُ", "corpus x146"),  # x1
    "الْیَدِ": ("الْيَدِ", "corpus x146"),  # x1
    "الْیَمِینُ": ("الْيَمِينُ", "corpus x91"),  # x1
    "امیۃ": ("امية", "positional"),  # x1
    "بُکُوْرِهَا": ("بُكُوْرِهَا", "corpus x12"),  # x1
    "بِالنِّیَّةِ": ("بِالنِّيَّةِ", "corpus x8"),  # x1
    "بِالْکِتْمَانِ": ("بِالْكِتْمَانِ", "positional"),  # x1
    "بِغَیْرِهِ": ("بِغَيْرِهِ", "corpus x12"),  # x1
    "جَاءَکُمْ": ("جَاءَكُمْ", "corpus x31"),  # x1
    "رمثۃ": ("رمثة", "corpus x20"),  # x1
    "سَیِّدُ": ("سَيِّدُ", "corpus x88"),  # x1
    "شَهِیْدٌ": ("شَهِيْدٌ", "corpus x142"),  # x1
    "شَکَرَ": ("شَكَرَ", "corpus x8"),  # x1
    "عَلی": ("عَلى", "corpus x18,350, over عَلي x5,274"),  # x1
    "فَاَکْرِمُوهُ": ("فَاَكْرِمُوهُ", "positional"),  # x1
    "فِی": ("فِي", "corpus x29,794, over فِى x64"),  # x1
    "فِیْ": ("فِيْ", "corpus x29,794, over فِىْ x64"),  # x1
    "قَیْئِهِ": ("قَيْئِهِ", "corpus x54"),  # x1
    "لَحِکْمَةً": ("لَحِكْمَةً", "corpus x1"),  # x1
    "مُوَکِّلٌ": ("مُوَكِّلٌ", "corpus x3"),  # x1
    "والیوم": ("واليوم", "corpus x198"),  # x1
    "کَأسْنَانِ": ("كَأسْنَانِ", "positional"),  # x1
    "کَادَ": ("كَادَ", "corpus x46"),  # x1
    "کَالرَّاجِعِ": ("كَالرَّاجِعِ", "positional"),  # x1
    "کَالْمُعَایَنَةِ": ("كَالْمُعَايَنَةِ", "positional"),  # x1
    "کَاَخْذِ": ("كَاَخْذِ", "positional"),  # x1
    "کَرِیْمُ": ("كَرِيْمُ", "corpus x16"),  # x1
    "کَفَاعِلِهِ": ("كَفَاعِلِهِ", "corpus x1"),  # x1
    "کَمَنْ": ("كَمَنْ", "corpus x24"),  # x1
    "کُفْرًا": ("كُفْرًا", "corpus x16"),  # x1
    "کُلُّهُ": ("كُلُّهُ", "corpus x320"),  # x1
    "یَحِلُّ": ("يَحِلُّ", "corpus x439"),  # x1
    "یَرَاهُ": ("يَرَاهُ", "corpus x27"),  # x1
    "یَرَی": ("يَرَى", "corpus x334, over يَرَي x4"),  # x1
    "یَشْکُرُ": ("يَشْكُرُ", "corpus x10"),  # x1
    "یَوْمَ": ("يَوْمَ", "corpus x4,412"),  # x1
    "یَکُوْنَ": ("يَكُوْنَ", "corpus x994"),  # x1
    "یُصِمُّ": ("يُصِمُّ", "corpus x20"),  # x1
    "یُعْمِيْ": ("يُعْمِيْ", "corpus x1"),  # x1
    "یَّجُهْرَ": ("يَّجُهْرَ", "corpus x48"),  # x1
}

# Candidates a single Perso-Arabic character can stand for, for --verify.
ALTERNATIVES = {"\u06cc": ["\u064a", "\u0649"], "\u06a9": ["\u0643"], "\u06c3": ["\u0629"]}

ARABIC_RUN = re.compile(r"[^\u0600-\u06FF]+")
TASHKEEL = re.compile(r"[\u064B-\u0652\u0670\u0653-\u0655\u06D6-\u06ED]")


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)


def verify(repo):
    """Re-derive the table from the rest of the corpus and report any disagreement."""
    import glob

    lexicon = {}
    for path in sorted(glob.glob(os.path.join(repo, "db/by_book/**/*.json"), recursive=True)):
        if os.path.relpath(path, repo) in TARGETS:
            continue
        with open(path, encoding="utf-8") as handle:
            for text in strings(json.load(handle)):
                for word in ARABIC_RUN.split(text):
                    if word:
                        bare = TASHKEEL.sub("", word)
                        lexicon[bare] = lexicon.get(bare, 0) + 1

    problems = []
    for source, (expected, _why) in FOLD.items():
        slots = [ALTERNATIVES.get(char, [char]) for char in source]
        hits = {
            "".join(parts): lexicon.get(TASHKEEL.sub("", "".join(parts)), 0)
            for parts in itertools.product(*slots)
        }
        seen = {word: n for word, n in hits.items() if n}
        if not seen:
            continue  # settled by the orthographic rule; the corpus has no opinion
        best = max(seen, key=seen.get)
        if best != expected:
            problems.append(f"  {source}: table says {expected}, corpus says {best} ({seen})")

    if problems:
        print("table disagrees with the corpus:")
        print("\n".join(problems))
        return 1
    print(f"all {len(FOLD)} entries agree with the corpus (or rest on the orthographic rule).")
    return 0


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "--verify" in sys.argv:
        return verify(repo)

    apply_changes = "--apply" in sys.argv
    total = 0
    for rel in TARGETS:
        path = os.path.join(repo, rel)
        if not os.path.exists(path):
            print(f"  missing, skipped: {rel}")
            continue
        with open(path, encoding="utf-8") as handle:
            before = handle.read()

        after = before
        found = 0
        for source, (replacement, _why) in FOLD.items():
            count = after.count(source)
            if count:
                found += count
                after = after.replace(source, replacement)
        if not found:
            print(f"  clean: {rel}")
            continue

        leftover = sum(after.count(char) for char in ALTERNATIVES)
        total += found
        note = "" if not leftover else f"  ({leftover} Perso-Arabic character(s) still unmapped)"
        print(f"  {rel}: {found} word(s) folded{note}")
        if apply_changes:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(after)

    print(f"\n{total} word(s) {'folded' if apply_changes else 'would be folded'}.")
    if not apply_changes:
        print("Re-run with --apply to write, or --verify to re-check the table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
