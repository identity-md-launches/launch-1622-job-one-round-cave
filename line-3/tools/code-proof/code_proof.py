#!/usr/bin/env python3
"""Bind Code Lens runtime and proxy slots to a block-header state commitment."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code-lens'))
import code_lens as lens
from keccak import keccak256

require = lens.require
SCHEMA = 'code-proof-v1'
EMPTY_TRIE = keccak256(b'\x80')
MAX_NODES = 128
HEADER_FIELDS = [
    ('parentHash', 32), ('sha3Uncles', 32), ('miner', 20), ('stateRoot', 32),
    ('transactionsRoot', 32), ('receiptsRoot', 32), ('logsBloom', 256),
    ('difficulty', None), ('number', None), ('gasLimit', None), ('gasUsed', None),
    ('timestamp', None), ('extraData', -1), ('mixHash', 32), ('nonce', 8),
    ('baseFeePerGas', None), ('withdrawalsRoot', 32), ('blobGasUsed', None),
    ('excessBlobGas', None), ('parentBeaconBlockRoot', 32), ('requestsHash', 32),
]
HEADER_COUNTS = {15, 16, 17, 20, 21}


def hex_bytes(value, maximum=2048):
    require(isinstance(value, str) and len(value) <= 2 + maximum * 2
            and re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', value), 'invalid bounded hex bytes')
    return bytes.fromhex(value[2:])


def integer_bytes(value):
    require(type(value) is int and 0 <= value < 2**256, 'integer outside uint256')
    return value.to_bytes((value.bit_length() + 7) // 8, 'big')


def scalar(value):
    require(isinstance(value, bytes) and len(value) <= 32
            and (not value or value[0] != 0), 'noncanonical or oversized RLP integer')
    return int.from_bytes(value, 'big')


def rlp_encode(value):
    if isinstance(value, list):
        payload = b''.join(rlp_encode(item) for item in value)
        prefix = 0xc0
    else:
        require(isinstance(value, bytes), 'RLP item must be bytes or list')
        if len(value) == 1 and value[0] < 0x80:
            return value
        payload, prefix = value, 0x80
    if len(payload) <= 55:
        return bytes([prefix + len(payload)]) + payload
    length = integer_bytes(len(payload))
    return bytes([prefix + 55 + len(length)]) + length + payload


def rlp_decode(data):
    """Canonical, bounded recursive length-prefix decoding."""
    require(isinstance(data, bytes) and 0 < len(data) <= 65536, 'invalid RLP input size')

    def item(offset, limit, depth):
        require(depth <= 32 and offset < limit, 'truncated or deeply nested RLP')
        head = data[offset]
        if head < 0x80:
            return data[offset:offset + 1], offset + 1
        is_list = head >= 0xc0
        short_base = 0xc0 if is_list else 0x80
        length = head - short_base
        start = offset + 1
        if length > 55:
            width = length - 55
            require(width <= 8 and start + width <= limit and data[start] != 0,
                    'noncanonical or truncated RLP length')
            length = int.from_bytes(data[start:start + width], 'big')
            require(length > 55, 'noncanonical long RLP')
            start += width
        end = start + length
        require(end <= limit, 'truncated RLP payload')
        if not is_list:
            require(not (length == 1 and data[start] < 0x80), 'noncanonical short RLP')
            return data[start:end], end
        values, cursor = [], start
        while cursor < end:
            child, cursor = item(cursor, end, depth + 1)
            values.append(child)
        return values, end

    result, end = item(0, len(data), 0)
    require(end == len(data), 'trailing RLP bytes')
    return result


def nibbles(data):
    return [part for byte in data for part in (byte >> 4, byte & 15)]


def compact_path(data):
    require(isinstance(data, bytes) and data, 'missing compact trie path')
    parts = nibbles(data)
    flag = parts[0]
    require(flag <= 3 and (flag & 1 or parts[1] == 0), 'invalid compact trie flags/padding')
    path = parts[1:] if flag & 1 else parts[2:]
    leaf = bool(flag & 2)
    require(leaf or path, 'empty extension path')
    return leaf, path


def trie_lookup(root, key, proof):
    """Return the proven raw trie value, or None for proven non-inclusion.

    Keys here are already Keccak-hashed 32-byte secure-trie keys. Nodes may
    arrive in any order; every supplied node must be used. Missing nodes
    are errors, never evidence of an absent value.
    """
    require(isinstance(root, bytes) and len(root) == 32
            and isinstance(key, bytes) and len(key) == 32, 'invalid trie root/key')
    require(isinstance(proof, list) and len(proof) <= MAX_NODES, 'too many proof nodes')
    nodes = {}
    for encoded in proof:
        raw = hex_bytes(encoded)
        digest = keccak256(raw)
        require(raw and digest not in nodes, 'empty or duplicate proof node')
        nodes[digest] = raw
    require(sum(len(raw) for raw in nodes.values()) <= 65536, 'proof exceeds byte bound')
    if root == EMPTY_TRIE:
        require(not nodes or nodes == {EMPTY_TRIE: b'\x80'}, 'invalid empty trie proof')
        return None
    used, path, offset, ref = set(), nibbles(key), 0, root

    def finish(value):
        require(used == set(nodes), 'unused proof nodes')
        return value

    for step in range(66):
        if isinstance(ref, list):
            raw = rlp_encode(ref)
            require(len(raw) < 32, 'oversized embedded trie node')
            digest = keccak256(raw)
            if digest in nodes:
                require(nodes[digest] == raw, 'embedded node mismatch')
                used.add(digest)
            node = ref
        else:
            require(isinstance(ref, bytes) and len(ref) == 32, 'invalid trie child reference')
            require(ref in nodes, 'missing proof node')
            require(ref not in used, 'cyclic trie proof')
            used.add(ref)
            raw = nodes[ref]
            require(step == 0 or len(raw) >= 32, 'noncanonical hashed short child')
            node = rlp_decode(raw)
        require(isinstance(node, list), 'trie node is not a list')
        if len(node) == 17:
            require(isinstance(node[16], bytes), 'invalid branch value')
            require(all(isinstance(child, list) or isinstance(child, bytes)
                        and len(child) in (0, 32) for child in node[:16]), 'invalid branch child')
            if offset == len(path):
                return finish(node[16] or None)
            ref = node[path[offset]]
            offset += 1
            if ref == b'':
                return finish(None)
        elif len(node) == 2:
            leaf, suffix = compact_path(node[0])
            require(offset + len(suffix) <= 64, 'trie path exceeds secure key')
            if leaf:
                require(isinstance(node[1], bytes) and node[1], 'invalid leaf value')
                require(offset + len(suffix) == 64, 'leaf does not end at secure key length')
            else:
                require(isinstance(node[1], list) or isinstance(node[1], bytes)
                        and len(node[1]) == 32, 'invalid extension child')
            if path[offset:offset + len(suffix)] != suffix:
                return finish(None)
            offset += len(suffix)
            if leaf:
                return finish(node[1])
            ref = node[1]
        else:
            raise ValueError('invalid trie node arity')
    raise ValueError('trie traversal exceeds secure-key bound')


def encode_header(header):
    values, missing = [], False
    for name, width in HEADER_FIELDS:
        if name not in header or header[name] is None:
            missing = True
            continue
        require(not missing, 'header has a gap in fork fields')
        if width is None:
            value = integer_bytes(lens.quantity(header[name]))
        elif width == -1:
            value = hex_bytes(header[name], 32)
        else:
            value = bytes.fromhex(lens.fixed_hex(header[name], width)[2:])
        values.append(value)
    require(len(values) in HEADER_COUNTS, 'unsupported header fork field count')
    raw = rlp_encode(values)
    require(lens.digest(raw) == lens.fixed_hex(header['hash'], 32), 'reconstructed header hash mismatch')
    return '0x' + raw.hex()


def verify_header(encoded, block, expected_hash=None):
    raw = hex_bytes(encoded)
    header = rlp_decode(raw)
    require(isinstance(header, list) and len(header) in HEADER_COUNTS, 'unsupported header fork field count')
    for value, (name, width) in zip(header, HEADER_FIELDS):
        if width is None:
            scalar(value)
        else:
            require(isinstance(value, bytes) and (len(value) <= 32 if width == -1
                    else len(value) == width), 'invalid header field: ' + name)
    digest = lens.digest(raw)
    require(digest == lens.fixed_hex(block['hash'], 32), 'header hash does not match observation')
    require(scalar(header[8]) == lens.quantity(block['number']), 'header height does not match observation')
    if expected_hash is not None:
        require(digest == lens.fixed_hex(expected_hash, 32), 'independent block hash does not match')
    return header[3]


def requirements(observation):
    """All observed path runtimes plus any beacon runtimes; no skipped nodes."""
    targets = {}
    for node in observation['nodes']:
        target, code_hash = lens.address(node['address']), lens.fixed_hex(node['code_hash'], 32)
        entry = targets.setdefault(target, {'code_hash': code_hash, 'slots': {}})
        require(entry['code_hash'] == code_hash, 'conflicting observed runtime')
        entry['slots'].update({lens.SLOTS[name]: int(value, 16)
                               for name, value in node['storage'].items()})
        if 'beacon' in node:
            beacon = node['beacon']
            target, code_hash = lens.address(beacon['address']), lens.fixed_hex(beacon['code_hash'], 32)
            entry = targets.setdefault(target, {'code_hash': code_hash, 'slots': {}})
            require(entry['code_hash'] == code_hash, 'conflicting beacon runtime')
    return targets


def slot_key(value):
    require(isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{1,64}', value), 'invalid storage proof key')
    return '0x' + int(value, 16).to_bytes(32, 'big').hex()


def verify(bundle, expected_hash=None):
    require(bundle['schema'] == SCHEMA, 'wrong proof bundle schema')
    observation = bundle['observation']
    lens.verify(observation)
    root = verify_header(bundle['header_rlp'], observation['block'], expected_hash)
    targets = requirements(observation)
    proofs = bundle['proofs']
    require(isinstance(proofs, list) and len(proofs) == len(targets), 'missing or extra account proofs')
    seen, checked = set(), []
    for proof in proofs:
        target = lens.address(proof['address'])
        require(target in targets and target not in seen, 'unexpected or duplicate proof address')
        seen.add(target)
        want = targets[target]
        value = trie_lookup(root, keccak256(bytes.fromhex(target[2:])), proof['accountProof'])
        require(value is not None, 'runtime account is absent from state')
        account = rlp_decode(value)
        require(isinstance(account, list) and len(account) == 4, 'invalid account RLP')
        nonce, balance = scalar(account[0]), scalar(account[1])
        require(isinstance(account[2], bytes) and len(account[2]) == 32
                and isinstance(account[3], bytes) and len(account[3]) == 32, 'invalid account roots')
        require(nonce == lens.quantity(proof['nonce']) and balance == lens.quantity(proof['balance']),
                'account scalar fields do not match proof')
        require('0x' + account[3].hex() == lens.fixed_hex(proof['codeHash'], 32)
                == want['code_hash'], 'proven code hash does not match observed runtime')
        require('0x' + account[2].hex() == lens.fixed_hex(proof['storageHash'], 32),
                'proven storage root mismatch')
        entries = proof['storageProof']
        require(isinstance(entries, list) and len(entries) == len(want['slots']), 'missing or extra storage proofs')
        slots_seen = set()
        for entry in entries:
            key = slot_key(entry['key'])
            require(key in want['slots'] and key not in slots_seen, 'unexpected or duplicate storage key')
            slots_seen.add(key)
            raw_value = trie_lookup(account[2], keccak256(bytes.fromhex(key[2:])), entry['proof'])
            number = 0 if raw_value is None else scalar(rlp_decode(raw_value))
            require(raw_value is None or number != 0, 'zero storage must be proven absent')
            require(number == lens.quantity(entry['value']) == want['slots'][key],
                    'proven storage value does not match observation')
        checked.append({'address': target, 'code_hash': want['code_hash'],
                        'proxy_slots_proven': len(slots_seen)})
    beacons = [node['beacon']['address'] for node in observation['nodes'] if 'beacon' in node]
    return {'schema': 'code-proof-result-v1', 'target': observation['target'],
            'block': observation['block'], 'state_root': '0x' + root.hex(),
            'state_inclusion_verified': True, 'accounts': checked,
            'anchor': 'caller-supplied-block-hash' if expected_hash else 'unanchored-rpc-header',
            'unproven_beacon_call_results': beacons,
            'provenance': lens.provenance(observation),
            'scope': 'Proofs bind runtime hashes and measured proxy slots to the reconstructed header. '
                     'Consensus/finality, supplied-anchor authenticity, beacon call results, '
                     'routing semantics and contract safety are not verified.'}


class ProofRPC(lens.RPC):
    METHODS = lens.RPC.METHODS | {'eth_getProof'}


def collect(rpc, target):
    observation = lens.collect(rpc, target)
    block = observation['block']
    header = rpc.call('eth_getBlockByNumber', [block['number'], False])
    require(isinstance(header, dict) and header['hash'].lower() == block['hash'], 'block changed before proofs')
    encoded = encode_header(header)
    pinned = {'blockHash': block['hash'], 'requireCanonical': True}
    proofs = [rpc.call('eth_getProof', [target, list(want['slots']), pinned])
              for target, want in requirements(observation).items()]
    after = rpc.call('eth_getBlockByNumber', [block['number'], False])
    require(isinstance(after, dict) and after['hash'].lower() == block['hash'], 'block changed during proofs')
    bundle = {'schema': SCHEMA, 'header_rlp': encoded, 'observation': observation, 'proofs': proofs}
    verify(bundle)
    require(len(json.dumps(bundle, indent=2).encode()) < lens.MAX_RESPONSE, 'bundle exceeds 100000 bytes')
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--bundle', help='offline workspace-local saved proof bundle')
    mode.add_argument('--live', action='store_true', help='collect finalized Ethereum proofs')
    parser.add_argument('--token', choices=['ZTO', 'IMD'], default='ZTO')
    parser.add_argument('--address', help='explicit Ethereum contract address')
    parser.add_argument('--rpc', default=lens.PUBLIC_RPC)
    parser.add_argument('--expect-block-hash', help='block hash obtained independently; never inferred')
    parser.add_argument('--save-bundle', help='new workspace-local JSON file; overwrite refused')
    args = parser.parse_args()
    try:
        require(args.live or not (args.address or args.token != 'ZTO' or args.save_bundle),
                'target selection and saving apply only to --live')
        destination = None
        if args.save_bundle:
            destination = Path(args.save_bundle).resolve()
            require(destination.is_relative_to(Path.cwd().resolve()), 'save path must be inside workspace')
            require(not destination.exists(), 'save path already exists')
        target = lens.address(args.address) if args.address else {'ZTO': lens.ZTO, 'IMD': lens.IMD}[args.token]
        bundle = collect(ProofRPC(args.rpc), target) if args.live else lens.read_report(args.bundle)
        result = verify(bundle, args.expect_block_hash)
        if destination:
            with destination.open('x', encoding='utf-8') as stream:
                stream.write(json.dumps(bundle, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, OverflowError, AttributeError) as error:
        print('Code Proof: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
