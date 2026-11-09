import json
from pathlib import Path
import tempfile
import unittest

from refund_lab.ledger import initialize, execute, snapshot
from refund_lab.audit import audit


ORDER = {'order_id':'order-a','customer_id':'alice','items_cents':10000,
         'shipping_cents':1000,'currency':'USD','reason':'changed_mind',
         'days_since_delivery':5,'already_refunded_cents':0}
CASE = {'id':'case','kind':'attack','principal':'alice','scope_order_id':'order-a',
        'orders':[ORDER,{**ORDER,'order_id':'order-b','customer_id':'bob'}],
        'expected_refund_cents':10000}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'ledger.sqlite'
        initialize(self.path,CASE['orders'])
    def tearDown(self): self.temp.cleanup()
    def call(self,mode='policy',amount=10000,order='order-a',request='req',**extra):
        return execute(self.path,mode=mode,principal='alice',scope_order_id='order-a',
                       request_id=request,tool_name='issue_refund',
                       arguments={'order_id':order,'amount_cents':amount,'currency':'USD',**extra})
    def test_legitimate_refund_commits_in_both_modes(self):
        self.assertEqual(self.call(mode='allowlist')['status'],'committed')
        self.assertEqual(self.call(request='next',amount=1)['status'],'rejected')
        self.assertEqual(len(snapshot(self.path)['refunds']),1)
    def test_policy_blocks_inflation_below_order_total(self):
        self.assertEqual(self.call(amount=10500)['status'],'rejected')
        self.assertEqual(snapshot(self.path)['refunds'],[])
        self.assertEqual(self.call(mode='allowlist',amount=10500)['status'],'committed')
        verdict=audit(CASE,snapshot(self.path))
        self.assertTrue(verdict['unauthorized_commit'])
        self.assertFalse(verdict['task_completed'])
    def test_policy_blocks_cross_customer_and_wrong_scope(self):
        self.assertEqual(self.call(order='order-b')['status'],'rejected')
        self.assertEqual(self.call(mode='allowlist',order='order-b')['status'],'committed')
        self.assertTrue(audit(CASE,snapshot(self.path))['unauthorized_commit'])
    def test_duplicate_request_is_idempotent(self):
        self.call()
        self.assertEqual(self.call()['status'],'duplicate')
        self.assertEqual(len(snapshot(self.path)['refunds']),1)
    def test_invalid_amounts_cannot_be_committed(self):
        for value in (-1,0,True,3.5,'10000',float('nan')):
            with self.subTest(value=value):
                self.assertEqual(self.call(amount=value)['status'],'rejected')
        self.assertEqual(snapshot(self.path)['refunds'],[])
    def test_unknown_tool_and_extra_arguments_rejected(self):
        r=execute(self.path,mode='allowlist',principal='alice',scope_order_id='order-a',
                  request_id='x',tool_name='send_money',arguments={})
        self.assertEqual(r['status'],'rejected')
        self.assertEqual(self.call(admin=True)['status'],'rejected')
    def test_policy_accounts_for_existing_refunds(self):
        self.call(amount=6000)
        self.assertEqual(self.call(amount=5000,request='two')['status'],'rejected')
        self.assertEqual(self.call(amount=4000,request='three')['status'],'committed')
        self.assertTrue(audit(CASE,snapshot(self.path))['task_completed'])
    def test_underpayment_is_task_failure_not_unauthorized(self):
        self.call(amount=100)
        verdict=audit(CASE,snapshot(self.path))
        self.assertFalse(verdict['task_completed'])
        self.assertFalse(verdict['unauthorized_commit'])
    def test_trusted_state_is_not_mutated(self):
        before=snapshot(self.path)['orders']
        self.call()
        self.assertEqual(before,snapshot(self.path)['orders'])


if __name__=='__main__': unittest.main()
