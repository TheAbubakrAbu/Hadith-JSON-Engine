#!/usr/bin/env python3
"""Build db/hadeethenc/ from a hadeethenc.com dump: the Hadith Encyclopedia corpus.

    python3 tools/build_hadeethenc.py --source <dir> [--apply]

The Hadith Encyclopedia (الموسوعة الحديثية, hadeethenc.com) is the one corpus in this repository
whose provenance is NOT sunnah.com. Everything under db/by_book/ descends from a sunnah.com scrape,
so an upstream error there reaches a reader through every path; this is an independent translation
effort, and the only one carrying a scholarly explanation, a benefits list, Arabic word glosses and
a full takhrij reference with each narration.

    2,328 narrations under 452 categories, Arabic and English.

<dir> holds the site's own dump, either as plain `.json` or as the brotli `.json.br` that Tilawa
commits (node decodes those; Python ships no brotli):

    catalog.json[.br]   {"tree": [{"id", "parent", "labels": {...}, "direct", "total"}],
                         "index": [{"id", "cats": [...], "langs": [...]}]}
    core.json[.br]      {"<id>": {"title", "intro", "body", "explanation", "benefits",
                                  "words", "attribution", "grade", "reference"}}   Arabic
    tr-en.json[.br]     {"<id>": {"title", "intro", "body", "explanation", "benefits",
                                  "attribution", "grade"}}                          English

THE CONTENT IS NEVER EDITED. hadeethenc.com permits reuse on two conditions: no modification,
addition or deletion of the content, and the source clearly credited. This script normalises
STRUCTURE only; the one text touch is CRLF to LF plus trimming outer whitespace, which changes no
content. Do not add a wording pass here, and do not let one in downstream without knowing that it
is a modification. (Al-Islam re-punctuates em dashes in the English commentary for its own house
style; that filter lives in the app, deliberately not in this repository. See
docs/05-hadeethenc.md.)

Writes, with --apply:

    db/hadeethenc/categories.json   the 452-node tree
    db/hadeethenc/narrations.json   the 2,328 narrations, ar + en, in ascending numeric id order
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "db" / "hadeethenc"

# The narration fields this corpus carries, per language. Arabic is canonical and carries three
# fields English has none of: `words` (glosses for the hard words), `reference` (the takhrij) and
# nothing else -- the English layer is a translation of the rest.
ARABIC_FIELDS = ("title", "intro", "body", "explanation", "benefits", "words", "attribution",
                 "grade", "reference")
ENGLISH_FIELDS = ("title", "intro", "body", "explanation", "benefits", "attribution", "grade")


def clean(value):
    """CRLF to LF and outer whitespace trimmed, recursively. The only text touch in this script."""
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    return value


def load(source, name):
    """`<name>.json` if it is there, else `<name>.json.br` through node."""
    plain = source / f"{name}.json"
    if plain.exists():
        return json.loads(plain.read_text(encoding="utf-8"))
    packed = source / f"{name}.json.br"
    if not packed.exists():
        sys.exit(f"{source}: neither {plain.name} nor {packed.name}")
    script = ("const z=require('zlib'),f=require('fs');"
              "process.stdout.write(z.brotliDecompressSync(f.readFileSync(process.argv[1])));")
    try:
        raw = subprocess.run(["node", "-e", script, str(packed)], check=True,
                             capture_output=True).stdout
    except FileNotFoundError:
        sys.exit(f"{packed.name} is brotli and node is not installed; decompress it first")
    return json.loads(raw)


def build(source):
    catalog = load(source, "catalog")
    core = load(source, "core")
    english = load(source, "tr-en")

    tree = []
    for node in catalog["tree"]:
        labels = node.get("labels", {})
        tree.append({
            "id": str(node["id"]),
            "parent": str(node["parent"]) if node.get("parent") is not None else None,
            "labels": {"en": clean(labels.get("en", "")), "ar": clean(labels.get("ar", ""))},
            "direct": int(node.get("direct", 0)),
            "total": int(node.get("total", 0)),
        })

    rows = {str(row["id"]): row for row in catalog.get("index", [])}
    narrations = []
    for hadith_id in sorted(core, key=lambda value: int(value)):
        arabic = core[hadith_id]
        translation = english.get(hadith_id)
        if not translation:
            continue
        row = rows.get(hadith_id, {})
        narrations.append({
            "id": str(hadith_id),
            "categories": [str(c) for c in row.get("cats", [])],
            "arabic": {field: clean(arabic.get(field, [] if field in ("benefits", "words") else ""))
                       for field in ARABIC_FIELDS},
            "english": {field: clean(translation.get(field, [] if field == "benefits" else ""))
                        for field in ENGLISH_FIELDS},
        })
    return catalog, tree, narrations


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=pathlib.Path,
                        help="directory holding catalog/core/tr-en as .json or .json.br")
    parser.add_argument("--apply", action="store_true", help="write db/hadeethenc/ (default: report)")
    args = parser.parse_args()

    catalog, tree, narrations = build(args.source)
    known = {node["id"] for node in tree}
    unknown = sorted({c for n in narrations for c in n["categories"]} - known)
    if unknown:
        sys.exit(f"{len(unknown)} category id(s) not in the tree: {unknown[:10]}")

    with_benefits = sum(1 for n in narrations if n["english"]["benefits"])
    with_words = sum(1 for n in narrations if n["arabic"]["words"])
    roots = sum(1 for node in tree if node["parent"] is None)
    print(f"{len(narrations)} narrations, {len(tree)} categories ({roots} roots); "
          f"english benefits on {with_benefits}, arabic glosses on {with_words}")

    if not args.apply:
        print("dry run; pass --apply to write db/hadeethenc/")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    categories = {
        "version": 1,
        "source": catalog.get("source", "hadeethenc.com"),
        "generatedAt": catalog.get("generatedAt", ""),
        "description": ("The Hadith Encyclopedia's category tree: 452 nodes, 7 roots, at most 4 "
                        "deep. `direct` is the narrations filed on the node itself, `total` the "
                        "subtree. A narration can sit under several categories, so the roots' "
                        "totals sum to more than the corpus."),
        "tree": tree,
    }
    (OUT / "categories.json").write_text(
        json.dumps(categories, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    body = {
        "version": 1,
        "source": catalog.get("source", "hadeethenc.com"),
        "generatedAt": catalog.get("generatedAt", ""),
        "count": len(narrations),
        "narrations": narrations,
    }
    (OUT / "narrations.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8")
    for path in (OUT / "categories.json", OUT / "narrations.json"):
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
