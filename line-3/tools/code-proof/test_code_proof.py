"""Offline proof checks; synthetic trie/header fixtures are never chain claims."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest

import code_proof as proof


def packed(path, leaf=True):
    parts = [2 * int(leaf) + len(path) % 2]
    if len(path) % 2 == 0:
        parts.append(0)
    parts += path
    return bytes((parts[i] << 4) | parts[i + 1] for i in range(0, len(parts), 2))


def encoded(node):
    return '0x' + proof.rlp_encode(node).hex()


def leaf_fixture(key, value):
    raw = proof.rlp_encode([packed(proof.nibbles(key)), value])
    return proof.keccak256(raw), ['0x' + raw.hex()]


def read_bundle(token='zto'):
    return json.loads((Path(__file__).parent / (token + '-proof.json')).read_text())


def synthetic_beacon_bundle():
    """Two synthetic accounts under an extension and branch, with nonzero storage."""
    bundle = read_bundle()
    observation = bundle['observation']
    zero = '0x' + '00' * 32
    word = '0x' + proof.lens.IMD[2:].rjust(64, '0')
    beacon_key = proof.keccak256(bytes.fromhex(proof.lens.SLOTS['beacon'][2:]))
    beacon_value = proof.rlp_encode(proof.integer_bytes(int(word, 16)))
    storage_root, storage_nodes = leaf_fixture(beacon_key, beacon_value)
    node = {'address': proof.lens.ZTO, 'code': '0x6000', 'code_bytes': 2,
            'code_hash': proof.lens.digest(b'\x60\x00'),
            'storage': {'implementation': zero, 'beacon': word},
            'kind': 'eip1967-beacon-candidate', 'next_address': proof.lens.IMD,
            'beacon': {'address': proof.lens.IMD, 'code': '0x6001',
                       'code_hash': proof.lens.digest(b'\x60\x01'), 'implementation_result': word}}
    terminal = {'address': proof.lens.IMD, 'code': '0x6001', 'code_bytes': 2,
                'code_hash': proof.lens.digest(b'\x60\x01'),
                'storage': {'implementation': zero, 'beacon': zero},
                'kind': 'no-supported-proxy-signal', 'next_address': None}
    observation['nodes'] = [node, terminal]
    observation['effective_address'] = terminal['address']
    observation['effective_code_hash'] = terminal['code_hash']
    branch, accounts, leaves = [b''] * 17, [], []
    for current, store_root in ((node, storage_root), (terminal, proof.EMPTY_TRIE)):
        path = proof.nibbles(proof.keccak256(bytes.fromhex(current['address'][2:])))
        # These two real address strings share first nibble 4, then differ e/f.
        account = proof.rlp_encode([b'\x01', b'', store_root,
                                    bytes.fromhex(current['code_hash'][2:])])
        leaf = proof.rlp_encode([packed(path[2:]), account])
        branch[path[1]] = proof.keccak256(leaf)
        leaves.append(leaf)
        slots = [{'key': key, 'value': hex(int(current['storage'][name], 16)),
                  'proof': storage_nodes if current is node else []}
                 for name, key in proof.lens.SLOTS.items()]
        accounts.append({'address': current['address'], 'nonce': '0x1', 'balance': '0x0',
                         'codeHash': current['code_hash'], 'storageHash': '0x' + store_root.hex(),
                         'storageProof': slots})
    branch_raw = proof.rlp_encode(branch)
    extension = proof.rlp_encode([b'\x14', proof.keccak256(branch_raw)])
    for account, leaf in zip(accounts, leaves):
        account['accountProof'] = ['0x' + raw.hex() for raw in (extension, branch_raw, leaf)]
    fields = proof.rlp_decode(bytes.fromhex(bundle['header_rlp'][2:]))
    fields[3] = proof.keccak256(extension)
    bundle['header_rlp'] = encoded(fields)
    observation['block']['hash'] = proof.lens.digest(proof.rlp_encode(fields))
    bundle['proofs'] = accounts
    return bundle


class ProofTests(unittest.TestCase):
    def test_real_zto_and_imd_proofs(self):
        for token in ('zto', 'imd'):
            bundle = read_bundle(token)
            result = proof.verify(bundle)
            self.assertTrue(result['state_inclusion_verified'])
            self.assertEqual(result['anchor'], 'unanchored-rpc-header')
            self.assertEqual(result['accounts'][0]['proxy_slots_proven'], 2)
            self.assertEqual(result['unproven_beacon_call_results'], [])
            self.assertEqual(result['accounts'][0]['code_hash'],
                             bundle['observation']['effective_code_hash'])

    def test_independent_anchor_must_match(self):
        bundle = read_bundle()
        anchor = bundle['observation']['block']['hash']
        self.assertEqual(proof.verify(bundle, anchor)['anchor'], 'caller-supplied-block-hash')
        with self.assertRaisesRegex(ValueError, 'independent block hash'):
            proof.verify(bundle, proof.lens.digest(b'wrong external checkpoint'))

    def test_corrupted_account_node(self):
        bundle = read_bundle()
        raw = bytearray.fromhex(bundle['proofs'][0]['accountProof'][0][2:])
        raw[-3] ^= 1
        bundle['proofs'][0]['accountProof'][0] = '0x' + raw.hex()
        with self.assertRaisesRegex(ValueError, 'missing proof node'):
            proof.verify(bundle)

    def test_missing_account_node_is_not_absence(self):
        bundle = read_bundle()
        bundle['proofs'][0]['accountProof'].pop(1)
        with self.assertRaisesRegex(ValueError, 'missing proof node'):
            proof.verify(bundle)

    def test_account_proof_for_wrong_address(self):
        bundle = read_bundle()
        bundle['proofs'][0]['address'] = proof.lens.IMD
        with self.assertRaisesRegex(ValueError, 'proof address'):
            proof.verify(bundle)

    def test_forged_runtime_even_with_consistent_auxiliary_hashes(self):
        bundle = read_bundle()
        node = bundle['observation']['nodes'][0]
        node.update(code='0x6000', code_bytes=2, code_hash=proof.lens.digest(b'\x60\x00'))
        bundle['observation']['effective_code_hash'] = node['code_hash']
        bundle['proofs'][0]['codeHash'] = node['code_hash']
        self.assertTrue(proof.lens.verify(bundle['observation']))
        with self.assertRaisesRegex(ValueError, 'proven code hash'):
            proof.verify(bundle)

    def test_forged_nonzero_slot_with_same_terminal_address(self):
        bundle = read_bundle()
        bundle['proofs'][0]['storageProof'][0]['value'] = '0x1'
        with self.assertRaisesRegex(ValueError, 'proven storage value'):
            proof.verify(bundle)

    def test_missing_duplicate_and_extra_storage_proofs(self):
        original = read_bundle()
        entries = original['proofs'][0]['storageProof']
        for bad in (entries[:1], [entries[0], entries[0]], entries + [entries[0]]):
            bundle = copy.deepcopy(original)
            bundle['proofs'][0]['storageProof'] = bad
            with self.subTest(count=len(bad)), self.assertRaises(ValueError):
                proof.verify(bundle)

    def test_missing_storage_node_is_not_zero(self):
        bundle = read_bundle()
        bundle['proofs'][0]['storageProof'][0]['proof'] = []
        with self.assertRaisesRegex(ValueError, 'missing proof node'):
            proof.verify(bundle)

    def test_tampered_storage_root_nonce_and_balance(self):
        for key, value in [('storageHash', proof.lens.digest(b'wrong root')),
                           ('nonce', '0x2'), ('balance', '0x1')]:
            bundle = read_bundle()
            bundle['proofs'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                proof.verify(bundle)

    def test_tampered_header_state_root_height_and_hash(self):
        original = read_bundle()
        fields = proof.rlp_decode(bytes.fromhex(original['header_rlp'][2:]))
        for index in (3, 8):
            bundle = copy.deepcopy(original)
            altered = copy.deepcopy(fields)
            altered[index] = b'\x01' * len(fields[index])
            bundle['header_rlp'] = encoded(altered)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'header hash'):
                proof.verify(bundle)
        bundle = copy.deepcopy(original)
        bundle['observation']['block']['number'] = '0x1'
        with self.assertRaisesRegex(ValueError, 'header height'):
            proof.verify(bundle)

    def test_forged_header_hash_does_not_forge_state_proof(self):
        bundle = read_bundle()
        fields = proof.rlp_decode(bytes.fromhex(bundle['header_rlp'][2:]))
        fields[3] = proof.keccak256(b'wrong state')
        bundle['header_rlp'] = encoded(fields)
        bundle['observation']['block']['hash'] = proof.lens.digest(proof.rlp_encode(fields))
        with self.assertRaisesRegex(ValueError, 'missing proof node'):
            proof.verify(bundle)

    def test_reordered_proof_nodes_work_but_junk_does_not(self):
        bundle = read_bundle()
        bundle['proofs'][0]['accountProof'].reverse()
        self.assertTrue(proof.verify(bundle)['state_inclusion_verified'])
        bundle['proofs'][0]['accountProof'].append(encoded([b'\x20', b'junk']))
        with self.assertRaisesRegex(ValueError, 'unused proof nodes'):
            proof.verify(bundle)

    def test_duplicate_and_oversized_proofs(self):
        root, nodes = leaf_fixture(b'a' * 32, b'value')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            proof.trie_lookup(root, b'a' * 32, nodes * 2)
        with self.assertRaisesRegex(ValueError, 'too many'):
            proof.trie_lookup(root, b'a' * 32, nodes * 129)
        with self.assertRaisesRegex(ValueError, 'bounded hex'):
            proof.trie_lookup(root, b'a' * 32, ['0x' + '00' * 2049])

    def test_leaf_inclusion_and_noninclusion(self):
        root, nodes = leaf_fixture(b'a' * 32, b'value')
        self.assertEqual(proof.trie_lookup(root, b'a' * 32, nodes), b'value')
        self.assertIsNone(proof.trie_lookup(root, b'b' * 32, nodes))

    def test_random_single_leaf_paths(self):
        rng = random.Random(737)
        for _ in range(64):
            key = bytes(rng.randrange(256) for _ in range(32))
            value = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 80)))
            root, nodes = leaf_fixture(key, value)
            self.assertEqual(proof.trie_lookup(root, key, nodes), value)
            missing = bytes([key[0] ^ 1]) + key[1:]
            self.assertIsNone(proof.trie_lookup(root, missing, nodes))

    def test_branch_hashed_child_and_absent_child(self):
        key = bytes.fromhex('12' + 'ab' * 31)
        leaf = [packed(proof.nibbles(key)[1:]), b'value']
        child = proof.rlp_encode(leaf)
        branch = [b''] * 17
        branch[1] = proof.keccak256(child)
        raw = proof.rlp_encode(branch)
        nodes = ['0x' + raw.hex(), '0x' + child.hex()]
        self.assertEqual(proof.trie_lookup(proof.keccak256(raw), key, nodes), b'value')
        self.assertIsNone(proof.trie_lookup(proof.keccak256(raw), b'\x22' + key[1:], nodes[:1]))
        with self.assertRaisesRegex(ValueError, 'missing proof node'):
            proof.trie_lookup(proof.keccak256(raw), key, nodes[:1])

    def test_extension_and_embedded_branch_leaf(self):
        key = b'\x12' * 32
        leaf = [b'\x20', b'x']  # zero remaining nibbles, embedded RLP length 3
        branch = [b''] * 17
        branch[2] = leaf
        extension = [packed(proof.nibbles(key)[:63], leaf=False), branch]
        self.assertLess(len(proof.rlp_encode(branch)), 32)
        raw = proof.rlp_encode(extension)
        self.assertEqual(proof.trie_lookup(proof.keccak256(raw), key, ['0x' + raw.hex()]), b'x')
        self.assertIsNone(proof.trie_lookup(proof.keccak256(raw), b'\x22' + key[1:], ['0x' + raw.hex()]))

    def test_hashed_extension_child(self):
        key = b'\x12' * 32
        leaf = [packed(proof.nibbles(key)[2:]), b'value']
        raw_leaf = proof.rlp_encode(leaf)
        raw = proof.rlp_encode([b'\x00\x12', proof.keccak256(raw_leaf)])
        self.assertEqual(proof.trie_lookup(proof.keccak256(raw), key,
                         ['0x' + raw.hex(), '0x' + raw_leaf.hex()]), b'value')

    def test_empty_storage_trie(self):
        for nodes in ([], ['0x80']):
            self.assertIsNone(proof.trie_lookup(proof.EMPTY_TRIE, b'x' * 32, nodes))
        with self.assertRaises(ValueError):
            proof.trie_lookup(proof.EMPTY_TRIE, b'x' * 32, ['0xc0'])

    def test_invalid_paths_child_reference_and_leaf_length(self):
        key = b'\x12' * 32
        malformed = [[b'\x40', b'x'], [b'\x21', b'x'], [b'\x00', b'a' * 32],
                     [b'\x20', b'x'], [b'\x11', b'bad-ref'], [b'x']]
        for node in malformed:
            raw = proof.rlp_encode(node)
            with self.subTest(node=node), self.assertRaises(ValueError):
                proof.trie_lookup(proof.keccak256(raw), key, ['0x' + raw.hex()])

    def test_noncanonical_rlp_and_integer_rejection(self):
        for raw in (b'', b'\x81\x01', b'\xb8\x01x', b'\xb9\x00\x38' + b'x' * 56,
                    b'\xc2\x80', b'\x80\x80', b'\xf8\x01\x80'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                proof.rlp_decode(raw)
        for value in (b'\x00', b'\x00\x01', b'\x01' * 33, []):
            with self.assertRaises(ValueError):
                proof.scalar(value)

    def test_rlp_roundtrip_boundaries(self):
        values = [b'', b'\x00', b'\x7f', b'\x80', b'x' * 55, b'x' * 56,
                  [], [b'', [b'x' * 56, b'\xff']]]
        for value in values:
            self.assertEqual(proof.rlp_decode(proof.rlp_encode(value)), value)

    def test_header_unsupported_fork_and_invalid_width(self):
        bundle = read_bundle()
        fields = proof.rlp_decode(bytes.fromhex(bundle['header_rlp'][2:]))
        for bad in (fields[:18], [b'x'] + fields[1:], fields[:12] + [b'x' * 33] + fields[13:]):
            with self.assertRaises(ValueError):
                proof.verify_header(encoded(bad), bundle['observation']['block'])

    def test_beacon_results_are_explicitly_not_proven(self):
        result = proof.verify(synthetic_beacon_bundle())
        self.assertEqual(result['unproven_beacon_call_results'], [proof.lens.IMD])
        self.assertEqual(len(result['accounts']), 2)
        self.assertTrue(all(account['proxy_slots_proven'] == 2 for account in result['accounts']))

    def test_beacon_runtime_and_nonzero_proxy_slot_cannot_be_forged(self):
        bundle = synthetic_beacon_bundle()
        bundle['proofs'][1]['codeHash'] = proof.lens.digest(b'changed beacon code')
        with self.assertRaisesRegex(ValueError, 'proven code hash'):
            proof.verify(bundle)
        bundle = synthetic_beacon_bundle()
        bundle['proofs'][0]['storageProof'][1]['value'] = '0x0'
        with self.assertRaisesRegex(ValueError, 'proven storage value'):
            proof.verify(bundle)

    def test_proxy_path_requires_every_account_proof(self):
        bundle = synthetic_beacon_bundle()
        bundle['proofs'].pop()
        with self.assertRaisesRegex(ValueError, 'missing or extra account proofs'):
            proof.verify(bundle)

    def test_live_collection_pins_all_proofs_and_checks_reorg(self):
        saved = read_bundle()
        header_values = proof.rlp_decode(bytes.fromhex(saved['header_rlp'][2:]))
        header = {}
        for value, (name, width) in zip(header_values, proof.HEADER_FIELDS):
            header[name] = hex(int.from_bytes(value, 'big')) if width is None else '0x' + value.hex()
        header['hash'] = saved['observation']['block']['hash']
        node = saved['observation']['nodes'][0]
        calls = []

        class FakeRPC:
            endpoint = proof.lens.PUBLIC_RPC
            reorg = False

            def call(self, method, params):
                calls.append((method, params))
                if method == 'eth_chainId':
                    return '0x1'
                if method == 'eth_getBlockByNumber':
                    result = copy.deepcopy(header)
                    if self.reorg and any(m == 'eth_getProof' for m, _ in calls):
                        result['hash'] = proof.lens.digest(b'changed block')
                    return result
                if method == 'eth_getCode':
                    return node['code']
                if method == 'eth_getStorageAt':
                    return '0x' + '00' * 32
                if method == 'eth_getProof':
                    return saved['proofs'][0]
                raise AssertionError(method)

        self.assertTrue(proof.verify(proof.collect(FakeRPC(), proof.lens.ZTO))['state_inclusion_verified'])
        for method, params in calls:
            if method in ('eth_getProof', 'eth_getCode', 'eth_getStorageAt'):
                self.assertEqual(params[-1], {'blockHash': header['hash'], 'requireCanonical': True})
        calls.clear()
        rpc = FakeRPC()
        rpc.reorg = True
        with self.assertRaisesRegex(ValueError, 'block changed during proofs'):
            proof.collect(rpc, proof.lens.ZTO)

    def test_cli_rejects_wrong_anchor_without_partial_json(self):
        args = [sys.executable, '-B', str(Path(__file__).parent / 'code_proof.py'),
                '--bundle', str(Path(__file__).parent / 'zto-proof.json'),
                '--expect-block-hash', proof.lens.digest(b'wrong checkpoint')]
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('independent block hash', result.stderr)

    def test_rpc_never_allows_transaction_submission(self):
        rpc = proof.ProofRPC(proof.lens.PUBLIC_RPC)
        with self.assertRaisesRegex(ValueError, 'allowlisted'):
            rpc.call('eth_sendRawTransaction', ['0x00'])


if __name__ == '__main__':
    unittest.main()
