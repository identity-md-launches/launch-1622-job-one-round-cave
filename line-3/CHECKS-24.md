# Pepe 24 checks

Local checks completed on 2026-10-13; execution/check profile is **none**. These results are worker observations and carry no independent authority.

- Code Lens: **16 tests passed**; saved ZTO verification demonstration passed.
- Code Changes: **10 tests passed**; saved before/after ZTO demonstration passed.
- Code Opcodes: **6 tests passed**; saved ZTO demonstration passed.
- Code Proof: **30 tests passed**; real saved ZTO and IMD proof demonstrations passed.

Total: **62 tests**, all passing. Commands, exits, test output, demonstration results and output hashes are recorded in `check-results-24.json`. Reproduce the new suite with:

```sh
python3 -B -m unittest discover -s line-3/tools/code-proof -p 'test_*.py' -v
```

Live ZTO and IMD captures both verified against the reconstructed header at block 26,185,280. Captures used the assigned relay, hash-pinned state/proof requests, block rechecks, and the inherited read-only allowlist. Full evidence is saved as ordinary JSON in the new tool folder. No state-changing RPC or transaction was used. These proofs establish state inclusion relative to the header; neither the supplied header nor finality was independently authenticated.

Structural image inspection passed: both wall paths contain identical valid RGB PNG bytes at **1254 × 1254**; the companion is a valid **512 × 512 JPEG**, **74,171 bytes**. Visually reviewed the final PNG and JPEG. `VISUAL-24.md` records appearance, digit review and limitations. `visual-checks-24.json` records the ancestor hash and pixel comparison: **zero changed pixels outside the new-mark mask**. FFmpeg softened the patch boundary within its existing mask; all ancestral painting areas remain excluded from the mask.

`delivery-checks-24.json` confirms: GOAL.md is byte-identical to the accepted tree; all older JSON/JPEG records are byte-identical; record 24 is the sole new record; its artifact URL matches the final wall's SHA-256; both wall copies match; all changes are inside authorized paths; every new non-artifact file is below 100,000 bytes. No configuration was changed. Artifact PNG outputs remain untracked for daemon upload.
