#!/usr/bin/env python3
"""Second repair pass: recover the records the first pass could not prove.

WHY A SECOND PASS EXISTS
------------------------
`final_repair.py` simulates the upstream bug with

    GREEDY = re.sub(r'\\[.*\\]', '', s)

and Python's `.` does not match a newline, so that is a faithful simulation *only if the
candidate still has the line breaks the scraper saw*. It does not. Upstream's regex is
JavaScript's `/\\[.*\\]/g` (`src/helpers/scrapeData.ts:70`), which is likewise per-line -
but BOTH clean donors ship the narration flattened onto one line, with any trailing
citation welded on by a space instead of a newline.

So for any hadith whose clean text carries a bracketed insertion AND a bracketed citation
- `... on five [pillars]: ...` plus a closing `[Bukhari & Muslim]` - simulating the bug on
the flattened donor deletes everything from the first `[` to the last `]`, i.e. the whole
narration. That never equals the damaged record, which kept its narration, so the proof
could not hold and the record was left alone. Unprovable, not undamaged.

THE FIX
-------
Model what the scraper actually did: the deletion ran independently per line, and a line
break is exactly what the donors lost. Instead of one greedy strip over the whole string,
consider every way the bracket pairs could have been distributed across lines - each
consecutive GROUP deletes from the group's first `[` to its last `]` - and ask whether ANY
grouping reproduces the damaged record.

The proof gate is unchanged and just as strict:

    exists a grouping G:  norm(strip_grouped(clean, G)) == norm(damaged)   # same hadith
    and                   norm(clean)                   != norm(damaged)   # text was lost

Nothing is guessed. No grouping reproduces the damage -> the record is left exactly as
upstream has it, same policy as before.

FINDING CANDIDATES AT SCALE
---------------------------
Pass 1 keyed an exact dict by `norm(GREEDY(c))`, which is precisely the key that fails
here. A linear scan instead is O(records x donors) and will not finish on Bukhari.

What every grouping preserves is the text BEFORE the first `[` - no grouping can delete it.
So `norm(damaged)` and `norm(clean)` share that prefix, which is usually dozens of
characters. Sort the donor texts by `norm` and the true candidate is a NEAREST NEIGHBOUR of
`norm(damaged)`: binary-search the insertion point and test a small window around it.
O(log n) per record instead of O(n).

The window can only ever cause a MISS (a record left as upstream has it), never a wrong
repair, because the grouped proof still gates every write.

Usage:
    python3 tools/repair_line_aware.py --donors <dir> [--only-book slug] [--apply]

`<dir>` holds `fawaz/<edition>.json` and `HadithsJSONFormat-main/Sunnah/<book>/*.json`.
"""
import json, os, re, sys
from bisect import bisect_left
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from final_repair import norm, tidy, estimate_split, GREEDY, looks_scarred

# slug -> (folder in db/by_book, fawazahmed0 edition or None, CheeseWithSauce dir or None)
BOOKS = {
    "bukhari": ("the_9_books", "eng-bukhari", "bukhari"),
    "muslim": ("the_9_books", "eng-muslim", "muslim"),
    "nasai": ("the_9_books", "eng-nasai", "nasai"),
    "abudawud": ("the_9_books", "eng-abudawud", "abudawud"),
    "tirmidhi": ("the_9_books", "eng-tirmidhi", "tirmidhi"),
    "ibnmajah": ("the_9_books", "eng-ibnmajah", "ibnmajah"),
    "malik": ("the_9_books", "eng-malik", "malik"),
    "ahmed": ("the_9_books", None, "ahmad"),
    "darimi": ("the_9_books", None, "darimi"),
    "qudsi40": ("forties", None, "forty"),
    "nawawi40": ("forties", "eng-nawawi", "forty"),
    "shahwaliullah40": ("forties", None, "forty"),
    "aladab_almufrad": ("other_books", None, "adab"),
    "shamail_muhammadiyah": ("other_books", None, "shamail"),
    "riyad_assalihin": ("other_books", None, "riyadussalihin"),
    "mishkat_almasabih": ("other_books", None, "mishkat"),
    "bulugh_almaram": ("other_books", None, "bulugh"),
}

# How many sorted neighbours to test around the insertion point. The true candidate shares a
# long prefix with the damaged text, so it lands within a handful of positions; 64 is slack.
WINDOW = 64
# Refuse to enumerate groupings beyond this many bracket pairs rather than burn 2^n on a
# record we would almost certainly reject anyway.
MAX_PAIRS = 12


