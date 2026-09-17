#!/usr/bin/env python3
"""The gate: prove the shipped packs are EXACTLY the JSON in db/by_book, and that every
specification in this repository still describes them.

`read_pack.py --verify` proves a pack decodes. That is a much weaker claim than the one that
matters, which is that the pack and the JSON say the same thing, a packer bug, a stale rebuild, or
an edited JSON that was never repacked all decode perfectly and all ship the wrong text. This tool
re-derives every byte of a pack from its source and compares:

    metadata      the four title/author strings
    chapters      id, display text, search folds, and the row range each one owns
    rows          id, idInBook, chapterId, citation, block index, both daily flags
    display text  arabic, narrator, text, grades, all four strings of all 50,884 hadiths
    folds         recomputed with tools/fold.py, and the fold fingerprint in every header
    manifest      sha256, byte size, and the shape counts of all 17 packs
    catalog       db/catalog.json against the corpus it describes
    conformance   every vector in conformance/vectors.json

    python3 tools/verify_packs.py                      # packs in ../Al-Islam-iOS (build.sh's default)
    python3 tools/verify_packs.py <packs-dir>
    python3 tools/verify_packs.py <packs-dir> --quiet   # only the summary and failures

Standard library only, no Apple frameworks, no third-party packages: it runs anywhere Python does,
so a port can use it as its own acceptance test. Exit status is 0 only if every check passed.

The one thing it cannot read is the SEARCH payload, which ships LZFSE (the standard library has no
decoder). Rebuild with HPK_SEARCH=2 and this tool verifies those folds too; the chapter folds, which
ride in the LZMA eager section, are always checked. See docs/PORTING.md.
"""
import hashlib
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fold                                          # noqa: E402
from read_pack import Pack, _inflate, _Cursor        # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The books, in the order pack-hadith.swift packs them.
BOOKS = [
    ('bukhari', 'the_9_books'), ('muslim', 'the_9_books'), ('ibnmajah', 'the_9_books'),
    ('abudawud', 'the_9_books'), ('tirmidhi', 'the_9_books'), ('nasai', 'the_9_books'),
    ('malik', 'the_9_books'), ('ahmed', 'the_9_books'), ('darimi', 'the_9_books'),
    ('qudsi40', 'forties'), ('nawawi40', 'forties'), ('shahwaliullah40', 'forties'),
    ('aladab_almufrad', 'other_books'), ('shamail_muhammadiyah', 'other_books'),
    ('riyad_assalihin', 'other_books'), ('mishkat_almasabih', 'other_books'),
    ('bulugh_almaram', 'other_books'),
]

DAILY_MAX_CHARACTERS = 220          # dailyMaxCharacters in pack-hadith.swift
DAILY_LENGTH, DAILY_GENTLE = 1 << 0, 1 << 1
LZFSE, LZMA = 1, 2

# Swift's.whitespacesAndNewlines, for trimmingCharacters: the same set tools/fold.py defines.
_TRIM = ''.join(fold._WHITESPACE)
# Swift's .whitespaces (Zs + TAB), which is what the grades trim uses. Newlines are NOT in it.
_TRIM_SPACES = ''.join(c for c in _TRIM if c not in '\n\x0b\x0c\r\x85  ')


class Report:
    """Collects failures instead of raising, so one run tells you everything that is wrong."""

    def __init__(self, quiet=False):
        self.failures = []
        self.checks = 0
        self.quiet = quiet
        self.notes = []

    def check(self, ok, label, detail=''):
        self.checks += 1
        if not ok:
            self.failures.append(f'{label}{": " + detail if detail else ""}')
        return ok

    def equal(self, want, got, label):
        return self.check(want == got, label, f'expected {_brief(want)}, found {_brief(got)}')

    def note(self, text):
        self.notes.append(text)

    def say(self, text):
        if not self.quiet:
            print(text)


def _brief(value):
    text = repr(value)
    return text if len(text) <= 100 else text[:97] + '...'


# --- Ports of the packer's own transforms ------------------------------------------------------

def cleaned_hadith_text(s):
    """String.cleanedHadithText in tools/pack/pack-hadith.swift, scalar for scalar.

    Deliberate paragraph breaks survive as one "\\n\\n"; every other whitespace run collapses to a
    single space. Note the guard: a string with none of the trigger characters is returned
  UNCHANGED (it is not even trimmed), and a port that trims unconditionally will differ.
    """
    if not ('\n' in s or '  ' in s or '\t' in s or '\r' in s or ' ' in s):
        return s
    import re
    t = s.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ').replace(' ', ' ')
    t = re.sub(r'[ ]*\n[ ]*', '\n', t)
    t = re.sub(r'\n{2,}', ' ', t)
    t = t.replace('\n', ' ')
    t = re.sub(r' {2,}', ' ', t)
    t = re.sub(r' ?  ?', '\n\n', t)
    return t.strip(_TRIM)


