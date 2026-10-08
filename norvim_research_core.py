"""NORVIM v2.8 research utilities. No network calls or persisted credentials."""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from statistics import median
from xml.sax.saxutils import escape
import csv
import json
import math
import re

MAX_SAVED = 50
STATUSES = ('Researching','Contractor estimate','Negotiating','Lender review','Under contract','Hold','Rejected','Sold')

def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def key_for(address):
    return re.sub(r'\W+', '', str(address).lower())

def number(v, fallback=None):
    try:
        f=float(str(v).replace(',','').replace('$',''))
        return f if math.isfinite(f) else fallback
    except (TypeError, ValueError):
        return fallback

def money(v):
    a=number(v)
    return f'${a:,.0f}' if a is not None else '—'

def normalize_portfolio(value):
    if isinstance(value,dict):
        value=value.get('items',[])
    if not isinstance(value,list):
        return []
    seen=set(); result=[]
    for item in value:
        if not isinstance(item,dict):
            continue
        address=str(item.get('address','')).strip()[:255]
        k=key_for(address)
        if not k or k in seen:continue
        seen.add(k)
        clean={'address':address, 'zip':str(item.get('zip','')).strip()[:10],
               'status':item.get('status') if item.get('status') in STATUSES else STATUSES[0],
               'purchase':number(item.get('purchase'),0), 'arv':number(item.get('arv'),0),
               'rehab':number(item.get('rehab'),0), 'contractor':str(item.get('contractor',''))[:250],
               'notes':str(item.get('notes',''))[:3000],
               'updated':str(item.get('updated',''))[:64] or now_utc(),
               'source':str(item.get('source',''))[:500]}
        result.append(clean)
        if len(result)==MAX_SAVED:break
    return result

def upsert_property(items, item):
    items=normalize_portfolio(items)
    entry=normalize_portfolio([item])
    if not entry:raise ValueError('Enter a valid address')
    entry=entry[0]
    k=key_for(entry['address'])
    kept=[x for x in items if key_for(x['address'])!=k]
    if len(kept)>=MAX_SAVED:raise ValueError('Portfolio full: export or remove a property before adding more')
    return [entry]+kept

def remove_property(items,address):
    return [x for x in normalize_portfolio(items) if key_for(x['address'])!=key_for(address)]

def json_backup(items):
    return json.dumps({'product':'NORVIM DealFinder','schema_version':1,'exported':now_utc(),
                       'items':normalize_portfolio(items)},indent=2).encode('utf-8')

def csv_backup(items):
    import io
    b=io.StringIO();cols=['address','zip','status','purchase','arv','rehab','contractor','notes','updated','source']
    writer=csv.DictWriter(b,fieldnames=cols);writer.writeheader()
    for r in normalize_portfolio(items):writer.writerow({c:r.get(c,'') for c in cols})
    return b.getvalue().encode('utf-8-sig')

def _date(s):
    try:
        d=datetime.fromisoformat(str(s)[:10]).replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None

def extract_rental_comps(payload,max_count=20,max_radius=2.0,days_old=180,as_of=None):
    """Only rental asking-price comps. Not executed rents. Incomplete records flagged, not fabricated."""
    if not isinstance(payload,dict):return []
    now=as_of or datetime.now(timezone.utc)
    result=[]
    for x in payload.get('comparables') or []:
        if not isinstance(x,dict):continue
        price=number(x.get('price') or x.get('rent'))
        if price is None or price<=0:continue
        distance=number(x.get('distance'))
        if distance is not None and distance>max_radius:continue
        listed=x.get('listedDate') or x.get('lastSeenDate') or x.get('removedDate')
        dt=_date(listed)
        if dt and (now-dt).days>days_old:continue
        result.append({'Address':str(x.get('formattedAddress') or x.get('address') or 'Unavailable'),
                       'Asking Rent':price,'Beds':number(x.get('bedrooms')),
                       'Sq Ft':number(x.get('squareFootage')), 'Miles':distance,
                       'Date':str(listed or ''),'Status':str(x.get('status') or 'Unknown'),
                       'Correlation':number(x.get('correlation'))})
    # Prefer provider's correlation ranking. Missing values last.
    result.sort(key=lambda x:(-(x['Correlation'] if x['Correlation'] is not None else -1),
                              x['Miles'] if x['Miles'] is not None else 1e6))
    return result[:max(1,min(int(max_count),20))]

def rent_stats(rows):
    values=[number(r.get('Asking Rent')) for r in rows or []]
    values=[v for v in values if v and v>0]
    return {'count':len(values),'median_asking_rent':median(values) if values else None,
            'min_asking_rent':min(values) if values else None,
            'max_asking_rent':max(values) if values else None}

def trend_points(entries):
    """Historical snapshots for ONE address, not broad neighborhood rent trends."""
    seen={}
    for e in entries or []:
        if not isinstance(e,dict):continue
        d=_date(e.get('date'));v=number(e.get('rent'))
        if d and v is not None and v>0:
            seen[d.date().isoformat()]=v
    return [{'Date':k,'Estimated rent':seen[k]} for k in sorted(seen)]

