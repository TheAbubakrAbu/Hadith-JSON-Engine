#!/usr/bin/env python3
"""Repair scrape artifacts in the `grades[].grade` strings. Musnad Ahmad only, in practice.

WHY
---
Four defects, all of them damage done to the string on its way out of sunnah.com, and all
of them confined to `ahmed.json` (the one book whose Darussalam gradings came through a
scanned donor). They are artifacts of transport, not disagreements about a verdict, so
repairing them changes no scholarly claim:

  1. NAME REPEATED IN THE VERDICT.  Every grade in this book carries `name: "Darussalam"`,
     and 684 of them ALSO spell "(Darussalam)" inside the verdict. The renderer's job is to
     print `grade (name)`, so these came out doubled:

         Grade: Da'if (Darussalam)] (Darussalam)

     The `name` field is the structured copy and the one the app composes with, so the
     redundant parenthetical is cut FROM THE VERDICT and the field is left alone. Cut only
     when it matches this record's own `name` - a verdict naming a DIFFERENT authority
     ("Sahih (Darussalam), al-Bukhari (4533)") keeps that, because there it is content.

  2. "Lts" / "lts" FOR "Its".  A capital I+t recognised as L+t, in Darussalam's "Its isnad
     is Sahih". These verdicts reach us from CheeseWithSauce/HadithsJSONFormat, a scrape of
     sunnah.com, whose Musnad Ahmad gradings are digitized from Darussalam's PRINTED edition -
     that scan is where the misread happened, upstream of every project here.

     Three proofs it is character recognition and not a typo or a bad encoding: correct and
     corrupted forms interleave through the same book (citations 23, 42, 81 correct against
     61, 228, 230 corrupt), so it is not a consistent human habit or a find-replace; it hits
     only the shape-ambiguous word ("Its"->"Lts" 106, "its"->"lts" 13) while plain "it"/"It",
     56 occurrences, is never touched; and all 117 sit on `name: "Darussalam"` rows, the one
     donor with a print origin. Case is preserved: "Lts" -> "Its", "lts" -> "its".

  3. BACKSLASH-ESCAPED APOSTROPHES.  `Da\\'if` - a JSON/PHP escape that was written through
     into the data instead of being consumed by the parser. 17 records. The corpus spells
     it `Da'if` everywhere else.

  4. UNBALANCED BRACKET SCARS.  The same greedy-bracket damage `final_repair.py` documents
     for the bodies, reaching the grade line: 813 stray closers ("Hasan (Darussalam)]") and
     96 stray openers ("Sahih (Darussalam) ["), plus a few `)` and `}` used as a closer.
     NO grade in the corpus uses brackets as content - every balanced pair is a real
     takhrij ("[Bukhari 3615 and Muslim 2009]") and is kept untouched. Only UNMATCHED
     delimiters are dropped, so a balanced string is provably unmoved.

  5. THE SAME VERDICT RECORDED TWICE.  "Da'if, Da'if" - one comma-separated part repeated
     VERBATIM. 16 records corpus-wide, in four books, so this one is upstream's own scrape
     quirk rather than Ahmad's OCR. Musnad Ahmad 1176 is the reason it is here: its two
     halves differed only by defect 3's backslash ("Da'if" vs "Da\\'if"), so repairing that
     turned a pair that merely LOOKED distinct into a provable duplicate.

     Collapsed only on an EXACT repeat of a whole comma-separated part, keeping first
     occurrence and order. A part that differs in any way is two gradings and is kept - this
     never decides that two DIFFERENT verdicts are "the same really", which is the scholarly
     judgement the whole tool stays out of.

WHAT THIS REFUSES TO DO
-----------------------
It never rewrites a verdict term, never reconciles a grade with `name`, and never touches a
record whose grade is already clean. It splits on commas ONLY to drop an exact repeat
(defect 5) and never to reorder, merge or re-punctuate what survives.
A repair that would empty a grade, or that leaves no verdict word behind, is refused and
reported rather than written - a missing grade is worse than an ugly one.

Usage:
    python3 tools/fix_grade_artifacts.py [--apply] [--verbose]
"""
import glob
import json
import os
import re
import sys