def normalized_chapter_id(raw):
    """Fractional chapter ids map to a stable synthetic integer, truncating would collide with 8."""
    return int(raw) if raw == int(raw) else 1000 + round(raw * 10)


def chapter_id(value):
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return normalized_chapter_id(value)
    if isinstance(value, str):
        try:
            return normalized_chapter_id(float(value))
        except ValueError:
            return 0
    return 0


def swift_character_count(s):
    """Swift's String.count is grapheme clusters, not code points.

    The packer's daily-length gate is written against it. Dropping combining marks reproduces it for
    every string in this corpus (verified across all 50,884 records); it is an approximation only in
    the sense that an exotic emoji sequence would need full UAX #29 segmentation.
    """
    return sum(1 for ch in s if not unicodedata.combining(ch))


def encoded_grades(entries):
    """The 4th display string: "name U+001F grade" records joined by U+001E, empty when ungraded."""
    out = []
    for g in entries or []:
        grade = (g.get('grade') or '').strip(_TRIM_SPACES)
        if not grade:
            continue
        out.append((g.get('name') or '').strip(_TRIM_SPACES) + '' + grade)
    return ''.join(out)


def citation_parts(citation):
    """"2950" -> (2950, 0); "8a" -> (8, 1). (0, 0) means no standard number exists."""
    if not citation:
        return 0, 0
    suffix = 0
    digits = citation
    if citation[-1].isalpha():
        suffix = ord(citation[-1].lower()) - 96
        digits = citation[:-1]
    return int(digits), suffix


# --- Search payload (only readable when the pack was built with an LZMA search section) ---------

def search_folds(path, pack):
    """Decode every block's search payload into per-row (arabic, english) folds.

    Returns None when the payload is LZFSE, which the standard library cannot decompress.
    """
    if pack.search_codec != LZMA:
        return None
    data = open(path, 'rb').read()
    folds = [None] * len(pack.rows)
    for first_row, _t_off, _t_len, _t_raw, s_off, s_len, s_raw in pack.blocks:
        body = _Cursor(_inflate(data[s_off:s_off + s_len], s_raw))
        count = body.u32()
        body.u32()                                   # arabic section length
        arabic_lengths = [body.u32() for _ in range(count)]
        english_lengths = [body.u32() for _ in range(count)]
        buf = body.buf
        cursor = body.i
        arabic = []
        for n in arabic_lengths:
            arabic.append(buf[cursor:cursor + n].decode('utf-8'))
            cursor += n + 1                          # each record is NUL-terminated
        english = []
        for n in english_lengths:
            english.append(buf[cursor:cursor + n].decode('utf-8'))
            cursor += n + 1
        for i in range(count):
            folds[first_row + i] = (arabic[i], english[i])
    return folds


# --- Per-book verification ---------------------------------------------------------------------