def bracket_spans(s):
    """The (start, end) of each `[...]` pair, scanned left to right, non-overlapping."""
    spans, i = [], 0
    while True:
        a = s.find('[', i)
        if a < 0:
            return spans
        b = s.find(']', a + 1)
        if b < 0:
            return spans
        spans.append((a, b + 1))
        i = b + 1


def strip_grouped(s, cuts, spans=None):
    """Delete each consecutive group of bracket pairs from its first `[` to its last `]`.

    `cuts[i]` is True when a line break fell between pair i and pair i+1, so the two were
    stripped independently instead of being swallowed by a single greedy match."""
    spans = bracket_spans(s) if spans is None else spans
    if not spans:
        return s
    out, last, start = [], 0, 0
    for i, span in enumerate(spans):
        if i == len(spans) - 1 or cuts[i]:
            out.append(s[last:spans[start][0]])
            last = span[1]
            start = i + 1
    out.append(s[last:])
    return ''.join(out)


def provable(clean, target_norm):
    """True when some line-grouping of `clean`'s brackets reproduces the damaged text."""
    spans = bracket_spans(clean)
    if not spans or len(spans) > MAX_PAIRS:
        return False
    for cuts in product((False, True), repeat=len(spans) - 1):
        if norm(strip_grouped(clean, cuts, spans)) == target_norm:
            return True
    return False


# Punctuation that can never legitimately OPEN a narration, so finding it at the front of a
# restored body means the narrator split landed a few characters early - inside the "(RAA):"
# that closes the narrator - and left its tail behind.
#
# The proof cannot catch this on its own: `norm` discards every non-alphanumeric character,
# so a split before "): " and a split after it are the SAME string to it, and the search
# takes whichever it reaches first. Trimming these is therefore proof-neutral by
# construction - it cannot change `norm`, so a repair that was proven stays proven.
#
# Quotes, `(` and `[` are deliberately NOT in this set: a narration really can open with
# `"`, `(ﷺ)` or `[He said:]`, and `lstrip` stops at the first character it does not hold.
LEAD_JUNK = ' \t\r\n):;,.-–, ]'


def restore(clean, narrator, before):
    """(new_narrator, new_text) with every bracket intact, or (None, None).

    Same split discipline as `final_repair.restore`: never trust the estimated narrator
    boundary, search a window around it, and require the proof to hold on the split we
    actually write back. If no split qualifies, fold the narrator into the body, which
    satisfies the proof by construction, rather than guess at a boundary."""
    target = norm(narrator + ' ' + before)
    if not provable(clean, target):
        return None, None
    est = estimate_split(clean, narrator)
    for delta in range(0, 61):
        for i in {est - delta, est + delta}:
            if not 0 <= i <= len(clean):
                continue
            cand = clean[i:].lstrip(LEAD_JUNK)
            if provable(narrator + ' ' + cand, target):
                return narrator, tidy(cand)
    return "", tidy(clean).lstrip(LEAD_JUNK)


class Donor:
    """One clean source for one book, indexed for nearest-neighbour lookup."""

    def __init__(self, name, texts):
        self.name = name
        # Dedupe on normalised content; the donors repeat texts across section files.
        seen = {}
        for t in texts:
            if t and t.strip():
                seen.setdefault(norm(t), t)
        self.pairs = sorted(seen.items())          # [(norm, raw)], sorted by norm
        self.keys = [k for k, _ in self.pairs]

    def candidates(self, target_norm):
        """Donor texts whose grouped strip could plausibly reproduce `target_norm`."""
        i = bisect_left(self.keys, target_norm)
        lo, hi = max(0, i - WINDOW), min(len(self.pairs), i + WINDOW)
        return [raw for _, raw in self.pairs[lo:hi]]

    def match(self, target_norm):
        """The one clean text that provably reproduces the damage, or None.

        Two candidates with different content both reproducing it is ambiguity, and
        ambiguity is refused rather than resolved - the same rule pass 1 used."""
        found = None
        for c in self.candidates(target_norm):
            if norm(c) == target_norm:
                continue                            # identical: nothing was lost
            if provable(c, target_norm):
                if found is not None and norm(found) != norm(c):
                    return None
                found = c
        return found


def load_fawaz(path):
    return [h.get('text', '') for h in json.load(open(path))['hadiths']]


def load_cws(directory):
    """Every section file in one CheeseWithSauce book directory.

    `utf-8-sig`, not `utf-8`: these files carry a BOM, and reading them as plain utf-8
    raises on the very first character. Swallowing that quietly would leave the book with
    no second donor and silently halve its confirmation - so a file that will not parse is
    reported, not skipped in silence."""
    texts = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith('.json'):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, encoding='utf-8-sig') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f'  warning: unreadable donor file {path}: {e}', file=sys.stderr)
            continue
        if isinstance(data, list):
            texts += [x.get('english', '') for x in data if isinstance(x, dict)]
    return texts


