#!/usr/bin/env python3
"""Reference decoder for the `.henc` container -- the executable version of docs/05-hadeethenc.md.

    python3 tools/read_henc.py <pack>.henc                 # summary
    python3 tools/read_henc.py <pack>.henc --id 1751       # one narration, both languages
    python3 tools/read_henc.py <pack>.henc --category 493  # what is filed under a category
    python3 tools/read_henc.py <pack>.henc --verify        # every block decodes, tree is sound

Standard library only, written from the specification rather than from tools/pack/pack_hadeethenc.py.
If this and the document disagree, one of them is a bug. Read it as the answer to "what does a
reader in my language have to do": open the header, keep it, and touch a block only when someone
opens a narration inside it.
"""
import argparse
import json
import lzma
import struct
import sys

MAGIC = b"HENC"
VERSION = 2
HEADER = "<4sHHIIIII"
BLOCK_ROW = "<IIII"
UNIT = "\x1f"

# The full record's fields, in order. Indexes 0 and 1 are the id and the comma-joined category ids.
FULL_FIELDS = ("id", "categories",
               "ar.title", "ar.intro", "ar.body", "ar.explanation", "ar.benefits",
               "ar.attribution", "ar.grade", "ar.reference",
               "en.title", "en.intro", "en.body", "en.explanation", "en.benefits",
               "en.attribution", "en.grade")
LIGHT_FIELDS = ("id", "categories", "en.title", "en.intro", "en.grade", "en.attribution")
TREE_FIELDS = ("id", "parent", "en", "ar", "direct", "total")


def read_table(raw, pos):
    """A string table: `u32 records`, each `u32 fields` then fields of `u32 length` + UTF-8."""
    if pos + 4 > len(raw):
        sys.exit("string table runs past the end of the buffer")
    (count,) = struct.unpack_from("<I", raw, pos)
    pos += 4
    # Bound the count before allocating against it: 8 bytes is the smallest a one-field record can be.
    if count > (len(raw) - pos) // 8 + 1:
        sys.exit(f"string table claims {count} records, the buffer cannot hold that many")
    records = []
    for _ in range(count):
        (fields,) = struct.unpack_from("<I", raw, pos)
        pos += 4
        record = []
        for _ in range(fields):
            (length,) = struct.unpack_from("<I", raw, pos)
            pos += 4
            record.append(raw[pos:pos + length].decode("utf-8"))
            pos += length
        records.append(record)
    return records, pos


class Pack:
    """A mapped `.henc`. The header is read at open; blocks are decompressed on demand and cached."""

    def __init__(self, path):
        self.data = path.read_bytes()
        size = struct.calcsize(HEADER)
        if len(self.data) < size:
            sys.exit(f"{path}: too small to be a pack")
        magic, version, per_block, header_xz, header_raw, blocks, entries, tree = \
            struct.unpack_from(HEADER, self.data, 0)
        if magic != MAGIC:
            sys.exit(f"{path}: magic {magic!r}, expected {MAGIC!r}")
        if version != VERSION:
            sys.exit(f"{path}: version {version}, this reader speaks {VERSION}")
        row = struct.calcsize(BLOCK_ROW)
        if blocks > (len(self.data) - size) // row:
            sys.exit(f"{path}: {blocks} blocks cannot fit in {len(self.data)} bytes")
        self.entriesPerBlock = per_block
        self.blocks = [struct.unpack_from(BLOCK_ROW, self.data, size + i * row) for i in range(blocks)]
        pos = size + blocks * row
        header = lzma.decompress(self.data[pos:pos + header_xz])
        if len(header) != header_raw:
            sys.exit(f"{path}: header inflated to {len(header)}, the head says {header_raw}")
        self.payloadStart = pos + header_xz

        tree_rows, cursor = read_table(header, 0)
        light_rows, _ = read_table(header, cursor)
        if len(tree_rows) != tree or len(light_rows) != entries:
            sys.exit(f"{path}: header holds {len(tree_rows)}/{len(light_rows)}, "
                     f"the head says {tree}/{entries}")
        self.tree = [{"id": r[0], "parent": r[1] or None, "en": r[2], "ar": r[3],
                      "direct": int(r[4]), "total": int(r[5])} for r in tree_rows]
        self.light = [{"id": r[0], "categories": r[1].split(",") if r[1] else [],
                       "title": r[2], "intro": r[3], "grade": r[4], "attribution": r[5]}
                      for r in light_rows]
        self.index = {row["id"]: i for i, row in enumerate(self.light)}
        self._cache = {}

    def block(self, number):
        if number not in self._cache:
            first, offset, compressed, raw_len = self.blocks[number]
            start = self.payloadStart + offset
            raw = lzma.decompress(self.data[start:start + compressed])
            if len(raw) != raw_len:
                sys.exit(f"block {number} inflated to {len(raw)}, the table says {raw_len}")
            rows, _ = read_table(raw, 0)
            self._cache[number] = (first, rows)
        return self._cache[number]

    def narration(self, position):
        """The full record at `position` in the pack's id order."""
        number = position // self.entriesPerBlock
        first, rows = self.block(number)
        row = rows[position - first]
        entry = {"id": row[0], "categories": row[1].split(",") if row[1] else [],
                 "arabic": {}, "english": {}}
        for name, value in zip(FULL_FIELDS[2:], row[2:]):
            language, field = name.split(".")
            target = entry["arabic"] if language == "ar" else entry["english"]
            target[field] = (value.split(UNIT) if value else []) if field == "benefits" else value
        return entry

    def byId(self, hadith_id):
        position = self.index.get(str(hadith_id))
        return None if position is None else self.narration(position)

    def under(self, category, recursive=True):
        """Every narration filed under a category, its subcategories included, without repeats."""
        wanted = {str(category)}
        if recursive:
            children = {}
            for node in self.tree:
                children.setdefault(node["parent"], []).append(node["id"])
            queue = [str(category)]
            while queue:
                node = queue.pop()
                for child in children.get(node, []):
                    if child not in wanted:
                        wanted.add(child)
                        queue.append(child)
        return [row for row in self.light if wanted & set(row["categories"])]


