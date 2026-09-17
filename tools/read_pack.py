#!/usr/bin/env python3
"""Reference decoder for the.hpk pack format, the executable version of docs/04-hpk-format.md.

This exists to prove the format is genuinely portable: it was written from the specification
alone, uses nothing but the standard library, and reads the same packs the Swift app ships.
If this file and the spec ever disagree, one of them is a bug.

    python3 tools/read_pack.py <pack.hpk>                 # summary
    python3 tools/read_pack.py <pack.hpk> --hadith 24     # one hadith by idInBook
    python3 tools/read_pack.py <pack.hpk> --chapter 1     # a chapter's hadiths
    python3 tools/read_pack.py <pack.hpk> --verify        # decode every row

Only the DISPLAY text is decoded here. The search payload is LZFSE, which the standard
library cannot decompress; its layout is specified in the doc and is straightforward to add
wherever an LZFSE binding is available.
"""
import lzma, struct, sys

MAGIC = 0x4B504448          # "HDPK"
FORMAT_VERSION = 4          # v3: 20-byte rows with the citation; v4: 4th display string, gradings
LZFSE, LZMA = 1, 2


def _inflate(blob, raw_length):
    """Apple's Compression LZMA output reads as standard XZ; fall back to the alone format."""
    for fmt in (lzma.FORMAT_XZ, lzma.FORMAT_ALONE):
        try:
            out = lzma.decompress(blob, format=fmt)
        except lzma.LZMAError:
            continue
        if len(out) == raw_length:
            return out
        raise ValueError(f'expected {raw_length} bytes, decoded {len(out)}')
    raise ValueError('not decodable as LZMA/XZ (LZFSE sections need a separate codec)')


class _Cursor:
    """Little-endian reader. Nothing in the file is guaranteed to be naturally aligned."""

    def __init__(self, buf, offset=0):
        self.buf, self.i = buf, offset

    def u8(self):
        v = self.buf[self.i]; self.i += 1; return v

    def u16(self):
        v, = struct.unpack_from('<H', self.buf, self.i); self.i += 2; return v

    def u32(self):
        v, = struct.unpack_from('<I', self.buf, self.i); self.i += 4; return v

    def i32(self):
        v, = struct.unpack_from('<i', self.buf, self.i); self.i += 4; return v

    def u64(self):
        v, = struct.unpack_from('<Q', self.buf, self.i); self.i += 8; return v

    def string(self):
        n = self.u32()
        s = self.buf[self.i:self.i + n].decode('utf-8')
        self.i += n
        return s


