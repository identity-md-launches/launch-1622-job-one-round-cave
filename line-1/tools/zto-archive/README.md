# ZTO Archive

Validate a complete, block-pinned ZTO/IMD Path snapshot or collect a new one from an ordered list of archive RPC endpoints. Each attempt is self-contained: initialization, pool state, tick bitmap and tick data must all come from the **same endpoint** and be pinned to one block hash. A failed endpoint contributes no data to a later fallback.

## One command to see it working

From the repository root, with Python 3.10+ and no installation or network:

```sh
python3 -B line-1/tools/zto-archive/zto_archive.py --snapshot line-1/tools/zto-path/observation.json
```

It validates the bundled real historical ZTO/IMD observation and prints its selected HTTPS source, exact block hash, active tick/liquidity summary and the no-mixing invariant. The bundled snapshot is historical evidence, not a current price.

For a fresh read, use `--live --rpc https://ethereum-rpc.publicnode.com --rpc https://eth.drpc.org --save-observation line-1/tools/zto-archive/new-observation.json`. Sources are tried in order; the first source that can independently return the full pinned observation is selected. This tool never combines an initialization log from one provider with state or ticks from another. It only uses public read-only RPC methods inherited from ZTO Path, never reads environment variables, and has no key, wallet, signing, sending or payment capability.

## What happened when tried

The offline command completed against the bundled real observation. All 6 tests passed: real-snapshot validation, tamper refusal, fallback isolation, honest all-provider failure, offline/no-network behavior, and invalid option handling.

```sh
python3 -B -m unittest discover -s line-1/tools/zto-archive -p 'test_*.py' -v
```

The output is selection evidence, not an archive provider guarantee or a state proof. A selected provider can still be stale, unavailable later, or wrong; the tool does not compare providers, calculate a quote, prepare calldata, guarantee execution, or simulate router settlement, token behavior, gas or MEV. Keep sibling `zto-path/` and `zto-band/` folders alongside this tool: they are ordinary standard-library source dependencies.
