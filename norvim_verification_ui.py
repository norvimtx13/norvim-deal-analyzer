"""Verification at address-search time and an on-demand distressed-property desk."""
from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from norvim_agent import fetch_county, run_research, ResearchError
from norvim_verification import (empty_report, check_rows, snapshot_key, merge_reports, export_json,
    import_leads_csv, merge_leads, export_leads_csv, LEAD_TYPES, county_report)

LEAD_KEY = 'norvim::distressed_leads::v1'

def _load(st, key, db_get, field, fallback):
    if key not in st.session_state:
        value = fallback
        if db_get:
            try:
                value = (db_get(key, max_age_days=None) or {}).get(field, fallback)
            except Exception:
                st.warning('Saved research could not be loaded. No clearance is inferred from a database error.')
        st.session_state[key] = value
    return st.session_state[key]

def _save(st, key, address, field, value, db_merge):
    st.session_state[key] = value
    if db_merge:
        try:
            if db_merge(key, address, {field: value}):
                return True
        except Exception:
            pass
    st.warning('Research is available in this session only. Download a backup; connect Supabase for persistence.')
    return False

def prepare_search_verification(st, analysis, enabled=True, db_get=None, db_merge=None):
    """Called only on an explicit new address-search submission, never on slider reruns."""
    subject = (analysis.get('valuation') or {}).get('subjectProperty') or {}
    address = subject.get('formattedAddress') or analysis['input']
    key = snapshot_key(address)
    saved = _load(st, key, db_get, 'verification', empty_report(address))
    if enabled:
        incoming = fetch_county(address, subject.get('latitude'), subject.get('longitude'))
        saved = merge_reports(saved, incoming)
        _save(st, key, address, 'verification', saved, db_merge)
    analysis['verification'] = saved
    return analysis

def _draw_checks(st, report):
    rows = check_rows(report)
    source_checked = sum(c['status'] == 'Source checked' for c in rows)
    a, b = st.columns(2)
    a.metric('Direct county source checks', source_checked)
    b.metric('Other / unresolved checks', len(rows) - source_checked)
    st.caption('County classification is separate from City-approved use. Historical final permits do not establish current code clearance.')
    st.caption('Last research run: ' + (report.get('checked_at') or 'Not run') + ' · Record dates are shown individually.')
    for i, c in enumerate(rows):
        with st.expander(c['title'] + ' — ' + c['status'], expanded=i < 2):
            st.write(c['finding'])
            st.caption('Source lookup checked: ' + (c['checked_at'] or 'Not recorded'))
            st.caption('Record / statement date: ' + (c['as_of'] or 'Unknown'))
            if c['source_url']:
                st.link_button('View supporting source', c['source_url'])
            st.write('Next step: ' + c['next_action'])
    st.caption('A missing or unavailable search is unresolved. AI-assisted findings require review of the linked records.')

def render_verification_panel(st, address, *, latitude=None, longitude=None, initial=None, db_get=None, db_merge=None, get_setting=None, key_prefix='search'):
    st.markdown('### Property verification')
    key = snapshot_key(address)
    report = _load(st, key, db_get, 'verification', initial or empty_report(address))
    settings = get_setting or (lambda name, default=None: default)
    api_key = str(settings('OPENAI_API_KEY', '') or '').strip()
    model = str(settings('OPENAI_RESEARCH_MODEL', 'gpt-6.2-astra') or 'gpt-6.2-astra')
    left, right = st.columns(2)
    county_clicked = left.button('Refresh county classification (free)', key=key_prefix + '_county')
    ai_clicked = right.button('Research legal records with AI', key=key_prefix + '_ai', disabled=not api_key)
    if not api_key:
        st.caption('Live AI research needs OPENAI_API_KEY in Streamlit Secrets. Free county checks, demo and CSV import work without it.')
    else:
        st.caption('AI research runs only when pressed and uses separately billed OpenAI API usage. Only this public address is sent; underwriting and contact records are excluded.')
    if latitude is None or longitude is None:
        st.caption('The free county check can search an exact numbered street address without RentCast. Ambiguous matches remain unresolved.')
    if county_clicked or ai_clicked:
        try:
            with st.spinner('Checking source records...'):
                incoming = fetch_county(address, latitude, longitude) if county_clicked else run_research(api_key, address=address, model=model)['report']
            report = merge_reports(report, incoming)
            permanent = _save(st, key, address, 'verification', report, db_merge)
            st.success('Research saved to Supabase.' if permanent else 'Research completed for this session.')
        except (ResearchError, ValueError) as exc:
            st.error(str(exc))
    _draw_checks(st, report)
    st.download_button('Download verification JSON', export_json(report), file_name='NORVIM_verification.json', mime='application/json', key=key_prefix + '_download')
    return report

