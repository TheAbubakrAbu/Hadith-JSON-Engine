#!/usr/bin/env python3
"""Attach authentication gradings (sahih / hasan / da'if) to every hadith we can match.

WHY
---
The upstream schema is `arabic` + `english{narrator, text}` and carries no grading at all,
so a reader cannot tell a sahih narration from a da'if one. For Tirmidhi and Ibn Majah in
particular that is not a cosmetic gap - those collections contain graded-weak material by
design, and presenting it undifferentiated misrepresents it.

Both clean donors already carry gradings, from different graders:

  fawazahmed0  `grades: [{name, grade}]`   Al-Albani, Zubair Ali Zai, Ahmad Muhammad Shakir
  CheeseWithSauce  `grade: "Grade : Sahih (Darussalam)"`   Darussalam

Both are sunnah.com's own gradings, which are themselves quoting the named scholars. This
attaches them; it does not compute, infer, or adjudicate anything. Where graders disagree,
BOTH are kept - reconciling them is a scholarly judgement, not a data-processing one.

MATCHING
--------
By content, never by hadith number - `idInBook` drift is a known upstream problem. A grade
is written only when the donor record is provably this same hadith:

  exact:  norm(donor) == norm(ours)
  or:     some line-grouping of the donor reproduces ours   (i.e. the donor is the clean
          twin of a record still carrying the greedy-bracket damage)

Anything else is left ungraded rather than guessed. A wrong grade on a hadith is worse than
no grade, so this refuses ambiguity: if two donor records with DIFFERENT gradings both match,
neither is written.

Usage:
    python3 tools/add_grades.py --donors <dir> [--apply]
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repair_line_aware import (BOOKS, Donor, norm, provable, load_cws, load_fawaz)

GRADE_PREFIX = re.compile(r'^\s*Grade\s*:\s*', re.I)
TRAILING_GRADER = re.compile(r'\(([^()]{2,40})\)\s*$')
# Many entries repeat the verdict in Arabic after the English one:
#   "Sahih (Al-Albani) صحيح (الألباني) حكم :"
# The two say the same thing. Keep the English half and cut from the first Arabic letter,
# otherwise the grader's name is buried behind the Arabic and never parses out.
ARABIC = re.compile(r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]')


def parse_cws_grade(raw):
    """'Grade : Sahih (Darussalam)' -> ('Darussalam', 'Sahih'). The grader is whoever the
    trailing parenthetical names; without one the attribution is left blank rather than
    invented.

    The literal `Grade :` prefix is REQUIRED. For Bukhari and Muslim this field holds the
    reference instead - 'Sahih al-Bukhari 1', 'Sahih Muslim 8 a' - because sunnah.com does
    not grade those two collections hadith by hadith; the collections are sahih by
    definition. Reading that as a grading would stamp every Bukhari hadith with a unique
    fake "grade" that is really just its number."""
    raw = (raw or '').strip()
    if not GRADE_PREFIX.match(raw):
        return None
    text = GRADE_PREFIX.sub('', raw).strip()
    m = ARABIC.search(text)
    if m:
        text = text[:m.start()].strip()
    if not text:
        return None
    m = TRAILING_GRADER.search(text)
    if m:
        return {'name': m.group(1).strip(), 'grade': text[:m.start()].strip()}
    return {'name': '', 'grade': text}


def load_fawaz_grades(path):
    """[(clean text, [{name, grade}])] for every graded record in a fawazahmed0 edition."""
    out = []
    for h in json.load(open(path))['hadiths']:
        grades = [g for g in (h.get('grades') or [])
                  if isinstance(g, dict) and (g.get('grade') or '').strip()]
        if grades and (h.get('text') or '').strip():
            out.append((h['text'], [{'name': (g.get('name') or '').strip(),
                                     'grade': g['grade'].strip()} for g in grades]))
    return out


def load_cws_grades(directory):
    out = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith('.json'):
            continue
        try:
            with open(os.path.join(directory, name), encoding='utf-8-sig') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, list):
            continue
        for x in data:
            if not isinstance(x, dict):
                continue
            g = parse_cws_grade(x.get('grade'))
            if g and (x.get('english') or '').strip():
                out.append((x['english'], [g]))
    return out


class GradeIndex:
    """Donor gradings, looked up by content: exact first, then clean-twin by grouping."""

    def __init__(self, entries):
        self.exact = {}
        for text, grades in entries:
            self.exact.setdefault(norm(text), []).append(grades)
        self.donor = Donor('grades', [t for t, _ in entries])
        self.by_norm = {}
        for text, grades in entries:
            self.by_norm.setdefault(norm(text), grades)

    def lookup(self, key):
        hit = self.exact.get(key)
        if hit is not None:
            flat = {(g['name'], g['grade']) for grades in hit for g in grades}
            names = {n for n, _ in flat}
            if len(flat) != len(names):        # same grader, two different verdicts
                return None
            return sorted(({'name': n, 'grade': g} for n, g in flat),
                          key=lambda x: (x['name'], x['grade']))
        # Still-damaged record: its clean twin in the donor carries the grading.
        found = None
        for cand in self.donor.candidates(key):
            if provable(cand, key):
                if found is not None and norm(found) != norm(cand):
                    return None                # ambiguous - refuse
                found = cand
        return self.by_norm.get(norm(found)) if found else None


def main():
    argv = sys.argv[1:]
    apply_changes = '--apply' in argv
    root = next((argv[i + 1] for i, a in enumerate(argv) if a == '--donors'), None)
    if not root:
        raise SystemExit(__doc__)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cws_root = os.path.join(root, 'HadithsJSONFormat-main', 'Sunnah')

    print(f"{'book':<24}{'hadiths':>9}{'graded':>9}{'%':>7}{'graders':>9}")
    tot = graded_tot = 0
    for slug, (folder, fawaz_edition, cws_dir) in BOOKS.items():
        path = os.path.join(repo, 'db', 'by_book', folder, f'{slug}.json')
        book = json.load(open(path))

        entries = []
        if fawaz_edition:
            p = os.path.join(root, 'fawaz', f'{fawaz_edition}.json')
            if os.path.exists(p):
                entries += load_fawaz_grades(p)
        if cws_dir:
            p = os.path.join(cws_root, cws_dir)
            if os.path.isdir(p):
                entries += load_cws_grades(p)
        tot += len(book['hadiths'])
        if not entries:
            print(f'{slug:<24}{len(book["hadiths"]):>9,}{0:>9,}{0.0:>6.1f}%{"-":>9}')
            continue

        index = GradeIndex(entries)
        graded = 0
        names = set()
        for h in book['hadiths']:
            # Cleared first so a re-run cannot leave a stale grading behind on a record
            # that no longer matches - this tool has to be idempotent.
            h['english'].pop('grades', None)
            text = (h['english'].get('text') or '').strip()
            if not text:
                continue
            grades = index.lookup(norm(h['english'].get('narrator', '') + ' ' + text))
            if not grades:
                grades = index.lookup(norm(text))
            if grades:
                h['english']['grades'] = grades
                graded += 1
                names.update(g['name'] for g in grades if g['name'])

        n = len(book['hadiths'])
        print(f'{slug:<24}{n:>9,}{graded:>9,}{graded / n * 100:>6.1f}%{len(names):>9}')
        graded_tot += graded
        if apply_changes and graded:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(book, ensure_ascii=False))

    print(f"\n{'TOTAL':<24}{tot:>9,}{graded_tot:>9,}{graded_tot / tot * 100:>6.1f}%")
    if not apply_changes:
        print('\nDRY RUN - pass --apply to write')


if __name__ == '__main__':
    main()