def verify_book(slug, folder, packs_dir, report):
    source_path = os.path.join(REPO, 'db', 'by_book', folder, f'{slug}.json')
    pack_path = os.path.join(packs_dir, f'{slug}.hpk')
    if not report.check(os.path.exists(pack_path), f'{slug}: pack missing', pack_path):
        return None
    src = json.load(open(source_path, encoding='utf-8'))
    pack = Pack(pack_path)

    def label(what):
        return f'{slug}: {what}'

    # --- metadata: the four eager strings, verbatim from the JSON ---
    arabic_meta = src['metadata'].get('arabic') or {}
    english_meta = src['metadata'].get('english') or {}
    report.equal(arabic_meta.get('title', ''), pack.arabic_title, label('metadata.arabic.title'))
    report.equal(arabic_meta.get('author', ''), pack.arabic_author, label('metadata.arabic.author'))
    report.equal(english_meta.get('title', ''), pack.english_title, label('metadata.english.title'))
    report.equal(english_meta.get('author', ''), pack.english_author, label('metadata.english.author'))

    # --- fingerprints stamped into the header ---
    report.equal(fold.fold_fingerprint(), pack.fold_fingerprint, label('foldFingerprint'))

    hadiths = src['hadiths']
    report.equal(len(hadiths), len(pack.rows), label('hadith count'))

    # --- the row table and all four display strings ---
    folds = search_folds(pack_path, pack)
    block_of_row = {}
    for index, (first_row, *_rest) in enumerate(pack.blocks):
        upper = pack.blocks[index + 1][0] if index + 1 < len(pack.blocks) else len(pack.rows)
        for row in range(first_row, upper):
            block_of_row[row] = index

    for row, h in enumerate(hadiths):
        if row >= len(pack.rows):
            break
        pr, pt = pack.rows[row], pack.texts[row]
        where = label(f'row {row} (idInBook {h.get("idInBook")})')
        if not report.check(pt is not None, where + ' display text', 'row is in no block'):
            continue

        english_block = h.get('english') or {}
        want = (
            cleaned_hadith_text(h.get('arabic') or ''),
            cleaned_hadith_text(english_block.get('narrator') or ''),
            cleaned_hadith_text(english_block.get('text') or ''),
            encoded_grades(english_block.get('grades')),
        )
        for i, field in enumerate(('arabic', 'narrator', 'text', 'grades')):
            report.equal(want[i], pt[i], f'{where} {field}')

        report.equal(h.get('id') or 0, pr['id'], f'{where} id')
        report.equal(h.get('idInBook') or 0, pr['idInBook'], f'{where} idInBook')
        report.equal(chapter_id(h.get('chapterId')), pr['chapterId'], f'{where} chapterId')
        report.equal(h.get('citation') or None, pr['citation'], f'{where} citation')
        base, suffix = citation_parts(h.get('citation'))
        report.check(base == 0 or 0 <= suffix <= 26, f'{where} citation suffix out of a-z', str(suffix))
        report.equal(block_of_row.get(row), pr['block'], f'{where} block index')

        # Daily-card flags, both halves, recomputed from the cleaned text.
        length_ok = (swift_character_count(want[0]) <= DAILY_MAX_CHARACTERS
                     and swift_character_count(want[2]) <= DAILY_MAX_CHARACTERS
                     and want[2] != '')
        report.equal(length_ok, bool(pr['flags'] & DAILY_LENGTH), f'{where} flag dailyLength')

        if folds is not None and folds[row] is not None:
            report.equal(fold.arabic(want[0]), folds[row][0], f'{where} arabic search fold')
            report.equal(fold.english(want[2] + '\n' + want[1]), folds[row][1], f'{where} english search fold')

    # --- chapters: contiguity, coverage, display text, and the folds that ride in the eager section ---
    runs, order = {}, []
    for row, h in enumerate(hadiths):
        cid = chapter_id(h.get('chapterId'))
        if cid in runs:
            first, count = runs[cid]
            report.check(first + count == row, label(f'chapter {cid} is not contiguous'),
                         f'row {row} follows a run ending at {first + count - 1}')
            runs[cid] = (first, count + 1)
        else:
            runs[cid] = (row, 1)
            order.append(cid)

    chapters = src['chapters']
    report.equal(len(chapters), len(pack.chapters), label('chapter count'))
    for i, c in enumerate(chapters):
        if i >= len(pack.chapters):
            break
        pc = pack.chapters[i]
        cid = chapter_id(c.get('id'))
        if not report.equal(cid, pc['id'], label(f'chapter index {i} id')):
            continue
        want_arabic = cleaned_hadith_text(c.get('arabic') or '')
        want_english = cleaned_hadith_text(c.get('english') or '')
        report.equal(want_arabic, pc['arabic'], label(f'chapter {cid} arabic'))
        report.equal(want_english, pc['english'], label(f'chapter {cid} english'))
        report.equal(fold.arabic(want_arabic), pc['foldArabic'], label(f'chapter {cid} arabic fold'))
        report.equal(fold.english(want_english), pc['foldEnglish'], label(f'chapter {cid} english fold'))
        if report.check(cid in runs, label(f'chapter {cid} has no hadiths')):
            first, count = runs[cid]
            report.equal((first, count), (pc['firstRow'], pc['rowCount']), label(f'chapter {cid} row range'))
            report.check(count > 0, label(f'chapter {cid} is empty'))

    covered = sum(c['rowCount'] for c in pack.chapters)
    report.check(covered == len(pack.rows), label('chapter coverage'),
                 f'{covered} rows covered of {len(pack.rows)}')

    graded = sum(1 for t in pack.texts if t and t[3])
    cited = sum(1 for r in pack.rows if r['citation'])
    with_english = sum(1 for t in pack.texts if t and t[2])
    report.say(f'  {slug:22} {len(pack.rows):5} hadiths  {len(pack.chapters):3} chapters  '
               f'{cited:5} cited  {graded:5} graded  {len(pack.blocks):3} blocks'
               + ('  folds ✓' if folds is not None else '  folds: LZFSE, skipped'))
    return {
        'slug': slug, 'folder': folder, 'pack': pack, 'path': pack_path,
        'hadiths': len(pack.rows), 'chapters': len(pack.chapters),
        'cited': cited, 'graded': graded, 'withEnglish': with_english,
        'foldsChecked': folds is not None,
    }


