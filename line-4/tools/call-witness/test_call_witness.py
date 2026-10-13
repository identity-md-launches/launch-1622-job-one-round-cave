"""Bounded offline tests for the two-provider call witness."""
import copy
import unittest

import call_witness as tool


class FakeRPC:
    def __init__(self, head, historical=None):
        self.head = head
        self.historical = historical or {}

    def call(self, method, params):
        if method == 'eth_chainId':
            return '0x1'
        if method == 'eth_getBlockByNumber':
            return self.head if params[0] == 'finalized' else self.historical[params[0]]
        raise AssertionError('unexpected method')


class WitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real = tool.load_bundle(tool.HERE / 'zto-witness.json')

    def test_real_saved_zto_agrees(self):
        result = tool.witness(self.real)
        self.assertEqual(result['verdict'], 'agree')
        self.assertEqual(result['block']['number'], '0x18f8d21')
        self.assertEqual(result['providers'][0]['result']['uint256'],
                         '1000000000000000000000000000')
        self.assertLessEqual(len(tool.encoded_bundle(self.real)), tool.MAX_BUNDLE)

    def test_conflicting_same_block_result_is_disagreement(self):
        pair = copy.deepcopy(self.real)
        pair[1]['outcome']['result'] = '0x' + format(1, '064x')
        result = tool.witness(pair)
        self.assertEqual(result['verdict'], 'disagree')

    def test_different_block_rejected(self):
        pair = copy.deepcopy(self.real)
        pair[1]['block']['number'] = hex(int(pair[1]['block']['number'], 16) + 1)
        pair[1]['block']['hash'] = '0x' + 'ef'*32
        pair[1]['block']['timestamp'] = hex(int(pair[1]['block']['timestamp'], 16) + 12)
        with self.assertRaisesRegex(ValueError, 'same block'):
            tool.witness(pair)

    def test_same_provider_rejected(self):
        pair = copy.deepcopy(self.real)
        pair[1]['source'] = pair[0]['source']
        with self.assertRaisesRegex(ValueError, 'distinct supported RPCs'):
            tool.witness(pair)

    def test_common_finalized_uses_lower_head(self):
        common = {'number': '0xa', 'hash': '0x' + 'ab'*32, 'timestamp': '0x64'}
        later = {'number': '0xc', 'hash': '0x' + 'cd'*32, 'timestamp': '0x7c'}
        self.assertEqual(tool.common_finalized(FakeRPC(common),
                         FakeRPC(later, {'0xa': common})), common)

    def test_explicit_finalized_block_is_shared_and_pinned(self):
        chosen = {'number': '0xa', 'hash': '0x' + 'ab'*32, 'timestamp': '0x64'}
        left_head = {'number': '0xb', 'hash': '0x' + 'bc'*32, 'timestamp': '0x70'}
        right_head = {'number': '0xc', 'hash': '0x' + 'cd'*32, 'timestamp': '0x7c'}
        self.assertEqual(tool.common_finalized(FakeRPC(left_head, {'0xa': chosen}),
                         FakeRPC(right_head, {'0xa': chosen}), '0xa'), chosen)

    def test_explicit_block_newer_than_finalized_head_is_rejected(self):
        head = {'number': '0xa', 'hash': '0x' + 'ab'*32, 'timestamp': '0x64'}
        with self.assertRaisesRegex(ValueError, 'newer'):
            tool.common_finalized(FakeRPC(head), FakeRPC(head), '0xb')

    def test_disagreeing_common_header_rejected(self):
        one = {'number': '0xa', 'hash': '0x' + 'ab'*32, 'timestamp': '0x64'}
        two = {'number': '0xa', 'hash': '0x' + 'cd'*32, 'timestamp': '0x64'}
        with self.assertRaisesRegex(ValueError, 'disagree'):
            tool.common_finalized(FakeRPC(one), FakeRPC(two))


if __name__ == '__main__':
    unittest.main()
