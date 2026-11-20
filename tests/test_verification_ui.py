"""Real Streamlit interaction tests, with provider calls mocked."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from norvim_verification import snapshot_key, empty_report, normalize_leads
from norvim_verification_ui import elysian_demo, LEAD_KEY
from norvim_agent import ResearchError
from test_workspace import fixture_analysis

APP = Path(__file__).resolve().parents[1] / 'app.py'
ADDRESS = '5405 Elysian St, Houston, TX 77009'

class VerificationUI(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{k:'' for k in ['OPENAI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','RENTCAST_API_KEY','APP_ACCESS_CODE','HUD_API_TOKEN','HUD_API_KEY','CENSUS_API_KEY','MAPBOX_ACCESS_TOKEN','MAPBOX_API_KEY','MAPBOX_TOKEN']})
        self.env.start()
        self.net=patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected network request'))
        self.http=self.net.start()
    def tearDown(self):
        self.net.stop();self.env.stop()
    def app(self, workflow='Verification & Foreclosures', **state):
        at=AppTest.from_file(str(APP),default_timeout=30)
        at.session_state['workflow_mode']=workflow
        for k,v in state.items(): at.session_state[k]=v
        return self.check(at.run())
    def check(self,at):
        self.assertEqual(len(at.exception),0,[x.message for x in at.exception])
        return at
    def test_desk_opens_with_ai_disabled_without_key(self):
        at=self.app()
        self.assertTrue(at.button(key='nv_find_leads').disabled)
        self.assertEqual(at.sidebar.radio(key='workflow_mode').value,'Verification & Foreclosures')
        self.http.assert_not_called()
    def test_demo_elysian_is_dated_and_does_not_persist(self):
        at=self.app()
        self.check(at.button(key='nv_elysian_demo').click().run())
        labels=[e.label for e in at.expander]
        self.assertIn('City-approved use — Unknown',labels)
        self.assertIn('Current code & unsafe-building cases — Unavailable',labels)
        self.assertTrue(any('2026-11-19' in c.value for c in at.caption))
        with self.assertRaises(KeyError): at.session_state[snapshot_key(ADDRESS)]
        self.http.assert_not_called()
    def test_free_county_button_works_without_rentcast_or_openai(self):
        at=self.app()
        self.check(at.text_input(key='nv_verify_address').set_value(ADDRESS).run())
        with patch('norvim_verification_ui.fetch_county',return_value=elysian_demo()) as lookup:
            self.check(at.button(key='desk_county').click().run())
        lookup.assert_called_once_with(ADDRESS,None,None)
        self.assertEqual(at.session_state[snapshot_key(ADDRESS)]['address'],ADDRESS)
        self.assertIn('City-approved use — Unknown',[e.label for e in at.expander])
        self.assertTrue(at.button(key='desk_ai').disabled)
        self.http.assert_not_called()
    def test_analyzer_displays_legal_panel_without_automatic_rerun_calls(self):
        at=self.app(workflow='Analyze Property',analysis=fixture_analysis())
        self.assertIn('Legal & property verification',[e.label for e in at.expander])
        self.check(at.text_input(key='setup_rehab').set_value('65,000').run())
        self.http.assert_not_called()
    def test_failed_ai_keeps_prior_verification(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'OFFLINE-TEST-KEY'}):
            before=elysian_demo()
            at=self.app(**{'nv_verify_address':ADDRESS,snapshot_key(ADDRESS):copy.deepcopy(before)})
            with patch('norvim_verification_ui.run_research',side_effect=ResearchError('Offline test failure')):
                self.check(at.button(key='desk_ai').click().run())
            self.assertEqual(at.session_state[snapshot_key(ADDRESS)],before)
            self.assertTrue(any('Offline test failure' in e.value for e in at.error))
        self.http.assert_not_called()
    def test_discovery_saves_candidates_without_marking_completed_sale(self):
        rows=normalize_leads([{'address':'DEMO PROPERTY, Houston, TX 77009','lead_type':'Tax delinquent','tax_due':900,'source_url':'https://hctax.net/Property/DelinquentTax'}])
        with patch.dict(os.environ,{'OPENAI_API_KEY':'OFFLINE-TEST-KEY'}):
            at=self.app()
            with patch('norvim_verification_ui.run_research',return_value={'leads':rows,'source_urls':[]}):
                self.check(at.button(key='nv_find_leads').click().run())
            self.assertEqual(len(at.session_state[LEAD_KEY]),1)
            self.assertEqual(at.session_state[LEAD_KEY][0]['status'],'Tax delinquency reported')
            self.assertIn('Analyze this address',[b.label for b in at.button])
        self.http.assert_not_called()

if __name__=='__main__': unittest.main(verbosity=2)