def changes(previous,current,pct=5):
    a=number(previous);b=number(current)
    if not a or b is None:return None
    delta=(b-a)/a*100
    return {'old':a,'new':b,'change_pct':delta,'significant':abs(delta)>=pct}

def report_pdf(property_info, rental_rows, snapshot=None, logo=None):
    """Generate a NORVIM research report in memory; no external services."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
    from reportlab.lib.units import inch
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=letter,rightMargin=45,leftMargin=45,topMargin=40,bottomMargin=42)
    styles=getSampleStyleSheet()
    dark=colors.HexColor('#28362E'); olive=colors.HexColor('#596b50'); light=colors.HexColor('#F5F2EA')
    styles.add(ParagraphStyle(name='NorvimTitle',parent=styles['Title'],fontName='Times-Bold',fontSize=24,leading=28,textColor=dark,spaceAfter=12))
    styles.add(ParagraphStyle(name='NorvimHeading',parent=styles['Heading2'],fontName='Helvetica-Bold',fontSize=12,textColor=dark,spaceBefore=13,spaceAfter=6))
    styles.add(ParagraphStyle(name='NorvimBody',parent=styles['BodyText'],fontSize=9,leading=13,textColor=dark,spaceAfter=8))
    p=lambda s:Paragraph(escape(str(s)),styles['NorvimBody'])
    header_style=ParagraphStyle(name='NorvimColHeader',parent=styles['NorvimBody'],fontName='Helvetica-Bold',fontSize=8,textColor=colors.white)
    story=[]
    if logo:
        try:
            from reportlab.lib.utils import ImageReader
            ir=ImageReader(BytesIO(logo));iw,ih=ir.getSize()
            scale=min(140/iw,52/ih)
            story.append(Image(BytesIO(logo),width=iw*scale,height=ih*scale));story.append(Spacer(1,8))
        except Exception:
            pass
    story.append(Paragraph('NORVIM | PROPERTY RESEARCH',styles['NorvimTitle']))
    story.append(p('Investment research only — not an appraisal or financing commitment'))
    story.append(Paragraph('Property overview',styles['NorvimHeading']))
    columns=[('Address',property_info.get('address','—')),('Status',property_info.get('status','—')),
             ('Asking / offer price',money(property_info.get('purchase'))),('Underwriting ARV',money(property_info.get('arv'))),
             ('Contractor rehab estimate',money(property_info.get('rehab'))),('Data source',property_info.get('source','—'))]
    cells=[[p(k),p(v)] for k,v in columns]
    t=Table(cells,colWidths=[150,365],hAlign='LEFT');t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),light),('ROWBACKGROUNDS',(0,0),(-1,-1),[light,colors.white]),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.append(t)
    note=property_info.get('notes') or ''
    if note:
        story.append(Paragraph('Contractor / acquisition notes',styles['NorvimHeading']));story.append(p(note))
    stats=rent_stats(rental_rows)
    story.append(Paragraph('Rental comparable listings',styles['NorvimHeading']))
    story.append(p(f"{stats['count']} asking-rent comps displayed. Median ASKING rent: {money(stats['median_asking_rent'])}. These are not signed leases."))
    header=['Address','Ask / mo','Beds','Sq ft','Miles']
    data=[[Paragraph(escape(v),header_style) for v in header]]
    for r in rental_rows[:20]:
        data.append([p(str(r.get('Address',''))[:48]),p(money(r.get('Asking Rent'))),p(r.get('Beds','—')),
                     p(r.get('Sq Ft','—')),p(round(r['Miles'],2) if r.get('Miles') is not None else '—')])
    if len(data)==1:data.append([p('No rental comps loaded'),p('—'),p('—'),p('—'),p('—')])
    t=Table(data,colWidths=[233,75,45,78,84],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),olive),('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,light]),
        ('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.5,dark)]))
    story.append(t)
    if snapshot:
        story.append(Paragraph('Data freshness',styles['NorvimHeading']))
        story.append(p(f"Rent estimate: {money(snapshot.get('rent_estimate'))}/month. Fetched: {snapshot.get('fetched_at','unknown')}."))
    story.append(Spacer(1,15))
    story.append(p('Sources are user inputs and optional RentCast API snapshots. Verify comps, permits, flood, title, insurance, lender terms and contractor bids independently. Closed-sale DOM cannot be inferred from active listing DOM.'))
    story.append(p('Generated '+now_utc()+' UTC | NORVIM'))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

def market_history_points(market,market_type='rental'):
    """RentCast ZIP history, grouped from active LISTINGS, not executed lease/sale prices."""
    group=(market or {}).get('rentalData' if market_type=='rental' else 'saleData') or {}
    hist=group.get('history') or {}
    points=[]
    if isinstance(hist,dict):
        iterable=hist.items()
    elif isinstance(hist,list):
        iterable=[(str(x.get('date',''))[:7],x) for x in hist if isinstance(x,dict)]
    else:iterable=[]
    measure='medianRent' if market_type=='rental' else 'medianPrice'
    for dt,entry in iterable:
        if not isinstance(entry,dict):continue
        val=number(entry.get(measure))
        if val is None or val<=0:continue
        month=str(dt)[:7]
        if len(month)==7 and month[4]=='-':points.append({'Month':month,measure:val})
    return sorted(points,key=lambda x:x['Month'])
