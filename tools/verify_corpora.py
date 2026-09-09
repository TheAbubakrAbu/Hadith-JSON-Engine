#!/usr/bin/env python3
"""The acceptance test for everything in db/ that is not db/by_book: the gate, standard library only.

    python3 tools/verify_corpora.py [--pack <HadeethEnc.henc>]

tools/verify_packs.py proves a `.hpk` says what db/by_book says. This proves the same thing for
the rest of db/, against conformance/vectors.json:

  * db/hadeethenc/    counts, the category tree's shape and integrity, every category id a
                      narration cites, and the known-record vectors
  * db/topics.json    counts per lane and per book, that `popular` owns no topic, that ranks are
                      unique, and that EVERY entry's slug + citation resolves in db/by_book
  * db/vocabulary.txt that it is exactly what tools/build_vocabulary.py derives from the corpus
                      today, hash included, and that it is sorted and unique
  * ranked search     every probe in vectors.json, hit count, relaxed flag, corrections and the
                      top five, re-run against db/by_book
  * --pack            a `.henc` decodes whole and agrees with db/hadeethenc/ record for record

Add --softened-dashes for a pack whose English commentary was re-punctuated downstream (Al-Islam
does this: its screens never show an em dash). The commentary is then held to structure and wording
rather than to characters, which is the part the licence actually protects: the same paragraphs, the
same words in the same order, and no dash left behind. Everything else still has to match exactly.

Exit status 1 on any failure. The vocabulary check and the probes each read the whole corpus, so
this takes about half a minute; that is the price of checking rather than asserting.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_vocabulary   # noqa: E402
import ranked_search      # noqa: E402
import read_henc          # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "db"
VECTORS = ROOT / "conformance" / "vectors.json"


class Report:
    def __init__(self):
        self.checked = 0
        self.failures = []

    def equal(self, want, got, label):
        self.checked += 1
        if want != got:
            self.failures.append(f"{label}: expected {want!r}, got {got!r}")
            return False
        return True

    def check(self, condition, label, detail=""):
        self.checked += 1
        if not condition:
            self.failures.append(f"{label}{': ' + detail if detail else ''}")
        return condition


def verify_hadeethenc(report, want):
    cats = json.loads((DB / "hadeethenc" / "categories.json").read_text(encoding="utf-8"))["tree"]
    narrations = json.loads((DB / "hadeethenc" / "narrations.json").read_text(encoding="utf-8"))["narrations"]
    by = {c["id"]: c for c in cats}

    def depth(node):
        value = 1
        while node["parent"]:
            node = by[node["parent"]]
            value += 1
        return value

    report.equal(want["narrations"], len(narrations), "hadeethenc narration count")
    report.equal(want["categories"], len(cats), "hadeethenc category count")
    report.equal(want["roots"], sum(1 for c in cats if c["parent"] is None), "hadeethenc roots")
    depths = [depth(c) for c in cats]
    report.equal(want["maxDepth"], max(depths), "hadeethenc tree depth")
    report.equal(want["nodesByDepth"],
                 [depths.count(d) for d in range(1, max(depths) + 1)], "hadeethenc nodes by depth")
    report.equal(want["rootTotalsSum"], sum(c["total"] for c in cats if c["parent"] is None),
                 "hadeethenc root totals")
    report.equal(want["withEnglishExplanation"],
                 sum(1 for n in narrations if n["english"]["explanation"]), "hadeethenc explanations")
    report.equal(want["withEnglishBenefits"],
                 sum(1 for n in narrations if n["english"]["benefits"]), "hadeethenc english benefits")
    report.equal(want["withArabicWords"],
                 sum(1 for n in narrations if n["arabic"]["words"]), "hadeethenc arabic glosses")
    report.equal(want["withReference"],
                 sum(1 for n in narrations if n["arabic"]["reference"]), "hadeethenc references")
    report.equal(want["maxCategoriesPerNarration"],
                 max(len(n["categories"]) for n in narrations), "hadeethenc max categories")

    ids = [n["id"] for n in narrations]
    report.check(len(set(ids)) == len(ids), "hadeethenc duplicate narration id")
    report.equal(want["idsAscendNumerically"], ids == sorted(ids, key=int), "hadeethenc id order")

    known = {c["id"] for c in cats}
    orphans = sorted({c for n in narrations for c in n["categories"]} - known)
    report.check(not orphans, "hadeethenc category ids not in the tree", ", ".join(orphans[:5]))
    lost = [c["id"] for c in cats if c["parent"] is not None and c["parent"] not in known]
    report.check(not lost, "hadeethenc category parents not in the tree", ", ".join(lost[:5]))
    for node in cats:   # no cycles: every walk to a root terminates
        seen, cursor = set(), node
        while cursor["parent"]:
            if cursor["id"] in seen:
                report.check(False, f"hadeethenc category {node['id']} sits in a cycle")
                break
            seen.add(cursor["id"])
            cursor = by[cursor["parent"]]

    index = {n["id"]: n for n in narrations}
    for case in want["known"]:
        entry = index.get(case["id"])
        if not report.check(entry is not None, f"hadeethenc {case['id']} is missing"):
            continue
        report.equal(case["categories"], entry["categories"], f"hadeethenc {case['id']} categories")
        report.equal(case["englishTitlePrefix"], entry["english"]["title"][:len(case["englishTitlePrefix"])],
                     f"hadeethenc {case['id']} english title")
        report.equal(case["arabicBodySha256"],
                     hashlib.sha256(entry["arabic"]["body"].encode("utf-8")).hexdigest(),
                     f"hadeethenc {case['id']} arabic body")
    return narrations, cats


DASHY = re.compile("[—–]| - ")
WORD = re.compile(r"[^\W_]+", re.UNICODE)
SOFTENED_FIELDS = ("explanation", "benefits")


def compare_softened(report, want, got, label):
    """Compare one English commentary field across a dash filter.

    A downstream reader is allowed to re-punctuate the site's em dashes (Al-Islam does: its screens
    never show one). It is not allowed to move a word or lose a paragraph. So: the same paragraph
    blocks, every dash-free block character for character, and in the rest the same words in the
    same order with no em dash left behind. This is what caught the paragraph collapse of 2026-09-08,
    where the filter rejoined its sentence split with a single space and flattened every blank line
    in the 12 explanations that carried both a dash and a paragraph break.
    """
    src, out = want.split("\n\n"), got.split("\n\n")
    if not report.equal(len(src), len(out), f"{label} paragraph count"):
        return
    for index, (a, b) in enumerate(zip(src, out)):
        if DASHY.search(a):
            report.check("—" not in b, f"{label} block {index} still carries an em dash")
            report.equal(WORD.findall(a.lower()), WORD.findall(b.lower()),
                         f"{label} block {index} wording")
        else:
            report.equal(a, b, f"{label} block {index}")


def verify_pack(report, path, narrations, cats, softened=False):
    pack = read_henc.Pack(path)
    format_want = json.loads(VECTORS.read_text(encoding="utf-8"))["hadeethenc"]["packFormat"]
    report.equal(format_want["entriesPerBlock"], pack.entriesPerBlock, "henc entriesPerBlock")
    report.equal(len(narrations), len(pack.light), "henc narration count")
    report.equal(len(cats), len(pack.tree), "henc category count")
    for position, want in enumerate(narrations):
        got = pack.narration(position)
        report.equal(want["id"], got["id"], f"henc row {position} id")
        report.equal(want["categories"], got["categories"], f"henc {want['id']} categories")
        for field in ("title", "intro", "body", "explanation", "benefits", "attribution", "grade"):
            mine, theirs = want["english"][field], got["english"][field]
            if not softened or field not in SOFTENED_FIELDS or mine == theirs:
                report.equal(mine, theirs, f"henc {want['id']} english {field}")
            elif isinstance(mine, list):
                if report.equal(len(mine), len(theirs), f"henc {want['id']} english {field} count"):
                    for line, (a, b) in enumerate(zip(mine, theirs)):
                        compare_softened(report, a, b, f"henc {want['id']} english {field} {line}")
            else:
                compare_softened(report, mine, theirs, f"henc {want['id']} english {field}")
        for field in ("title", "intro", "body", "explanation", "benefits", "attribution", "grade",
                      "reference"):
            report.equal(want["arabic"][field], got["arabic"][field], f"henc {want['id']} arabic {field}")


def verify_topics(report, want):
    data = json.loads((DB / "topics.json").read_text(encoding="utf-8"))
    lane_of = {t["id"]: t["lane"] for t in data["topics"]}
    report.equal(want["entries"], len(data["entries"]), "topics entry count")
    report.equal(want["topics"], len(data["topics"]), "topics topic count")
    report.equal(want["lanes"], len(data["lanes"]), "topics lane count")

    def tally(key):
        out = {}
        for entry in data["entries"]:
            value = key(entry)
            out[value] = out.get(value, 0) + 1
        return dict(sorted(out.items()))

    report.equal(want["entriesByLane"], tally(lambda e: e["lane"]), "topics entries by lane")
    report.equal(want["entriesByTopicLane"], tally(lambda e: lane_of[e["topic"]]),
                 "topics entries by topic lane")
    report.equal(want["entriesBySlug"], tally(lambda e: e["slug"]), "topics entries by book")
    report.equal(want["crossLaneEntries"],
                 sum(1 for e in data["entries"] if e["lane"] != lane_of[e["topic"]]),
                 "topics entries whose lane is not their topic's")
    report.equal(want["ranksAreUnique"],
                 len({e["rank"] for e in data["entries"]}) == len(data["entries"]), "topics rank uniqueness")

    lane_ids = {l["id"] for l in data["lanes"]}
    report.check(all(t["lane"] in lane_ids for t in data["topics"]), "topics with an unknown lane")
    report.check(all(e["lane"] in lane_ids for e in data["entries"]), "entries with an unknown lane")
    topic_ids = set(lane_of)
    report.check(all(e["topic"] in topic_ids for e in data["entries"]), "entries with an unknown topic")

    catalog = {row["slug"]: row for row in json.loads((DB / "catalog.json").read_text(encoding="utf-8"))["books"]}
    citations, missing = {}, []
    for entry in data["entries"]:
        slug = entry["slug"]
        if slug not in citations:
            row = catalog[slug]
            book = json.loads((DB / "by_book" / row["folder"] / f"{slug}.json").read_text(encoding="utf-8"))
            citations[slug] = {str(h.get("citation")) for h in book["hadiths"] if h.get("citation")}
        if entry["citation"] not in citations[slug]:
            missing.append(f"{entry['id']} -> {slug} {entry['citation']}")
    report.check(not missing, "topics entries whose citation is not on the shelf",
                 ", ".join(missing[:5]))
    report.equal(want["everyCitationResolves"], not missing, "topics citation resolution")
    for case in want["known"]:
        entry = next((e for e in data["entries"] if e["id"] == case["id"]), None)
        if report.check(entry is not None, f"topics {case['id']} is missing"):
            for field in ("slug", "citation", "topic", "lane", "title"):
                report.equal(case[field], entry[field], f"topics {case['id']} {field}")


def verify_vocabulary(report, want):
    shipped = [w for w in (DB / "vocabulary.txt").read_text(encoding="utf-8").split("\n") if w]
    report.equal(want["words"], len(shipped), "vocabulary word count")
    report.equal(want["sortedAndUnique"], shipped == sorted(set(shipped)), "vocabulary is sorted and unique")
    report.equal(want["sha256"], hashlib.sha256(("\n".join(shipped) + "\n").encode("utf-8")).hexdigest(),
                 "vocabulary sha256")
    report.check(all(want["minLength"] <= len(w) <= want["maxLength"] for w in shipped),
                 "vocabulary word outside the length bounds")
    report.check(all(w.isascii() and w.islower() and w.isalpha() for w in shipped),
                 "vocabulary word that is not lowercase ASCII letters")
    present = set(shipped)
    for word in want["contains"]:
        report.check(word in present, f"vocabulary is missing {word!r}")
    for word in want["excludes"]:
        report.check(word not in present, f"vocabulary should not contain {word!r}")
    # The gate that matters: the shipped list IS what the corpus yields today.
    derived = build_vocabulary.collect()
    report.equal(derived, shipped, "vocabulary matches what db/by_book yields today")


def verify_ranked_search(report, want):
    for name, value in want["weights"].items():
        got = {"primary": ranked_search.PRIMARY_WEIGHT, "citation": ranked_search.CITATION_WEIGHT,
               "body": ranked_search.BODY_WEIGHT,
               "phraseBonusPrimary": ranked_search.PHRASE_BONUS_PRIMARY,
               "phraseBonusBody": ranked_search.PHRASE_BONUS_BODY,
               "wholeWordBonus": ranked_search.WHOLE_WORD_BONUS,
               "stemPenalty": ranked_search.STEM_PENALTY,
               "fuzzyPenalty": ranked_search.FUZZY_PENALTY,
               "relaxedTokenWeight": ranked_search.RELAXED_TOKEN_WEIGHT, "minimumHit": 1}[name]
        report.equal(value, got, f"ranked search weight {name}")
    report.equal(sorted(want["stopwords"]), sorted(ranked_search.STOPWORDS), "ranked search stopwords")

    vocabulary = ranked_search.Vocabulary.load()
    catalog = json.loads((DB / "catalog.json").read_text(encoding="utf-8"))
    for case in want["probes"]:
        query = ranked_search.parse(case["query"], vocabulary)
        if not report.check(query is not None, f"probe {case['query']!r} did not parse"):
            continue
        report.equal(case["tokens"], [t.text for t in query.tokens], f"probe {case['query']!r} tokens")
        report.equal(case["corrections"], [{"from": a, "to": b} for a, b in query.corrections],
                     f"probe {case['query']!r} corrections")
        hits, relaxed = ranked_search.search(query, None, catalog)
        report.equal(case["hits"], len(hits), f"probe {case['query']!r} hit count")
        report.equal(case["relaxed"], relaxed, f"probe {case['query']!r} relaxed")
        report.equal(case["top"],
                     [{"slug": h.slug, "row": h.row, "score": h.score, "matched": h.matched}
                      for h in hits[:len(case["top"])]], f"probe {case['query']!r} top hits")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", type=pathlib.Path, help="a HadeethEnc.henc to check against db/")
    parser.add_argument("--softened-dashes", action="store_true",
                        help="the pack's English commentary was re-punctuated downstream (Al-Islam "
                             "does this): compare paragraphs and wording instead of characters")
    args = parser.parse_args()

    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    report = Report()
    narrations, cats = verify_hadeethenc(report, vectors["hadeethenc"])
    if args.pack:
        verify_pack(report, args.pack, narrations, cats, softened=args.softened_dashes)
    verify_topics(report, vectors["topics"])
    verify_vocabulary(report, vectors["vocabulary"])
    verify_ranked_search(report, vectors["rankedSearch"])

    print(f"{report.checked:,} assertions")
    if report.failures:
        print(f"\nFAILED: {len(report.failures)}", file=sys.stderr)
        for line in report.failures[:30]:
            print("  " + line, file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
