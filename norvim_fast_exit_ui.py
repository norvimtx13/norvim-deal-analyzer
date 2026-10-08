"""Drop-in UI for NORVIM DealFinder v2.6+. No third-party calls on load."""
from __future__ import annotations
from io import StringIO
from datetime import datetime, timezone
import csv
from dataclasses import replace
from norvim_fast_exit import (FundingTerms, FlipInputs, flip_model, stress_test,
    maximum_offer, resale_quality, comparable_evidence, dollars, finite, prescreen_area)


SUGGESTED_AREAS = "77062, 77070, 77581, 77089, 77084"


def _money(value):
    return dollars(value)


def _save_csv(rows):
    if not rows:
        return ''
    buf=StringIO()
    writer=csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader();writer.writerows(rows)
    return buf.getvalue()


def render_fast_exit_dashboard(st, pd, db_get=None, db_merge=None, open_callback=None):
    """Operates on the existing 'area_scan_df' cache. Never spends RentCast calls."""
    st.markdown("### NORVIM · Fast-Exit Deal Desk")
    st.caption("Established Houston neighborhoods · Verified closed comps · Contractor budget · 90% lender model. "
               "No RentCast calls are made by this screen. This is not an appraisal or lender approval.")
    with st.expander("Acquisition criteria and workflow", expanded=True):
        st.write("**Area first:** 77062 / 77070 / 77581 / 77089 / 77084 are screening candidates, not automatic approvals. "
                 "Qualify the specific subdivision and price bracket with recent SOLD comps. Exclude poorly supported exits.")
        st.write("**Target:** 3–4 bedroom single-family, documented demand, verified sale prices, realistic contractor scope, "
                 "minimum $35K modeled profit and a nonnegative stressed exit. The app does not assume any ZIP is always fast.")
        st.code(SUGGESTED_AREAS, language="text")
        def go_scan():
            st.session_state['workflow_mode']='Find Deals by Area'
            st.session_state['scout_area_preset']='Custom ZIPs'
            st.session_state['scout_zips']=SUGGESTED_AREAS
            st.session_state['scout_strategy']='Flip'
        st.button("Go to Area Scout with these ZIPs", on_click=go_scan, use_container_width=True,
                  help="Area Scout uses about one RentCast listing call per ZIP unless cached.")

    area_df=st.session_state.get('area_scan_hcad')
    if area_df is None or getattr(area_df,'empty',True):
        area_df=st.session_state.get('area_scan_df')
    st.markdown('#### Acquisition shortlist')
    if area_df is not None and not area_df.empty:
        quick=prescreen_area(area_df)
        cols=[x for x in ['Acquisition Screen','Address','ZIP','Price','Beds','Baths','Sq Ft',
                          'DOM','Liquidity Status','Why it surfaced'] if x in quick.columns]
        st.dataframe(quick[cols].head(50),use_container_width=True,hide_index=True)
        st.caption("This is an asking-price screen, NOT a resale-speed ranking. "
                   "An old active listing can be negotiable even in a slow resale market.")
        options=quick['Address'].dropna().astype(str).tolist()
    else:
        st.info('No cached Area Scout results in this session. Run an area scan first, or enter an address manually below.')
        options=[]

    st.markdown('#### Deal you are analyzing')
    choice=st.selectbox('Select candidate', ['Enter an address']+options, key='fe_choice')
    if choice=='Enter an address':
        address=st.text_input('Property address',key='fe_manual_address',placeholder='Street address, Houston, TX')
        ask=0.
    else:
        address=choice
        match=quick[quick['Address'].astype(str)==address]
        ask=finite(match.iloc[0].get('Price'),0) or 0 if not match.empty else 0
    address=address.strip()
    if not address:
        st.info('Select a scanned listing or enter a property address to open the deal model.')
        return
    property_key='fast_exit::'+''.join(ch for ch in address.lower() if ch.isalnum())
    if st.session_state.get('fe_loaded_key')!=property_key:
        saved={}
        if db_get:
            try:
                snap=db_get(property_key,max_age_days=None) or {}
                saved=snap.get('fast_exit_review') or {}
            except Exception:
                pass
        st.session_state['fe_saved']=saved
        st.session_state['fe_loaded_key']=property_key
    saved=st.session_state.get('fe_saved') or {}

    st.markdown('##### 1. House + contractor quote')
    c1,c2,c3=st.columns(3)
    with c1:
        purchase=st.number_input('Offer / purchase ($)',min_value=0.,max_value=3000000.,value=float(saved.get('purchase',ask)),step=5000.,key=f'{property_key}_purchase')
        rehab=st.number_input('Contractor rehab estimate ($)',min_value=0.,max_value=2000000.,value=float(saved.get('rehab',45000)),step=2500.,key=f'{property_key}_rehab')
    with c2:
        arv=st.number_input('Verified ARV ($)',min_value=0.,max_value=4000000.,value=float(saved.get('arv',0)),step=5000.,key=f'{property_key}_arv',help='Enter after reviewing recent SOLD comps. Leave zero if unverified.')
        months=st.number_input('Total hold through sale (months)', min_value=1., max_value=30.,value=float(saved.get('months',6)),step=1.,key=f'{property_key}_months')
    with c3:
        target=st.number_input('Minimum NORVIM net target ($)',min_value=0.,max_value=1000000.,value=float(saved.get('target_profit',35000)),step=5000.,key=f'{property_key}_target')
        monthly_hold=st.number_input('Monthly property carrying costs ($, excl. loan interest)',min_value=0.,max_value=20000.,value=float(saved.get('monthly_hold',600)),step=100.,key=f'{property_key}_carry')

    st.markdown('##### 2. Lender term sheet (not yet verified)')
    f1,f2,f3,f4=st.columns(4)
    with f1:
        ltc=st.number_input('Loan-to-cost (%)',50.,100.,float(saved.get('ltc',90)),1.,key=f'{property_key}_ltc')
        points=st.number_input('Origination points (%)',0.,10.,float(saved.get('points',3)),.5,key=f'{property_key}_points')
    with f2:
        arv_cap=st.number_input('Loan-to-ARV cap (%)',40.,100.,float(saved.get('arv_cap',70)),1.,key=f'{property_key}_arvcap')
        rate=st.number_input('Annual interest rate (%)',0.,30.,float(saved.get('rate',10)),.5,key=f'{property_key}_rate')
    with f3:
        clos_adv=st.number_input('Purchase paid by lender at closing (%)',0.,100.,float(saved.get('purchase_advance',90)),5.,key=f'{property_key}_closeadv')
        draw_buffer=st.number_input('Cash needed before rehab draw (%)',0.,100.,float(saved.get('draw_buffer',25)),5.,key=f'{property_key}_draw')
    with f4:
        clos_cost=st.number_input('Acquisition closing costs ($)',min_value=0.,max_value=100000.,value=float(saved.get('closing',4000)),step=500.,key=f'{property_key}_closing')
        cont=st.number_input('Rehab contingency (%)',0.,50.,float(saved.get('contingency',10)),1.,key=f'{property_key}_contingency')
    st.caption('90% LTC may still be limited by the ARV cap. Rehab draws may be reimbursement-only. '
               'The model assumes interest on the entire approved balance throughout the hold, conservatively.')

    deal=FlipInputs(purchase=purchase,rehab=rehab,arv=arv,months=months,acquisition_closing=clos_cost,
                    monthly_hold_ex_interest=monthly_hold,rehab_contingency=cont/100,target_profit=target)
    funding=FundingTerms(ltc=ltc/100,max_arv_ltv=arv_cap/100,purchase_advance=clos_adv/100,
                         annual_interest=rate/100,points=points/100,draw_bridge_fraction=draw_buffer/100)

    st.markdown('##### 3. Closed-sale proof of quick resale')
    st.caption('Upload actual SOLD comps if you have them. Subject listing DOM does not count as sold-home DOM. '
               'Redfin/Zillow/HAR screenshots or asking prices alone cannot establish a verified resale-speed score.')
    sample_cols=['Address','Status','Sold Price','Sale Date','Sq Ft','Beds','Distance (mi)','DOM','List Price']
    st.download_button('Download comparable-sales CSV template', _save_csv([dict.fromkeys(sample_cols,'')]),
                       file_name='NORVIM_sold_comps_template.csv',mime='text/csv')
    comp_upload=st.file_uploader('Upload SOLD comps CSV (optional)',type=['csv'],key=f'{property_key}_comps')
    evidence=None
    if comp_upload:
        try:
            comps=pd.read_csv(comp_upload)
            match_sf=st.number_input('Subject house sq ft',min_value=0.,max_value=20000.,value=0.,step=100.,key=f'{property_key}_sqft')
            match_beds=st.number_input('Subject bedrooms',min_value=0,max_value=12,value=3,step=1,key=f'{property_key}_beds')
            evidence=comparable_evidence(comps.to_dict('records'),subject_sqft=match_sf or None,subject_beds=match_beds or None)
            st.caption(f"Qualified closed comps within 1 mile and 180 days: {evidence['closed_comps']} · "
                       f"Median closed-sale DOM: {evidence['median_closed_dom'] if evidence['median_closed_dom'] is not None else 'unknown'}")
        except Exception as exc:
            st.warning(f'Cannot read comps CSV: {exc}')
    elif saved.get('closed_comps',0):
        st.caption('Previously saved counts are editable below. Attach the supporting comparable sales before approval.')

    m1,m2,m3,m4=st.columns(4)
    with m1:
        verified_sales=st.number_input('Closed comparable sales (180d)',min_value=0,max_value=100,
                                      value=int(evidence['closed_comps'] if evidence else saved.get('closed_comps',0)),key=f'{property_key}_sales')
    with m2:
        dom_closed=st.number_input('Median CLOSED-sale DOM (0 = unknown)',min_value=0.,max_value=365.,
                                   value=float(evidence['median_closed_dom'] if evidence and evidence['median_closed_dom'] is not None else saved.get('closed_dom',0)),step=1.,key=f'{property_key}_dom')
    with m3:
        sale_list=st.number_input('Sold/list ratio % (0 = unknown)',min_value=0.,max_value=150.,
                                  value=float((evidence['sale_to_list']*100) if evidence and evidence['sale_to_list'] is not None else saved.get('sale_to_list_pct',0)),step=1.,key=f'{property_key}_ratio')
    with m4:
        competition=st.number_input('Similar competing active homes (0 = unknown)',min_value=0,max_value=100,
                                     value=int(saved.get('active_competition',0)),key=f'{property_key}_active')
    st.text_input('Closed-sale data source and verified date', value=str(saved.get('source','')),
                  key=f'{property_key}_source',placeholder='HAR MLS closed comps, reviewed 2026-10-08')

    if arv<=0:
        st.warning('Enter a defensible ARV supported by closed comparables before reviewing profitability.')
        return
    model=flip_model(deal,funding)
    stress=stress_test(deal,funding)
    quality=resale_quality(closed_comps=verified_sales,median_closed_dom=dom_closed if dom_closed>0 else None,
                           sale_to_list=sale_list/100 if sale_list>0 else None,
                           active_competition=competition if competition>0 else None,
                           profit=model['profit'],stress_profit=stress['stress_profit'])
    st.markdown('#### Deal underwriting & decision')
    a,b,c,d=st.columns(4)
    with a: st.metric('Modeled lender loan',_money(model['loan']))
    with b: st.metric('Cash at closing estimate',_money(model['cash_at_closing_estimate']))
    with c: st.metric('Peak accessible cash estimate',_money(model['minimum_accessible_cash_estimate']))
    with d: st.metric('Base net profit before tax',_money(model['profit']))
    e,f,g,h=st.columns(4)
    with e: st.metric('Stressed profit',_money(stress['stress_profit']))
    with f:
        ceiling=maximum_offer(deal,funding)
        st.metric('Max offer for your net target',_money(ceiling))
    with g: st.metric('Loan / total project cost',f"{model['loan']/(purchase+rehab)*100:.1f}%" if purchase+rehab else '—')
    with h: st.metric('Exit confidence',quality['status'])
    st.caption(quality['reason'])
    st.caption('Peak cash is an estimate based on acquisition funds, origination, expected first rehab draw and contingency. '
               'It is NOT a lender closing statement or a guarantee of draw timing. Cash at closing is only one part of funding.')
    with st.expander('All calculations'):
        st.json({k:round(v,2) if isinstance(v,(int,float)) else v for k,v in model.items()})

    st.markdown('#### Ready to pursue?')
    q1,q2,q3,q4=st.columns(4)
    with q1: comps_ok=st.checkbox('Sold comps inspected',value=bool(saved.get('comps_ok',False)),key=f'{property_key}_compsok')
    with q2: contractor_ok=st.checkbox('Written contractor quote',value=bool(saved.get('contractor_ok',False)),key=f'{property_key}_contractorok')
    with q3: lender_ok=st.checkbox('Lender term sheet confirmed',value=bool(saved.get('lender_ok',False)),key=f'{property_key}_lenderok')
    with q4: equity_ok=st.checkbox('Cash gap + draw reserves funded',value=bool(saved.get('equity_ok',False)),key=f'{property_key}_equityok')
    ready=(all([comps_ok,contractor_ok,lender_ok,equity_ok]) and quality['status']=='FAST EXIT'
           and model['pass_target'] and stress['stress_profit']>=0)
    if ready:
        st.success('All screening gates passed. Still verify title, inspection, flood/insurance, permit and purchase agreement before closing.')
    else:
        st.warning('RESEARCH / NEGOTIATE — not cleared for acquisition. Resolve the missing checklist items, liquidity evidence or margins.')

    payload={"address":address,"purchase":purchase,"rehab":rehab,"arv":arv,"months":months,
             "target_profit":target,"monthly_hold":monthly_hold,"ltc":ltc,"arv_cap":arv_cap,
             "purchase_advance":clos_adv,"points":points,"rate":rate,"draw_buffer":draw_buffer,
             "closing":clos_cost,"contingency":cont,"closed_comps":verified_sales,
             "closed_dom":dom_closed,"sale_to_list_pct":sale_list,"active_competition":competition,
             "source":st.session_state.get(f'{property_key}_source',''),"comps_ok":comps_ok,
             "contractor_ok":contractor_ok,"lender_ok":lender_ok,"equity_ok":equity_ok,
             "market_status":quality['status'],"modeled_profit":model['profit'],"stress_profit":stress['stress_profit'],
             "saved_at":datetime.now(timezone.utc).isoformat()}
    buttons=st.columns(3)
    with buttons[0]:
        if st.button('Save this deal to NORVIM',use_container_width=True,key=f'{property_key}_save'):
            st.session_state['fe_saved']=payload
            if db_merge:
                try:
                    db_merge(property_key,address,{'fast_exit_review':payload,'time':payload['saved_at']})
                    st.success('Saved in NORVIM database.')
                except Exception as exc:
                    st.warning(f'Only saved in current session; database failed: {exc}')
            else:
                st.success('Saved in this Streamlit session (database not configured).')
    with buttons[1]:
        st.download_button('Export lender brief (CSV)',_save_csv([payload]),
                           file_name='NORVIM_FastExit_'+''.join(ch for ch in address if ch.isalnum())[:30]+'.csv',
                           mime='text/csv',use_container_width=True)
    with buttons[2]:
        if open_callback:
            st.button('Open in full analyzer',on_click=open_callback,args=(address,'Flip',purchase),use_container_width=True)