# --- Repository-wide checks ---------------------------------------------------------------------

def verify_blocked_words(packs, report):
    path = os.path.join(REPO, 'tools', 'pack', 'daily-blocked-words.txt')
    words = set()
    for line in open(path, encoding='utf-8'):
        text = line.strip()
        if text and not text.startswith('#'):
            words.add(text.lower())
    expected = fold.word_list_fingerprint(words)
    for book in packs:
        report.equal(expected, book['pack'].blocked_word_fingerprint,
                     f'{book["slug"]}: blockedWordFingerprint')
    return words, expected


def verify_manifest(packs, packs_dir, report):
    path = os.path.join(packs_dir, 'manifest.json')
    if not report.check(os.path.exists(path), 'manifest.json missing', path):
        return
    manifest = json.load(open(path, encoding='utf-8'))
    by_slug = {b['slug']: b for b in manifest['books']}
    report.equal(4, manifest.get('formatVersion'), 'manifest formatVersion')
    report.equal(f'{fold.fold_fingerprint():016x}', manifest.get('foldFingerprint'),
                 'manifest foldFingerprint')
    report.equal(len(packs), len(manifest['books']), 'manifest book count')

    for book in packs:
        entry = by_slug.get(book['slug'])
        if not report.check(entry is not None, f'manifest: {book["slug"]} not listed'):
            continue
        raw = open(book['path'], 'rb').read()
        report.equal(hashlib.sha256(raw).hexdigest(), entry['sha256'], f'manifest {book["slug"]} sha256')
        report.equal(len(raw), entry['bytes'], f'manifest {book["slug"]} bytes')
        report.equal(book['hadiths'], entry['hadiths'], f'manifest {book["slug"]} hadiths')
        report.equal(book['chapters'], entry['chapters'], f'manifest {book["slug"]} chapters')
        source = os.path.join(REPO, 'db', 'by_book', book['folder'], f'{book["slug"]}.json')
        report.equal(os.path.getsize(source), entry['sourceBytes'],
                     f'manifest {book["slug"]} sourceBytes (JSON changed without a repack?)')
        daily = sum(1 for r in book['pack'].rows
                    if r['flags'] & DAILY_LENGTH and r['flags'] & DAILY_GENTLE)
        report.equal(daily, entry['dailyCandidates'], f'manifest {book["slug"]} dailyCandidates')

    report.equal(sum(b['hadiths'] for b in packs), manifest.get('totalHadiths'), 'manifest totalHadiths')
    report.equal(sum(b['chapters'] for b in packs), manifest.get('totalChapters'), 'manifest totalChapters')


def verify_catalog(packs, report):
    path = os.path.join(REPO, 'db', 'catalog.json')
    if not report.check(os.path.exists(path), 'db/catalog.json missing', path):
        return
    catalog = json.load(open(path, encoding='utf-8'))
    entries = catalog['books']
    report.equal([b['slug'] for b in packs], [e['slug'] for e in entries],
                 'catalog: slugs and their order must match the corpus')

    groups = {g['key'] for g in catalog['groups']}
    by_slug = {b['slug']: b for b in packs}
    seen_aliases = {}
    for i, entry in enumerate(entries):
        slug = entry['slug']
        where = f'catalog {slug}'
        report.equal(i + 1, entry['number'], f'{where}: number')
        report.check(entry['group'] in groups, f'{where}: unknown group', entry['group'])
        book = by_slug.get(slug)
        if book:
            report.equal(book['folder'], entry['folder'], f'{where}: folder')
            report.equal(book['hadiths'], entry['hadiths'], f'{where}: hadith count')
            report.equal(book['chapters'], entry['chapters'], f'{where}: chapter count')
        for field in ('englishTitle', 'arabicTitle', 'authorEnglish', 'authorArabic', 'era',
                      'shortDescription', 'longDescription'):
            report.check(bool(entry.get(field)), f'{where}: {field} is empty')
        report.check(bool(entry['aliases']), f'{where}: has no aliases')
        for alias in entry['aliases']:
            report.check(alias == alias.lower() and alias.isalnum(),
                         f'{where}: alias {alias!r} is not lowercase alphanumeric')
            owner = seen_aliases.setdefault(alias, slug)
            report.check(owner == slug, f'catalog: alias {alias!r} is claimed by two books',
                         f'{owner} and {slug}')


