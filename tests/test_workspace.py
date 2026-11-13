"""Offline regression checks. Never call or consume a production property API."""
import ast
import copy
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def fixture_analysis(with_comps=True, square_feet=1996, manual=False):
    comps = [
        {'formattedAddress':f'Sample comparable {i+1}, Houston, TX 77077', 'zipCode':'77077', 'city':'Houston',
         'price':price,'squareFootage':sf,'bedrooms':4,'bathrooms':2.5,'daysOnMarket':30+i,
         'distance':.3+i*.15,'correlation':.85,'latitude':29.74+i*.001,'longitude':-95.60-i*.001,
         'propertyType':'Single Family','status':'Inactive'}
        for i,(price,sf) in enumerate([(350000,1900),(360000,2000),(370000,2050)])
    ] if with_comps else []
    return {'input':'Sample property, Houston, TX 77077','address_key':'qa-sample-property',
            'valuation':{'price':360000,'priceRangeLow':330000,'priceRangeHigh':390000,'subjectProperty':{
                'formattedAddress':'Sample property, Houston, TX 77077','zipCode':'77077','city':'Houston',
                'propertyType':'Single Family','bedrooms':4,'bathrooms':2.5,'squareFootage':square_feet,
                'yearBuilt':1965,'latitude':29.74,'longitude':-95.60},'comparables':comps},
            'rent':{'rent':2400,'comparables':[]},'market':{},'property_record':{},'listing_record':{},
            'manual_mode':manual,'time':'2026-11-13T16:00:00Z','cache_source':'Offline QA fixture'}


def module_stubs():
    result={}
    for name,function in [('norvim_fast_exit','prescreen_area'),('norvim_fast_exit_ui','render_fast_exit_dashboard'),('norvim_research_ui','render_research_hub')]:
        m=types.ModuleType(name)
        setattr(m,function,lambda *args,**kwargs: None)
        result[name]=m
    return result


class WorkspaceRegression(unittest.TestCase):
    def setUp(self):
        self.mods=patch.dict(sys.modules,module_stubs());self.mods.start()
        self.environment=patch.dict(os.environ,{k:'' for k in ['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','RENTCAST_API_KEY','APP_ACCESS_CODE','HUD_API_TOKEN','HUD_API_KEY','CENSUS_API_KEY','MAPBOX_ACCESS_TOKEN','MAPBOX_API_KEY','MAPBOX_TOKEN']});self.environment.start()
        self.network=patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected outbound API request in offline QA'));self.http=self.network.start()
    def tearDown(self):
        self.network.stop();self.environment.stop();self.mods.stop()
    def run_app(self,analysis=None,strategy='Flip',**state):
        at=AppTest.from_file(str(APP),default_timeout=30)
        if analysis is not None:at.session_state['analysis']=analysis
        at.session_state['setup_strategy']=strategy
        for k,v in state.items():at.session_state[k]=v
        at.run()
        self.assertEqual(len(at.exception),0,[x.message for x in at.exception])
        return at
    def test_blank_startup_and_sidebar_navigation(self):
        at=self.run_app()
        self.assertIn('Workspace navigation',[x.label for x in at.sidebar.radio])
        self.assertTrue(any('Your next move, in focus.' in x.value for x in at.markdown))
        self.http.assert_not_called()
    def test_comp_arv_is_ready_before_summary(self):
        at=self.run_app(fixture_analysis())
        labels=[b.label for b in at.button]
        self.assertTrue(any('Use NORVIM Comp ARV' in x for x in labels))
        self.assertTrue(any('NORVIM Comp ARV:' in x.value for x in at.info))
        self.http.assert_not_called()
    def test_comp_arv_button_applies_without_extra_requests(self):
        at=self.run_app(fixture_analysis())
        at.button(key='use_norvim_comp_arv_top').click().run()
        self.assertEqual(len(at.exception),0,[x.message for x in at.exception])
        self.assertEqual(at.text_input(key='setup_underwriting_arv_qa-sample-property').value,'363,000')
        self.http.assert_not_called()
    def test_underwriting_values_survive_navigation_round_trip(self):
        at=self.run_app(fixture_analysis())
        at.text_input(key='setup_rehab').set_value('55,000').run()
        at.sidebar.radio(key='workflow_mode').set_value('Area Radar').run()
        at.sidebar.radio(key='workflow_mode').set_value('Analyze Property').run()
        self.assertEqual(len(at.exception),0,[x.message for x in at.exception])
        self.assertEqual(at.text_input(key='setup_rehab').value,'55,000')
        self.http.assert_not_called()
    def test_no_comps_and_missing_subject_size_remain_unavailable(self):
        for analysis in [fixture_analysis(False),fixture_analysis(True,0)]:
            at=self.run_app(analysis)
            self.assertFalse(any('Use NORVIM Comp ARV' in b.label for b in at.button))
    def test_all_five_strategies_render(self):
        for strategy in ['Flip','Wholesale','BRRRR','Rental','Section 8']:
            self.run_app(fixture_analysis(),strategy)
    def test_cached_neighborhood_map_preserves_selection_chart(self):
        data=fixture_analysis()
        snapshot={'address_key':data['address_key'],'recent_sales':[],'active_listings':[],'time':data['time']}
        at=self.run_app(data,neighborhood_snapshot=snapshot)
        self.assertGreaterEqual(len(at.get('deck_gl_json_chart')),1)
        self.http.assert_not_called()
    def test_manual_analysis_has_no_paid_requests(self):
        self.run_app(fixture_analysis(False,manual=True))
        self.http.assert_not_called()


class MapboxUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=ast.parse(APP.read_text())
        wanted={'get_mapbox_token','norvim_map_options'}
        selected=[node for node in source.body if isinstance(node,ast.FunctionDef) and node.name in wanted]
        selected += [node for node in source.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'NORVIM_MAPBOX_STYLES','NORVIM_FREE_MAP_STYLE'} for t in node.targets)]
        cls.code=compile(ast.Module(body=selected,type_ignores=[]),str(APP),'exec')
    def namespace(self,settings,state=None):
        import re
        n={'re':re,'get_setting':lambda key,default=None:settings.get(key,default),'st':types.SimpleNamespace(session_state=state or {})}
        exec(self.code,n)
        return n
    def test_no_token_uses_free_maps(self):
        n=self.namespace({});self.assertEqual(n['norvim_map_options']()['map_provider'],'carto')
    def test_public_token_and_each_alias(self):
        for key in ['MAPBOX_ACCESS_TOKEN','MAPBOX_API_KEY','MAPBOX_TOKEN']:
            n=self.namespace({key:'pk.offline_test_placeholder'},{'norvim_map_style':'Satellite + streets','norvim_map_provider':'Mapbox'})
            opts=n['norvim_map_options']();self.assertEqual(opts['map_provider'],'mapbox');self.assertEqual(opts['map_style'],'mapbox://styles/mapbox/satellite-streets-v12')
            self.assertEqual(opts['api_keys']['mapbox'],'pk.offline_test_placeholder')
    def test_secret_token_never_passed_to_browser(self):
        n=self.namespace({'MAPBOX_ACCESS_TOKEN':'sk.offline_test_placeholder'})
        opts=n['norvim_map_options']();self.assertEqual(opts['map_provider'],'carto');self.assertNotIn('api_keys',opts)
    def test_explicit_free_map_choice(self):
        n=self.namespace({'MAPBOX_ACCESS_TOKEN':'pk.offline_test_placeholder'},{'norvim_map_provider':'Free map (Carto)'})
        self.assertEqual(n['norvim_map_options']()['map_provider'],'carto')
    def test_custom_style(self):
        n=self.namespace({'MAPBOX_ACCESS_TOKEN':'pk.offline_test_placeholder','MAPBOX_STYLE':'mapbox://styles/norvim/custom_style'},{'norvim_map_style':'Custom style'})
        self.assertEqual(n['norvim_map_options']()['map_style'],'mapbox://styles/norvim/custom_style')


if __name__=='__main__':unittest.main(verbosity=2)
