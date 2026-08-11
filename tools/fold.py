#!/usr/bin/env python3
"""The search fold, in portable Python — the cross-platform twin of tools/pack/HadithFold.swift.

The packs ship text that was folded at BUILD time by the Swift fold. A query only ever finds that
text if it folds through the exact same rules, so any port has to agree with the packer scalar for
scalar. `fold_fingerprint()` is how you prove it did: the packer stamps its own value into every
pack, and this module recomputes it from the same probes. If the two agree, this port is correct on
every rule the fold has — the probes are chosen to exercise all of them.

    python3 tools/fold.py                      # print the fingerprints
    python3 tools/fold.py "الصلاة خير من النوم"  # fold one string both ways

Nothing here is Apple-specific and nothing is imported beyond the standard library, so this is the
file to translate when porting the engine to a new language. See docs/PORTING.md.
"""
import sys
import unicodedata

# --- Character classes -------------------------------------------------------------------------
# Swift's CharacterSet.punctuationCharacters is Unicode category P*, .symbols is S*, and
# .nonBaseCharacters is M* (the combining marks). Categories, not code point lists, so this stays
# correct as Unicode grows — exactly as the Swift original does.


def _is_punct_symbol_or_mark(ch):
    return unicodedata.category(ch)[0] in ('P', 'S', 'M')


# The boolean-search operators the query parser owns are never stripped from Arabic.
_KEPT_OPERATORS = frozenset('&|!#')

# Canonical Arabic search folds: hamza carriers to bare letters, dagger alif to alif, alif maqsurah
# to alif, teh marbuta to heh. None means "drop this scalar".
_CANONICAL = {
    0x0670: 0x0627,   # dagger alif -> alif
    0x0671: 0x0627,   # hamzatul-wasl -> alif
    0x0623: 0x0627,   # أ
    0x0625: 0x0627,   # إ
    0x0622: 0x0627,   # آ
    0x0672: 0x0627,   # ٲ
    0x0673: 0x0627,   # ٳ
    0x0675: 0x0627,   # ٵ
    0x0624: 0x0648,   # ؤ -> و
    0x0626: 0x064A,   # ئ -> ي
    0x0621: None,     # bare hamza - dropped
    0x0674: None,     # high hamza - dropped
    0x0676: 0x0648,   # ٶ -> و
    0x0677: 0x0648,   # ٷ -> و
    0x0678: 0x064A,   # ٸ -> ي
    0x06E5: 0x0648,   # ۥ -> و
    0x06E6: 0x064A,   # ۦ -> ي
    0x0649: 0x0627,   # alif maqsurah -> alif
    0x0629: 0x0647,   # teh marbuta -> heh
}

# Tashkeel, Quranic annotation signs, and the loose marks.
_STRIP = (frozenset(range(0x064B, 0x0660)) | frozenset(range(0x06D6, 0x06EE))
          | frozenset((0x0670, 0x0657, 0x0674, 0x0656)))

# Swift's CharacterSet.whitespacesAndNewlines, exactly: .whitespaces is Unicode category Zs plus
# TAB, and .newlines is U+000A...U+000D, U+0085, U+2028, U+2029. Nothing else - the C0 separators
# U+001C...U+001F are NOT in it, and folding on them would split text the packer left whole.
_WHITESPACE = frozenset(
    '\t\n\x0b\x0c\r\x85\u2028\u2029'                      # newlines
    ' \xa0\u1680\u202f\u205f\u3000'                        # Zs, the singletons
    + ''.join(chr(c) for c in range(0x2000, 0x200B))       # Zs, the en/em quad block
)


# --- The folds ---------------------------------------------------------------------------------

def english(text):
    """Strip punctuation, symbols, and combining marks, then lowercase.

    No whitespace collapsing: the app's highlighter twin doesn't collapse either, and a query folded
    the same way lines up with it.
    """
    return ''.join(c for c in text if not _is_punct_symbol_or_mark(c)).lower()


