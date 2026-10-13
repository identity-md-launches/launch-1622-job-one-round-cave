# Allowance Union

Keep every known ERC-20 owner–spender pair when combining inventories from different discovery windows or workers, then measure the whole union at one Ethereum block. An empty recent scan cannot remove older permissions. Zero allowances remain in the inventory because they may change later.

Python 3.10+ and the standard library are sufficient. The adjacent Permission Gate, Allowance Changes and Allowance Lens modules are ordinary repository dependencies; keep those folders beside this one. No installation, account, wallet or secret is needed. ZTO is the demonstration token; validated IMD observations also work. Inputs cannot mix tokens.

## One command to see it working

From the repository root:

```sh
python3 -B line-2/tools/allowance-union/allowance_union.py
```

This runs offline against three **real saved Ethereum observations**. It returns `requires_recheck`, **19 distinct pairs across 16 owners**, even though one input is an empty recent Approval-event window. `example-report.json` records the exact output. The plan contains pair identities and evidence fingerprints, not balances assembled from different blocks.

## What happened when tried

| Check | Result |
| --- | --- |
| Original ZTO discovery at block 26,183,751 | 19 pairs |
| Empty 50-block scan ending at 26,184,356 | All 19 old pairs retained |
| Later real inventory at 26,184,897 | Repeated pairs deduplicated; 19 total |
| Complementary overlapping subsets of that real inventory | Union recovered all 19 pairs |
| Full real later inventory checked against the earlier union | All 19 rechecked; three active permissions |
| Empty later scan checked against the older inventory | 19 missing pairs, exit 4 |
| Offline checks | 24 new tests; 71 ancestor tests; all passed |

These historical measurements came from the bundled ancestor observations, not new accounts or invented balances. Negative tests mutate copies and never save them as chain evidence. A completed coverage check is **not policy approval**: all three active permissions remain visible to Permission Gate.

Live attempts and their actual outcomes are recorded in `live-attempts.json`. A failed attempt saves no raw inventory. Offline replay remains available without network access.

## Combine actual observations

Repeat `--input` for 1–16 existing raw Allowance Lens observations or Allowance Changes inventories:

```sh
python3 -B line-2/tools/allowance-union/allowance_union.py --input line-2/tools/allowance-lens/observation.json --input line-2/tools/allowance-changes/lens-recheck.json
```

The union accepts at most 64 distinct pairs and rejects overflow instead of dropping entries. Identical pairs across files are deduplicated. Evidence must have matching chain, token and decimals. Conflicting headers at one height, contradictory same-block allowances, conflicting balances for a shared owner, backwards timestamps, malformed calldata and incomplete raw measurements are rejected. Each input file is limited to 96 KiB and must be inside the current workspace. Duplicate JSON object keys are rejected.

Each pair lists the SHA-256 fingerprints of its source inputs. Fingerprints use UTF-8 JSON with sorted object keys, compact separators and the original array order. They bind normalized input content; they are not Ethereum proofs and need not match a file's byte hash. Repeated identical files remain visible in the `inputs` list but do not multiply pairs or source references.

## Check a saved remeasurement

```sh
python3 -B line-2/tools/allowance-union/allowance_union.py --input line-2/tools/allowance-lens/observation.json --input line-2/tools/allowance-changes/lens-recheck.json --after line-2/tools/permission-gate/live-observation.json
```

This historical example returns `all_known_pairs_rechecked`, with three active known pairs. Every required pair must appear in validated evidence at one block at least as new as every input. Missing pairs are reported explicitly; they are never treated as zero. Extra measured pairs are counted separately. An empty required inventory cannot pass. The recheck must also agree with any input at the same block.

Use the **raw recheck file**, not the union plan or coverage report, with Permission Gate and a deliberately selected policy. `policy_approval` is always `null` in a union coverage result. The coverage exit code does not grant permission to spend.

## Refresh the entire union with public reads

```sh
python3 -B line-2/tools/allowance-union/allowance_union.py --input line-2/tools/allowance-lens/observation.json --input line-2/tools/allowance-changes/lens-recheck.json --refresh --timeout 90 --save line-2/tools/allowance-union/next-observation.json
```

The default endpoint is `https://ethereum-rpc.publicnode.com`; `--rpc https://eth.drpc.org` selects the other supported public endpoint. No local relay or environment-derived proxy is used. The inherited transport sends `User-Agent: Pepeolithic-AllowanceLens/1.0`, refuses redirects, and allowlists read methods only.

The collector validates the union before network access, checks Ethereum chain 1 and the canonical headers of all input audit blocks, then selects one finalized block. All token reads use that block's hash with `requireCanonical: true`; it checks the selected header again afterward. Token decimals are read once, each owner's balance once and each pair's allowance once. It never calls approval, transfer or signing methods. A changed block, changed decimals, missing response or deadline produces an error; it saves only a fully validated union recheck.

`--block` accepts `finalized`, `safe`, `latest` or a decimal block number. Numeric requests must match the returned header. Historical calls need provider support for the requested state and hash-based calls. The output is an ordinary Allowance Changes inventory, so it works with the existing comparison and policy tools without conversion. Saving refuses to overwrite an existing file and enforces the 96 KiB output limit.

The inherited spawned-process supervisor limits the **whole live operation**, including all requests and DNS, to `--timeout` seconds (default 90; positive and at most 600), plus about 1.1 seconds of cleanup and scheduling overhead. Low-level library `refresh()` is synchronous; use `lens.run_bounded()` for a deadline and a standard `if __name__ == '__main__'` guard in callers.

## Exits and boundaries

| Exit | Meaning |
| --- | --- |
| 0 | Nonempty identity plan produced, or all known pairs rechecked; neither is policy approval |
| 1 | Invalid input, incompatible evidence, RPC/deadline/file failure |
| 2 | Argument usage error |
| 4 | Empty inventory or missing required recheck pairs |

Default mode is labelled `demonstration: true`. Explicit inputs use `false`. `--refresh` and `--after` require explicit inputs; no implicit account is chosen. Plans and checks print JSON to stdout; handled failures print JSON to stderr. `--save` applies only to a live refresh.

This tool combines **known** pairs; it does not discover unknown spenders. Use bounded Allowance Lens event discovery or explicitly supplied real owner/spender reads to obtain more input evidence. Unioning windows does not establish complete event coverage, wallet completeness, wall-clock freshness, present canonicality of an offline snapshot, or future state. Permit2 sub-permissions, unused signatures, custom token authorizations and other chains remain outside scope. RPC claims are trusted evidence, not independent certification. No transactions are prepared, signed or sent.

Run the tests:

```sh
python3 -B -m unittest discover -s line-2/tools/allowance-union -p 'test_*.py' -v
```
