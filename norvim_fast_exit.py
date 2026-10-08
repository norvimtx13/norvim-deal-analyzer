"""NORVIM 2.7 conservative flip math and verified-exit-evidence checks.
No HTTP calls. Python stdlib + optional pandas for pre-screen DataFrame.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Optional, Sequence, Mapping
import math


def finite(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (ValueError, TypeError):
        return default


def dollars(value):
    return f"${float(value):,.0f}" if finite(value) is not None else "—"


@dataclass
class FundingTerms:
    ltc: float = .90                 # Example only. Lender MUST confirm
    max_arv_ltv: float = .70          # Often tighter than the LTC limit
    purchase_advance: float = .90    # Share of acquisition funded AT CLOSING
    annual_interest: float = .10
    points: float = .03
    draw_bridge_fraction: float = .25  # Rehab pay-before-reimbursement buffer
    minimum_extra_cash: float = 0


@dataclass
class FlipInputs:
    purchase: float = 180000
    rehab: float = 45000
    arv: float = 320000
    months: float = 6
    acquisition_closing: float = 4000
    monthly_hold_ex_interest: float = 600
    rehab_contingency: float = .10
    sale_cost_fraction: float = .08
    target_profit: float = 35000
    monthly_draw_fee: float = 0


def flip_model(deal: FlipInputs, financing: FundingTerms):
    """Conservative full-balance loan interest, no assumed unrealized upside."""
    p, rehab, arv = max(deal.purchase, 0), max(deal.rehab, 0), max(deal.arv, 0)
    months = max(deal.months, 0)
    total_cost_basis = p + rehab
    loan = min(total_cost_basis * max(financing.ltc, 0), arv * max(financing.max_arv_ltv, 0))
    loan = max(loan, 0)
    initial_advance = min(p * max(financing.purchase_advance, 0), loan)
    equity_gap = max(total_cost_basis - loan, 0)
    cash_at_closing = max(p - initial_advance, 0) + deal.acquisition_closing + loan * financing.points
    reimbursement_buffer = rehab * max(financing.draw_bridge_fraction, 0)
    contingency = rehab * max(deal.rehab_contingency, 0)
    interest = loan * max(financing.annual_interest, 0) * months / 12
    holding = deal.monthly_hold_ex_interest * months + deal.monthly_draw_fee * months
    sale_costs = arv * max(deal.sale_cost_fraction, 0)
    fee = loan * max(financing.points, 0)
    cost = p + rehab + contingency + deal.acquisition_closing + fee + holding + interest + sale_costs
    profit = arv - cost
    initial_liquidity = cash_at_closing + reimbursement_buffer + contingency + max(financing.minimum_extra_cash, 0)
    return {
        "loan": loan, "advance_at_close": initial_advance,
        "equity_gap_total": equity_gap, "cash_at_closing_estimate": cash_at_closing,
        "draw_buffer": reimbursement_buffer, "contingency": contingency,
        "minimum_accessible_cash_estimate": initial_liquidity,
        "origination_fee": fee, "interest": interest, "noninterest_holding": holding,
        "selling_costs": sale_costs, "total_project_cost": cost,
        "profit": profit, "net_margin_on_sale": profit / arv if arv else 0,
        "pass_target": profit >= deal.target_profit,
        "assumptions": "full loan balance charged interest for entire modeled hold; no tax or partner split",
    }


def maximum_offer(deal: FlipInputs, financing: FundingTerms):
    """Maximum price meeting target_profit, using nonlinear loan constraints."""
    from dataclasses import replace
    lo, hi = 0., max(deal.arv, 1.)
    if flip_model(replace(deal, purchase=0), financing)["profit"] < deal.target_profit:
        return None
    for _ in range(65):
        mid = (lo + hi) / 2
        if flip_model(replace(deal, purchase=mid), financing)["profit"] >= deal.target_profit:
            lo = mid
        else:
            hi = mid
    return lo


def stress_test(deal: FlipInputs, financing: FundingTerms):
    from dataclasses import replace
    base = flip_model(deal, financing)
    stressed = replace(deal, arv=deal.arv*.95, rehab=deal.rehab*1.15, months=deal.months+3)
    stressed_result = flip_model(stressed, financing)
    return {"base_profit": base["profit"], "stress_profit": stressed_result["profit"], "stress_case": stressed}


def _date(value):
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            dt=value
        else:
            dt=datetime.fromisoformat(str(value)[:10])
        return dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt
    except Exception:
        return None


def comparable_evidence(rows: Sequence[Mapping], subject_sqft=None, subject_beds=None, max_miles=1.0, lookback_days=180, reference_date=None):
    """Use ONLY recorded CLOSED sales; active listings never count as sold comps.

    Input columns may use 'Sold Price', 'Sale Date', 'Sq Ft', 'Distance (mi)',
    'Beds', 'DOM', and optionally 'List Price'. Missing DOM remains unknown.
    """
    now = reference_date or datetime.now(timezone.utc)
    accepted=[]
    for row in rows or []:
        status=str(row.get('Status') or row.get('status') or 'Sold').lower()
        if status not in ('sold','closed','completed'):
            continue
        price=finite(row.get('Sold Price',row.get('sold_price',row.get('lastSalePrice'))))
        sold=_date(row.get('Sale Date',row.get('sale_date',row.get('lastSaleDate'))))
        if not price or not sold or sold>now or (now-sold).days>lookback_days:
            continue
        sqft=finite(row.get('Sq Ft',row.get('squareFootage')))
        beds=finite(row.get('Beds',row.get('bedrooms')))
        dist=finite(row.get('Distance (mi)',row.get('distance_miles')))
        if subject_sqft and sqft and not (.80*subject_sqft<=sqft<=1.20*subject_sqft):
            continue
        if subject_beds and beds is not None and abs(beds-subject_beds)>1:
            continue
        if dist is None or dist>max_miles:
            continue
        accepted.append({"sold":price, "sqft":sqft,"dom":finite(row.get('DOM', row.get('daysOnMarket'))),
                         "list":finite(row.get('List Price',row.get('list_price'))),"date":sold.isoformat(),"distance":dist})
    dom=[r['dom'] for r in accepted if r['dom'] is not None]
    ratios=[r['sold']/r['list'] for r in accepted if r['list'] and r['list']>0]
    prices=[r['sold'] for r in accepted]
    ppsf=[r['sold']/r['sqft'] for r in accepted if r['sqft'] and r['sqft']>0]
    count=len(accepted)
    median_dom=median(dom) if len(dom)>=3 else None
    sale_list=median(ratios) if len(ratios)>=3 else None
    return {"closed_comps":count,"median_sold":median(prices) if prices else None,
            "median_sold_ppsf":median(ppsf) if ppsf else None,
            "median_closed_dom":median_dom,"sale_to_list":sale_list,
            "dom_sample":len(dom),"ratio_sample":len(ratios),"filtered_records":accepted,
            "evidence_status":"Verified sample" if count>=5 and median_dom is not None else "Incomplete evidence"}


def resale_quality(*, closed_comps=None, median_closed_dom=None, sale_to_list=None, active_competition=None, profit=None, stress_profit=None):
    """Reject certainty when closed DOM or closed sale samples aren't available."""
    n=finite(closed_comps,0) or 0
    dom=finite(median_closed_dom)
    ratio=finite(sale_to_list)
    competition=finite(active_competition)
    if dom is None or n<5:
        return {"status":"UNVERIFIED", "score":None,
                "reason":"Need ≥5 comparable CLOSED sales and observed sold-home DOM; listing DOM is not resale DOM."}
    score=35
    score+=25 if dom<=30 else (17 if dom<=45 else (8 if dom<=60 else 0))
    score+=15 if n>=10 else (10 if n>=7 else 6)
    score+=15 if ratio is not None and ratio>=.98 else (8 if ratio is not None and ratio>=.95 else 0)
    score+=10 if competition is not None and competition<=3 else (4 if competition is not None and competition<=6 else 0)
    if profit is not None and profit<30000: score-=20
    if stress_profit is not None and stress_profit<0: score-=20
    score=max(0,min(100,score))
    status="FAST EXIT" if score>=80 and dom<=45 else ("REVIEW" if score>=60 and dom<=60 else "SLOW / RISKY")
    return {"status":status,"score":score,"reason":f"{n:.0f} closed comps; median sold DOM {dom:.0f} days"}


