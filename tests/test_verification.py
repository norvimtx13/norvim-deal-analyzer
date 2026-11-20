"""Offline checks for legal evidence, agent validation, imports and persistence."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from norvim_verification import (county_report, check_rows, empty_report, normalize_agent_report, merge_reports,
    normalize_leads, import_leads_csv, merge_leads, official_url, iso_date, snapshot_key, export_leads_csv)
from norvim_agent import run_research, fetch_county, ResearchError
from norvim_verification_ui import elysian_demo, prepare_search_verification

ADDRESS = '5405 Elysian St, Houston, TX 77009'
URL = 'https://www.cclerk.hctx.net/Applications/WebSearch/ViewECdocs.aspx?ID=TEST'
PARCEL = {'acct_num':'0311780000009','tax_year':2026,'state_class':'B2','land_use':'Residential Duplex',
          'site_str_num':'5405','site_str_name':'ELYSIAN','site_str_sfx':'ST','site_city':'HOUSTON'}

class Reply:
    ok = True
    status_code = 200
    def __init__(self, data): self.data = data
    def json(self): return self.data
    def raise_for_status(self): pass

def response(body, urls=(URL,)):
    return Reply({'status':'completed','id':'offline-response','usage':{'total_tokens':123},'output':[
        {'type':'web_search_call','action':{'sources':[{'url':u} for u in urls]}},
        {'type':'message','content':[{'type':'output_text','text':json.dumps(body),'annotations':[]}]}]})

class EvidenceTests(unittest.TestCase):
    def test_matching_county_never_establishes_city_use(self):
        report = county_report(ADDRESS, PARCEL, '2026-11-19T10:00:00Z')
        rows = {r['category']:r for r in check_rows(report)}
        self.assertEqual(rows['county']['status'], 'Source checked')
        self.assertEqual(rows['permitted_use']['status'], 'Unknown')
        self.assertEqual(rows['enforcement']['status'], 'Unknown')
        self.assertIn('0311780000009',rows['county']['finding'])
    def test_empty_or_neighboring_county_is_not_verified(self):
        self.assertEqual(county_report(ADDRESS,{})['checks'][0]['status'],'Unavailable')
        p = dict(PARCEL,site_str_num='5407')
        self.assertEqual(county_report(ADDRESS,p)['checks'][0]['status'],'Needs review')
        p = dict(PARCEL,site_city='DALLAS')
        self.assertEqual(county_report(ADDRESS,p)['checks'][0]['status'],'Needs review')
    def test_elysian_reference_retains_unknowns_and_date(self):
        rows = {r['category']:r for r in check_rows(elysian_demo())}
        self.assertEqual(rows['enforcement']['status'],'Unavailable')
        self.assertEqual(rows['county']['checked_at'][:10],'2026-11-19')
        self.assertEqual(rows['county']['as_of'],'')
        self.assertEqual(rows['title']['status'],'Unknown')
    def test_cited_ai_finding_still_needs_review(self):
        payload={'address':ADDRESS,'checks':[{'category':'permitted_use','status':'Verified','finding':'Model claims approval','source_url':URL,'as_of':'2026-11-19'}]}
        r=normalize_agent_report(payload,ADDRESS,[URL])
        self.assertEqual(r['checks'][0]['status'],'Needs review')
        r=normalize_agent_report(payload,ADDRESS,[])
        self.assertEqual(r['checks'][0]['status'],'Unknown')
        self.assertEqual(r['checks'][0]['source_url'],'')
    def test_wrong_address_is_rejected(self):
        with self.assertRaises(ValueError): normalize_agent_report({'address':'5407 Elysian St','checks':[]},ADDRESS,[])
        with self.assertRaises(ValueError): merge_reports(empty_report(ADDRESS),empty_report('Other address'))
    def test_ai_does_not_overwrite_direct_county_facts(self):
        before=county_report(ADDRESS,PARCEL)
        ai=normalize_agent_report({'address':ADDRESS,'checks':[{'category':'county','finding':'Unverified alternative','source_url':URL}]},ADDRESS,[URL])
        after=merge_reports(before,ai)
        self.assertEqual(after['checks'][0]['status'],'Source checked')
        self.assertIn('0311780000009',after['checks'][0]['finding'])
    def test_official_domain_and_dates(self):
        for u in ['https://hctx.net.evil.example/a','https://hctx.net@evil.example/a','javascript:alert(1)','http://hctx.net/a']:
            self.assertFalse(official_url(u))
        self.assertTrue(official_url(URL))
        self.assertEqual(iso_date('2026-02-31'),'')
        self.assertEqual(iso_date('12/1/2026'),'2026-12-01')
    def test_free_fetch_handles_failure_and_multiple_matches(self):
        import requests
        def fail(*args,**kwargs): raise requests.Timeout()
        self.assertEqual(fetch_county(ADDRESS,29,-95,get=fail)['checks'][0]['status'],'Unavailable')
        r=fetch_county(ADDRESS,29,-95,get=lambda *a,**k:Reply({'features':[{'attributes':PARCEL},{'attributes':PARCEL}]}))
        self.assertEqual(r['checks'][0]['status'],'Unavailable')
        r=fetch_county(ADDRESS,29,-95,get=lambda *a,**k:Reply({'features':[{'attributes':PARCEL}]}))
        self.assertEqual(r['checks'][0]['status'],'Source checked')
    def test_county_fallback_uses_exact_address_without_geocoding(self):
        captured={}
        def get(url,**kwargs):
            captured.update(kwargs)
            return Reply({'features':[{'attributes':PARCEL}]})
        r=fetch_county(ADDRESS,get=get)
        self.assertNotIn('geometry',captured['params'])
        self.assertIn("site_str_num = '5405'",captured['params']['where'])
        self.assertEqual(r['checks'][0]['status'],'Source checked')

class LeadTests(unittest.TestCase):
    def test_existing_collector_csv_stays_unclassified_without_record_link(self):
        data=b'address,city,zip,auction_date\nDEMO PROPERTY,Houston,77009,12/1/2026\n'
        rows=import_leads_csv(data,'Trustee sale notice')
        self.assertEqual(rows[0]['lead_type'],'Unclassified notice')
        self.assertEqual(rows[0]['auction_date'],'2026-12-01')
        self.assertIsNone(rows[0]['tax_due'])
    def test_notice_and_tax_delinquency_are_not_completed_foreclosures(self):
        rows=normalize_leads([{'address':ADDRESS,'lead_type':'Trustee sale notice','auction_date':'2026-12-01','source_url':URL},
                              {'address':ADDRESS,'lead_type':'Tax delinquent','source_url':'https://www.hctax.net/Property/DelinquentTax','tax_due':'$1,250.20'}])
        self.assertEqual(rows[0]['status'],'Scheduled sale reported')
        self.assertEqual(rows[1]['status'],'Tax delinquency reported')
        self.assertEqual(rows[1]['auction_date'],'')
        self.assertEqual(rows[1]['tax_due'],1250.2)
    def test_duplicate_import_is_idempotent_and_preserves_other_records(self):
        rows=normalize_leads([{'address':ADDRESS,'source_url':URL}])
        self.assertEqual(len(merge_leads(rows,rows)),1)
        newer=normalize_leads([{'address':'DEMO B','source_url':URL}])
        self.assertEqual(len(merge_leads(rows,newer)),2)
    def test_bad_import_and_nonfinite_tax(self):
        with self.assertRaises(ValueError): import_leads_csv(b'name\nTest\n')
        with self.assertRaises(ValueError): import_leads_csv(b'a'*2_000_001)
        row=normalize_leads([{'address':ADDRESS,'tax_due':'NaN'}])[0]
        self.assertIsNone(row['tax_due'])
    def test_ai_uncited_leads_are_discarded(self):
        self.assertEqual(normalize_leads([{'address':ADDRESS,'source_url':URL}],trusted_sources=[]),[])
    def test_zero_tax_is_not_labeled_delinquent_and_csv_is_literal(self):
        rows=normalize_leads([{'address':'=DEMO FORMULA','lead_type':'Tax delinquent','tax_due':0}])
        self.assertEqual(rows[0]['lead_type'],'Unclassified notice')
        self.assertIn("'=DEMO FORMULA",export_leads_csv(rows).decode('utf-8-sig'))

class AgentTests(unittest.TestCase):
    def test_no_key_does_not_make_a_request(self):
        def fail(*a,**k): self.fail('Network must not run')
        with self.assertRaises(ResearchError): run_research('',address=ADDRESS,post=fail)
    def test_request_is_bounded_and_contains_no_financial_context(self):
        captured={}
        def post(url,**kwargs):
            captured.update(kwargs)
            return response({'address':ADDRESS,'checks':[],'leads':[]})
        result=run_research('OFFLINE-TEST-KEY',address=ADDRESS,post=post)
        body=captured['json']
        self.assertEqual(body['max_tool_calls'],4)
        self.assertFalse(body['store'])
        self.assertEqual(body['tool_choice'],'required')
        self.assertIn(ADDRESS,body['input'])
        self.assertNotIn('OFFLINE-TEST-KEY',json.dumps(result))
    def test_incomplete_refusal_and_invalid_response_preserve_existing_findings(self):
        examples=[{'status':'incomplete','output':[]},{'status':'completed','output':[]},
            {'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]}]
        for payload in examples:
            with self.assertRaises(ResearchError): run_research('OFFLINE',address=ADDRESS,post=lambda *a,**k:Reply(payload))
    def test_discovery_filters_wrong_sale_date_and_uncited_address(self):
        rows=[{'address':ADDRESS,'lead_type':'Trustee sale notice','auction_date':'2026-12-01','source_url':URL},
              {'address':'DEMO OLD','lead_type':'Trustee sale notice','auction_date':'2026-11-03','source_url':URL},
              {'address':'DEMO UNCITED','lead_type':'Tax delinquent','source_url':'https://hctax.net/not-returned'}]
        out=run_research('OFFLINE',mode='discovery',sale_date='2026-12-01',post=lambda *a,**k:response({'address':'','checks':[],'leads':rows}))
        self.assertEqual([r['address'] for r in out['leads']],[ADDRESS])
    def test_search_snapshot_persistence_is_separate_from_underwriting(self):
        class State:
            session_state={}
            def warning(self,*a): pass
        state=State(); saves=[]
        analysis={'input':ADDRESS,'valuation':{'price':350000,'subjectProperty':{'formattedAddress':ADDRESS,'latitude':29,'longitude':-95}},'rent':{'rent':3000}}
        before=copy.deepcopy(analysis)
        with patch('norvim_verification_ui.fetch_county',return_value=county_report(ADDRESS,PARCEL)):
            prepare_search_verification(state,analysis,True,db_merge=lambda *a:saves.append(a) or True)
        self.assertEqual(analysis['valuation'],before['valuation'])
        self.assertEqual(analysis['rent'],before['rent'])
        self.assertEqual(saves[0][0],snapshot_key(ADDRESS))
        self.assertEqual(list(saves[0][2]),['verification'])

if __name__=='__main__': unittest.main(verbosity=2)
