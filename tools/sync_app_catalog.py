#!/usr/bin/env python3
"""Bring db/catalog.json's authored prose back in line with the app that writes it.

    python3 tools/sync_app_catalog.py --app /path/to/Al-Islam-iOS            # dry run
    python3 tools/sync_app_catalog.py --app /path/to/Al-Islam-iOS --apply

WHICH SIDE IS RIGHT. Almost everything in this repository flows outward: the corpus is repaired
here and the app's packs are built from it, so when the two disagree about hadith TEXT the app is
stale. The catalog's prose is the one exception. Its titles, author names and descriptions are not
scraped or derived from anything; they were written for the app's own Hadith tab, they are display
copy in the app's own voice, and `verify_packs.py` cross-checks them precisely because the same
facts then exist twice. So for these nine fields the app is upstream and this file follows it.

WHY IT DRIFTED. The app vocalized its authored Arabic: full tashkeel on every letter except that no
sukoon is ever written, so a letter that would carry one carries nothing. That pass moved 36 fields
across all 17 books (every `authorArabic` and `longDescription`, plus two `arabicTitle`s) and left
this file behind, which is 36 of the 36 failures `verify_packs.py` reports.

WHAT IT REFUSES TO DO. A vocalization pass may add and remove marks; it may not change which
letters are there. So every rewrite is held to two tests, and one failure stops the whole run:

  - the consonantal skeleton must be identical once the marks are stripped, which is what catches a
    genuine edit (a corrected name, a reworded sentence) hiding inside a cosmetic diff, and
  - the incoming Arabic must carry no sukoon, U+0652 or U+06E1, since the rule that produced it
    forbids both.

An English field that changed is reported and copied, since the skeleton test says nothing about
it: read those before applying. `--apply` rewrites nothing else in the file, so the groups table,
slugs, ordering and every non-prose field stay exactly as they are.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The nine fields verify_packs.py cross-checks, in its order.
FIELDS = ('group', 'englishTitle', 'arabicTitle', 'authorEnglish', 'authorArabic',
          'era', 'shortDescription', 'longDescription', 'aliases')

# Arabic combining marks: everything a vocalization pass is allowed to add or remove.
MARKS = set("ًٌٍَُِّْٰٕٓٔۡ")
# The two the app's rule forbids outright.
SUKOON = ("ْ", "ۡ")
ARABIC = re.compile(r'[؀-ۿ]')


def unescape(literal: str) -> str:
    """Swift string-literal escapes, including \\u{...}. Mirrors verify_packs.py."""
    out, i = [], 0
    escapes = {'n': '\n', 't': '\t', '"': '"', '\\': '\\', "'": "'", '0': '\0'}
    while i < len(literal):
        if literal[i] == '\\' and i + 1 < len(literal):
            nxt = literal[i + 1]
            if nxt in escapes:
                out.append(escapes[nxt])
                i += 2
                continue
            if nxt == 'u' and literal[i + 2:i + 3] == '{':
                close = literal.index('}', i)
                out.append(chr(int(literal[i + 3:close], 16)))
                i = close + 1
                continue
        out.append(literal[i])
        i += 1
    return ''.join(out)


def parse_app_catalog(app_dir: Path) -> list[dict]:
    """`HadithCatalogBook.all` as data. Deliberately the same regexes verify_packs.py uses: if this
    file and the gate ever read the Swift differently, a sync could 'fix' the gate into silence."""
    swift_path = app_dir / 'iPhone' / 'Hadith' / 'HadithModels.swift'
    if not swift_path.exists():
        raise SystemExit(f"no app catalog at {swift_path}")
    source = swift_path.read_text(encoding='utf-8')
    start = source.find('static let all: [HadithCatalogBook] = [')
    if start < 0:
        raise SystemExit(f"HadithCatalogBook.all not found in {swift_path}")
    body = source[start:source.index('\n    ]\n', start)]

    entries = []
    for chunk in re.findall(r'HadithCatalogBook\(\s*\n(.*?)\n\s*\),?\n', body + '\n', re.S):
        def field(name, text=chunk):
            m = re.search(name + r':\s*"((?:[^"\\]|\\.)*)"', text)
            return unescape(m.group(1)) if m else None
        aliases = re.search(r'aliases:\s*\[(.*?)\]', chunk, re.S)
        entries.append({
            'slug': field('slug'),
            'group': re.search(r'group:\s*\.(\w+)', chunk).group(1),
            'englishTitle': field('englishTitle'), 'arabicTitle': field('arabicTitle'),
            'authorEnglish': field('authorEnglish'), 'authorArabic': field('authorArabic'),
            'era': field('era'), 'shortDescription': field('shortDescription'),
            'longDescription': field('longDescription'),
            'aliases': [unescape(a) for a in
                        re.findall(r'"((?:[^"\\]|\\.)*)"', aliases.group(1))],
        })
    return entries


def skeleton(text: str) -> str:
    """The letters alone: the part a vocalization pass must leave untouched."""
    return ''.join(c for c in unicodedata.normalize('NFC', text) if c not in MARKS)


def describe(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    flat = text.replace('\n', '\\n')
    return flat if len(flat) <= 72 else flat[:69] + '...'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--app', required=True, type=Path, help='the Al-Islam-iOS checkout')
    parser.add_argument('--apply', action='store_true', help='write db/catalog.json')
    args = parser.parse_args()

    path = REPO / 'db' / 'catalog.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    books = catalog['books']
    entries = parse_app_catalog(args.app)

    if [b['slug'] for b in books] != [e['slug'] for e in entries]:
        raise SystemExit('the app and db/catalog.json list different books, or list them in a '
                         'different order: that is a real divergence, not a prose refresh')

    changes, refusals, english = [], [], []
    for book, entry in zip(books, entries):
        for name in FIELDS:
            before, after = book[name], entry[name]
            if before == after:
                continue
            where = f"{book['slug']}.{name}"
            if isinstance(before, list) or isinstance(after, list):
                refusals.append(f"{where}: {describe(before)} -> {describe(after)} (a list field)")
                continue
            if ARABIC.search(before) or ARABIC.search(after):
                if skeleton(before) != skeleton(after):
                    refusals.append(f"{where}: the letters themselves changed, not just the marks")
                    continue
                if any(s in after for s in SUKOON):
                    refusals.append(f"{where}: the app's text carries a sukoon, which its own rule "
                                    f"forbids: check the app, not this file")
                    continue
            else:
                english.append(where)
            changes.append((book, name, before, after))

    for book, name, before, after in changes:
        print(f"{book['slug']}.{name}")
        print(f"  - {describe(before)}")
        print(f"  + {describe(after)}")

    if english:
        print(f"\n{len(english)} field(s) with no Arabic changed, so nothing verified the edit "
              f"beyond this diff: {', '.join(english)}")

    if refusals:
        print(f"\nREFUSED, nothing written ({len(refusals)}):", file=sys.stderr)
        for line in refusals:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)

    if not changes:
        print('db/catalog.json already matches the app.')
        return

    if not args.apply:
        print(f"\n{len(changes)} field(s) would change. Re-run with --apply to write them.")
        return

    for book, name, _before, after in changes:
        book[name] = after
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"\n{len(changes)} field(s) written to {path.relative_to(REPO)}. "
          f"Re-run tools/verify_packs.py to confirm.")


if __name__ == '__main__':
    main()