# "Its isnad is ..." - the OCR misread. Bounded so it cannot touch a real word ending in
# "lts" (e.g. "results"); the corpus has no standalone token "lts" that is not this one.
OCR_ITS = re.compile(r'\b([Ll])ts\b')

# A backslash before the apostrophe of Da'if / da'eef and friends: `Da\'if` -> `Da'if`.
ESCAPED_QUOTE = re.compile(r'\\+([\'"])')

# Verdict words that must survive the repair, in any casing. Used only as a safety net:
# if a "repaired" string no longer contains one of these, the record is refused.
VERDICT = re.compile(
    r"sahih|sah\u012bh|hasan|da'if|da\u2019if|da'eef|daif|d[ae]'?[ei]f|"
    r"isnad|isn\u0101d|mauquf|munkar|mursal|shadh|matruk|maudu|"
    r"no basis|corroborat|weakness|interrupted|unknown|qawi|lighairihi|li ghairihi",
    re.I)


def drop_unmatched_brackets(s):
    """Remove only bracket characters that have no partner, keeping every matched pair.

    Two passes: left to right tracking open brackets to find unmatched CLOSERS, then the
    mirror for unmatched OPENERS. A string whose brackets all pair up comes back identical,
    which is what makes this safe to run over the whole corpus.
    """
    # Closers with no opener before them.
    drop = set()
    stack = []
    for i, ch in enumerate(s):
        if ch == '[':
            stack.append(i)
        elif ch == ']':
            if stack:
                stack.pop()
            else:
                drop.add(i)
    out = ''.join(ch for i, ch in enumerate(s) if i not in drop)

    # An opener whose closer was lost is CLOSED at the end rather than deleted. Deleting it
    # would weld the verdict onto the takhrij it introduces - "Sahih (Darussalam) [ al-Bukhari
    # (6647)" becoming "Sahih al-Bukhari (6647)", which reads as a grading OF Sahih al-Bukhari.
    # Restoring the bracket keeps the citation visibly a citation, which is what it is.
    if stack:
        out = out.rstrip()
        # A trailing full stop stays outside the restored bracket.
        tail = ''
        while out and out[-1] in '. ':
            tail = out[-1] + tail
            out = out[:-1]
        out = out + ']' * len(stack) + tail.strip()
    return out