def elysian_demo():
    address = '5405 Elysian St, Houston, TX 77009'
    report = county_report(address, {'acct_num': '0311780000009', 'tax_year': 2026, 'state_class': 'B2 — Residential, Two-Family',
        'land_use': 'Residential Duplex', 'site_str_num': '5405', 'site_str_name': 'ELYSIAN', 'site_str_sfx': 'ST', 'site_city': 'HOUSTON'}, '2026-11-19T00:00:00Z')
    report['checks'] += [
        {'category': 'permitted_use', 'status': 'Unknown', 'finding': 'City-approved two-unit use was not confirmed in the November 19 review.',
         'source_url': 'https://cohtora.houstontx.gov/approot/soldpermits/online_permit.htm', 'as_of': '', 'checked_at': '2026-11-19T00:00:00Z', 'next_action': 'Request approved plans and applicable final inspections.'},
        {'category': 'enforcement', 'status': 'Unavailable', 'finding': 'The public permit search returned a maintenance message. Current code and unsafe-building status remains unknown.',
         'source_url': 'https://cohtora.houstontx.gov/approot/soldpermits/online_permit.htm', 'as_of': '', 'checked_at': '2026-11-19T00:00:00Z', 'next_action': 'Request current cases and closure/compliance records from the City.'}]
    report['demo'] = True
    return report

