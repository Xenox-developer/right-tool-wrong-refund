import unittest
from refund_lab.protocol import parse_proposal, request_for


class ProtocolTests(unittest.TestCase):
    def test_native_tool_call_is_parsed_without_executing_text(self):
        response={'done':True,'message':{'tool_calls':[{'function':{'name':'issue_refund',
            'arguments':{'order_id':'a','amount_cents':100,'currency':'USD'}}}]}}
        proposal,error=parse_proposal(response)
        self.assertIsNone(error)
        self.assertEqual(proposal['arguments']['amount_cents'],100)
    def test_missing_multiple_and_truncated_calls_are_recorded(self):
        for response in ({'done':True,'message':{'content':'issue_refund(...)'}},
                         {'done':False,'message':{}},
                         {'done':True,'message':{'tool_calls':[{},{}]}}):
            with self.subTest(response=response):
                proposal,error=parse_proposal(response)
                self.assertIsNone(proposal)
                self.assertIsNotNone(error)
    def test_gold_answers_never_enter_the_prompt(self):
        case={'principal':'alice','scope_order_id':'a','orders':[],
              'document':'customer evidence','expected_refund_cents':987654321}
        req=request_for('qwen3:8b',case,42)
        self.assertNotIn('987654321',str(req))
        self.assertEqual(len(req['tools']),1)
        self.assertFalse(req['think'])


if __name__=='__main__': unittest.main()
