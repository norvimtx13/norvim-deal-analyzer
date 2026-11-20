"""Source-aware property checks and distressed-lead imports. No network or secrets."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import re
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

CATEGORIES = {
    'county': ('County classification & units', 'Check the official parcel record and its stated building classification.'),
    'permitted_use': ('City-approved use', 'Request approved plans, applicable permits and final inspections for the stated unit count.'),
    'permits': ('Permits & inspections', 'Review original permit scope, inspection results and missing files.'),
    'enforcement': ('Current code & unsafe-building cases', 'Request current open cases, orders, corrective requirements and closure records.'),
    'taxes': ('Delinquent property taxes', 'Check the current Tax Office statement by parcel/account; preserve its statement date.'),
    'foreclosure': ('Foreclosure / auction status', 'Review the actual notice, scheduled date and any cancellation or completed-sale evidence.'),
    'title': ('Title, liens & restrictions', 'Have title review recorded restrictions, liens and survey exceptions.'),
    'flood': ('Flood risk & insurance', 'Review the official flood map and obtain a property-specific insurance quote.'),
}
LEAD_TYPES = ('Trustee sale notice', 'Tax sale scheduled', 'Tax delinquent', 'Unclassified notice')
OFFICIAL_DOMAINS = ('hcad.org', 'hctx.net', 'harriscountytx.gov', 'hctax.net', 'houstontx.gov', 'houstonpermittingcenter.org', 'fema.gov')

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def web_url(value):
    try:
        p = urlsplit(str(value).strip())
        return str(value).strip() if p.scheme == 'https' and p.hostname and not p.username and not p.password else ''
    except ValueError:
        return ''

def official_url(value):
    url = web_url(value)
    host = (urlsplit(url).hostname or '').lower()
    return bool(url) and any(host == d or host.endswith('.' + d) for d in OFFICIAL_DOMAINS)

def address_key(address):
    value = str(address).lower()
    for a, b in [('street','st'), ('drive','dr'), ('road','rd'), ('avenue','ave'), ('lane','ln'), ('boulevard','blvd')]:
        value = re.sub(r'\b' + a + r'\b', b, value)
    return re.sub(r'[^a-z0-9]', '', value)

def snapshot_key(address):
    return 'norvim::verification::' + hashlib.sha256(address_key(address).encode()).hexdigest()[:24]

def iso_date(value):
    value = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(value[:10] if fmt == '%Y-%m-%d' else value, fmt).date().isoformat()
        except ValueError:
            pass
    return ''

def empty_report(address):
    return {'address': str(address).strip(), 'checked_at': '', 'summary': 'Verification has not been completed.', 'checks': [], 'sources': [], 'method': 'unreviewed'}

def check_rows(report):
    saved = {c.get('category'): c for c in (report or {}).get('checks', []) if isinstance(c, dict)}
    result = []
    for category, (title, action) in CATEGORIES.items():
        c = saved.get(category, {})
        result.append({'category': category, 'title': title, 'status': c.get('status', 'Unknown'),
                       'finding': c.get('finding') or 'No conclusion has been recorded.',
                       'source_url': web_url(c.get('source_url', '')), 'as_of': c.get('as_of', ''), 'checked_at': c.get('checked_at', ''),
                       'next_action': c.get('next_action') or action})
    return result

def county_report(address, parcel, checked_at=None):
    """A matching county source establishes its classification, never City approval."""
    report = empty_report(address)
    report.update(checked_at=checked_at or utc_now(), method='county_gis')
    p = parcel if isinstance(parcel, dict) else {}
    street = ' '.join(str(p.get(k) or '').strip() for k in ('site_str_num', 'site_str_name', 'site_str_sfx')).strip()
    match = bool(street and address_key(street) == address_key(str(address).split(',')[0]))
    city_match = len(str(address).split(',')) < 2 or bool(p.get('site_city') and address_key(str(address).split(',')[1]) == address_key(p['site_city']))
    account = str(p.get('acct_num') or '').strip()
    state_class = str(p.get('state_class') or '').strip()
    usable = match and city_match and account and state_class
    finding = (f"County account {account}; tax year {p.get('tax_year') or 'not supplied'}; state class {state_class}; "
               f"land use {p.get('land_use') or 'not supplied'}. "
               'This is county tax-record classification; City-approved use remains unconfirmed.') if usable else (
               'No matching, complete county classification record was returned. No legal-use conclusion can be drawn.')
    report['checks'] = [{'category': 'county', 'status': 'Source checked' if usable else 'Needs review' if p else 'Unavailable',
        'finding': finding, 'source_url': 'https://search.hcad.org/', 'as_of': '', 'checked_at': report['checked_at'],
        'next_action': 'Review City-approved unit count separately.' if usable else CATEGORIES['county'][1]}]
    report['summary'] = 'County record checked; other verification categories remain unresolved.' if usable else 'County lookup unresolved.'
    report['sources'] = [{'url': 'https://search.hcad.org/', 'title': 'HCAD official parcel record', 'accessed_at': report['checked_at']}]
    return report

def normalize_agent_report(payload, expected_address, source_urls, checked_at=None):
    """AI findings are review items, even when the model requests a verified label."""
    if not isinstance(payload, dict) or address_key(payload.get('address', '')) != address_key(expected_address):
        raise ValueError('Research returned a different property address. Previous findings are unchanged.')
    stamp = checked_at or utc_now()
    sources = {web_url(u) for u in source_urls if official_url(u)}
    rows, seen = [], set()
    for c in payload.get('checks', []):
        category = c.get('category') if isinstance(c, dict) else None
        if category not in CATEGORIES or category in seen:
            continue
        seen.add(category)
        url = web_url(c.get('source_url', ''))
        supported = bool(url and url in sources)
        finding = str(c.get('finding', '')).strip()[:2400]
        status = 'Unavailable' if c.get('status') == 'Unavailable' else 'Needs review' if supported else 'Unknown'
        if not supported:
            finding = 'No matching official source was returned for this conclusion. It remains unverified.'
            url = ''
        rows.append({'category': category, 'status': status, 'finding': finding or 'No usable finding returned.',
                     'source_url': url, 'as_of': iso_date(c.get('as_of')), 'checked_at': stamp,
                     'next_action': str(c.get('next_action') or CATEGORIES[category][1])[:1500]})
    return {'address': expected_address, 'checked_at': stamp, 'method': 'ai_web_research',
            'summary': 'AI-assisted source screening. Review the linked records; this is not legal clearance.',
            'checks': rows, 'sources': [{'url': u, 'title': 'Official research source', 'accessed_at': stamp} for u in sorted(sources)]}

def merge_reports(existing, incoming):
    if existing and address_key(existing.get('address', '')) != address_key(incoming.get('address', '')):
        raise ValueError('Cannot merge verification for different addresses.')
    old = {c['category']: c for c in (existing or {}).get('checks', [])}
    for c in incoming.get('checks', []):
        # Preserve the narrow, direct county finding; AI cannot replace it with a broader conclusion.
        if c['category'] == 'county' and old.get('county', {}).get('status') == 'Source checked' and incoming.get('method') == 'ai_web_research':
            continue
        old[c['category']] = c
    return {**incoming, 'checks': list(old.values()), 'sources': list({s['url']: s for s in (existing or {}).get('sources', []) + incoming.get('sources', [])}.values())}

def _amount(value):
    if value in (None, ''):
        return None
    try:
        n = float(str(value).replace('$', '').replace(',', ''))
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None

def normalize_leads(rows, default_type='Unclassified notice', trusted_sources=None, checked_at=None):
    result, seen = [], set()
    allowed = None if trusted_sources is None else {web_url(u) for u in trusted_sources if official_url(u)}
    for raw in rows[:500]:
        if not isinstance(raw, dict):
            continue
        r = {str(k).strip().lower().replace(' ', '_'): v for k, v in raw.items()}
        address = str(r.get('address') or r.get('property_address') or '').strip()[:255]
        if not address:
            continue
        if ',' not in address and r.get('city'):
            address += ', ' + str(r['city']).strip() + ', ' + str(r.get('state') or 'TX').strip() + ' ' + str(r.get('zip') or r.get('zip_code') or '').strip()
        kind = str(r.get('lead_type') or default_type)
        if kind not in LEAD_TYPES:
            kind = 'Unclassified notice'
        sale_date = iso_date(r.get('auction_date') or r.get('sale_date'))
        doc = str(r.get('document_id') or '').strip()[:100]
        source = web_url(r.get('source_url') or r.get('source') or '')
        supported = official_url(source) and (allowed is None or source in allowed)
        if allowed is not None and not supported:
            continue  # AI discovery cannot invent leads without a returned official source.
        if kind in ('Trustee sale notice', 'Tax sale scheduled') and (not supported or not sale_date):
            kind = 'Unclassified notice'
        if kind == 'Tax delinquent' and _amount(r.get('tax_due')) == 0:
            kind = 'Unclassified notice'
        identity = (address_key(address), kind, sale_date, doc)
        if identity in seen:
            continue
        seen.add(identity)
        status = 'Tax delinquency reported' if kind == 'Tax delinquent' else 'Scheduled sale reported' if kind in ('Trustee sale notice', 'Tax sale scheduled') else 'Needs classification'
        result.append({'address': address, 'lead_type': kind, 'auction_date': sale_date, 'document_id': doc,
            'account': str(r.get('account') or r.get('account_number') or '').strip()[:40],
            'tax_due': _amount(r.get('tax_due')), 'source_url': source, 'status': status,
            'checked_at': checked_at or utc_now(), 'record_as_of': iso_date(r.get('record_as_of') or r.get('statement_date')),
            'notes': str(r.get('notes') or '')[:2000], 'review_required': True})
    return result

def import_leads_csv(data, default_type='Unclassified notice'):
    if len(data) > 2_000_000:
        raise ValueError('CSV exceeds the 2 MB import limit.')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Save the collector CSV as UTF-8.') from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not any(str(x).strip().lower().replace(' ', '_') in ('address', 'property_address') for x in reader.fieldnames):
        raise ValueError('CSV needs an address or property_address column.')
    rows = []
    for row in reader:
        rows.append(row)
        if len(rows) > 500:
            raise ValueError('Import a maximum of 500 rows at a time.')
    return normalize_leads(rows, default_type)

def merge_leads(existing, incoming):
    def identity(r):
        return (address_key(r['address']), r['lead_type'], r['auction_date'], r['document_id'])
    merged = {identity(r): r for r in existing}
    for row in incoming:
        merged[identity(row)] = row
    return list(merged.values())[-500:]

def export_json(value):
    return json.dumps(value, indent=2, ensure_ascii=False).encode('utf-8')

def export_leads_csv(rows):
    out = io.StringIO()
    fields = ['address','lead_type','auction_date','document_id','account','tax_due','source_url','status','checked_at','record_as_of','notes','review_required']
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        clean = {k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k, v in row.items()}
        writer.writerow(clean)
    return out.getvalue().encode('utf-8-sig')
