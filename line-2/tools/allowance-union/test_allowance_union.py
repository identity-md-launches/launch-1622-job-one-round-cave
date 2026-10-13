"""Real saved chain evidence and explicitly synthetic negative mutations; no network."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import allowance_union as union
lens, changes = union.lens, union.changes
OLD, EMPTY, AFTER = [union.gate.load(p) for p in union.DEFAULTS]


def subset(start, end):
    result = copy.deepcopy(AFTER)
    result['observations'] = result['observations'][start:end]
    return result


class ReplayRPC:
    endpoint = lens.PUBLIC_RPC

    def __init__(self):
        self.calls = []
        self.chain = '0x1'
        self.reorg_old = False
        self.reorg_target = False
        self.target_reads = 0

    def call(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == 'eth_chainId':
            return self.chain
        target = AFTER['observations'][0]['block']
        if method == 'eth_getBlockByNumber':
            for source in (OLD, EMPTY):
                if params[0] == source['block']['number']:
                    header = copy.deepcopy(source['block'])
                    if self.reorg_old:
                        header['hash'] = target['hash']
                    return header
            self.target_reads += 1
            header = copy.deepcopy(target)
            if self.reorg_target and self.target_reads > 1:
                header['hash'] = OLD['block']['hash']
            return header
        if method == 'eth_call':
            assert params[1] == {'blockHash': target['hash'], 'requireCanonical': True}
            assert params[0]['to'] == lens.TOKENS['ZTO']
            if params[0]['data'] == '0x313ce567':
                return AFTER['observations'][0]['raw']['decimals']
            for observation in AFTER['observations']:
                for row in observation['raw']['balances'] + observation['raw']['allowances']:
                    if row['data'] == params[0]['data']:
                        return row['result']
            raise AssertionError('unrecorded calldata')
        raise AssertionError('unexpected RPC method: ' + method)


class UnionTests(unittest.TestCase):
    def test_real_empty_scan_cannot_erase_older_pairs(self):
        result = union.inventory([OLD, EMPTY])
        self.assertEqual(result['pair_count'], 19)
        self.assertEqual(result['owner_count'], 16)
        self.assertEqual(result['status'], 'requires_recheck')
        self.assertFalse(result['complete_wallet_audit'])
        self.assertTrue(all('allowance_raw' not in row for row in result['pairs']))

    def test_complementary_real_subsets_union_without_duplicate_pairs(self):
        result = union.inventory([subset(0, 10), subset(6, 16)])
        self.assertEqual(result['pair_count'], 19)
        self.assertTrue(any(len(row['source_sha256']) == 2 for row in result['pairs']))

    def test_order_independence_and_duplicate_input_idempotence(self):
        self.assertEqual(union.inventory([OLD, EMPTY]), union.inventory([EMPTY, OLD]))
        self.assertEqual(union.inventory([OLD, OLD])['pairs'], union.inventory([OLD])['pairs'])

    def test_zero_allowances_remain_in_inventory(self):
        result = union.inventory([AFTER])
        self.assertEqual(result['pair_count'], 19)
        self.assertEqual(sum(row['allowance_raw'] == '0'
                             for row in changes.flatten(AFTER)['pairs'].values()), 16)

    def test_complete_recheck_is_coverage_not_policy_approval(self):
        result = union.assess([OLD, EMPTY], AFTER)
        self.assertEqual(result['status'], 'all_known_pairs_rechecked')
        self.assertEqual(result['known_pairs_measured'], 19)
        self.assertEqual(result['active_known_pairs'], 3)
        self.assertIsNone(result['policy_approval'])

    def test_missing_recent_pairs_stay_unknown(self):
        result = union.assess([OLD], EMPTY)
        self.assertEqual(result['status'], 'incomplete_recheck')
        self.assertEqual(len(result['missing_pairs']), 19)
        self.assertEqual(result['known_pairs_measured'], 0)

    def test_partial_recheck_does_not_pass(self):
        result = union.assess([OLD], subset(0, 10))
        self.assertEqual(result['status'], 'incomplete_recheck')
        self.assertGreater(len(result['missing_pairs']), 0)

    def test_extra_measured_pairs_are_reported(self):
        result = union.assess([subset(0, 10)], AFTER)
        self.assertEqual(result['status'], 'all_known_pairs_rechecked')
        self.assertGreater(result['additional_measured_pairs'], 0)

    def test_empty_inventory_cannot_pass(self):
        self.assertEqual(union.inventory([EMPTY])['status'], 'empty_inventory')
        self.assertEqual(union.assess([EMPTY], AFTER)['status'], 'incomplete_recheck')
        with self.assertRaisesRegex(ValueError, 'empty union'):
            union.refresh(ReplayRPC(), [EMPTY])

    def test_no_or_too_many_inputs_rejected(self):
        for values in ([], [EMPTY] * 17):
            with self.subTest(count=len(values)), self.assertRaises(ValueError):
                union.inventory(values)

    def test_union_cap_rejected_without_truncation(self):
        with patch.object(lens, 'MAX_PAIRS', 18), self.assertRaises(ValueError):
            union.inventory([subset(0, 10), subset(10, 16)])

    def test_same_block_state_conflict_rejected(self):
        wrong = copy.deepcopy(AFTER)
        wrong['observations'][0]['raw']['allowances'][0]['result'] = '0x' + format(123, '064x')
        with self.assertRaisesRegex(ValueError, 'conflicting pair state'):
            union.inventory([AFTER, wrong])

    def test_disjoint_spenders_still_need_consistent_owner_balance(self):
        observation = copy.deepcopy(next(o for o in AFTER['observations']
                                         if len(o['raw']['allowances']) > 1))
        a, b = copy.deepcopy(observation), copy.deepcopy(observation)
        for obs, row in ((a, observation['raw']['allowances'][0]),
                         (b, observation['raw']['allowances'][1])):
            obs['raw']['allowances'] = [copy.deepcopy(row)]
            obs['query']['spenders'] = [row['spender']]
        b['raw']['balances'][0]['result'] = '0x' + format(123, '064x')
        with self.assertRaisesRegex(ValueError, 'conflicting owner balance'):
            union.inventory([a, b])

    def test_conflicting_headers_rejected_even_without_common_pairs(self):
        wrong = subset(10, 16)
        for obs in wrong['observations']:
            obs['block']['hash'] = OLD['block']['hash']
        with self.assertRaisesRegex(ValueError, 'conflicting headers'):
            union.inventory([subset(0, 10), wrong])

    def test_identity_mismatch_rejected(self):
        for field in ('token', 'decimals'):
            wrong = copy.deepcopy(AFTER)
            for obs in wrong['observations']:
                if field == 'token':
                    obs['token'], obs['token_address'] = 'IMD', lens.TOKENS['IMD']
                else:
                    obs['raw']['decimals'] = '0x' + format(6, '064x')
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'chain, token and decimals'):
                union.inventory([OLD, wrong])

    def test_malformed_evidence_rejected_before_rpc(self):
        bad = copy.deepcopy(OLD)
        bad['raw']['allowances'].pop()
        rpc = ReplayRPC()
        with self.assertRaises(ValueError):
            union.refresh(rpc, [bad])
        self.assertEqual(rpc.calls, [])

    def test_backwards_recheck_and_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, 'predates'):
            union.assess([AFTER], OLD)
        wrong = copy.deepcopy(AFTER)
        for obs in wrong['observations']:
            obs['block']['timestamp'] = hex(lens.quantity(OLD['block']['timestamp']) - 1)
        with self.assertRaisesRegex(ValueError, 'timestamps go backwards'):
            union.inventory([OLD, wrong])

    def test_real_rpc_replay_reads_all_pairs_at_one_hash(self):
        rpc = ReplayRPC()
        result = union.refresh(rpc, [OLD, EMPTY])
        self.assertEqual(result, AFTER)
        self.assertEqual(sum(method == 'eth_call' and p[0]['data'] == '0x313ce567'
                             for method, p in rpc.calls), 1)
        self.assertFalse(any(method == 'eth_getLogs' for method, _ in rpc.calls))
        self.assertEqual(sum(method == 'eth_call' and p[0]['data'].startswith('0xdd62ed3e')
                             for method, p in rpc.calls), 19)

    def test_chain_reorg_and_wrong_requested_block_fail(self):
        for attribute in ('chain', 'reorg_old', 'reorg_target'):
            rpc = ReplayRPC()
            setattr(rpc, attribute, '0x2' if attribute == 'chain' else True)
            with self.subTest(attribute=attribute), self.assertRaises(ValueError):
                union.refresh(rpc, [OLD, EMPTY])
        with self.assertRaisesRegex(ValueError, 'different requested block'):
            union.refresh(ReplayRPC(), [OLD], hex(26184898))

    def test_default_demo_has_no_network(self):
        stream = io.StringIO()
        with patch.object(lens, 'RPC', side_effect=AssertionError('no network')):
            with contextlib.redirect_stdout(stream):
                self.assertEqual(union.main([]), 0)
        result = json.loads(stream.getvalue())
        self.assertTrue(result['demonstration'])
        self.assertEqual(result['pair_count'], 19)

    def test_explicit_incomplete_recheck_exit_four(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(union.main(['--input', str(union.DEFAULTS[0]),
                                         '--after', str(union.DEFAULTS[1])]), 4)

    def test_cli_refuses_implicit_live_or_unused_options(self):
        for args in (['--refresh'], ['--after', str(union.DEFAULTS[2])], ['--timeout', '1'],
                     ['--save', 'line-2/unwanted.json']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(union.main(args), 1)

    def test_strict_json_and_workspace_boundary(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            json.loads('{"a":1,"a":2}', object_pairs_hook=union.gate.unique_object)
        with self.assertRaisesRegex(ValueError, 'current workspace'):
            union.gate.load(Path.cwd().parent / 'not-read.json')
        with self.assertRaises(FileExistsError):
            changes.save(union.DEFAULTS[0], {})

    def test_public_endpoints_only(self):
        with self.assertRaises(ValueError):
            union.UnionRPC(lens.ASSIGNMENT_RPC)


if __name__ == '__main__':
    unittest.main()