def render_verification_desk(st, *, db_get=None, db_merge=None, get_setting=None, open_callback=None):
    settings = get_setting or (lambda name, default=None: default)
    st.markdown('### Legal checks & distressed-property research')
    st.caption('Search one address, discover sourced leads, or import your existing foreclosure collector output.')
    tabs = st.tabs(['Property checks', 'Foreclosure & tax leads', 'Test without API costs'])
    with tabs[0]:
        address = st.text_input('Address to verify', key='nv_verify_address', placeholder='5405 Elysian St, Houston, TX 77009').strip()
        if len(address) >= 8:
            render_verification_panel(st, address, db_get=db_get, db_merge=db_merge, get_setting=settings, key_prefix='desk')
        else:
            st.info('Enter an address, or use the Elysian reference snapshot in the test tab.')
    with tabs[1]:
        leads = _load(st, LEAD_KEY, db_get, 'distressed_leads', [])
        st.info('Trustee notices, tax-sale listings and delinquent-tax accounts stay separate. A notice is not proof that a foreclosure sale occurred.')
        day = datetime.now(ZoneInfo('America/Chicago')).date()
        # First Tuesday in the next calendar month is a useful default, not a guarantee of an auction.
        next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
        next_sale = next_month + timedelta(days=(1 - next_month.weekday()) % 7)
        sale_date = st.date_input('Scheduled sale date to research', next_sale, key='nv_sale_date')
        limit = st.slider('Maximum candidate leads', 1, 20, 10, key='nv_lead_limit')
        api_key = str(settings('OPENAI_API_KEY', '') or '').strip()
        st.caption('On-demand public-source screening; partial coverage. No unattended crawler or scheduled monitoring is running.')
        if st.button('Find foreclosure & delinquent-tax leads with AI', disabled=not api_key, type='primary', key='nv_find_leads'):
            try:
                with st.spinner('Researching Harris County official records...'):
                    result = run_research(api_key, mode='discovery', sale_date=sale_date.isoformat(), limit=limit,
                                          model=str(settings('OPENAI_RESEARCH_MODEL', 'gpt-6.2-astra')))
                leads = merge_leads(leads, result['leads'])
                _save(st, LEAD_KEY, 'NORVIM distressed-property leads', 'distressed_leads', leads, db_merge)
                st.success(f"{len(result['leads'])} supported candidates returned. An empty result does not establish that no notices exist.")
                for url in result['source_urls']:
                    st.link_button('Official source consulted', url)
            except (ResearchError, ValueError) as exc:
                st.error(str(exc))
        if not api_key:
            st.caption('Add OPENAI_API_KEY in Streamlit Secrets for the live agent, or import the CSV your collector already produces.')
        st.markdown('#### Import your foreclosure collector CSV')
        st.caption('Accepts address, city, state, zip and auction_date. Optional: source_url, document_id, account, tax_due, record_as_of and lead_type. Missing evidence stays unclassified.')
        kind = st.selectbox('Record type when the file does not specify one', LEAD_TYPES, index=3, key='nv_import_kind')
        upload = st.file_uploader('Collector output (UTF-8 CSV, up to 500 rows)', type=['csv'], key='nv_lead_upload')
        if upload and st.button('Import candidate leads', key='nv_import_leads'):
            try:
                imported = import_leads_csv(upload.getvalue(), kind)
                leads = merge_leads(leads, imported)
                _save(st, LEAD_KEY, 'NORVIM distressed-property leads', 'distressed_leads', leads, db_merge)
                st.success(f'{len(imported)} candidate rows imported. Review sources and current status before relying on them.')
            except ValueError as exc:
                st.error(str(exc))
        if leads:
            st.dataframe(pd.DataFrame(leads), hide_index=True, use_container_width=True)
            selected = st.selectbox('Open a candidate', range(len(leads)), format_func=lambda i: leads[i]['address'] + ' · ' + leads[i]['lead_type'], key='nv_lead_selection')
            row = leads[selected]
            if row.get('source_url'):
                st.link_button('Open original record', row['source_url'])
            if open_callback:
                st.button('Analyze this address', on_click=open_callback, args=(row['address'],), key='nv_analyze_lead')
            st.download_button('Download leads CSV', export_leads_csv(leads), 'NORVIM_distressed_leads.csv', 'text/csv', key='nv_leads_csv')
            st.download_button('Download leads JSON backup', export_json(leads), 'NORVIM_distressed_leads.json', 'application/json', key='nv_leads_json')
        else:
            st.info('No candidate leads saved. Run research or import your collector output.')
    with tabs[2]:
        st.markdown('#### Elysian reference snapshot')
        st.warning('DEMO / REFERENCE — findings from November 19, 2026. This is not a new live verification and is not saved to your property records.')
        if st.button('Show Elysian test snapshot', key='nv_elysian_demo'):
            st.session_state['nv_show_demo'] = True
        if st.session_state.get('nv_show_demo'):
            _draw_checks(st, elysian_demo())
        sample = ('address,city,state,zip,auction_date,source_url,document_id,lead_type,notes\n'
                  'DEMO PROPERTY A,Houston,TX,77009,2026-12-01,,,Unclassified notice,TEST ROW NOT A REAL FORECLOSURE\n')
        st.download_button('Download sample collector CSV', sample, 'NORVIM_DEMO_collector.csv', 'text/csv', key='nv_demo_csv')
        st.caption('Test plan: open the Elysian snapshot, import the sample CSV, confirm unknowns stay unresolved, then connect an API key for a small live run.')
