#!/usr/bin/env python3
"""Keep every known ERC-20 permission across observations, then recheck their union."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'permission-gate'))
import permission_gate as gate
changes, lens = gate.changes, gate.lens
MAX_INPUTS = 16
IDENTITY = ('chain_id', 'token', 'token_address', 'decimals')
DEFAULTS = (HERE.parent / 'allowance-lens' / 'observation.json',
            HERE.parent / 'allowance-changes' / 'lens-recheck.json',
            HERE.parent / 'permission-gate' / 'live-observation.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def inventory(values):
    """Union identities, never mix historical balances into a current-state snapshot."""
    lens.require(isinstance(values, list) and 1 <= len(values) <= MAX_INPUTS,
                 'supply 1..16 raw observations or inventories')
    checked = [changes.flatten(value) for value in values]
    first = checked[0]
    headers, states, balances, members, inputs = {}, {}, {}, {}, []
    for value, measured in zip(values, checked):
        lens.require(all(measured[k] == first[k] for k in IDENTITY),
                     'all inputs must share chain, token and decimals')
        number = measured['block_number']
        block = (measured['block_hash'], measured['block_time_utc'])
        lens.require(number not in headers or headers[number] == block,
                     'conflicting headers at the same height')
        headers[number] = block
        fingerprint = digest(value)
        inputs.append({'sha256_canonical_json': fingerprint,
                       **changes.block_summary(measured), 'pair_count': len(measured['pairs'])})
        for pair, row in measured['pairs'].items():
            key = (number, pair)
            state = changes.state(row)
            lens.require(key not in states or states[key] == state,
                         'conflicting pair state at the same block')
            states[key] = state
            balance_key = (number, pair[0])
            lens.require(balance_key not in balances or balances[balance_key] == row['balance_raw'],
                         'conflicting owner balance at the same block')
            balances[balance_key] = row['balance_raw']
            members.setdefault(pair, set()).add(fingerprint)
    lens.require(len(members) <= lens.MAX_PAIRS, 'union exceeds 64 pairs; partition the inputs')
    ordered = sorted(headers)
    lens.require(all(headers[a][1] <= headers[b][1] for a, b in zip(ordered, ordered[1:])),
                 'block timestamps go backwards')
    return {
        'schema': 'allowance-union-plan-v1', **{k: first[k] for k in IDENTITY},
        'status': 'requires_recheck' if members else 'empty_inventory',
        'complete_wallet_audit': False,
        'pair_count': len(members), 'owner_count': len({p[0] for p in members}),
        'inputs': sorted(inputs, key=lambda item: (item['block_number'], item['sha256_canonical_json'])),
        'pairs': [{'owner': pair[0], 'spender': pair[1], 'source_sha256': sorted(sources)}
                  for pair, sources in sorted(members.items())],
        'limitations': [
            'This is a union of known identities, not a current allowance or permission-policy decision.',
            'Zero allowances and pairs absent from later scans remain in the recheck inventory.',
            'Empty scans do not clear older pairs; unknown spenders outside supplied evidence remain unknown.',
            'Recheck all listed pairs at one block before passing evidence to a policy checker.',
            'Permit2 sub-permissions, unused signatures and custom token authorizations are omitted.',
            'Input hashes bind normalized JSON content; RPC evidence is not a cryptographic chain proof.',
        ],
    }


def assess(values, after):
    plan = inventory(values)
    measured = changes.flatten(after)
    lens.require(all(measured[k] == plan[k] for k in IDENTITY),
                 'recheck chain, token or decimals differ')
    lens.require(measured['block_number'] >= max(i['block_number'] for i in plan['inputs']),
                 'recheck predates an input block')
    lens.require(measured['block_time_utc'] >= max(i['block_time_utc'] for i in plan['inputs']),
                 'recheck timestamp predates an input')
    # Also rejects contradictions when an input and the recheck have the same block.
    # Use pairwise validation so 16 input files still permit one recheck file.
    for value in values:
        inventory([value, after])
    wanted = {(row['owner'], row['spender']) for row in plan['pairs']}
    missing = wanted - set(measured['pairs'])
    complete = bool(wanted) and not missing
    return {
        'schema': 'allowance-union-check-v1',
        'status': 'all_known_pairs_rechecked' if complete else 'incomplete_recheck',
        **{k: plan[k] for k in IDENTITY}, 'complete_wallet_audit': False,
        'required_pair_count': len(wanted), 'measured_pair_count': len(measured['pairs']),
        'known_pairs_measured': len(wanted & set(measured['pairs'])),
        'missing_pairs': [{'owner': a, 'spender': b} for a, b in sorted(missing)],
        'additional_measured_pairs': len(set(measured['pairs']) - wanted),
        'block': changes.block_summary(measured),
        'active_known_pairs': sum(int(measured['pairs'][p]['allowance_raw']) > 0
                                  for p in wanted & set(measured['pairs'])),
        'policy_approval': None,
        'limitations': ['Coverage only: rechecked pairs can still have active or excessive permissions.',
                        'No wall-clock freshness, wallet completeness, current canonicality or future-state guarantee.',
                        'Use the raw recheck with Permission Gate and an explicit policy to decide limits.'],
    }


class UnionRPC(lens.RPC):
    """Reuse the ancestor read-only transport; restrict new live work to public endpoints."""
    def __init__(self, endpoint):
        lens.require(endpoint in lens.PUBLIC_ENDPOINTS, 'use a supported public Ethereum endpoint')
        super().__init__(endpoint)


def refresh(rpc, values, block_tag='finalized'):
    plan = inventory(values)
    lens.require(plan['pairs'], 'cannot refresh an empty union')
    lens.require(block_tag in ('finalized', 'safe', 'latest') or
                 (isinstance(block_tag, str) and block_tag.startswith('0x')
                  and lens.quantity(block_tag) >= 0), 'invalid block selector')
    lens.require(rpc.call('eth_chainId', []) == '0x1', 'expected Ethereum chain 1')
    unique_blocks = {item['block_number']: item for item in plan['inputs']}
    for number, item in sorted(unique_blocks.items()):
        actual = lens.header(rpc.call('eth_getBlockByNumber', [hex(number), False]))
        expected_time = next(value['block']['timestamp']
                             for bundle in values
                             for value in (bundle['observations'] if bundle.get('schema') == changes.BUNDLE_SCHEMA
                                           else [bundle])
                             if lens.quantity(value['block']['number']) == number)
        lens.require(lens.quantity(actual['number']) == number
                     and actual['hash'] == item['block_hash'] and actual['timestamp'] == expected_time,
                     'input block is no longer canonical or header differs')
    block = lens.header(rpc.call('eth_getBlockByNumber', [block_tag, False]))
    if block_tag.startswith('0x'):
        lens.require(lens.quantity(block['number']) == lens.quantity(block_tag),
                     'RPC returned a different requested block')
    lens.require(lens.quantity(block['number']) >= max(unique_blocks), 'refresh predates an input block')
    # Read shared metadata once, and each balance/allowance only once. All
    # calls use the selected canonical hash, including across different owners.
    pin = {'blockHash': block['hash'], 'requireCanonical': True}

    def call(data):
        return rpc.call('eth_call', [{'to': plan['token_address'], 'data': data}, pin])

    decimals = call('0x313ce567')
    lens.require(lens.word(decimals) == plan['decimals'], 'token decimals changed')
    observations = []
    for owner in sorted({row['owner'] for row in plan['pairs']}):
        spenders = [row['spender'] for row in plan['pairs'] if row['owner'] == owner]
        balance_data = '0x70a08231' + lens.address_arg(owner)
        raw = {'decimals': decimals,
               'balances': [{'owner': owner, 'data': balance_data, 'result': call(balance_data)}],
               'allowances': []}
        for spender in spenders:
            data = '0xdd62ed3e' + lens.address_arg(owner) + lens.address_arg(spender)
            raw['allowances'].append({'owner': owner, 'spender': spender,
                                      'data': data, 'result': call(data)})
        number = lens.quantity(block['number'])
        observed = {'schema': lens.SCHEMA, 'source': rpc.endpoint, 'chain_id': 1,
                    'token': plan['token'], 'token_address': plan['token_address'], 'block': block,
                    'query': {'mode': 'explicit_pairs', 'from_block': number, 'to_block': number,
                              'owner': owner, 'spenders': spenders},
                    'logs': [], 'log_headers': {}, 'raw': raw}
        lens.report(observed)
        observations.append(observed)
    final = lens.header(rpc.call('eth_getBlockByNumber', [block['number'], False]))
    lens.require(final == block, 'refresh block changed during capture')
    result = {'schema': changes.BUNDLE_SCHEMA, 'observations': observations}
    lens.require(assess(values, result)['status'] == 'all_known_pairs_rechecked',
                 'refresh did not measure the full union')
    return result


def refresh_endpoint(endpoint, values, block_tag):
    return refresh(UnionRPC(endpoint), values, block_tag)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', action='append', help='raw evidence file; repeat up to 16 times')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--after', help='offline raw recheck to assess against the union')
    mode.add_argument('--refresh', action='store_true', help='read the union at one Ethereum block')
    parser.add_argument('--rpc', choices=sorted(lens.PUBLIC_ENDPOINTS), default=lens.PUBLIC_RPC)
    parser.add_argument('--block', default='finalized', help='finalized, safe, latest, or decimal block')
    parser.add_argument('--timeout', type=float, default=90, help='total live deadline in seconds, at most 600')
    parser.add_argument('--save', help='new workspace file for complete raw refresh evidence')
    args = parser.parse_args(argv)
    try:
        lens.require(not (args.after or args.refresh) or args.input,
                     '--after and --refresh require explicit --input evidence')
        paths = args.input or DEFAULTS
        lens.require(1 <= len(paths) <= MAX_INPUTS, 'supply 1..16 input files')
        values = [gate.load(path) for path in paths]
        inventory(values)  # Validate the entire union before network access.
        if args.refresh:
            tag = hex(int(args.block)) if args.block.isdecimal() else args.block
            after = lens.run_bounded(refresh_endpoint, (args.rpc, values, tag), timeout=args.timeout)
            result = assess(values, after)
            if args.save:
                changes.save(args.save, after)
        else:
            lens.require(not args.save and args.rpc == lens.PUBLIC_RPC
                         and args.block == 'finalized' and args.timeout == 90,
                         'RPC, block, timeout and save options require --refresh')
            result = assess(values, gate.load(args.after)) if args.after else inventory(values)
        result['demonstration'] = not bool(args.input)
        print(json.dumps(result, indent=2))
        return 4 if result['status'] in ('incomplete_recheck', 'empty_inventory') else 0
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