class Pack:
    """One decoded book. `texts[row]` is (arabic, narrator, text, grades) - grades encoded
    "name\x1fgrade" joined by "\x1e", empty when ungraded."""

    def __init__(self, path):
        data = open(path, 'rb').read()
        if len(data) < 48:
            raise ValueError('too short to hold a header')

        head = _Cursor(data)
        if head.u32() != MAGIC:
            raise ValueError('not an .hpk file (bad magic)')
        self.version = head.u16()
        if self.version != FORMAT_VERSION:
            raise ValueError(f'unsupported format version {self.version}')
        eager_codec, text_codec, self.search_codec = head.u8(), head.u8(), head.u8()
        head.u8()                                   # reserved
        block_count = head.u16()
        head.u32(); head.u32()                      # counts repeated in the eager section
        eager_offset, eager_len, eager_raw = head.u32(), head.u32(), head.u32()
        self.fold_fingerprint = head.u64()
        self.blocked_word_fingerprint = head.u64()

        # Bound the block count by what the file could actually hold before trusting it.
        block_count = min(block_count, max(0, (len(data) - 48) // 28))
        self.blocks = [struct.unpack_from('<7I', data, 48 + i * 28) for i in range(block_count)]

        if eager_codec != LZMA:
            raise ValueError('this reference decoder only handles an LZMA eager section')
        eager = _Cursor(_inflate(data[eager_offset:eager_offset + eager_len], eager_raw))

        self.arabic_title, self.arabic_author = eager.string(), eager.string()
        self.english_title, self.english_author = eager.string(), eager.string()

        self.chapters = []
        for _ in range(eager.u32()):
            cid, first, count = eager.i32(), eager.u32(), eager.u32()
            self.chapters.append({
                'id': cid, 'firstRow': first, 'rowCount': count,
                'arabic': eager.string(), 'english': eager.string(),
                'foldArabic': eager.string(), 'foldEnglish': eager.string(),
            })

        self.rows = []
        for _ in range(eager.u32()):
            row = {'id': eager.u32(), 'idInBook': eager.u32(), 'chapterId': eager.i32()}
            base, suffix = eager.u32(), eager.u8()
            row['citation'] = f'{base}{chr(96 + suffix) if suffix else ""}' if base else None
            row['block'], row['flags'] = eager.u16(), eager.u8()
            self.rows.append(row)

        # Chapters are stored as ranges; a truncated file can point one outside the table.
        for c in self.chapters:
            if not (0 <= c['firstRow'] <= len(self.rows)
                    and 0 <= c['rowCount'] <= len(self.rows) - c['firstRow']):
                c['firstRow'], c['rowCount'] = 0, 0

        if text_codec != LZMA:
            raise ValueError('this reference decoder only handles LZMA display text')
        self.texts = [None] * len(self.rows)
        for first_row, t_off, t_len, t_raw, *_ in self.blocks:
            body = _Cursor(_inflate(data[t_off:t_off + t_len], t_raw))
            row = first_row
            while body.i < len(body.buf):
                self.texts[row] = (body.string(), body.string(), body.string(), body.string())
                row += 1

    DAILY_LENGTH, DAILY_GENTLE = 1 << 0, 1 << 1

    def row_for(self, id_in_book):
        return next((i for i, r in enumerate(self.rows) if r['idInBook'] == id_in_book), None)


def _show(pack, row):
    r, (arabic, narrator, text, grades) = pack.rows[row], pack.texts[row]
    cite = f", citation {r['citation']}" if r['citation'] else ''
    print(f"--- idInBook {r['idInBook']}  (row {row}, chapter {r['chapterId']}, flags {r['flags']}{cite}) ---")
    if arabic:
        print(f'  arabic  : {arabic}')
    if narrator:
        print(f'  narrator: {narrator}')
    print(f'  english : {text or "(no English translation)"}')
    for entry in (g for g in grades.split('\x1e') if g):
        name, _, grade = entry.partition('\x1f')
        print(f'  grade   : {grade}' + (f' ({name})' if name else ''))
    print()


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    pack = Pack(sys.argv[1])
    args = sys.argv[2:]

    print(f'{pack.english_title} / {pack.arabic_title}')
    print(f'  {len(pack.chapters)} chapters, {len(pack.rows)} hadiths, {len(pack.blocks)} blocks')
    print(f'  fold fingerprint {pack.fold_fingerprint:016x}, '
          f'blocked-word fingerprint {pack.blocked_word_fingerprint:016x}\n')

    if '--hadith' in args:
        n = int(args[args.index('--hadith') + 1])
        row = pack.row_for(n)
        if row is None:
            raise SystemExit(f'no hadith with idInBook {n}')
        _show(pack, row)
    elif '--chapter' in args:
        n = int(args[args.index('--chapter') + 1])
        ch = next((c for c in pack.chapters if c['id'] == n), None)
        if ch is None:
            raise SystemExit(f'no chapter {n}')
        print(f"chapter {ch['id']}: {ch['english'] or ch['arabic']} "
              f"({ch['rowCount']} hadiths)\n")
        for row in range(ch['firstRow'], ch['firstRow'] + ch['rowCount']):
            _show(pack, row)
    elif '--verify' in args:
        missing = [i for i, t in enumerate(pack.texts) if t is None]
        covered = sum(c['rowCount'] for c in pack.chapters)
        print(f'rows decoded      : {len(pack.rows) - len(missing)}/{len(pack.rows)}')
        print(f'chapter coverage  : {covered}/{len(pack.rows)}')
        daily = sum(1 for r in pack.rows
                    if r['flags'] & Pack.DAILY_LENGTH and r['flags'] & Pack.DAILY_GENTLE)
        print(f'daily candidates  : {daily}')
        cited = sum(1 for r in pack.rows if r['citation'])
        print(f'cited rows        : {cited}/{len(pack.rows)}')
        graded = sum(1 for t in pack.texts if t and t[3])
        print(f'graded rows       : {graded}/{len(pack.rows)}')
        print('OK' if not missing and covered == len(pack.rows) else 'FAILED')


if __name__ == '__main__':
    main()