def tidy_spacing(s, original):
    """Clean up ONLY what a cut above left behind - never punctuation upstream shipped.

    Every rule here is gated on the damage actually being new: a double space, a dangling
    comma or an emptied "()" is tidied when the ORIGINAL did not already have it at that
    spot. This is what keeps the pass off records whose punctuation is merely ugly - a
    trailing "1:" enumerating a multi-part grading, or an ellipsis inside a quoted phrase,
    is upstream's own text and stays exactly as it is.
    """
    s = re.sub(r'\(\s*\)', '', s)             # an emptied "()" left by the name cut
    s = re.sub(r'\[\s*\]', '', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    s = re.sub(r'\s+([,;])', r'\1', s)        # " ," welded on where a delimiter was cut

    # A trailing joiner is dropped only when the cut created it. If the original already
    # ended that way, it is upstream's and is preserved.
    if not re.search(r'[\s,;]+$', original):
        s = re.sub(r'[\s,;]+$', '', s)
    # Same gate for orphaned leading punctuation.
    if not re.match(r'^[\s,;:.\]\)\}]', original):
        s = re.sub(r'^[\s,;:.\]\)\}]+', '', s)
    return s.strip()


def collapse_repeated_parts(s):
    """Drop a comma-separated part that repeats an earlier one VERBATIM, keeping order.

    Whole parts only, compared exactly (after trimming surrounding space). "Da'if, Da'if"
    collapses; "Sahih, Sahih Hadeeth" does not, because those are not the same string.
    Rejoined with the same ", " the corpus uses, and only when something was actually
    dropped - so a grade with no repeat is returned untouched.
    """
    parts = [p.strip() for p in s.split(',')]
    if len(parts) < 2:
        return s
    kept, seen = [], set()
    for p in parts:
        if p and p in seen:
            continue
        seen.add(p)
        kept.append(p)
    return ', '.join(kept) if len(kept) != len(parts) else s


def has_repeated_part(s):
    parts = [p.strip() for p in s.split(',')]
    return len(parts) > 1 and len({p for p in parts if p}) < len([p for p in parts if p])


def has_artifact(grade, name):
    """True when this string carries one of the four documented defects.

    The gate for touching a record at all: a grade that is merely untidy (double spaces,
    a trailing comma, an odd ellipsis) is upstream's own text and must come through
    byte-identical, so only these four provable defects open the door.
    """
    return bool(
        (name and '(%s)' % name in grade)
        or OCR_ITS.search(grade)
        or ESCAPED_QUOTE.search(grade)
        or grade.count('[') != grade.count(']')
        or has_repeated_part(grade)
    )


def repair(grade, name):
    """Return the repaired grade string. Pure - no I/O, so it is directly testable."""
    if not has_artifact(grade, name):
        return grade
    out = grade

    # 1. The record's own grader name, repeated inside the verdict the renderer will already
    #    append it to. Only this name; another authority named here is content.
    if name:
        out = out.replace('(%s)' % name, ' ')
        # The same name written without parentheses, immediately before a stray closer, is
        # left alone: it is too close to legitimate prose to cut safely.

    # 2. OCR misread, preserving the case of the first letter.
    out = OCR_ITS.sub(lambda m: 'I' + 'ts' if m.group(1) == 'L' else 'its', out)

    # 3. Escaped apostrophes written through into the data.
    out = ESCAPED_QUOTE.sub(r'\1', out)

    # 4. Bracket scars, and the stray `}` / `)` used as a closer where no opener exists.
    out = drop_unmatched_brackets(out)
    if out.count('(') != out.count(')'):
        # Mirror of the bracket pass for parentheses, which the name-cut above can unbalance.
        drop, stack = set(), []
        for i, ch in enumerate(out):
            if ch == '(':
                stack.append(i)
            elif ch == ')':
                stack.pop() if stack else drop.add(i)
        drop.update(stack)
        out = ''.join(c for i, c in enumerate(out) if i not in drop)
    out = out.replace('}', '') if out.count('}') > out.count('{') else out

    out = tidy_spacing(out, grade)

    # 5. An exact repeat of a whole part, LAST - defects 1-4 are what expose it (1176's two
    #    halves are only provably identical once the stray backslash and brackets are gone).
    return collapse_repeated_parts(out)


def main():
    apply_changes = '--apply' in sys.argv
    verbose = '--verbose' in sys.argv
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    changed = refused = scanned = 0
    per_file = {}

    for path in sorted(glob.glob(os.path.join(repo, 'db', 'by_book', '*', '*.json'))):
        book = json.load(open(path, encoding='utf-8'))
        hits = 0

        for h in book.get('hadiths', []):
            english = h.get('english') or {}
            for g in (english.get('grades') or []):
                grade, name = g.get('grade', ''), g.get('name', '')
                scanned += 1
                fixed = repair(grade, name)
                if fixed == grade:
                    continue

                # Refuse a repair that destroys the verdict rather than tidying it.
                if not fixed or (VERDICT.search(grade) and not VERDICT.search(fixed)):
                    refused += 1
                    print('REFUSED  %s  %r -> %r' % (os.path.basename(path), grade, fixed))
                    continue

                if verbose:
                    print('  %-26s %r\n  %-26s %r\n' % ('was:', grade, 'now:', fixed))
                g['grade'] = fixed
                hits += 1
                changed += 1

        if hits:
            per_file[os.path.basename(path)] = hits
            if apply_changes:
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump(book, fh, ensure_ascii=False, indent=2)
                    fh.write('\n')

    print('\nscanned %d grade strings' % scanned)
    for f, n in sorted(per_file.items()):
        print('  %-28s %d repaired' % (f, n))
    print('%d repaired, %d refused' % (changed, refused))
    print('(dry run - pass --apply to write)' if not apply_changes else '(written)')
    return 1 if refused else 0


if __name__ == '__main__':
    sys.exit(main())
