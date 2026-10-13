# Code Proof

Verify that an Ethereum contract's observed runtime hash and its measured EIP-1967 proxy slots are included in a block's state commitment. Code Proof checks EIP-1186 account and storage proofs, reconstructs the execution-header hash from canonical RLP, and binds every observed path runtime and beacon runtime to that header. It uses Python 3.9+ and only the standard library.

One command from the repository root demonstrates it offline on a saved **real ZTO** observation:

```sh
python3 -B line-3/tools/code-proof/code_proof.py --bundle line-3/tools/code-proof/zto-proof.json
```

Expected: `state_inclusion_verified: true`, one account, two proven proxy slots, and `anchor: unanchored-rpc-header`. Try the same command with `imd-proof.json` to check IMD. Keep the sibling `code-lens/` directory: its verifier, read-only RPC transport and Keccak implementation are ordinary committed dependencies. No install or network is needed for these commands.

## What this adds

Code Lens's existing hash checks detect internally inconsistent reports. Code Proof additionally requires each runtime hash to match the code hash in a proven account, and each measured implementation/beacon slot to match a proven storage value under that account's storage root. The account proof then connects that storage root to the state root inside the RLP header, whose Keccak hash must match the observation's block hash. Missing proof nodes fail; they never silently mean a zero slot. Valid non-inclusion proofs establish zero storage. Extra, duplicate, oversized and noncanonical evidence is refused.

The trie verifier handles branches, extensions, leaves, inline child nodes and hashed child nodes. It hashes the 20-byte account address and the full 32-byte storage key using Ethereum Keccak, rather than NIST SHA3. Proof order does not matter, but every supplied proof node must be used. Work is bounded by the 64-nibble secure key, 128 nodes per proof, 2,048 bytes per node, 65,536 proof bytes, and the inherited 100,000-byte report limit. Supported header field counts are 15, 16, 17, 20 and 21, through Prague's `requestsHash`; unsupported future headers fail verification.

## What happened when tried

Live public reads checked **ZTO first, then IMD**, at Ethereum block **26,185,280** (`0x18f8e40`), reported finalized by the selected RPC:

- Block hash: `0x57f561e7217307ab29f9fc3563627b97b97242261522b70429f2a873cf2593fd`.
- State root: `0x1c5813cfa4438e08260256d1bc9d4c08321cb97ee1653200a7d53feeb61dc634`.
- ZTO runtime: 1,287 bytes, hash `0x24e03ed7d7d3d6dc010b9a9836e419a3eb4215383b463f4e6685b4816435f16d`.
- IMD runtime: 22,990 bytes, hash `0x79a1ae149d27d4aae006d4dd75cb834222c9623799bbf34359428aaf66fec3bf`.

Both account proofs and both measured zero proxy slots per account verified. Neither observation has a supported proxy signal. The complete raw bundles are saved as `zto-proof.json` and `imd-proof.json`; they replay without network. Proof collection used the assignment-provided Ethereum relay. Public attribution is [Ethereum PublicNode](https://ethereum-rpc.publicnode.com); the bundle explicitly labels relay transport and does not claim to identify its upstream. The relay URL is absent from the delivered evidence.

Thirty new offline tests passed, including the real bundles, forged runtime with self-consistent auxiliary hashes, corrupted/missing nodes, nonzero synthetic beacon storage, missing implementation account evidence, embedded children, non-inclusion, canonical RLP rejection, header reconstruction, a wrong external anchor and a reorg during collection. The 32 ancestor tests also passed. Test fixtures involving fabricated headers or proxy state are tests only, never chain observations.

```sh
python3 -B -m unittest discover -s line-3/tools/code-proof -p 'test_*.py' -v
```

## Anchoring and limits

A proof can bind data to an invented header. Without an independently trusted block hash the result is explicitly **unanchored**. A worker with a block hash from their own independently verified chain view can pass `--expect-block-hash` to require that exact hash. That value is never guessed or selected by this tool. A mismatch exits 1 with no partial result. Passing a hash copied from this same bundle exercises comparison, but supplies no independent trust.

Even with a genuine trusted block hash, Code Proof does not verify consensus or finality itself, audit contract safety, prove source-code equivalence, enumerate custom/diamond/EIP-7702 delegation, or prove routing reachability. Beacon account code can be proven, but its `implementation()` **call result is not a storage proof**. The output lists every such address in `unproven_beacon_call_results`; downstream candidate code is proven at its address without claiming the beacon actually returns that address. Unmeasured storage, upgrade authorization and later changes remain outside this check. No finding grants permission to spend or transact.

## Fresh collection

An outside worker can collect a new finalized ZTO bundle:

```sh
python3 -B line-3/tools/code-proof/code_proof.py --live --save-bundle line-3/tools/code-proof/fresh-proof.json
```

PublicNode is the default; `--rpc https://eth.drpc.org` is the other supported public endpoint. A worker with an assignment-provided loopback Ethereum relay supplies its endpoint with `--rpc`. The live checks in this assignment used that relay as required. `--token IMD` selects IMD; `--address` accepts a specific nonzero contract address. All state reads and proofs are pinned with `blockHash` and `requireCanonical`; the block is rechecked after collection. A provider lacking hash-pinned proofs fails explicitly, with no fallback to latest or partial bundle. Archive state/proof availability depends on the provider.

The tool only sends allowlisted read-only RPC requests, with the inherited Pepeolithic User-Agent, no redirects, no environment-derived proxy configuration and 25-second per-request timeouts. There is no signing, transaction submission, payment, publishing, wallet/secret access or deployment. File inputs/outputs must resolve inside the current workspace; saved bundles cannot overwrite an existing file. Exit 0 means proof verification within the stated scope; exit 1 means invalid, unavailable or conflicting evidence.

Design references: [EIP-1186](https://eips.ethereum.org/EIPS/eip-1186) defines the proof response and non-inclusion semantics; [Ethereum's Merkle Patricia trie documentation](https://ethereum.org/developers/docs/data-structures-and-encoding/patricia-merkle-trie/) describes secure keys, compact paths, node references and account/storage contents. The implementation is local, with no fetched code dependency.

The mark's meaning: Pepe follows the branching code stones down to one root.
