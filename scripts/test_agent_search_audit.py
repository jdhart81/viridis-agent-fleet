import unittest
from unittest.mock import patch
import agent_search_audit as a


class SearchAuditTests(unittest.TestCase):
    def test_no_match_requires_explicit_rejection(self):
        reply={'decision':'NEEDS_INPUT','money_moved':False,'payment_authorized':False,'tool_executed':False,'state_persisted':False}
        with patch.object(a,'fetch',return_value=reply):
            self.assertEqual(a.check_case({'query':'Order pizza','expected_route':None})['status'],'fail')
        reply['decision']='NO_MATCH'
        with patch.object(a,'fetch',return_value=reply):
            self.assertEqual(a.check_case({'query':'Order pizza','expected_route':None})['status'],'pass')

    def test_network_failure_is_unavailable_not_no_match(self):
        with patch.object(a,'fetch',side_effect=TimeoutError):
            self.assertEqual(a.check_case({'query':'Order pizza','expected_route':None})['status'],'unavailable')

    def test_expected_selection_cannot_hide_execution(self):
        reply={'decision':'NEEDS_INPUT','route_decision':{'selected':{'route':'a/b'}},
               'money_moved':False,'payment_authorized':False,'tool_executed':True,'state_persisted':False}
        with patch.object(a,'fetch',return_value=reply):
            self.assertEqual(a.check_case({'query':'Perform task','expected_route':'a/b'})['status'],'fail')

    def test_all_catalog_routes_count_for_external_coverage(self):
        merchant={'pagination':{'total':1},'resources':[{'resource':a.BASE+'/x402/a/b'}]}
        r=a.inventory(merchant,{'a/b','c/d'})
        self.assertEqual(r['indexed_count'],1);self.assertEqual(r['missing_routes'],['c/d'])
        merchant['pagination']['total']=2
        self.assertEqual(a.inventory(merchant,{'a/b'})['status'],'unavailable')

    def test_unconfigured_destination_cannot_be_fetched(self):
        with self.assertRaises(ValueError):a.fetch('https://untrusted.example/')

    def test_bounded_query_set(self):
        with self.assertRaises(ValueError):a.audit([{'query':'same','expected_route':None}]*31)

    def test_wrong_price_units_are_flagged(self):
        row={'agent':'a','tool':'b','endpoint':a.BASE+'/x402/a/b','description':'Task',
             'price_minor':100,'amount_atomic_usdc':'100','value_decision':{'job_to_be_done':'job','expected_outcome':'out','not_for':'other'}}
        r=a.contracts({'routes':[row]}, {'paths':{}})[0]
        self.assertIn('price_units_mismatch',r['issues'])
        self.assertIn('missing_input_schema',r['issues'])


if __name__=='__main__':unittest.main()