def verify(pack):
    problems = []
    ids = set()
    for position in range(len(pack.light)):
        entry = pack.narration(position)
        light = pack.light[position]
        if entry["id"] != light["id"]:
            problems.append(f"row {position}: block says {entry['id']}, header says {light['id']}")
        if entry["categories"] != light["categories"]:
            problems.append(f"{entry['id']}: categories differ between header and block")
        if entry["english"]["title"] != light["title"]:
            problems.append(f"{entry['id']}: title differs between header and block")
        if not entry["arabic"]["body"]:
            problems.append(f"{entry['id']}: empty Arabic body")
        ids.add(entry["id"])
    known = {node["id"] for node in pack.tree}
    for row in pack.light:
        for category in row["categories"]:
            if category not in known:
                problems.append(f"{row['id']}: category {category} is not in the tree")
    for node in pack.tree:
        if node["parent"] is not None and node["parent"] not in known:
            problems.append(f"category {node['id']}: parent {node['parent']} is not in the tree")
    if len(ids) != len(pack.light):
        problems.append(f"{len(pack.light) - len(ids)} duplicate id(s)")

    roots = [n for n in pack.tree if n["parent"] is None]
    print(f"{len(pack.light)} narrations in {len(pack.blocks)} blocks of {pack.entriesPerBlock}; "
          f"{len(pack.tree)} categories, {len(roots)} roots")
    for node in roots:
        print(f"  {node['id']:>4}  {node['total']:>5}  {node['en']}")
    if problems:
        print(f"\nFAILED: {len(problems)} problem(s)", file=sys.stderr)
        for line in problems[:20]:
            print("  " + line, file=sys.stderr)
        return 1
    print("\nOK")
    return 0


def main():
    import pathlib
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pack", type=pathlib.Path)
    parser.add_argument("--id", help="print one narration")
    parser.add_argument("--category", help="list what is filed under a category")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    pack = Pack(args.pack)
    if args.id:
        entry = pack.byId(args.id)
        if not entry:
            sys.exit(f"{args.id}: not in this pack")
        print(json.dumps(entry, ensure_ascii=False, indent=1))
        return
    if args.category:
        rows = pack.under(args.category)
        node = next((n for n in pack.tree if n["id"] == str(args.category)), None)
        print(f"{node['en'] if node else args.category}: {len(rows)} narration(s)")
        for row in rows[:40]:
            print(f"  {row['id']:>5}  {row['title'][:90]}")
        return
    if args.verify:
        sys.exit(verify(pack))
    print(f"{len(pack.light)} narrations, {len(pack.tree)} categories, "
          f"{len(pack.blocks)} blocks of {pack.entriesPerBlock}")


if __name__ == "__main__":
    main()
