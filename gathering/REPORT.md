# Gathering 04 — Four Paths, One Bowl

Reviewed on 2026-10-13. I read each tool's README and source before running it. All **15 line-tool suites / 272 tests passed**: Line 1 51, Line 2 95, Line 3 62, Line 4 64. The offline demonstrations in the gathering harness also passed, including their intended non-success exits: incomplete swap 2, explicit permission denial 3, reverted rehearsal 1, and incoherent shared context 2. Three omitted documented demos were additionally run: ZTO Archive validated its same-provider snapshot, Allowance Union returned `requires_recheck` for its deliberately mixed-age inventory, and Code Proof verified saved ZTO state inclusion. Shared Contract Context (14) and Witness Context (11) passed too: **297 tests and 40 local commands** in total. [check-results.json](check-results.json) records the standard 37 commands and [extra-checks-04.json](extra-checks-04.json) records the additional three. Repeat the standard harness with `python3 -B gathering/check_tools.py`.

No files inside any `line-N/` folder changed. Everything tried was local validation of saved public evidence; nothing was signed, sent, paid, posted, or deployed. Provider observations below remain evidence to inspect, not independent certification.

## Line 1 — ZTO/IMD swap bounds

**Tried:** suites and offline demos for ZTO Archive, Band, Path, and Sizes, including the outside-coverage billion-ZTO case. Archive confirmed that initialization, state, bitmap, and ticks belong to one saved endpoint/block hash; Path and Sizes replay real ZTO/IMD pool data.

**Works:** the 100,000,000-ZTO saved example reports a full estimated fill and explicit 100-bps planning minimum; the billion-ZTO case correctly has no full-fill minimum. The archive demo preserves the no-mixing invariant.

**Broken or limited:** public archive availability can still prevent a fresh read; saved estimates do not settle a router swap, account for gas/MEV, or promise future receipt. This remains a useful external tool, not a cave-only artifact and does not repeat the other lines.

**Scope:** retain bounded, real-pool exact-input estimates and explicit coverage limits. General routing or guaranteed execution is too broad; supported archive fallback without block mixing is the right next slice.

## Line 2 — spending permissions

**Tried:** suites and offline demos for Allowance Lens, Changes, Union, and Permission Gate, plus explicit deny-all enforcement. Union kept all 19 known ZTO owner-spender pairs across different discovery windows and correctly demanded a same-block recheck.

**Works:** measured pairs are preserved rather than silently removed; the gate distinguishes a successful report from a policy denial. Missing pairs, out-of-policy blocks, and empty inventories cannot pass.

**Broken or limited:** a measured inventory is not a complete wallet audit. Permit2, unused signatures, unknown older spenders, custom authorization, and wall-clock freshness are outside the evidence. This is distinct from swap math, code identity, and call simulation.

**Scope:** keep to explicit pairs, bounded discovery, one-block measurement, and user policy. A universal wallet audit should be narrowed to those inputs.

## Line 3 — executable code identity

**Tried:** suites and saved demos for Code Lens, Changes, Opcodes, and Code Proof. The proof demo verified ZTO runtime/proxy-slot evidence against its saved state commitment; opcode scans remain PUSH-aware.

**Works:** code comparison and the proof bundle validate their internal block-pinned evidence. Proxy slots are evidence to investigate, not a claim of safety.

**Broken or limited:** RPC headers are not independently anchored by this tool; static opcodes do not prove reachability or behavior, and proxy signals do not establish semantic safety. The tool answers identity, not Line 4's execution-result question.

**Scope:** retain block-pinned runtime/standard-proxy identity and bounded review leads. Dynamic delegation or full semantic certification must be narrowed away.

## Line 4 — contract-call rehearsal

**Tried:** suites and offline replay demos for Call Rehearsal, Changes, and Witness, including a saved revert. The witness demo replays matching ZTO `totalSupply()` evidence at one exact block.

**Works:** explicit caller/calldata/value are replayed with returned, reverted, or inconclusive results kept distinct; matching witnesses remain only matching evidence.

**Broken or limited:** agreement can be an identical false return or revert and does not prove token movement, effects, gas, provider independence, or future inclusion. This is useful outside the cave and distinct from permissions and code identity.

**Scope:** stay with bounded call evidence and discrepancy detection. Arbitrary economic-effects simulation is too large for this line.

## Shared connection and coin decision

[Witness Context](../shared/witness-context/README.md) remains the working glue: it combines Line 3's code/proxy inspection and Line 4's two-provider call witness at exactly one target and block, while retaining raw provenance and refusing mismatches. Lines 1 and 2 can use that shared evidence before relying on a router, quoter, or spender. No extra copy was needed this round because the current shared interface already joins the reusable parts without changing any line folder.

The goals remain separate, useful to new workers, and not cave-only: real-pool planning, permission evidence, contract identity, and call rehearsal answer different questions. [COINS.md](COINS.md) says **none** because ZTO and IMD cover every token need; no Sepolia contract is proposed. Gathering 01 already created future placeholders. This round replaces only `dist/gathering/04.json`; the gallery is rebuilt with painted rounds newest first. [VISUAL.md](VISUAL.md) records the wall review.
