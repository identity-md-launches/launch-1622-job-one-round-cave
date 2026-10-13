# Call Witness

Ask two public Ethereum RPCs for the **same contract call at the same finalized block**. This helps a worker spot inconsistent provider answers before treating one rehearsal as evidence. It uses Python 3.9+ standard library only and the adjacent `call-changes/` tool from this line. No installation, account, key, wallet or transaction is needed.

From the repository root, run this offline demonstration of a saved real ZTO call:

```sh
python3 -B line-4/tools/call-witness/call_witness.py demo
```

It reports `agree` for ZTO `totalSupply()`. Both providers returned `1000000000000000000000000000` base units at Ethereum mainnet finalized block `0x18f8d21`, hash `0xa15b57ef67efc19a40505b4d28f5ed90bdcde23a17a315702c133c33b9d62593`. The two raw observations are in `zto-witness.json`; the command reinterprets them rather than trusting a saved verdict.

For a fresh read-only check, ZTO is the default:

```sh
python3 -B line-4/tools/call-witness/call_witness.py live
```

Use `live --token IMD` for the supplied real IMD contract. To check an **actual proposed call**, first save an observation with [Call Rehearsal](../call-rehearsal/README.md), supplying its real sender, target, calldata and value. Then run:

```sh
python3 -B line-4/tools/call-witness/call_witness.py live --from-observation path/to/rehearsal.json --save path/to/new-witness.json
```

By default the tool chooses the latest height finalized by both providers. A worker who needs a repeatable, already-finalized checkpoint can require one explicit hexadecimal height instead:

```sh
python3 -B line-4/tools/call-witness/call_witness.py live --block 0x18f8d21
```

Both providers must still report that exact header and must each have finalized at least that height. An unfinalized or malformed height stops before any `eth_call` is made.

`--save` creates one raw evidence bundle inside the current workspace and refuses to overwrite an existing file. Replay it offline with `replay path/to/new-witness.json`. The tool never sends or signs a transaction and does not obtain a sender, recipient or value for a custom call. It repeats precisely the baseline call fields and return interpretation.

## How it works

The tool confirms chain ID 1 at PublicNode and dRPC, selects the lower of their finalized heads (or checks an explicit height is finalized by both), and requires both providers to return the same header at that height. It then uses Call Changes to confirm target code and run `eth_call` at that exact canonical block hash on each provider. Both saved observations are validated and independently reinterpreted before comparison. A header mismatch stops the check. The endpoints, headers, call fields and raw outcomes remain in the bundle.

| Verdict | Exit | Meaning |
| --- | ---: | --- |
| `agree` | 0 | Same return bytes or same explicit revert bytes. This can include `false` or a revert. |
| `disagree` | 1 | Different return/revert evidence at the same block. Investigate; this is inconsistent evidence, not a state change. |
| `inconclusive` | 2 | Missing revert bytes, unexpected ABI bytes or an RPC failure prevented comparison. |
| Input or transport error | 2 | JSON error on stderr; no verdict claimed. |

## What happened when tried

On 2026-10-13, `live --save line-4/tools/call-witness/zto-witness.json` completed in about one second against both public endpoints and returned `agree`. The saved block and value above came from those calls. `live --token IMD` also returned `agree` at finalized block `0x18f8d41`, with both providers reporting `4174529951491000000000000` base units. The offline `demo` exited 0. On this contribution, `live --block 0x18f8d21` confirmed the common header but returned `inconclusive`: dRPC returned the saved ZTO value while PublicNode reported that its historical state was unavailable. That is an honest non-success result, not an agreement claim. The focused tests cover a conflicting result, a different block, a duplicate provider, a mismatched finalized header, explicit shared-block selection, and rejection of an unfinalized requested height. These failure examples are synthetic; no live disagreement was observed.

```sh
python3 -B -m unittest discover -s line-4/tools/call-witness -p 'test_*.py' -v
```

## Limits

RPC responses are provider claims, not cryptographic proofs of execution or provider independence. Equal bytes do not establish equal side effects, gas use, balances, permissions, code identity, safety or future inclusion. Provider-default gas and fee context may differ for a custom call. A historic state query may be unavailable later. No trace or receipt is produced. A returned `false` and identical reverts are still only agreement about those results.

The shared transport accepts only `eth_chainId`, `eth_getBlockByNumber`, `eth_getCode` and `eth_call`, disables redirects and environment proxy discovery, bounds RPC responses to 90 KB, and sends `Pepeolithic-CallRehearsal/1.0` as its User-Agent. Saved witness bundles are capped at 95 KB. Each HTTP request has a 25-second socket timeout; there is no total deadline in the shipped CLI. No keys, wallet files, environment variables, signatures, payments, broadcasts or deployments are used.

Protocol references: [EIP-1898 block-hash state queries](https://eips.ethereum.org/EIPS/eip-1898) and [Ethereum JSON-RPC methods](https://ethereum.org/developers/docs/apis/json-rpc/).
