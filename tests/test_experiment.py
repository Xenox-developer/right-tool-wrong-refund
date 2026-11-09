import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from refund_lab.analysis import analyze
from refund_lab.experiment import ROOT, MODELS, run, schedule_for
from refund_lab.fixtures import load_cases
from refund_lab.protocol import parse_proposal


class ExperimentTests(unittest.TestCase):
    def test_malformed_native_calls_are_reported(self):
        for message in (None,[],{'tool_calls':[None]}, {'tool_calls':[{'function':None}]}):
            with self.subTest(message=message):
                proposal,error=parse_proposal({'done':True,'message':message})
                self.assertIsNone(proposal)
                self.assertIsNotNone(error)

    def test_fixture_strata_and_repeat_schedule(self):
        cases=load_cases(ROOT/'data/cases.json')
        schedule=schedule_for(cases)
        self.assertEqual(len(schedule),48)
        self.assertEqual(schedule,schedule_for(cases))
        self.assertEqual(len({(r['model'],r['case_id'],r['seed']) for r in schedule}),48)
        for model in MODELS:
            self.assertEqual(sum(r['model']==model for r in schedule),24)

    def test_full_run_replay_audit_and_integrity(self):
        cases=load_cases(ROOT/'data/cases.json')
        calls=[]

        def fake_http(endpoint,payload=None,timeout=30):
            if endpoint=='/api/tags':
                return {'models':[{'name':model,'digest':'test-only'} for model in MODELS]}
            if endpoint=='/api/version':
                return {'version':'test-only'}
            if endpoint=='/api/generate':
                self.assertNotIn('prompt',payload)
                return {'done':True}
            self.assertEqual(endpoint,'/api/chat')
            calls.append(payload)
            user=payload['messages'][-1]['content']
            if user=='Reply OK.':
                return {'done':True,'message':{'content':'OK'}}
            case=next(c for c in cases if f'for order {c["scope_order_id"]}.' in user)
            # Known mock behavior tests execution/audit, never model quality.
            amount=case['expected_refund_cents']*(2 if case['kind']=='attack' else 1)
            return {'done':True,'done_reason':'stop','message':{'tool_calls':[
              {'function':{'name':'issue_refund','arguments':{
                'order_id':case['scope_order_id'],'amount_cents':amount,'currency':'USD'}}}]}}

        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'run'
            with contextlib.redirect_stdout(io.StringIO()):
                state=run(directory,transport=fake_http,commit='unit-test-only')
            self.assertEqual(state['attempts'],50)
            self.assertEqual(len(calls),50)
            result=analyze(directory)
            self.assertFalse(result['requires_protocol_review'])
            for row in result['summary']:
                self.assertEqual(row['benign_completed'],8)
                self.assertEqual(row['unauthorized_commits'],16 if row['mode']=='allowlist' else 0)
                self.assertEqual(row['authorized_proposals_rejected'],0)
            # A real ledger mutation must be detected, not trusted from JSON.
            import sqlite3
            db_path=next((directory/'ledgers').glob('*allowlist.sqlite'))
            with sqlite3.connect(db_path) as db:
                db.execute('DELETE FROM refunds')
            with self.assertRaisesRegex(ValueError,'snapshot'):
                analyze(directory)

    def test_failed_requests_charge_budget_and_never_execute(self):
        def unavailable(endpoint,payload=None,timeout=30):
            if endpoint=='/api/tags':
                return {'models':[{'name':m} for m in MODELS]}
            if endpoint=='/api/version':
                return {}
            if endpoint=='/api/generate':
                return {}
            raise TimeoutError('test-only timeout')
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'run'
            with contextlib.redirect_stdout(io.StringIO()):
                state=run(directory,transport=unavailable,commit='unit-test-only')
            self.assertEqual(state['attempts'],50)
            result=analyze(directory)
            self.assertTrue(result['requires_protocol_review'])
            for row in result['summary']:
                self.assertEqual(row['transport_errors'],24)
                self.assertEqual(row['benign_completed'],0)
                self.assertEqual(row['valid_native_proposals'],0)
            manifest=json.loads((directory/'manifest.json').read_text())
            frozen=directory/'frozen'/next(iter(manifest['files_sha256']))
            frozen.write_text('tampered')
            with self.assertRaisesRegex(ValueError,'Changed frozen input'):
                analyze(directory)


if __name__=='__main__':
    unittest.main()
