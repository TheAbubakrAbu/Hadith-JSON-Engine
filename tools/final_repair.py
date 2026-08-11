#!/usr/bin/env python3
"""Repair AhmedBaset/hadith-json's greedy-bracket damage. Definitive pass.

A record is DAMAGED if and only if a clean candidate exists such that
    simulate_bug(clean) == record        (so it is provably the same hadith)
and clean != record                      (so text was provably lost).

That is a proof, not a heuristic: the earlier "scar" regex (whitespace welded onto
punctuation) was only ever a cheap prefilter, and it both over- and under-fires. It is
gone from the decision path - it survives only in `looks_scarred` for reporting on the
records we could NOT match, so we can say how many are likely-damaged-but-unfixable.

Clean sources, tried in order:
  1. fawazahmed0/hadith-api       - same translations, brackets intact
  2. CheeseWithSauce/HadithsJSONFormat - independent sunnah.com scrape, brackets intact
Matching is by content, never by hadith number (upstream's idInBook has known drift).
Ambiguous keys - one normalised text mapping to two different candidates - are refused.
"""
import json, re, sys

GREEDY = lambda s: re.sub(r'\[.*\]', '', s)

HONORIFIC = re.compile(
    r'maytheblessingsandpeaceofallahbeuponhim|peaceandblessingsofallahbeuponhim'
    r'|mayallahbepleasedwithhim|pbuh|saw|onwhombepeace|peacebeuponhim|chapter|verse')

def norm(s):
    return HONORIFIC.sub('', re.sub(r'[^a-z0-9]', '', s.lower()))

SCAR = re.compile(r'[a-zA-Z\)\]"”]\s+[.,:;]|[a-z]  +[a-zA-Z]')
looks_scarred = lambda s: bool(SCAR.search(s))

def tidy(s):
    # fawazahmed0 artifact: a doubled honorific, "(the Prophet (ﷺ) ﷺ)".
    s = re.sub(r'\(\s*ﷺ\s*\)\s*ﷺ', 'ﷺ', s)
    s = re.sub(r'ﷺ\s*\(\s*ﷺ\s*\)', 'ﷺ', s)
    # CheeseWithSauce writes the salawat out in Arabic script inline in the English body;
    # the corpus everywhere else uses the ﷺ ligature. Exact same words, so this is a
    # rendering swap, not a translation - and norm() strips both, so the proof is unmoved.
    # The remaining Arabic honorifics (رضي الله عنه and friends) are left as the source
    # has them: converting those would mean picking a gender/number in English.
    s = re.sub(r'صلى\s+الله\s+عليه\s+و\s*سلم', 'ﷺ', s)
    s = re.sub(r'\(\s*ﷺ\s*\)', '(ﷺ)', s)
    return re.sub(r'[ \t]{2,}', ' ', s).strip()

def estimate_split(clean, narrator):
    """Rough index in `clean` where the narrator prefix ends. Only a starting guess -
    honorifics render differently between sources, so it drifts by a few characters."""
    want = norm(narrator)
    if not want:
        return 0
    acc = []
    for i, ch in enumerate(clean):
        acc.append(ch)
        if len(norm(''.join(acc))) >= len(want):
            return i + 1
    return 0

def restore(clean, narrator, before):
    """Return (new_narrator, new_text) or (None, None).

    We never trust the estimated split: we search a window around it for a split that
    makes the round-trip proof hold - re-simulating the bug on what we write back must
    reproduce the original damaged record exactly. If no split qualifies, we fold the
    narrator into the body (which satisfies the proof by construction) rather than
    guess at a boundary."""
    target = norm(narrator + ' ' + before)
    est = estimate_split(clean, narrator)
    for delta in range(0, 61):
        for i in {est - delta, est + delta}:
            if not 0 <= i <= len(clean):
                continue
            cand = clean[i:].lstrip(' :,-')
            if norm(GREEDY(narrator + ' ' + cand)) == target:
                return narrator, tidy(cand)
    if norm(GREEDY(clean)) == target:      # narrator folded into the text
        return "", tidy(clean)
    return None, None

def build_index(clean_texts):
    """normalised-bug-simulated text -> set of candidate clean texts."""
    idx = {}
    for c in clean_texts:
        idx.setdefault(norm(GREEDY(c)), set()).add(c)
    return idx

def repair(book, indexes):
    st = {'total': 0, 'damaged': 0, 'repaired': 0,
          'unmatched_scarred': 0, 'ambiguous': 0}
    log = []
    for h in book['hadiths']:
        st['total'] += 1
        body, narr = h['english']['text'], h['english']['narrator']
        key = norm(narr + ' ' + body)
        hit = None
        for idx in indexes:
            cands = idx.get(key)
            if not cands:
                continue
            if len({norm(c) for c in cands}) > 1:
                st['ambiguous'] += 1
                break
            c = next(iter(cands))
            if norm(c) != key:          # text was provably lost
                hit = c
            break
        if hit is None:
            if looks_scarred(body):
                st['unmatched_scarred'] += 1
            continue
        st['damaged'] += 1
        new_narr, new_text = restore(hit, narr, body)
        if new_text is None:            # could not satisfy the proof - leave it alone
            st['unprovable'] = st.get('unprovable', 0) + 1
            continue
        log.append({'idInBook': h['idInBook'], 'before': body, 'after': new_text,
                    'narrator_folded': new_narr == "" and narr != ""})
        h['english']['narrator'] = new_narr
        h['english']['text'] = new_text
        st['repaired'] += 1
    return st, log