def verify_app_catalog(app_dir, report):
    """Cross-check db/catalog.json against the consuming app's Swift copy of the same facts.

    The app compiles its catalog rather than parsing JSON at launch, which is the right call for it
    and means the same facts exist twice. This is the alarm if they drift - the same role the fold
    fingerprint plays for the search fold. Skipped, not failed, when the app is not checked out.
    """
    swift_path = os.path.join(app_dir, 'iPhone', 'Hadith', 'HadithModels.swift')
    if not os.path.exists(swift_path):
        report.note(f'app catalog: not checked (no app at {app_dir})')
        return
    import re

    source = open(swift_path, encoding='utf-8').read()
    start = source.find('static let all: [HadithCatalogBook] = [')
    if not report.check(start >= 0, 'app catalog: HadithCatalogBook.all not found', swift_path):
        return
    body = source[start:source.index('\n    ]\n', start)]

    def unescape(literal):
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

    entries = []
    for chunk in re.findall(r'HadithCatalogBook\(\s*\n(.*?)\n\s*\),?\n', body + '\n', re.S):
        def field(name, text=chunk):
            m = re.search(name + r':\s*"((?:[^"\\]|\\.)*)"', text)
            return unescape(m.group(1)) if m else None
        aliases_match = re.search(r'aliases:\s*\[(.*?)\]', chunk, re.S)
        entries.append({
            'slug': field('slug'),
            'group': re.search(r'group:\s*\.(\w+)', chunk).group(1),
            'englishTitle': field('englishTitle'), 'arabicTitle': field('arabicTitle'),
            'authorEnglish': field('authorEnglish'), 'authorArabic': field('authorArabic'),
            'era': field('era'), 'shortDescription': field('shortDescription'),
            'longDescription': field('longDescription'),
            'aliases': [unescape(a) for a in
                        re.findall(r'"((?:[^"\\]|\\.)*)"', aliases_match.group(1))],
        })

    catalog = json.load(open(os.path.join(REPO, 'db', 'catalog.json'), encoding='utf-8'))['books']
    if not report.equal([b['slug'] for b in catalog], [e['slug'] for e in entries],
                        'app catalog: books and their order'):
        return
    for want, got in zip(catalog, entries):
        for field_name in ('group', 'englishTitle', 'arabicTitle', 'authorEnglish', 'authorArabic',
                           'era', 'shortDescription', 'longDescription', 'aliases'):
            report.equal(want[field_name], got[field_name],
                         f'app catalog: {want["slug"]}.{field_name} has drifted from db/catalog.json')
    report.note(f'app catalog: {len(entries)} books cross-checked against {swift_path}')