def prescreen_area(df):
    """Preliminary *acquisition* priority only. Never claims quick resale.

    Older DOM may indicate negotiating opportunity, NOT liquid exit.
    """
    if df is None or getattr(df,'empty',True):
        return df
    import pandas as pd
    out=df.copy()
    out['Original Screen Score']=out['Screen Score'] if 'Screen Score' in out else None
    price=pd.to_numeric(out.get('Price'),errors='coerce')
    sf=pd.to_numeric(out.get('Sq Ft'),errors='coerce')
    beds=pd.to_numeric(out.get('Beds'),errors='coerce')
    yr=pd.to_numeric(out.get('Year Built'),errors='coerce')
    ppsf=price/sf.where(sf>0)
    median_by_zip=ppsf.groupby(out['ZIP'].astype(str)).transform('median')
    spread=(1-ppsf/median_by_zip).clip(lower=-.40,upper=.40)
    # Capital conservatism: relative ask discount merits REVIEW, never an ARV claim.
    val=45+(spread.fillna(0)*70)
    val=val+(beds.between(3,4).fillna(False)*6)+(yr.between(1960,2005).fillna(False)*5)
    # Missing essentials reduce confidence. Subject listing DOM is not an EXIT factor.
    val=val-(price.isna()*15)-(sf.isna()*15)
    out['Acquisition Screen']=val.round().clip(0,69).astype(int)  # Never auto-greenlight with unverified sold comps
    out['Liquidity Status']='NOT VERIFIED'
    out['Why it surfaced']=out['Why it surfaced'].fillna('') if 'Why it surfaced' in out else ''
    out['Why it surfaced']=out['Why it surfaced'].astype(str).str.replace(r'\s*·?\s*\d+ DOM','',regex=True).str.strip(' ·') + ' · Verify closed sales & sold-home DOM'
    out['Screen Score']=out['Acquisition Screen']
    return out.sort_values(['Acquisition Screen','Price'],ascending=[False,True],na_position='last').reset_index(drop=True)
