#!/usr/bin/env python3
"""Attach the standard sunnah.com citation number to every hadith we can match.

WHY
---
Upstream's `idInBook` is a row index over its own scrape, not a citation key - its own
docs and ours both say so ([upstream #11], docs/01-data-schema.md). But it is the number
apps end up showing, and it drifts from the numbering readers actually cite: sunnah.com's,
which follows the Dar-us-Salam prints. Jami` at-Tirmidhi 2950 sits at `idInBook` 3033 -
progressive drift, +97 by the end of the book.

Renumbering `idInBook` cannot fix this. The standard numbering is not a sequence of
integers: Sahih Muslim cites as "8a"/"8b" (6,187 of its 7,459 rows carry a letter), and
several books number multiple rows under one base. So the citation becomes its own field,
and `idInBook` stays what it always was - a stable internal row key.

THE SOURCE
----------
CheeseWithSauce carries, for every row, the Arabic text AND sunnah.com's own reference
line ("Reference : Jami` at-Tirmidhi 1 In-book reference : ..."). Its row sets match ours
book for book (both scraped the same sunnah.com rows), so nearly every row pairs up by
content. fawazahmed0's `hadithnumber` independently confirms the result for five of the
six big books (Sahih Muslim's lettered numbering is not comparable to fawaz's continuous
scheme) plus an-Nawawi's Forty.

One book is deliberately left without citations:

  malik   sunnah.com itself has no collection-level number for Muwatta Malik - only
          "Book X, Hadith Y" references, and its Arabic-edition numbers are non-unique,
          non-monotonic, and missing for 153 rows. No standard single number exists.
          (darimi, by contrast, DOES get one: its "Arabic reference" numbering is
          continuous, unique, and complete (1..3406), and it is how Darimi is cited.)

MATCHING
--------
By content, never by number - the whole point is that the numbers cannot be trusted.

  T1  unique folded-Arabic equality
  T2  fold collision groups paired in book order (equal group sizes only)
  T3  English content, exact norm or provable clean-twin (the repair-pipeline proof)
  T4  sandwich: both neighbours matched to adjacent donor rows, one donor row between
  T5  nearest-neighbour folded-Arabic prefix, only inside a T4-style positional window

Anything else stays uncited rather than guessed: a wrong citation under a hadith is worse
than no citation. Rows whose donor twin has no parseable reference stay uncited too.

Usage:
    python3 tools/add_citations.py --donors <dir> [--apply]
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repair_line_aware import BOOKS, Donor, norm, provable

# ---------------------------------------------------------------- reference parsing

# The segment of the CWS reference line that carries the collection-level citation,
# cut before the per-book/per-translation references that follow it.
REF_SEGMENT = re.compile(
    r'Reference\s*:\s*(.*?)\s*(?:(?:In-book|Sunnah\.com|USC-MSA[^:]*|English|Arabic(?:/English)?)'
    r'\s*(?:reference|translation|book reference)|$)', re.S)
# "2950", "8 a", "282, 283" - number tokens with an optional letter suffix.
NUM_TOKEN = re.compile(r'(\d+)\s*([a-z])?(?![\w])')
# darimi: the continuous Arabic-edition number, unique and complete for every row.
DARIMI_REF = re.compile(r'Arabic reference\s*:\s*Book\s*\d+,\s*Hadith\s*(\d+)')


def parse_citation(slug, raw):
    """(base:int, suffix:str) or None. Multi-number rows ("282, 283") take the first."""
    raw = raw or ''
    if slug == 'darimi':
        m = DARIMI_REF.search(raw)
        return (int(m.group(1)), '') if m else None
    if slug == 'malik':
        return None
    seg = REF_SEGMENT.search(raw)
    if seg:
        tokens = NUM_TOKEN.findall(seg.group(1))
        if tokens:
            base, suffix = tokens[0]
            return (int(base), suffix or '')
    if slug == 'aladab_almufrad':
        # Seven of its books carry no "Reference :" line on sunnah.com, but Al-Adab
        # Al-Mufrad's book reference numbering IS its citation numbering (verified:
        # book 13 ends at 259, book 14's book references run 260..308, book 15
        # resumes at 309 - one continuous sequence).
        m = re.search(r'Arabic/English book reference\s*:\s*Book\s*\d+,\s*Hadith\s*(\d+)', raw)
        if m:
            return (int(m.group(1)), '')
    return None


def citation_str(cite):
    return f'{cite[0]}{cite[1]}' if cite else None


# ---------------------------------------------------------------- arabic fold

# A matching fold, not the search fold: everything that is not a base Arabic letter is
# dropped, including whitespace, so two scrapes of the same row cannot disagree over
# tashkeel, punctuation, or line wrapping.
AR_MARKS = re.compile(r'[ؐ-ًؚ-ٰٟـۖ-ۭ]')
AR_LETTER = re.compile(r'[^ء-ي]')
AR_CANON = str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ى': 'ا',
                          'ة': 'ه', 'ؤ': 'و', 'ئ': 'ي', 'ء': ''})


def afold(s):
    return AR_LETTER.sub('', AR_MARKS.sub('', s or '').translate(AR_CANON))


# ---------------------------------------------------------------- donor loading

def cws_files(directory):
    """Section files in book order - numeric filename prefixes decide, '.json' is book 0."""
    def key(name):
        m = re.match(r'(\d+)', name)
        return int(m.group(1)) if m else 0
    return [os.path.join(directory, n)
            for n in sorted((n for n in os.listdir(directory) if n.endswith('.json')), key=key)]


# The forties share one CWS directory; each slug owns exactly one file of it.
FORTY_FILES = {
    'nawawi40': 'forty_hadith_of_an-nawawi.json',
    'qudsi40': 'forty_hadith_qudsi.json',
    'shahwaliullah40': 'forty_hadith_of_shah_waliullah_dehlawi.json',
}


def load_cws_rows(slug, directory):
    """[(order, citation|None, afold(arabic), english)] for one book, in book order."""
    if slug in FORTY_FILES:
        paths = [os.path.join(directory, FORTY_FILES[slug])]
    else:
        paths = cws_files(directory)
    rows = []
    for path in paths:
        try:
            with open(path, encoding='utf-8-sig') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f'  warning: unreadable donor file {path}: {e}', file=sys.stderr)
            continue
        for x in data:
            if isinstance(x, dict):
                rows.append((len(rows), parse_citation(slug, x.get('reference')),
                             afold(x.get('arabic')), x.get('english') or ''))
    return rows


# Below this, English texts collide across unrelated hadiths ("perform ghusl", chapter
# stubs) and a cross-check comparison would be comparing coincidences, not rows.
CROSSCHECK_MIN_NORM = 40


def load_fawaz_numbers(path):
    """norm(english) -> {int base} for rows whose content is unique in the edition."""
    seen = {}
    for h in json.load(open(path))['hadiths']:
        text = (h.get('text') or '').strip()
        key = norm(text)
        if len(key) >= CROSSCHECK_MIN_NORM:
            seen.setdefault(key, set()).add(int(h['hadithnumber']))
    return {k: v for k, v in seen.items() if len(v) == 1}


# ---------------------------------------------------------------- matching

def match_book(ours, cws):
    """assignment: our row index -> cws row index. Content first, position only to break
    ties or bridge gaps between content-matched neighbours."""
    n, m = len(ours), len(cws)
    ours_fold = [afold(h['arabic']) for h in ours]
    assigned = [None] * n
    taken = [False] * m
    tiers = {}

    by_fold = {}
    for j, (_, _, fold, _) in enumerate(cws):
        by_fold.setdefault(fold, []).append(j)
    ours_by_fold = {}
    for i, fold in enumerate(ours_fold):
        ours_by_fold.setdefault(fold, []).append(i)

    # T1 unique on both sides; T2 equal-sized collision groups paired in book order.
    for fold, js in by_fold.items():
        is_ = ours_by_fold.get(fold)
        if not is_ or not fold:
            continue
        if len(is_) == len(js):
            for i, j in zip(sorted(is_), sorted(js)):
                assigned[i], taken[j] = j, True
                tiers[i] = 'T1' if len(js) == 1 else 'T2'

    # T3 English content - exact norm, then the repair proof for still-damaged rows.
    open_is = [i for i in range(n) if assigned[i] is None]
    open_js = [j for j in range(m) if not taken[j]]
    if open_is and open_js:
        by_norm = {}
        for j in open_js:
            eng = cws[j][3]
            if eng.strip():
                by_norm.setdefault(norm(eng), []).append(j)
        donor = Donor('citations', [cws[j][3] for j in open_js if cws[j][3].strip()])
        for i in open_is:
            h = ours[i]
            text = (h['english'].get('text') or '').strip()
            if not text:
                continue
            keys = [norm(h['english'].get('narrator', '') + ' ' + text), norm(text)]
            hit = None
            for key in keys:
                js = [j for j in by_norm.get(key, []) if not taken[j]]
                if len(js) == 1:
                    hit = js[0]
                    break
                if js:
                    hit = None
                    break
                for cand in donor.candidates(key):
                    if provable(cand, key):
                        cjs = [j for j in by_norm.get(norm(cand), []) if not taken[j]]
                        if len(cjs) == 1 and (hit is None or hit == cjs[0]):
                            hit = cjs[0]
                        else:
                            hit = None
                            break
                if hit is not None:
                    break
            if hit is not None:
                assigned[i], taken[hit] = hit, True
                tiers[i] = 'T3'

    # STRUCTURAL GUARD. Both datasets scraped the same sunnah.com pages in page order, so
    # true matches advance together on both sides - in long runs, broken only where
    # upstream moved a whole block (it ships the muqaddimah of Muslim, Ibn Majah, Darimi,
    # and Riyad's introduction at the END of the book; sunnah.com puts it first). A match
    # that sits in no such run is how an anthology's repeated hadith grabs its far twin's
    # number (Riyad repeats dozens of narrations with near-identical text), and a wrong
    # citation is exactly what this tool exists to end. Off-structure matches are
    # unassigned here and recovered positionally below, or left uncited.
    MIN_RUN = 5
    pairs = [(i, a) for i, a in enumerate(assigned) if a is not None]
    run = []
    runs = []
    for p in pairs:
        if run and 0 < p[1] - run[-1][1] <= 4 and p[0] - run[-1][0] <= 4:
            run.append(p)
        else:
            runs.append(run)
            run = [p]
    runs.append(run)
    for run in runs:
        if 0 < len(run) < MIN_RUN:
            for i, a in run:
                assigned[i] = None
                taken[a] = False
                tiers.pop(i, None)

    # T4 positional recovery, to fixpoint: k consecutive open rows whose neighbours are
    # matched to donor rows exactly k+1 apart can only be the k donor rows between them.
    changed = True
    while changed:
        changed = False
        i = 0
        while i < n:
            if assigned[i] is not None:
                i += 1
                continue
            j = i
            while j < n and assigned[j] is None:
                j += 1
            left = assigned[i - 1] if i > 0 else -1
            right = assigned[j] if j < n else m
            k = j - i
            # Position can only interpolate BETWEEN content anchors, never stand alone: a
            # book with no content matches at all must not be assigned wholesale by index.
            if k < n and left is not None and right is not None and right - left == k + 1 \
                    and all(not taken[left + 1 + t] for t in range(k)):
                for t in range(k):
                    assigned[i + t] = left + 1 + t
                    taken[left + 1 + t] = True
                    tiers[i + t] = 'T4'
                changed = True
            i = j

    # T5 folded-prefix nearest neighbour, positional window only. Catches rows whose two
    # scrapes differ by a trailing commentary line while agreeing on the narration itself.
    for i in range(n):
        if assigned[i] is not None:
            continue
        prefix = ours_fold[i][:48]
        if len(prefix) < 48:
            continue
        left = next((assigned[k] for k in range(i - 1, -1, -1) if assigned[k] is not None), -1)
        right = next((assigned[k] for k in range(i + 1, n) if assigned[k] is not None), m)
        cands = [j for j in range(left + 1, right)
                 if not taken[j] and len(cws[j][2]) >= 24
                 and (cws[j][2].startswith(prefix) or prefix.startswith(cws[j][2][:48]))]
        if len(cands) == 1:
            assigned[i], taken[cands[0]] = cands[0], True
            tiers[i] = 'T5'

    return assigned, tiers


# ---------------------------------------------------------------- main

def main():
    argv = sys.argv[1:]
    apply_changes = '--apply' in argv
    root = next((argv[i + 1] for i, a in enumerate(argv) if a == '--donors'), None)
    if not root:
        raise SystemExit(__doc__)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cws_root = os.path.join(root, 'HadithsJSONFormat-main', 'Sunnah')

    print(f"{'book':<22}{'rows':>7}{'cited':>7}{'%':>7}"
          f"{'T1':>7}{'T2':>5}{'T3':>5}{'T4':>5}{'T5':>5}{'unmat':>6}{'inv':>5}{'desc':>5}{'fawaz':>12}")
    total = cited_total = 0
    for slug, (folder, fawaz_edition, cws_dir) in BOOKS.items():
        path = os.path.join(repo, 'db', 'by_book', folder, f'{slug}.json')
        book = json.load(open(path))
        ours = book['hadiths']
        total += len(ours)

        cws_path = os.path.join(cws_root, cws_dir) if cws_dir else None
        if not cws_path or not os.path.isdir(cws_path):
            print(f'{slug:<22}{len(ours):>7,}{"-":>7}')
            continue
        cws = load_cws_rows(slug, cws_path)
        assigned, tiers = match_book(ours, cws)

        counts = {t: 0 for t in ('T1', 'T2', 'T3', 'T4', 'T5')}
        for t in tiers.values():
            counts[t] += 1
        unmatched = sum(1 for a in assigned if a is None)

        # Citations, and the audits that keep them honest. `inv` counts citation-order
        # inversions, which are FEATURES of the standard numbering (Sahih Muslim numbers a
        # repeated narration by identity, so "33c" genuinely sits in Book 5). `desc`
        # counts donor-row-order descents, which after the structural guard should equal
        # the number of moved blocks (0-1 per book) and nothing else.
        cites = [cws[a][1] if a is not None else None for a in assigned]
        seq = [c for c in cites if c]
        inversions = sum(1 for a, b in zip(seq, seq[1:]) if b < a)
        matched_seq = [a for a in assigned if a is not None]
        descents = sum(1 for a, b in zip(matched_seq, matched_seq[1:]) if b < a)

        agree = disagree = fixed = 0
        if fawaz_edition and slug not in ('muslim', 'malik'):
            p = os.path.join(root, 'fawaz', f'{fawaz_edition}.json')
            if os.path.exists(p):
                fw = load_fawaz_numbers(p)
                hits = {}
                for i, h in enumerate(ours):
                    if not cites[i]:
                        continue
                    text = h['english'].get('text') or ''
                    narrator = h['english'].get('narrator') or ''
                    for key in (norm(narrator + ' ' + text), norm(text)):
                        if len(key) >= CROSSCHECK_MIN_NORM and key in fw:
                            hits[i] = next(iter(fw[key]))
                            break
                suspects = {i for i, n in hits.items() if cites[i][0] != n}

                # Where the two donors disagree, the local sequence adjudicates: sunnah.com
                # pages carry occasional typos ("2735" sitting between 2534 and 2536), and
                # the number that fits strictly between the surrounding citations is the
                # printed number readers will actually look up. A fix requires BOTH that
                # the CWS number breaks its own context and that fawaz's fits it - anything
                # less stays donor-verbatim (fawaz has drift of its own).
                def neighbor(i, step):
                    j = i + step
                    while 0 <= j < len(cites):
                        if j not in suspects and cites[j]:
                            return cites[j][0]
                        j += step
                    return None

                for i in sorted(suspects):
                    lo, hi = neighbor(i, -1), neighbor(i, +1)
                    if lo is None or hi is None:
                        continue
                    fits = lambda x: lo < x < hi
                    if not fits(cites[i][0]) and fits(hits[i]):
                        cites[i] = (hits[i], '')
                        fixed += 1
                agree = sum(1 for i, n in hits.items() if cites[i][0] == n)
                disagree = len(hits) - agree
        fawaz_col = f'{agree}/{agree + disagree}' if (agree or disagree) else '-'
        fawaz_col += f' fx{fixed}' if fixed else ''

        cited = sum(1 for c in cites if c)
        cited_total += cited
        print(f'{slug:<22}{len(ours):>7,}{cited:>7,}{cited / len(ours) * 100:>6.1f}%'
              f'{counts["T1"]:>7,}{counts["T2"]:>5}{counts["T3"]:>5}{counts["T4"]:>5}'
              f'{counts["T5"]:>5}{unmatched:>6}{inversions:>5}{descents:>5}{fawaz_col:>12}')

        # The report that started all of this: Jami` at-Tirmidhi 2950 lives at idInBook
        # 3033. If this pairing ever changes, the alignment is broken - fail loudly.
        if slug == 'tirmidhi':
            spot = next(citation_str(c) for h, c in zip(ours, cites) if h['idInBook'] == 3033)
            assert spot == '2950', f'tirmidhi spot check failed: idInBook 3033 -> {spot}'

        if apply_changes:
            for h, cite in zip(ours, cites):
                # Cleared first so a re-run cannot leave a stale citation behind.
                h.pop('citation', None)
                if cite:
                    h['citation'] = citation_str(cite)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(book, ensure_ascii=False))

    print(f"\n{'TOTAL':<22}{total:>7,}{cited_total:>7,}{cited_total / total * 100:>6.1f}%")
    if not apply_changes:
        print('\nDRY RUN - pass --apply to write')


if __name__ == '__main__':
    main()