def verify_conformance(packs, report):
    path = os.path.join(REPO, 'conformance', 'vectors.json')
    if not report.check(os.path.exists(path), 'conformance/vectors.json missing', path):
        return
    vectors = json.load(open(path, encoding='utf-8'))
    by_slug = {b['slug']: b for b in packs}

    corpus = vectors['corpus']
    report.equal(corpus['books'], len(packs), 'vectors corpus.books')
    report.equal(corpus['hadiths'], sum(b['hadiths'] for b in packs), 'vectors corpus.hadiths')
    report.equal(corpus['chapters'], sum(b['chapters'] for b in packs), 'vectors corpus.chapters')
    report.equal(corpus['graded'], sum(b['graded'] for b in packs), 'vectors corpus.graded')
    report.equal(corpus['cited'], sum(b['cited'] for b in packs), 'vectors corpus.cited')

    for want in vectors['books']:
        book = by_slug.get(want['slug'])
        if not report.check(book is not None, f'vectors: unknown book {want["slug"]}'):
            continue
        for field in ('folder', 'hadiths', 'chapters', 'withEnglish', 'graded', 'cited'):
            report.equal(want[field], book[field], f'vectors {want["slug"]}.{field}')

    def row_text(slug, id_in_book):
        book = by_slug.get(slug)
        if book is None:
            return None
        row = book['pack'].row_for(id_in_book)
        return None if row is None else book['pack'].texts[row]

    for case in vectors['repairedRecords']['cases']:
        text = row_text(case['book'], case['idInBook'])
        if report.check(text is not None, f'vectors repaired: {case["book"]} {case["idInBook"]} missing'):
            report.equal(case['englishText'], text[2],
                         f'vectors repaired: {case["book"]} {case["idInBook"]} (stale or unrepaired data)')

    for case in vectors['mustContain']['cases']:
        text = row_text(case['book'], case['idInBook'])
        if report.check(text is not None, f'vectors mustContain: {case["book"]} {case["idInBook"]} missing'):
            for substring in case['substrings']:
                report.check(substring in text[2],
                             f'vectors mustContain: {case["book"]} {case["idInBook"]}',
                             f'{substring!r} was lost again')

    for case in vectors['emptyEnglish']['cases']:
        book = by_slug.get(case['book'])
        if report.check(book is not None, f'vectors emptyEnglish: unknown book {case["book"]}'):
            empty = sum(1 for t in book['pack'].texts if t and not t[2])
            report.equal(case['expectEmptyCount'], empty, f'vectors emptyEnglish: {case["book"]}')

    for case in vectors['chapterIdMapping']['cases']:
        report.equal(case['expected'], chapter_id(float(case['input'])),
                     f'vectors chapterIdMapping: {case["input"]}')

    pack_format = vectors['packFormat']
    report.equal(f'{fold.fold_fingerprint():016x}', pack_format['foldFingerprint'],
                 'vectors packFormat.foldFingerprint')
    for book in packs:
        report.equal(pack_format['formatVersion'], book['pack'].version,
                     f'vectors packFormat.formatVersion ({book["slug"]})')
        report.equal(int(pack_format['blockedWordFingerprint'], 16),
                     book['pack'].blocked_word_fingerprint,
                     f'vectors packFormat.blockedWordFingerprint ({book["slug"]})')

    for case in vectors['citations']['spot']:
        book = by_slug.get(case['slug'])
        if not report.check(book is not None, f'vectors citations: unknown book {case["slug"]}'):
            continue
        row = book['pack'].row_for(case['idInBook'])
        if report.check(row is not None,
                        f'vectors citations: {case["slug"]} idInBook {case["idInBook"]} missing'):
            report.equal(case['citation'], book['pack'].rows[row]['citation'],
                         f'vectors citations: {case["slug"]} {case["idInBook"]}')


# --- Main ---------------------------------------------------------------------------------------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    quiet = '--quiet' in sys.argv
    app_dir = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--app=')),
                   os.path.join(os.path.dirname(REPO), 'Al-Islam-iOS'))
    default = os.path.join(app_dir, 'Resources', 'Data', 'Hadith')
    packs_dir = args[0] if args else default
    if not os.path.isdir(packs_dir):
        raise SystemExit(f'error: no pack directory at {packs_dir}\n'
                         f'usage: python3 tools/verify_packs.py [packs-dir] [--app=<path>] [--quiet]')

    report = Report(quiet=quiet)
    report.say(f'verifying {packs_dir}\n')
    packs = []
    for slug, folder in BOOKS:
        book = verify_book(slug, folder, packs_dir, report)
        if book:
            packs.append(book)

    report.say('')
    verify_blocked_words(packs, report)
    verify_manifest(packs, packs_dir, report)
    verify_catalog(packs, report)
    verify_app_catalog(app_dir, report)
    verify_conformance(packs, report)

    total_hadiths = sum(b['hadiths'] for b in packs)
    total_chapters = sum(b['chapters'] for b in packs)
    skipped = [b['slug'] for b in packs if not b['foldsChecked']]
    for note in report.notes:
        print(note)
    print(f'{len(packs)} books, {total_hadiths} hadiths, {total_chapters} chapters, '
          f'{report.checks} assertions')
    if skipped:
        print(f'search folds: not checked (LZFSE payload; rebuild with HPK_SEARCH=2 to include them) '
              f'- {len(skipped)} books. Chapter folds were checked in every book.')

    if report.failures:
        print(f'\nFAILED - {len(report.failures)} problems:')
        for failure in report.failures[:80]:
            print(f'  {failure}')
        if len(report.failures) > 80:
            print(f'  ... and {len(report.failures) - 80} more')
        return 1
    print('\nOK - every pack is exactly the JSON it was built from, and every specification '
          'in this repository still describes it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
