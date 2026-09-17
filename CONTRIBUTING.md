# Contributing

The most valuable contribution to this repository is not code.

## What is most needed

**1. Scholarly review of the repairs.** Every change is in [`logs/<book>.repairlog.json`](logs) with the exact `before` and `after`. 290 second-pass repairs, of which **115 rest on a single source** (`confirmed_by: 1`). Someone qualified reading those diffs is worth more than any feature. If you review a batch and it is sound, say so in an issue: that is a real contribution and it will be recorded.

**2. A third text source.** 19 records are still provably truncated, 22 are undecidable, and 16 Ibn Majah records were refused as ambiguous. All of them are stuck because the two available donors share the same gaps. See [docs/faq.md](docs/faq.md#why-cant-the-last-few-be-fixed) for what has already been tried. An [api.sunnah.com](https://github.com/sunnah-com/api) key, or any independent clean scrape, would close most of this.

**3. Pack readers in other languages.** The format is fully specified in [docs/04-hpk-format.md](docs/04-hpk-format.md) with a reference decoder at [`tools/read_pack.py`](tools/read_pack.py). A Kotlin, Rust, Dart, or Go reader would let more apps ship this data. Start from [docs/PORTING.md](docs/PORTING.md).

**4. Bug reports about the text itself.** If a hadith reads wrong, open an issue with the book slug, `idInBook`, and what you believe it should say.

## The rule that matters

**Never write text to a hadith that you cannot prove.**

A record is changed only if re-simulating the upstream bug on the replacement reproduces the damaged record **exactly**:

```
simulate_bug(clean) == damaged      # provably the same hadith
clean               != damaged      # text was provably lost
```

If it does not reproduce, leave the record exactly as upstream has it. A gap left honestly is better than a guess written confidently; a wrong hadith in someone's app is something they may act on.

Corollaries, all of which the existing tools follow:

- **Match by content, never by hadith number.** `idInBook` drifts.
- **Refuse ambiguity.** Two candidates that both reproduce the damage means neither is written.
- **Never normalise the text you write out.** Normalisation is for comparison only.
- **Prefer a false negative.** A missed repair is a record left as-is. A false positive is a fabricated hadith.
- **Do not touch the Arabic.** No tool in this repository modifies it.

If you are adding a heuristic, it belongs in candidate *selection* (which records to try), never in the decision to write. Selection can only cause misses; the proof gate does the deciding.

## Practical notes

**Every tool is dry-run by default.** Drop `--apply` and it prints what it would change. Please look at the output before applying: the `[pillars]` fix, the Bukhari fake-grades bug, and the narrator-tail bug were all caught that way.

**Serialise the way the pipeline does**, or every file shows as fully rewritten:

```python
open(path, "w", encoding="utf-8").write(json.dumps(book, ensure_ascii=False))
```

Default separators, no indent, no trailing newline. This round-trips the committed files byte for byte.

**Log every change.** Append to `logs/<book>.repairlog.json` with `before`, `after`, and how many independent sources confirmed it. An unlogged change cannot be audited, which defeats the point.

**Tools must be idempotent.** Re-running must not compound or leave stale state. `add_grades.py` clears `grades` before each run for exactly this reason.

**Read donor files with `utf-8-sig`.** The CheeseWithSauce files carry a BOM; plain `utf-8` throws on the first character. Report an unreadable donor file rather than skipping it silently, swallowing that error quietly halved donor coverage across most books until it was caught.

## After changing data

```bash
tools/pack/build.sh /path/to/your-app        # rebuild packs
python3 tools/read_pack.py <pack>.hpk --verify
```

Then check the corpus still verifies end to end: every hadith byte-identical between JSON and pack, all 17 checksums matching `manifest.json`, and the round-trip proof still holding on every logged repair. If you change the pack format, bump `formatVersion` and update [docs/04-hpk-format.md](docs/04-hpk-format.md) and [`tools/read_pack.py`](tools/read_pack.py) in the same commit: the spec, the reference reader, and the packer are one unit.

If you add or change a behaviour, add a case to [`conformance/vectors.json`](conformance/vectors.json) so every port picks it up.

## Tone

This data is the words of the Prophet ﷺ. Claims about it should be precise: say what was verified, how, and what remains unverified. If you are unsure whether something is right, say that too; the [FAQ](docs/faq.md) and the README both document what is still wrong, on purpose. Overstating correctness here is worse than admitting a gap.