def main():
    argv = sys.argv[1:]
    apply_changes = '--apply' in argv
    donors_root = next((argv[i + 1] for i, a in enumerate(argv) if a == '--donors'), None)
    only_book = next((argv[i + 1] for i, a in enumerate(argv) if a == '--only-book'), None)
    only_ids = next((a.split('=', 1)[1] for a in argv if a.startswith('--only-ids=')), None)
    only_ids = {int(x) for x in only_ids.split(',')} if only_ids else None
    if not donors_root:
        raise SystemExit(__doc__)

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cws_root = os.path.join(donors_root, 'HadithsJSONFormat-main', 'Sunnah')
    grand = {'total': 0, 'repaired': 0, 'one_donor': 0, 'ambiguous': 0, 'scarred_left': 0}
    rows = []

    for slug, (folder, fawaz_edition, cws_dir) in BOOKS.items():
        if only_book and slug != only_book:
            continue
        book_path = os.path.join(repo, 'db', 'by_book', folder, f'{slug}.json')
        book = json.load(open(book_path))

        donors = []
        if fawaz_edition:
            p = os.path.join(donors_root, 'fawaz', f'{fawaz_edition}.json')
            if os.path.exists(p):
                donors.append(Donor('fawaz', load_fawaz(p)))
        if cws_dir:
            p = os.path.join(cws_root, cws_dir)
            if os.path.isdir(p):
                donors.append(Donor('cws', load_cws(p)))
        if not donors:
            rows.append((slug, len(book['hadiths']), 0, 0, 0, 'no donor'))
            continue

        repaired = ambiguous = one_donor = scarred_left = 0
        log_path = os.path.join(repo, 'logs', f'{slug}.repairlog.json')
        log = json.load(open(log_path)) if os.path.exists(log_path) else []
        already = {e['idInBook'] for e in log}

        for h in book['hadiths']:
            if only_ids is not None and h['idInBook'] not in only_ids:
                continue
            body, narr = h['english']['text'], h['english']['narrator']
            target = norm(narr + ' ' + body)

            hits = [d.match(target) for d in donors]
            confirmed = [x for x in hits if x is not None]
            if not confirmed:
                if looks_scarred(body):
                    scarred_left += 1
                continue
            if len({norm(x) for x in confirmed}) != 1:
                ambiguous += 1                       # donors disagree - refuse
                continue

            clean = confirmed[0]
            new_narr, new_text = restore(clean, narr, body)
            if new_text is None:
                continue
            if norm(new_narr + ' ' + new_text) == target:
                continue                             # nothing actually recovered

            if h['idInBook'] in already:             # pass 1 already wrote this one
                continue
            log.append({'idInBook': h['idInBook'], 'before': body, 'after': new_text,
                        'narrator_folded': new_narr == "" and narr != "",
                        'confirmed_by': len(confirmed), 'pass': 'line_aware'})
            h['english']['narrator'] = new_narr
            h['english']['text'] = new_text
            repaired += 1
            if len(confirmed) == 1:
                one_donor += 1

        rows.append((slug, len(book['hadiths']), repaired, one_donor, ambiguous,
                     f'{len(donors)} donor' + ('s' if len(donors) > 1 else '')))
        grand['total'] += len(book['hadiths'])
        grand['repaired'] += repaired
        grand['one_donor'] += one_donor
        grand['ambiguous'] += ambiguous
        grand['scarred_left'] += scarred_left

        if apply_changes and repaired:
            # Default separators, no indent, no trailing newline: verified to round-trip the
            # book files byte for byte, so the diff is the repaired hadiths and nothing else.
            with open(book_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(book, ensure_ascii=False))
            log.sort(key=lambda e: e['idInBook'])
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"{'book':<24}{'hadiths':>9}{'repaired':>10}{'1-donor':>9}{'ambig':>7}  sources")
    for slug, total, repaired, one, amb, note in rows:
        print(f'{slug:<24}{total:>9,}{repaired:>10,}{one:>9,}{amb:>7,}  {note}')
    print(f"\n{'TOTAL':<24}{grand['total']:>9,}{grand['repaired']:>10,}"
          f"{grand['one_donor']:>9,}{grand['ambiguous']:>7,}")
    print(f"still scarred and unmatched (left as upstream): {grand['scarred_left']:,}")
    if not apply_changes:
        print('\nDRY RUN - pass --apply to write')


if __name__ == '__main__':
    main()
