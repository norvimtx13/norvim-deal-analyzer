"""NORVIM Research Hub for existing v2.6/v2.7 app. Never calls provider without click."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
import pandas as pd
from norvim_research_core import (MAX_SAVED, STATUSES, normalize_portfolio, upsert_property,
    remove_property, json_backup, csv_backup, money, number, now_utc, key_for,
    extract_rental_comps, rent_stats, report_pdf, trend_points, changes, market_history_points)

INDEX_KEY='norvim::portfolio::v1'


def _load_portfolio(st,db_get):
    if 'nrh_portfolio' not in st.session_state:
        snapshot={}
        if db_get:
            try:snapshot=db_get(INDEX_KEY,max_age_days=None) or {}
            except Exception:pass
        st.session_state['nrh_portfolio']=normalize_portfolio(snapshot.get('portfolio_items',[]))
    return st.session_state['nrh_portfolio']


def _persist_portfolio(st,items,db_merge):
    st.session_state['nrh_portfolio']=normalize_portfolio(items)
    if db_merge:
        try:
            ok=db_merge(INDEX_KEY,'NORVIM research portfolio',{'portfolio_items':st.session_state['nrh_portfolio'],'time':now_utc()})
            if ok:
                st.success('Saved permanently in NORVIM Supabase database.')
                return True
        except Exception as exc:
            st.warning(f'Database save problem: {exc}')
    st.warning('Only saved for this browser session. Export a JSON backup now; cloud restarts may clear unsynced changes.')
    return False


def _save_snapshot(st,db_merge,snapshot_key,address,data):
    st.session_state[snapshot_key]=data
    if db_merge:
        try:
            ok=db_merge(snapshot_key,address,{'research_comps':data,'time':now_utc()})
            return bool(ok)
        except Exception:return False
    return False


def render_research_hub(st,db_get=None,db_merge=None,get_api_key=None,api_call=None,usage_fn=None,limit=50):
    st.markdown('### NORVIM · Research Hub')
    st.caption('Saved pipeline · Adjustable rental and sale-listing comps · Historical snapshots · NORVIM-branded reports. '
               'RentCast calls happen ONLY when you press a refresh button. Existing Deep Analyzer / Fast Exit tabs remain available.')
    items=_load_portfolio(st,db_get)
    col_a,col_b,col_c=st.columns(3)
    with col_a:st.metric('Saved properties',f'{len(items)} / {MAX_SAVED}')
    try:used=max(0,int(usage_fn())) if usage_fn else 0
    except Exception:used=0
    try:maximum=max(1,int(limit))
    except Exception:maximum=50
    remaining=max(0,maximum-used)
    with col_b:st.metric('Est. RentCast calls left',f'{remaining} / {maximum}')
    with col_c:st.metric('Reopen saved property','0 API calls')
    st.caption('API usage reflects this app’s tracked requests and configured offset; cross-app usage may differ from the RentCast dashboard.')

    tabs=st.tabs(['My portfolio','Comps & rents','Trends & updates','NORVIM reports'])
    with tabs[0]:
        st.markdown('#### My properties')
        if items:
            view=pd.DataFrame(items)
            display_cols=['address','zip','status','purchase','arv','rehab','updated']
            st.dataframe(view[display_cols],hide_index=True,use_container_width=True,
                column_config={'purchase':st.column_config.NumberColumn('Price',format='$%.0f'),
                    'arv':st.column_config.NumberColumn('ARV',format='$%.0f'),
                    'rehab':st.column_config.NumberColumn('Rehab',format='$%.0f')})
        else:st.info('No saved properties yet. Add the first house below.')

        pick=['New property']+[e['address'] for e in items]
        selection=st.selectbox('Edit or add property',pick,key='nrh_portfolio_select')
        current=next((e for e in items if e['address']==selection),{})
        with st.form('nrh_portfolio_form'):
            address=st.text_input('Property address',value=current.get('address',''),placeholder='123 Main St, Houston, TX 77062')
            a,b,c=st.columns(3)
            with a:
                zipcode=st.text_input('ZIP',value=current.get('zip',''))
                price=st.number_input('Offer / asking price',0.,10000000.,float(current.get('purchase',0)),step=5000.)
            with b:
                status=st.selectbox('Deal stage',STATUSES,index=STATUSES.index(current.get('status',STATUSES[0])))
                arv=st.number_input('Underwriting ARV',0.,10000000.,float(current.get('arv',0)),step=5000.)
            with c:
                contractor=st.text_input('Contractor contact',value=current.get('contractor',''))
                rehab=st.number_input('Contractor rehab estimate',0.,10000000.,float(current.get('rehab',0)),step=2500.)
            source=st.text_input('Data / listing source',value=current.get('source',''),placeholder='HAR URL, seller, inspection, etc.')
            notes=st.text_area('Notes and next steps',value=current.get('notes',''),height=100)
            saved=st.form_submit_button('Save property',type='primary')
        if saved:
            if not address.strip():st.error('Enter a property address.')
            else:
                new={'address':address.strip(),'zip':zipcode,'status':status,'purchase':price,'arv':arv,
                     'rehab':rehab,'contractor':contractor,'source':source,'notes':notes,'updated':now_utc()}
                try:
                    next_items=upsert_property(items,new)
                    if current and key_for(current['address'])!=key_for(address):
                        next_items=remove_property(next_items,current['address'])
                    _persist_portfolio(st,next_items,db_merge)
                except ValueError as exc:st.error(str(exc))
        if current and st.button('Remove selected property',key='nrh_remove'):
            _persist_portfolio(st,remove_property(items,current['address']),db_merge)
            st.rerun()
        x,y=st.columns(2)
        with x:st.download_button('Export portfolio JSON backup',json_backup(items),'NORVIM_portfolio_backup.json',mime='application/json',use_container_width=True)
        with y:st.download_button('Export portfolio CSV',csv_backup(items),'NORVIM_portfolio.csv',mime='text/csv',use_container_width=True)
        imported=st.file_uploader('Restore portfolio JSON (merge by address, max 50)',type=['json'],key='nrh_import')
        if imported and st.button('Import saved properties',key='nrh_import_btn'):
            if imported.size>2_000_000:st.error('Backup file is too large.')
            else:
                try:
                    inp=json.loads(imported.getvalue().decode('utf-8'))
                    imported_items=normalize_portfolio(inp)
                    merged=items
                    for item in reversed(imported_items):merged=upsert_property(merged,item)
                    _persist_portfolio(st,merged,db_merge)
                except (ValueError,UnicodeDecodeError,TypeError,json.JSONDecodeError) as exc:
                    st.error(f'Cannot import backup: {exc}')

    with tabs[1]:
        st.markdown('#### Comparable rental listings')
        st.caption('Compare **asking rents** from active and recently seen rental listings. Not executed lease rents or guaranteed Section 8 payment standards.')
        properties=[e['address'] for e in items]
        selected=st.selectbox('Choose a saved address or type a new one',['Type an address']+properties,key='nrh_comp_select')
        subject=st.text_input('Subject address',value='' if selected=='Type an address' else selected,key='nrh_comp_address') if selected=='Type an address' else selected
        c1,c2,c3=st.columns(3)
        with c1:radius=st.selectbox('Comparable radius (miles)',[.5,1.,2.,3.,5.],index=2)
        with c2:lookback=st.selectbox('Lookback (days)',[30,60,90,180,270,365],index=3)
        with c3:count=st.slider('Number of comps',5,20,20)
        a,b=st.columns(2)
        with a:kind=st.selectbox('Comparable type',['Rental asking rents','Sale asking prices (AVM comps)'])
        with b:unit_type=st.selectbox('Property type',['Single Family','Townhouse','Condo','Multi-Family','Apartment'])
        subject=subject.strip()
        if not subject:st.info('Choose or type a full subject property address.')
        else:
            kind_prefix='rent' if kind.startswith('Rental') else 'sale'
            code=hashlib.sha256(f'{subject.lower()}|{kind_prefix}|{radius}|{lookback}|{count}|{unit_type}'.encode()).hexdigest()[:24]
            skey='norvim::comp::'+code
            data=st.session_state.get(skey)
            if data is None and db_get:
                try:
                    data=(db_get(skey,max_age_days=None) or {}).get('research_comps')
                except Exception:pass
            if data:
                st.info(f"Previously saved snapshot: {data.get('fetched_at','unknown')} · No API call used to display it.")
            st.caption('Refresh counts as 1 new RentCast API call per type/setting. Cached settings can be reopened free.')
            if st.button('Refresh comparables (uses 1 API request)',type='primary',disabled=(remaining<1 or api_call is None),key='nrh_fetch_'+code):
                try:
                    api_key=get_api_key() if get_api_key else None
                    if not api_key:raise ValueError('RentCast API key missing. Set RENTCAST_API_KEY in Streamlit Secrets.')
                    endpoint='/avm/rent/long-term' if kind_prefix=='rent' else '/avm/value'
                    params={'address':subject,'maxRadius':radius,'daysOld':lookback,'compCount':count,'propertyType':unit_type}
                    with st.spinner('Fetching one RentCast comparable snapshot...'):
                        payload=api_call(endpoint,params,api_key,key_for(subject))
                    if not isinstance(payload,dict):raise ValueError('API returned an unexpected result')
                    fetched=now_utc()
                    previous=data if isinstance(data,dict) else {}
                    history=previous.get('history',[])
                    estimate=number(payload.get('rent') if kind_prefix=='rent' else payload.get('price'))
                    if estimate:
                        history=(history+[{'date':fetched,'rent':estimate,'type':kind_prefix}])[-48:]
                    data={'type':kind_prefix,'fetched_at':fetched,'response':payload,'history':history,
                          'estimated_value':estimate,'settings':params}
                    is_persisted=_save_snapshot(st,db_merge,skey,subject,data)
                    st.success('Comparable snapshot fetched and '+('saved to Supabase.' if is_persisted else 'kept in this session. Export backups for safety.'))
                except Exception as exc:st.error(f'Could not fetch comps: {exc}')
            if data:
                payload=data.get('response') or {}
                comps=extract_rental_comps(payload,max_count=count,max_radius=radius,days_old=lookback) if kind_prefix=='rent' else []
                if kind_prefix=='rent':
                    stats=rent_stats(comps)
                    k1,k2,k3=st.columns(3)
                    with k1:st.metric('RentCast rent estimate',money(payload.get('rent')))
                    with k2:st.metric('Median comp asking rent',money(stats['median_asking_rent']))
                    with k3:st.metric('Comparable listings',len(comps))
                    if comps:
                        st.dataframe(pd.DataFrame(comps).drop(columns=['Correlation'],errors='ignore'),use_container_width=True,hide_index=True)
                        st.download_button('Download rental comps CSV',pd.DataFrame(comps).to_csv(index=False),
                                           'NORVIM_rental_comps.csv',mime='text/csv')
                    else:st.warning('No usable rental comps returned for these settings. Try a larger radius or lookback.')
                else:
                    rows=[]
                    for x in (payload.get('comparables') or [])[:count]:
                        if isinstance(x,dict):
                            rows.append({'Address':x.get('formattedAddress'),'Listing Price':x.get('price'),
                              'Status':x.get('status'),'Date Listed':x.get('listedDate'),
                              'Sq Ft':x.get('squareFootage'),'Beds':x.get('bedrooms'),
                              'Distance':x.get('distance')})
                    st.metric('RentCast estimated property value (not verified ARV)',money(payload.get('price')))
                    if rows:st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
                    st.warning('These are sale LISTING comparables from an AVM. Do not label them closed sales or rely on them alone to establish fast resale. Use the Fast Exit Deal Desk for verified sold comps and closed-sale DOM.')
                st.session_state['nrh_current_research']={'address':subject,'type':kind_prefix,'data':data,'comps':comps if kind_prefix=='rent' else []}

    with tabs[2]:
        st.markdown('#### Historical rent trends & manual market updates')
        latest=st.session_state.get('nrh_current_research') or {}
        if latest.get('type')=='rent':
            data=latest['data'];series=trend_points(data.get('history',[]))
            if series:
                st.caption('History from YOUR saved RentCast rent-estimate snapshots at this address. Not a ZIP-wide rental market index.')
                st.line_chart(pd.DataFrame(series).set_index('Date'))
            else:st.info('Refresh a property in the Comps tab to record the first point on its personal rental history.')
            if len(series)>=2:
                c=changes(series[-2]['Estimated rent'],series[-1]['Estimated rent'])
                if c:
                    st.metric('Change since prior saved estimate',f"{c['change_pct']:+.1f}%")
                    if c['significant']:st.warning('Estimated rent changed by at least 5% since previous saved snapshot. Review the comparables and listing quality.')
        else:
            st.info('Refresh a property in the Comps tab to add dated snapshots of its rent estimate.')
        st.markdown('##### ZIP-wide historical market data')
        auto_zip=next((x.get('zip') for x in items if x['address']==latest.get('address')),'')
        zip_choice=st.text_input('ZIP to research',value=str(auto_zip or ''),key='nrh_trend_zip').strip()
        if len(zip_choice)==5 and zip_choice.isdigit():
            zkey='zip::'+zip_choice
            mkey='nrh_zip_market_'+zip_choice
            market=st.session_state.get(mkey)
            if market is None and db_get:
                try:market=(db_get(zkey,max_age_days=None) or {}).get('market')
                except Exception:market=None
            if market:
                st.caption('Previously cached ZIP-level RentCast market snapshot. No new API request to display it.')
            if st.button('Refresh ZIP market (uses 1 API request)',key='nrh_market_'+zip_choice,
                         disabled=(remaining<1 or api_call is None)):
                try:
                    api_key=get_api_key() if get_api_key else None
                    if not api_key:raise ValueError('Missing RentCast API key')
                    with st.spinner('Fetching 12 months of ZIP market history...'):
                        market=api_call('/markets',{'zipCode':zip_choice,'dataType':'All','historyRange':12},api_key,zkey)
                    if not isinstance(market,dict):raise ValueError('Unexpected market response')
                    st.session_state[mkey]=market
                    if db_merge:db_merge(zkey,'ZIP '+zip_choice,{'market':market,'market_fetched_at':now_utc()})
                    st.success('Market history saved for ZIP '+zip_choice)
                except Exception as exc:st.error(str(exc))
            if market:
                section=st.radio('Market history',['Rental listing rents','Sale listing prices'],horizontal=True,key='nrh_market_kind')
                typ='rental' if section.startswith('Rental') else 'sale'
                history=market_history_points(market,typ)
                if history:
                    st.caption('ZIP-level monthly MEDIAN ASKING prices from RentCast listings; not verified executed leases or sold prices.')
                    st.line_chart(pd.DataFrame(history).set_index('Month'))
                else:st.info('No monthly market history available for this ZIP in the stored data.')
                summary=(market.get('rentalData') or {}) if typ=='rental' else (market.get('saleData') or {})
                if typ=='rental':
                    st.write('Median listed rent:',money(summary.get('medianRent')),'· Average listed rent:',money(summary.get('averageRent')))
                else:
                    st.write('Median sale ASKING price:',money(summary.get('medianPrice')),'· Median active DOM:',summary.get('medianDaysOnMarket','—'))
        else:
            st.caption('Enter a five-digit ZIP above to view cached market trends or explicitly request a new market snapshot.')
        st.markdown('##### Manual updates — no background monitoring')
        st.caption('The Hub will compare saved snapshots when you explicitly refresh. It does not email automatic future alerts or run unattended.')

    with tabs[3]:
        st.markdown('#### NORVIM branded lender / investor report')
        latest=st.session_state.get('nrh_current_research') or {}
        addresses=[e['address'] for e in items]
        repselect=st.selectbox('Report property',addresses if addresses else ['No saved properties'],key='nrh_report_select')
        info=next((e for e in items if e['address']==repselect),None)
        if info:
            logof=st.file_uploader('Optional NORVIM logo (PNG / JPG)',type=['png','jpg','jpeg'],key='nrh_logo')
            logo=logof.getvalue() if logof is not None and logof.size<2_000_000 else None
            same=latest.get('address')==repselect and latest.get('type')=='rent'
            data=latest['data'] if same else None
            comps=latest.get('comps',[]) if same else []
            if not same:st.caption('No rental comps loaded in this session for this address. PDF will include the property details and a no-data disclosure.')
            try:
                pdf=report_pdf(info,comps,data,logo)
                st.download_button('Download NORVIM PDF report',pdf,file_name='NORVIM_'+key_for(repselect)[:36]+'.pdf',
                                   mime='application/pdf',type='primary',use_container_width=True)
            except ImportError:
                st.error('ReportLab is not installed. Add reportlab>=4 to requirements.txt and redeploy.')
            except Exception as exc:st.error(f'PDF generation error: {exc}')
            body=(f"NORVIM property review — {info['address']}\n\n"
                  f"Offer: {money(info['purchase'])}; underwriting ARV: {money(info['arv'])}; "
                  f"contractor rehab: {money(info['rehab'])}.\n"
                  "The attached report contains our preliminary underwriting and comp research. "
                  "Figures require independent verification before closing.\n")
            st.text_area('Copy this note into an email to your lender / investor',value=body,height=145)
            st.download_button('Download email text',body,'NORVIM_message.txt',mime='text/plain')
            st.caption('Sharing is manual: download the PDF, then attach it in Gmail or your email app. No automatic emails are sent.')
        else:st.info('Save at least one property in My portfolio to generate a report.')
