#!/usr/bin/env python3
"""Build HadeethEnc.henc from db/hadeethenc/ -- the Hadith Encyclopedia container.

    python3 tools/pack/pack_hadeethenc.py <out-dir> [--entries-per-block 128]

`.henc` is the encyclopedia's answer to the same problem `.hpk` solves for the books: 14.8 MB of
JSON is not something to parse at the door for a list of titles. The container splits into a header
every screen needs and blocks nothing reads until a narration is opened. Format v2, specified byte
by byte in docs/05-hadeethenc.md; tools/read_henc.py is the reference decoder, written from that
document rather than from this file.

    2,328 narrations, 452 categories -> 19 blocks, about 2.9 MB.

The pack carries the fields the app's screens render. `arabic.words` (the glosses) and
`arabic.reference` beyond the first line are in db/hadeethenc/narrations.json and NOT in the block
payload: keep the JSON if you want them.
"""
import argparse
import json
import lzma
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DB = ROOT / "db" / "hadeethenc"

MAGIC = b"HENC"
VERSION = 2
HEADER = "<4sHHIIIII"
BLOCK_ROW = "<IIII"
UNIT = "\x1f"   # joins a benefits list inside one field

# The field order of a full narration inside a block. A reader indexes into this; appending to it
# is a format change, so it is spelled out here and in docs/05-hadeethenc.md and nowhere else.
FULL_FIELDS = (
    ("id",), ("categories",),
    ("arabic", "title"), ("arabic", "intro"), ("arabic", "body"), ("arabic", "explanation"),
    ("arabic", "benefits"), ("arabic", "attribution"), ("arabic", "grade"), ("arabic", "reference"),
    ("english", "title"), ("english", "intro"), ("english", "body"), ("english", "explanation"),
    ("english", "benefits"), ("english", "attribution"), ("english", "grade"),
)


def xz(raw):
    return lzma.compress(raw, format=lzma.FORMAT_XZ, preset=9 | lzma.PRESET_EXTREME)


def string_table(records):
    """`u32 records`, each `u32 fields` then fields of `u32 length` + UTF-8."""
    out = bytearray(struct.pack("<I", len(records)))
    for record in records:
        out += struct.pack("<I", len(record))
        for field in record:
            data = str(field).encode("utf-8")
            out += struct.pack("<I", len(data)) + data
    return bytes(out)


def full_record(entry):
    record = []
    for path in FULL_FIELDS:
        if path == ("id",):
            record.append(entry["id"])
        elif path == ("categories",):
            record.append(",".join(entry["categories"]))
        else:
            value = entry[path[0]].get(path[1], "")
            if path[1] == "benefits":
                if any(UNIT in item for item in value):
                    sys.exit(f"{entry['id']}: a benefit contains U+001F, the list separator")
                value = UNIT.join(value)
            record.append(value)
    return record


def write_pack(tree, entries, out, per_block=128):
    tree_rows = [[n["id"], n["parent"] or "", n["labels"]["en"], n["labels"]["ar"],
                  n["direct"], n["total"]] for n in tree]
    light_rows = [[e["id"], ",".join(e["categories"]), e["english"]["title"], e["english"]["intro"],
                   e["english"]["grade"], e["english"]["attribution"]] for e in entries]
    header_raw = string_table(tree_rows) + string_table(light_rows)
    header_xz = xz(header_raw)

    table, payload = [], bytearray()
    for start in range(0, len(entries), per_block):
        raw = string_table([full_record(e) for e in entries[start:start + per_block]])
        compressed = xz(raw)
        table.append((start, len(payload), len(compressed), len(raw)))
        payload += compressed

    head = struct.pack(HEADER, MAGIC, VERSION, per_block, len(header_xz), len(header_raw),
                       len(table), len(entries), len(tree))
    out.write_bytes(head + b"".join(struct.pack(BLOCK_ROW, *row) for row in table)
                    + header_xz + bytes(payload))
    return {"blocks": len(table), "headerRaw": len(header_raw), "headerXZ": len(header_xz),
            "payload": len(payload), "bytes": out.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=pathlib.Path, help="directory to write HadeethEnc.henc into")
    parser.add_argument("--entries-per-block", type=int, default=128)
    args = parser.parse_args()

    tree = json.loads((DB / "categories.json").read_text(encoding="utf-8"))["tree"]
    entries = json.loads((DB / "narrations.json").read_text(encoding="utf-8"))["narrations"]
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "HadeethEnc.henc"
    sizes = write_pack(tree, entries, out, args.entries_per_block)
    print(f"{len(entries)} narrations, {len(tree)} categories; {sizes['blocks']} blocks of "
          f"{args.entries_per_block}, header {sizes['headerRaw']:,} -> {sizes['headerXZ']:,}, "
          f"payload {sizes['payload']:,}; {sizes['bytes']:,} bytes at {out}")


if __name__ == "__main__":
    main()
