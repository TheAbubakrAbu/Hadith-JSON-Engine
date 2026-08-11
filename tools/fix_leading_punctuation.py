#!/usr/bin/env python3
"""Trim the narrator tail left at the front of records repaired by pass 1.

`final_repair.restore` finds where the narrator ends by searching for a split that keeps
the round-trip proof true. The proof compares with `norm`, which discards every
non-alphanumeric character - so a split placed just BEFORE the "):" that closes a narrator
and one placed just after it are indistinguishable to it, and the search keeps whichever it
reaches first. When it keeps the early one, the restored body opens with the narrator's
leftover punctuation:

    narrator: "Narrated Abu Sa'id al-Khudri (RAA):"
    text:     "): Two men set out on a journey ..."

`restore` strips `' :,-'`, which does not include `)`, so these survived. 646 of the 4,188
records repaired by pass 1 are affected.

This is cosmetic damage to otherwise correct repairs: no words are missing, the wrong
characters are simply at the front. Trimming them is proof-neutral BY CONSTRUCTION - `norm`
ignores punctuation, so every repair that was proven stays proven, and re-verification is
unaffected.

Only records that appear in a repair log are touched, and only their leading punctuation -
never a record upstream shipped that way itself.

Usage:
    python3 tools/fix_leading_punctuation.py [--apply]
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repair_line_aware import BOOKS, LEAD_JUNK


def main():
    apply_changes = '--apply' in sys.argv
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    total = 0

    for slug, (folder, _, _) in BOOKS.items():
        log_path = os.path.join(repo, 'logs', f'{slug}.repairlog.json')
        if not os.path.exists(log_path):
            continue
        log = json.load(open(log_path))
        repaired_ids = {e['idInBook'] for e in log}

        book_path = os.path.join(repo, 'db', 'by_book', folder, f'{slug}.json')
        book = json.load(open(book_path))

        fixed = 0
        for h in book['hadiths']:
            if h['idInBook'] not in repaired_ids:
                continue
            text = h['english']['text']
            trimmed = text.lstrip(LEAD_JUNK)
            if trimmed != text and trimmed:
                h['english']['text'] = trimmed
                fixed += 1
        if not fixed:
            continue

        for entry in log:                       # keep the audit trail honest
            t = entry['after'].lstrip(LEAD_JUNK)
            if t and t != entry['after']:
                entry['after'] = t

        print(f'{slug:24} {fixed:4} record(s) trimmed')
        total += fixed

        if apply_changes:
            with open(book_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(book, ensure_ascii=False))
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=2)

    print(f'\ntotal: {total} record(s)' + ('' if apply_changes else '  (DRY RUN - pass --apply)'))


if __name__ == '__main__':
    main()
