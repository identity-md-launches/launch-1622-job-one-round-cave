#!/usr/bin/env python3
"""Compare one rehearsed Ethereum call across two public RPCs at one finalized block."""
import argparse
import json
from pathlib import Path
import sys

# Reuse the line's reviewed, bounded call collector and interpreter.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'call-changes'))
import call_changes as changes

core = changes.core
HERE = Path(__file__).resolve().parent
SCHEMA = 'call-witness-v1'
MAX_BUNDLE = 95_000


def common_finalized(left, right, block='finalized'):
    """Choose a mutually finalized requested height and verify its header agrees."""
    block = changes.block_selector(block)
    heads = []
    for rpc in (left, right):
        core.require(rpc.call('eth_chainId', []) == '0x1', 'expected Ethereum mainnet')
        heads.append(core.header(rpc.call('eth_getBlockByNumber', ['finalized', False])))
    height = (min(core.quantity(head['number']) for head in heads) if block == 'finalized'
              else core.quantity(block))
    core.require(all(height <= core.quantity(head['number']) for head in heads),
                 'requested block is newer than a provider finalized head')
    selected = []
    for rpc, head in zip((left, right), heads):
        if core.quantity(head['number']) == height:
            selected.append(head)
        else:
            selected.append(core.header(rpc.call('eth_getBlockByNumber', [hex(height), False])))
    core.require(selected[0]['number'] == selected[1]['number'] == hex(height),
                 'providers returned the wrong common height')
    core.require(selected[0] == selected[1],
                 'providers disagree on the common finalized block header')
    return selected[0]


def witness(observations):
    core.require(isinstance(observations, list) and len(observations) == 2,
                 'exactly two observations required')
    a, b = observations
    core.require(isinstance(a, dict) and isinstance(b, dict),
                 'each observation must be an object')
    core.require(a.get('source') == core.ENDPOINTS[0] and
                 b.get('source') == core.ENDPOINTS[1],
                 'observations must use the two distinct supported RPCs in order')
    comparison = changes.compare(a, b)
    core.require(comparison['same_block'] and not comparison['same_provider'],
                 'observations must be from distinct RPCs at the same block')
    verdict = {'unchanged': 'agree', 'inconsistent_observations': 'disagree',
               'inconclusive': 'inconclusive'}[comparison['verdict']]
    return {
        'schema': SCHEMA, 'verdict': verdict, 'reason': comparison['reason'],
        'block': comparison['before']['block'], 'call': comparison['call'],
        'returns': comparison['returns'],
        'providers': [
            {'source': part['source'], 'result': part['result']}
            for part in (comparison['before'], comparison['after'])
        ],
        'limits': 'Two unauthenticated public RPC observations at one finalized block. '
                  'Agreement of return or revert bytes does not prove safety, gas, state '
                  'effects, provider independence, or future execution. Nothing sent.',
    }


def capture_pair(tx, returns, clients=None, block='finalized'):
    tx = core.transaction(tx)
    core.require(returns in ('raw', 'bool', 'uint256'), 'unsupported return interpretation')
    left, right = clients or tuple(core.RPC(endpoint) for endpoint in core.ENDPOINTS)
    selected = common_finalized(left, right, block)
    block = selected['number']
    observations = [changes.capture(rpc, tx, returns, block) for rpc in (left, right)]
    core.require(all(core.header(obs['block']) == selected for obs in observations),
                 'captured block differs from the agreed finalized header')
    witness(observations)
    return observations


def encoded_bundle(observations):
    witness(observations)
    raw = (json.dumps({'schema': SCHEMA, 'observations': observations},
                      indent=2, allow_nan=False) + '\n').encode()
    core.require(len(raw) <= MAX_BUNDLE, 'witness bundle exceeds 95 KB')
    return raw


def load_bundle(path):
    with core.workspace_path(path).open('rb') as handle:
        raw = handle.read(MAX_BUNDLE + 1)
    core.require(len(raw) <= MAX_BUNDLE, 'witness bundle exceeds 95 KB')
    value = json.loads(raw, object_pairs_hook=changes.no_duplicates,
                       parse_constant=changes.reject_constant)
    core.require(isinstance(value, dict) and set(value) == {'schema', 'observations'}
                 and value['schema'] == SCHEMA, 'invalid witness bundle')
    witness(value['observations'])
    return value['observations']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    commands.add_parser('demo', help='replay saved real ZTO observations offline')
    replay = commands.add_parser('replay', help='replay a saved raw witness bundle')
    replay.add_argument('bundle')
    live = commands.add_parser('live', help='read two public RPCs; no transaction sent')
    live.add_argument('--token', choices=core.TOKENS, default='ZTO')
    live.add_argument('--from-observation', help='reuse exact call and return type from a saved rehearsal')
    live.add_argument('--block', default='finalized',
                      help='finalized or a canonical hexadecimal block number finalized by both providers')
    live.add_argument('--save', help='create a new raw witness bundle within the workspace')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'demo':
            observations = load_bundle(HERE / 'zto-witness.json')
        elif args.mode == 'replay':
            observations = load_bundle(args.bundle)
        else:
            if args.from_observation:
                baseline = changes.load_observation(args.from_observation)
                tx, returns = baseline['call'], baseline['returns']
            else:
                tx = {'to': core.TOKENS[args.token], 'data': '0x18160ddd', 'value': '0x0'}
                returns = 'uint256'
            destination = core.workspace_path(args.save) if args.save else None
            if destination:
                core.require(not destination.exists(), 'save destination already exists')
                core.require(destination.parent.is_dir(), 'save parent directory does not exist')
            observations = capture_pair(tx, returns, block=changes.block_selector(args.block))
            if destination:
                with destination.open('xb') as handle:
                    handle.write(encoded_bundle(observations))
        result = witness(observations)
        print(json.dumps(result, indent=2, allow_nan=False))
        return {'agree': 0, 'disagree': 1, 'inconclusive': 2}[result['verdict']]
    except (ValueError, KeyError, TypeError, OSError, RecursionError, core.RPCError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
