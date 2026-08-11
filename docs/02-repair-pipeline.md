# The repair pipeline

This is the heart of the repository. If you read one document, read this one — it is what you would need to decide whether to trust the data.

## The bug

`AhmedBaset/hadith-json` strips sunnah.com's editorial square brackets with a **greedy** regex ([`scrapeData.ts:70`](https://github.com/AhmedBaset/hadith-json/blob/main/src/helpers/scrapeData.ts#L70), and the same pattern at lines 59, 65, 86, 87):

```ts
.replace(/\[.*\]/g, "")
```

`.*` is greedy. With **one** bracket pair on a line the damage is cosmetic — you lose `[of His]`. With **two or more**, the match opens at the first `[`, closes at the last `]`, and everything between them is deleted. The surviving fragments then weld together into fluent, plausible, wrong text.

### Worked example — Forty Hadith Qudsi 24

Source ([sunnah.com/qudsi40:24](https://sunnah.com/qudsi40:24)):

> If Allah has loved a servant **[of His]** He calls Gabriel and says: I **love** So-and-so… Then acceptance is established for him on earth. And if Allah has **abhorred** a servant **[of His]**, He calls Gabriel and says: I abhor So-and-so…

Both halves contain `a servant [of His]`, so the greedy match spans from the first to the second. What upstream ships:

> If Allah has loved a servant , He calls Gabriel and says: I **abhor** So-and-so, therefore abhor him…

The hadith now says Allah abhors the servant He loves. The `arabic` field of the same record is complete and contains both halves — **the record contradicts itself**, which is how the bug stayed invisible for so long: nothing looks broken unless you read both scripts side by side.

## The proof gate

Text deleted by the scraper is unrecoverable from the JSON, so it is recovered from independent clean scrapes of the same sunnah.com translations. **Every repair is proof-gated.** A record is damaged if and only if a clean candidate exists such that

```
simulate_bug(clean) == damaged      # provably the same hadith
clean               != damaged      # text was provably lost
```

Re-running the upstream bug on the candidate must reproduce the damaged record exactly. If it does not reproduce, nothing is written.

This makes a mis-attributed repair **structurally impossible**: the pipeline cannot match the wrong hadith, because the wrong hadith would not reproduce the damage. It is a proof, not a similarity score.

Comparison normalises away honorific and citation rendering (`ﷺ` vs `pbuh`, `Quran 3:169` vs `Quran chapter 3 verse 169`) so cosmetic differences between sources don't block a match. **It never normalises the text that gets written out.**

Matching is **by content, never by hadith number**, because upstream's `idInBook` drifts. Any normalised text mapping to more than one distinct candidate is refused as ambiguous.

## Pass 1 — whole-string greedy

[`final_repair.py`](../tools/final_repair.py), driven by [`runall.py`](../tools/runall.py). Simulates the bug as a single greedy strip over the whole string and indexes each donor by `norm(GREEDY(clean))`. **4,187 repairs.**

## Pass 2 — per-line grouping

[`repair_line_aware.py`](../tools/repair_line_aware.py). **290 repairs**, and the reason it exists is a subtle and instructive bug in pass 1.

### Why pass 1 missed them

Pass 1's simulation is `re.sub(r'\[.*\]', '', s)`, and Python's `.` does not match a newline. Neither does JavaScript's — upstream's regex is likewise **per line**. So the simulation is faithful *only if the candidate still has the line breaks the scraper saw*.

**It does not.** Both clean donors ship the narration flattened onto one line, with any trailing citation welded on by a space instead of a newline.

So for a hadith carrying a bracketed insertion **and** a bracketed citation — `... on five [pillars]: ...` plus a closing `[Bukhari & Muslim]` — simulating the bug on the flattened donor deletes everything from the first `[` to the last `]`, which is the entire narration. That can never equal the damaged record, which kept its narration. The proof could not hold, and the record was correctly left alone.

**Unprovable, not undamaged.** The distinction matters: pass 1 was not wrong to skip them, it was wrong about what the bug did.

### What pass 2 does

Model what the scraper actually did. The deletion ran independently per line, and a line break is exactly what the donors lost. So instead of one greedy strip, consider **every way the bracket pairs could have been distributed across lines** — each consecutive group deleting from its first `[` to its last `]` — and ask whether any grouping reproduces the damage:

```
exists a grouping G:  norm(strip_grouped(clean, G)) == norm(damaged)
and                   norm(clean)                   != norm(damaged)
```

For `A [one] B [two] C [three] D` the four groupings give:

| Grouping | Result |
|---|---|
| all merged (one greedy match) | `A  D` |
| all separate (each on its own line) | `A  B  C  D` |
| `[one]` alone, `[two][three]` merged | `A  B  D` |
| `[one][two]` merged, `[three]` alone | `A  C  D` |

Pass 1 only ever tested the first row. Pass 2 tests all of them.

Pass 2 is also **stricter** in one respect: where two donors cover a book, both must independently yield the same text. 174 of the 290 have that; the remaining 116 are in books only one donor covers.

### Finding candidates at scale

Pass 1's exact dict keyed by `norm(GREEDY(c))` is precisely the key that fails here, and a linear scan is O(records × donors) — it will not finish on Bukhari.

What every grouping preserves is the text **before the first `[`** — no grouping can delete it. So the damaged and clean texts share that prefix, usually dozens of characters. Sort the donor texts by their normalised form and the true candidate is a **nearest neighbour** of `norm(damaged)`: binary-search the insertion point and test a small window around it. O(log n) per record.

A window that misses can only ever cause a **miss** — a record left as upstream has it — never a wrong repair, because the grouped proof still gates every write.

## Pass 3 — the narrator tail

[`fix_leading_punctuation.py`](../tools/fix_leading_punctuation.py). **646 records.**

`restore` finds where a narrator ends by searching for a split that keeps the proof true. But the proof compares with `norm`, which discards every non-alphanumeric character — so a split placed just *before* the `):` closing a narrator and one placed just *after* it are **indistinguishable to it**, and the search keeps whichever it reaches first. When it kept the early one, the restored body opened with the leftover punctuation:

```
narrator: "Narrated Abu Sa'id al-Khudri (RAA):"
text:     "): Two men set out on a journey …"
```

`restore` stripped `' :,-'`, which does not include `)`. 646 of the 4,188 pass-1 records were affected.

This is cosmetic damage to otherwise-correct repairs: no words are missing, the wrong characters are simply at the front. Trimming them is **proof-neutral by construction** — `norm` ignores punctuation, so every repair that was proven stays proven.

## Verification

Every repair is re-verified against the **shipped** text, not the intermediate: re-simulating the bug on what was written must reproduce the original damaged record.

**4,476 of 4,477 hold.** The one exception is `muslim` #7393, a pass-1 `narrator_folded` record whose original narrator no longer exists anywhere in the repository, so the target cannot be reconstructed. That is unverifiable by harness, not failed.

Additionally, all 50,884 hadiths are verified byte-for-byte between the JSON and the built packs, and all 17 pack checksums are verified against the manifest.

## What is left

Comparing every still-scarred record against the nearest clean donor:

| | Records |
|---|---:|
| Donor text **identical** — nothing was ever lost | 2,562 |
| Donor genuinely holds more text — **real damage**, no grouping reproduces it | 19 |
| No close donor match, undecidable | 22 |

**The scar regex over-fires roughly 130 to 1.** `final_repair.py`'s own docstring warns that it "both over- and under-fires"; this is what that looks like measured. Do not read a scar count as a damage count.

The honest residual is **19 known-damaged plus 22 unknown**, all left exactly as upstream has them. Closing them needs a third source — see [faq.md](faq.md#why-cant-the-last-few-be-fixed).

## The limit of all this

The proof is **structural, not scholarly**. It proves a repair restored the *same hadith* that was damaged — that no wrong narration was spliced in. It proves nothing about whether the translation is accurate, or whether the donor carried its own errors. A wrong translation that reproduces the damage passes the gate.

Verifying a data pipeline and authenticating hadith are not the same activity. This repository does the first one carefully and makes no claim about the second.
