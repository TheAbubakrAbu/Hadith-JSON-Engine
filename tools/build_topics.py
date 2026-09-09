#!/usr/bin/env python3
"""Build db/topics.json: a curated way into the corpus, by subject.

    python3 tools/build_topics.py --source <hadithDatabase.ts> [--apply]

The 17 collections are organised the way their compilers organised them, by chapter. That is the
right structure for the books and the wrong one for a reader who wants to know what the Prophet
(peace be upon him) said about anger, or about a neighbour: the answer is spread across four books
under four different chapter headings.

This is the other index. 331 narrations, each given a plain-English title and filed under one of
21 subjects in seven lanes, so one subject can be read as Bukhari words it, next to Muslim, next to
at-Tirmidhi. The curation is Tilawa's (Jamil Hammoudeh, used with permission).

NO TEXT IS COPIED. Every entry is reduced to a `slug` + `citation` pair and resolved against
db/by_book/ at read time, so what a reader sees is this repository's own repaired text, with its
gradings, and a curated row can never drift from the corpus behind it. An entry whose citation is
not on the shelf FAILS the build rather than shipping a dead row.

<hadithDatabase.ts> is Tilawa's generated module (src/data/generated/hadithDatabase.ts). Its
literals are read with node, which is the only dependency here; the type dressing is stripped
first, since the point is the data and not a TypeScript toolchain.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOKS = ROOT / "db" / "by_book"
OUT = ROOT / "db" / "topics.json"

# Which folder each collection lives in. Only the six the curation draws on.
FOLDERS = {"bukhari": "the_9_books", "muslim": "the_9_books", "abudawud": "the_9_books",
           "tirmidhi": "the_9_books", "nasai": "the_9_books", "ibnmajah": "the_9_books"}

_STRIP = (
    (re.compile(r"^import\b[\s\S]*?;\s*$", re.M), ""),
    (re.compile(r"^export type\b[\s\S]*?;\s*$", re.M), ""),
    (re.compile(r"^export interface\b[\s\S]*?^\}\s*$", re.M), ""),
    (re.compile(r"^export function\b[\s\S]*?^\}\s*$", re.M), ""),
    (re.compile(r"^export \{[^}]*\}[^\n]*$", re.M), ""),
    (re.compile(r"^export const (\w+)\s*:[^=]*?=", re.M), r"const \1 ="),
    (re.compile(r"^export const (\w+)\s*=", re.M), r"const \1 ="),
    (re.compile(r"\s+as const\b"), ""),
)


def read_consts(path, names):
    """The named top-level constants of a TypeScript module, as Python data."""
    source = path.read_text(encoding="utf-8")
    for pattern, replacement in _STRIP:
        source = pattern.sub(replacement, source)
    payload = "{" + ",".join(f"{n}:(typeof {n}==='undefined'?null:{n})" for n in names) + "}"
    script = source + "\nprocess.stdout.write(JSON.stringify(" + payload + "));\n"
    try:
        result = subprocess.run(["node", "-"], input=script.encode("utf-8"), capture_output=True)
    except FileNotFoundError:
        sys.exit("node is not installed; it is what evaluates the TypeScript literals")
    if result.returncode != 0:
        sys.exit(f"node failed on {path}:\n{result.stderr.decode('utf-8')[:2000]}")
    return json.loads(result.stdout.decode("utf-8"))


_books = {}


def book(slug):
    if slug not in _books:
        path = BOOKS / FOLDERS[slug] / f"{slug}.json"
        if not path.exists():
            sys.exit(f"book missing: {path}")
        _books[slug] = json.loads(path.read_text(encoding="utf-8"))
    return _books[slug]


def by_citation(slug):
    """{citation: hadith} for one book. The citation is the key a curated row points at, because
    `idInBook` drifts and a curation outlives an index."""
    return {str(h.get("citation") or ""): h for h in book(slug)["hadiths"] if h.get("citation")}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=pathlib.Path,
                        help="Tilawa's src/data/generated/hadithDatabase.ts")
    parser.add_argument("--apply", action="store_true", help="write db/topics.json (default: report)")
    args = parser.parse_args()

    data = read_consts(args.source, ["HADITH_LANES", "HADITH_TOPICS", "HADITH_DATABASE",
                                     "HADITH_DATABASE_SOURCE"])
    lanes = [{"id": l["id"], "label": l["label"], "subtitle": l["subtitle"]}
             for l in data["HADITH_LANES"]]
    topics = [{"id": t["id"], "label": t["label"], "subtitle": t["subtitle"], "lane": t["laneId"]}
              for t in data["HADITH_TOPICS"]]
    lane_ids = {l["id"] for l in lanes}
    topic_ids = {t["id"] for t in topics}

    entries, problems, seen = [], [], set()
    graded = 0
    for row in data["HADITH_DATABASE"]:
        reference = row.get("reference", "")
        match = re.match(r"^https://sunnah\.com/([a-z]+):(\d+[a-z]?)$", reference)
        if not match:
            match = re.match(r"^([a-z]+)-(\d+[a-z]?)$", row["id"])
        if not match:
            problems.append(f"{row['id']}: no citation in {reference!r}")
            continue
        slug, citation = match.group(1), match.group(2)
        if slug not in FOLDERS:
            problems.append(f"{row['id']}: {slug} is not a collection this index covers")
            continue
        hadith = by_citation(slug).get(citation)
        if hadith is None:
            problems.append(f"{row['id']}: {slug} {citation} is not on the shelf")
            continue
        if row["topicId"] not in topic_ids:
            problems.append(f"{row['id']}: unknown topic {row['topicId']}")
        if row["laneId"] not in lane_ids:
            problems.append(f"{row['id']}: unknown lane {row['laneId']}")
        key = (slug, citation, row["topicId"])
        if key in seen:
            problems.append(f"{row['id']}: duplicate of {slug} {citation} under {row['topicId']}")
            continue
        seen.add(key)
        if hadith.get("english", {}).get("grades"):
            graded += 1
        entries.append({
            "id": row["id"],
            "title": row["title"],
            "topic": row["topicId"],
            "lane": row["laneId"],
            "slug": slug,
            "citation": citation,
            "tags": [t for t in row.get("tags", []) if t],
            "rank": int(row.get("rank", 0)),
        })

    if problems:
        print(f"FAILED: {len(problems)} problem(s)", file=sys.stderr)
        for line in problems[:40]:
            print("  " + line, file=sys.stderr)
        sys.exit(1)

    per_slug = {}
    for entry in entries:
        per_slug[entry["slug"]] = per_slug.get(entry["slug"], 0) + 1
    print(f"{len(entries)} entries, {len(topics)} topics, {len(lanes)} lanes; "
          f"{graded} carry a grading in this corpus")
    print("  " + ", ".join(f"{slug} {count}" for slug, count in sorted(per_slug.items())))

    if not args.apply:
        print("dry run; pass --apply to write db/topics.json")
        return

    source = data.get("HADITH_DATABASE_SOURCE") or {}
    OUT.write_text(json.dumps({
        "version": 1,
        "description": ("A curated subject index over db/by_book/: 331 narrations under 21 topics "
                        "in 7 lanes. Entries carry a citation, never text; resolve `slug` + "
                        "`citation` against the book file to get this corpus's own repaired text "
                        "and its gradings."),
        "curation": {
            "by": "Jamil Hammoudeh",
            "project": "Tilawa",
            "note": "Used with permission. The titles are the curator's; the text is not copied.",
            "importedOn": source.get("importedOn", ""),
        },
        "lanes": lanes,
        "topics": topics,
        "entries": entries,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