def arabic(text):
    """Canonical letter folds and whitespace collapsing, then the diacritic and sign strip.

    In that order — the second pass reads what the first one produced.
    """
    built = []
    for ch in text:
        code = ord(ch)
        if code in _CANONICAL:
            mapped = _CANONICAL[code]
            if mapped is None:
                continue
            built.append(chr(mapped))
        elif not _is_punct_symbol_or_mark(ch) or ch in _KEPT_OPERATORS:
            built.append(ch)

    collapsed = ' '.join(
        part for part in _split_whitespace(''.join(built).lower()) if part
    )

    out = []
    for ch in collapsed:
        code = ord(ch)
        if code == 0x0671:
            out.append('ا')
        elif code not in _STRIP:
            out.append(ch)
    return ''.join(out)


def _split_whitespace(text):
    parts, current = [], []
    for ch in text:
        if ch in _WHITESPACE:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
    parts.append(''.join(current))
    return parts


def is_arabic_script(text):
    """Whether the text carries Arabic script — which fold a query gets, and which field it can match."""
    return any(0x0600 <= ord(c) <= 0x06FF or 0x0750 <= ord(c) <= 0x077F
               or 0x08A0 <= ord(c) <= 0x08FF for c in text)


def query(raw):
    """Fold a raw query the way its script demands. Returns (folded_utf8_bytes, is_arabic, folded)."""
    trimmed = raw.strip(''.join(_WHITESPACE))
    is_ar = is_arabic_script(trimmed)
    folded = arabic(trimmed) if is_ar else english(trimmed)
    return folded.encode('utf-8'), is_ar, folded


# --- Fingerprints ------------------------------------------------------------------------------

def fingerprint(text):
    """FNV-1a, 64-bit — deliberately not a seeded hash, which would differ between processes."""
    h = 0xcbf29ce484222325
    for byte in text.encode('utf-8'):
        h ^= byte
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h


# Strings chosen to exercise every rule above: hamza carriers, dagger alif, alif maqsurah, teh
# marbuta, tashkeel, Quranic signs, the salawat ligature, apostrophes, punctuation, digits, and
# whitespace collapsing. Change a fold rule and at least one of these changes with it.
PROBES = [
    "إنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ",
    "قَالَ رَسُولُ اللَّهِ ﷺ",
    "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ",
    "الصَّلَاةُ خَيْرٌ مِنَ النَّوْمِ",
    "أَبُو هُرَيْرَةَ، ؤ، ئ، ء، ٱ، ى، ة، ٰ",
    "مَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الْآخِرِ",
    "Narrated 'A'ishah (may Allah be pleased with her):",
    'The Messenger of Allah (ﷺ) said: "Actions are (judged) by motives (niyyah)"',
    "Mu'adh ibn Jabal - [of His] - Abu Dawud 1:23",
    "  doubled   spaces\tand\ttabs\nand\nnewlines  ",
    "MiXeD CaSe, punctuation!? and symbols +=%$#@ and digits 0123456789",
    "",
]


def fold_fingerprint():
    """One value standing for the whole fold: every probe through BOTH folds, hashed.

    Must equal the value stamped in every pack header (and packFormat.foldFingerprint in
    conformance/vectors.json). If it doesn't, this port and the packer disagree somewhere.
    """
    joined = ''.join(arabic(p) + '\u0001' + english(p) + '\u0002' for p in PROBES)
    return fingerprint(joined)


def word_list_fingerprint(words):
    """Order-independent fingerprint of a blocked-word list — content has to match, not order."""
    return fingerprint('\n'.join(sorted(w.lower() for w in words)))


def main():
    if len(sys.argv) > 1:
        for raw in sys.argv[1:]:
            print(f'input   : {raw!r}')
            print(f'  arabic : {arabic(raw)!r}')
            print(f'  english: {english(raw)!r}')
            print(f'  script : {"arabic" if is_arabic_script(raw) else "latin"}')
        return
    print(f'fold fingerprint: {fold_fingerprint():016x}')


if __name__ == '__main__':
    main()
