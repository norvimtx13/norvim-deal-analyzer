import os
import re
import math
from datetime import datetime
from urllib.parse import quote
import pandas as pd
import requests
import streamlit as st
import pydeck as pdk

API_BASE = "https://api.rentcast.io/v1"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

st.set_page_config(page_title="NORVIM Deal Analyzer", page_icon="🏠", layout="wide")
st.markdown("""
<style>
:root { color-scheme: light !important; }
html, body, [data-testid="stAppViewContainer"], .stApp {
    background: #F6F2E9 !important;
    color: #252A24 !important;
}
[data-testid="stHeader"] { background: rgba(246,242,233,.96) !important; }
[data-testid="stSidebar"] { background: #ECE6D8 !important; }
[data-testid="stSidebar"] * { color: #252A24 !important; }
.block-container { padding-top: 1.5rem; }
.k { letter-spacing:.15em; text-transform:uppercase; font-size:.78rem; color:#59634F !important; }
.t { font-family:Georgia,serif; font-size:2.3rem; line-height:1.05; color:#172019 !important; }
.s { color:#666B62 !important; margin-bottom:1rem; }

/* Inputs */
.stTextInput input, .stNumberInput input, [data-baseweb="select"] > div {
    background:#FFFFFF !important;
    color:#252A24 !important;
    border-color:#CFC7B8 !important;
}
.stTextInput label, .stNumberInput label, .stSelectbox label,
[data-testid="stWidgetLabel"] p, .stCaptionContainer p, .stMarkdown p {
    color:#4E554B !important;
}

/* Buttons */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
    background:#59634F !important;
    color:#FFFFFF !important;
    border:1px solid #59634F !important;
}

/* Tabs */
button[data-baseweb="tab"] { color:#59634F !important; }
button[data-baseweb="tab"][aria-selected="true"] { color:#252A24 !important; }

/* Alerts */
[data-testid="stAlert"] * { color:#252A24 !important; }

/* Tables */
[data-testid="stDataFrame"] { color:#252A24 !important; }

/* Custom result cards: avoids Streamlit metric/theme conflicts */
.norvim-card {
    background:#FFFDF7;
    border:1px solid #D8D1C2;
    border-radius:12px;
    padding:16px 16px 14px;
    min-height:118px;
}
.norvim-card .label {
    color:#697066 !important;
    font-size:.82rem;
    font-weight:600;
    margin-bottom:10px;
    line-height:1.25;
}
.norvim-card .value {
    color:#172019 !important;
    font-size:1.85rem;
    font-weight:700;
    line-height:1.08;
    overflow-wrap:anywhere;
}
.norvim-card .sub {
    color:#7A8077 !important;
    font-size:.78rem;
    margin-top:7px;
}

.friendly-status {
    border-radius:16px;
    padding:18px 20px;
    margin:10px 0 18px;
    border:1px solid #D8D1C2;
    background:#FFFDF7;
}
.friendly-status.good { background:#EAF2E5; border-color:#B9CCAF; }
.friendly-status.warn { background:#FFF3D8; border-color:#E3C884; }
.friendly-status.bad { background:#F8E5E1; border-color:#D9AAA0; }
.friendly-status .eyebrow {
    font-size:.76rem;
    font-weight:700;
    letter-spacing:.08em;
    text-transform:uppercase;
    color:#6B7168 !important;
    margin-bottom:5px;
}
.friendly-status .headline {
    font-family:Georgia,serif;
    font-size:1.7rem;
    font-weight:700;
    color:#172019 !important;
    margin-bottom:6px;
}
.friendly-status .body {
    font-size:.95rem;
    color:#4E554B !important;
    line-height:1.45;
}
.explain-box {
    background:#F1EEE5;
    border-left:4px solid #59634F;
    border-radius:8px;
    padding:12px 14px;
    margin:8px 0 14px;
}
.explain-box strong { color:#172019 !important; }
.action-card {
    background:#FFFDF7;
    border:1px solid #D8D1C2;
    border-radius:12px;
    padding:14px 16px;
    margin-bottom:10px;
}
.action-card .title {
    font-weight:700;
    color:#172019 !important;
    margin-bottom:4px;
}
.action-card .copy {
    color:#596058 !important;
    font-size:.9rem;
    line-height:1.4;
}
@media (max-width: 700px) {
    .norvim-card .value { font-size:1.45rem; }
}
</style>
""", unsafe_allow_html=True)


def money(v):
    try: return f"${float(v):,.0f}"
    except: return "—"


def result_card(label, value, sub=None):
    safe_label = str(label or "")
    safe_value = str(value or "—")
    safe_sub = f'<div class="sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="norvim-card"><div class="label">{safe_label}</div><div class="value">{safe_value}</div>{safe_sub}</div>',
        unsafe_allow_html=True,
    )


def get_key():
    try:
        if "RENTCAST_API_KEY" in st.secrets:
            return st.secrets["RENTCAST_API_KEY"]
    except Exception:
        pass
    return os.getenv("RENTCAST_API_KEY") or st.session_state.get("rentcast_api_key", "")


def api_get(path, params, key):
    r = requests.get(f"{API_BASE}{path}", params=params,
                     headers={"Accept":"application/json","X-Api-Key":key}, timeout=30)
    if r.status_code == 401: raise RuntimeError("RentCast rejected the API key.")
    if r.status_code == 429: raise RuntimeError("RentCast request limit reached.")
    if not r.ok:
        try: detail = r.json().get("message", "")
        except: detail = r.text[:250]
        raise RuntimeError(f"Property-data request failed ({r.status_code}). {detail}")
    return r.json()



def api_get_optional(path, params, key):
    """Same as api_get, but return an empty object if a record simply does not exist."""
    r = requests.get(
        f"{API_BASE}{path}",
        params=params,
        headers={"Accept":"application/json","X-Api-Key":key},
        timeout=30,
    )
    if r.status_code == 404:
        return {}
    if r.status_code == 401:
        raise RuntimeError("RentCast rejected the API key.")
    if r.status_code == 429:
        raise RuntimeError("RentCast request limit reached.")
    if not r.ok:
        try:
            detail = r.json().get("message", "")
        except:
            detail = r.text[:250]
        raise RuntimeError(f"Property-data request failed ({r.status_code}). {detail}")
    return r.json()


def first_record(payload):
    if isinstance(payload, list):
        return payload[0] if payload else {}
    return payload or {}


def normalize_address(address):
    """Create a stable cache key so small formatting/case changes reuse the same property snapshot."""
    cleaned = re.sub(r"[^a-z0-9#]+", " ", address.strip().lower())
    return " ".join(cleaned.split())


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def analyze_cached(address_key, key, _address_for_api):
    """
    Fetch one property snapshot and cache it for 30 days.
    _address_for_api starts with an underscore so Streamlit does not hash formatting differences;
    address_key is the normalized identity used for the cache key.
    """
    val = api_get("/avm/value", {"address":_address_for_api,"lookupSubjectAttributes":"true","maxRadius":2,"daysOld":365,"compCount":15}, key)
    rent = api_get("/avm/rent/long-term", {"address":_address_for_api,"lookupSubjectAttributes":"true","maxRadius":3,"daysOld":365,"compCount":15}, key)
    subj = val.get("subjectProperty") or {}
    market = api_get("/markets", {"zipCode":subj.get("zipCode"), "dataType":"All", "historyRange":12}, key) if subj.get("zipCode") else {}

    # Public-record profile: owner, tax history, sale history, HOA, subdivision, features, etc.
    property_payload = api_get_optional("/properties", {"address":_address_for_api}, key)
    property_record = first_record(property_payload)

    # Exact sale-listing record (if one exists). The listing record contains current status,
    # asking price, DOM, MLS/agent/office data, and listing history.
    listing_record = {}
    property_id = property_record.get("id") or subj.get("id")
    if property_id:
        listing_record = api_get_optional(
            f"/listings/sale/{quote(str(property_id), safe='')}",
            {},
            key,
        )

    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return val, rent, market, property_record, listing_record, fetched_at



def haversine_miles(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except Exception:
        return None
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * r * math.asin(min(1, math.sqrt(a)))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def neighborhood_cached(address_key, key, _address_for_api, property_type):
    """
    Optional neighborhood snapshot. This is deliberately separate from the core analysis
    so the user only spends the two additional API calls when they want the neighborhood map.
    """
    params_sales = {
        "address": _address_for_api,
        "radius": 1.5,
        "saleDateRange": 365,
        "limit": 75,
    }
    params_active = {
        "address": _address_for_api,
        "radius": 1.5,
        "status": "Active",
        "limit": 75,
    }
    if property_type:
        params_sales["propertyType"] = property_type
        params_active["propertyType"] = property_type

    recent_sales = api_get("/properties", params_sales, key)
    active_listings = api_get("/listings/sale", params_active, key)
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return recent_sales or [], active_listings or [], fetched_at


def recent_sales_df(records, subject_lat=None, subject_lon=None):
    rows = []
    for r in records or []:
        sqft = r.get("squareFootage")
        price = r.get("lastSalePrice")
        lat, lon = r.get("latitude"), r.get("longitude")
        rows.append({
            "Address": r.get("formattedAddress"),
            "ZIP": r.get("zipCode"),
            "Sold Price": price,
            "Sale Date": str(r.get("lastSaleDate") or "")[:10] or None,
            "Beds": r.get("bedrooms"),
            "Baths": r.get("bathrooms"),
            "Sq Ft": sqft,
            "$/Sq Ft": (float(price)/float(sqft) if price and sqft else None),
            "Distance (mi)": haversine_miles(subject_lat, subject_lon, lat, lon) if None not in (subject_lat, subject_lon, lat, lon) else None,
            "Latitude": lat,
            "Longitude": lon,
        })
    df = pd.DataFrame(rows)
    if not df.empty and "Sale Date" in df.columns:
        df = df.sort_values("Sale Date", ascending=False, na_position="last")
    return df


def active_listing_df(records, subject_lat=None, subject_lon=None):
    rows = []
    for r in records or []:
        sqft = r.get("squareFootage")
        price = r.get("price")
        lat, lon = r.get("latitude"), r.get("longitude")
        rows.append({
            "Address": r.get("formattedAddress"),
            "ZIP": r.get("zipCode"),
            "Ask Price": price,
            "Beds": r.get("bedrooms"),
            "Baths": r.get("bathrooms"),
            "Sq Ft": sqft,
            "$/Sq Ft": (float(price)/float(sqft) if price and sqft else None),
            "DOM": r.get("daysOnMarket"),
            "Listed": str(r.get("listedDate") or "")[:10] or None,
            "Distance (mi)": haversine_miles(subject_lat, subject_lon, lat, lon) if None not in (subject_lat, subject_lon, lat, lon) else None,
            "Latitude": lat,
            "Longitude": lon,
        })
    df = pd.DataFrame(rows)
    if not df.empty and "Distance (mi)" in df.columns:
        df = df.sort_values(["Distance (mi)", "DOM"], ascending=[True, True], na_position="last")
    return df


def neighborhood_map_rows(subj, sales_df, active_df, comps_df):
    rows = []
    slat, slon = subj.get("latitude"), subj.get("longitude")
    if slat is not None and slon is not None:
        rows.append({
            "lat": slat, "lon": slon, "type": "Subject property",
            "address": subj.get("formattedAddress") or "Subject property",
            "price": None, "dom": None, "detail": "Property being analyzed",
        })
    for _, r in sales_df.dropna(subset=["Latitude","Longitude"]).iterrows() if not sales_df.empty else []:
        rows.append({
            "lat": r["Latitude"], "lon": r["Longitude"], "type": "Recent sale",
            "address": r.get("Address"), "price": r.get("Sold Price"), "dom": None,
            "detail": f"Sold {r.get('Sale Date') or 'date unavailable'}",
        })
    for _, r in active_df.dropna(subset=["Latitude","Longitude"]).iterrows() if not active_df.empty else []:
        rows.append({
            "lat": r["Latitude"], "lon": r["Longitude"], "type": "Active listing",
            "address": r.get("Address"), "price": r.get("Ask Price"), "dom": r.get("DOM"),
            "detail": f"Listed {r.get('Listed') or 'date unavailable'}",
        })
    for _, r in comps_df.dropna(subset=["Latitude","Longitude"]).iterrows() if not comps_df.empty else []:
        rows.append({
            "lat": r["Latitude"], "lon": r["Longitude"], "type": "AVM comp",
            "address": r.get("Address"), "price": r.get("Price"), "dom": r.get("DOM"),
            "detail": f"{r.get('Distance (mi)'):.2f} mi away" if pd.notna(r.get("Distance (mi)")) else "Comparable property",
        })
    return pd.DataFrame(rows)


def render_neighborhood_map(map_df, subject_lat=None, subject_lon=None):
    if map_df.empty:
        st.info("No map coordinates were returned.")
        return

    color_map = {
        "Subject property": [89, 99, 79, 255],
        "Recent sale": [61, 120, 184, 210],
        "Active listing": [214, 137, 63, 220],
        "AVM comp": [126, 92, 120, 190],
    }
    layers = []
    for category, rgba in color_map.items():
        layer_df = map_df[map_df["type"] == category]
        if layer_df.empty:
            continue
        radius = 105 if category == "Subject property" else 70
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=layer_df,
                get_position="[lon, lat]",
                get_fill_color=rgba,
                get_line_color=[255,255,255,220],
                line_width_min_pixels=1,
                get_radius=radius,
                radius_min_pixels=7 if category == "Subject property" else 5,
                radius_max_pixels=16 if category == "Subject property" else 11,
                pickable=True,
                stroked=True,
            )
        )

    if subject_lat is None or subject_lon is None:
        subject_lat = float(map_df["lat"].mean())
        subject_lon = float(map_df["lon"].mean())

    view_state = pdk.ViewState(
        latitude=float(subject_lat),
        longitude=float(subject_lon),
        zoom=13.2,
        pitch=0,
    )
    tooltip = {
        "html": "<b>{type}</b><br/>{address}<br/><b>Price:</b> {price}<br/><b>DOM:</b> {dom}<br/>{detail}",
        "style": {"backgroundColor": "#252A24", "color": "white"},
    }
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip=tooltip,
    )
    st.pydeck_chart(deck, use_container_width=True)
    st.caption("Map legend: subject property · recent recorded sales · active listings · AVM comparable properties.")



def offer_math(strategy, arv, rent, rehab, closing, selling, holding, contingency, target_profit, assignment, refi_ltv, vacancy, opex, cap):
    arv, rent, rehab = max(float(arv or 0),0), max(float(rent or 0),0), max(float(rehab or 0),0)
    close_d = arv*closing/100; sell_d = arv*selling/100; cont_d = rehab*contingency/100
    flip = max(0, arv-rehab-close_d-sell_d-holding-cont_d-target_profit)
    if strategy == "Flip": return flip, "Maximum purchase price", "ARV less rehab, costs, contingency and target profit."
    if strategy == "Wholesale": return max(0, flip-assignment), "Maximum contract price", f"Leaves about {money(assignment)} for your assignment fee."
    if strategy == "BRRRR":
        ceiling = max(0, arv*refi_ltv/100-rehab-close_d-holding-cont_d)
        return ceiling, "Max purchase for modeled refinance", f"Uses a {refi_ltv:.0f}% ARV refinance assumption."
    noi = rent*12*(1-vacancy/100)*(1-opex/100)
    value = noi/(cap/100) if cap else 0
    return max(0, value-rehab-close_d-holding-cont_d), "Maximum purchase price", f"Uses a {cap:.1f}% target cap rate and modeled NOI of {money(noi)}."



def monthly_pi_payment(loan_amount, annual_rate_pct, years):
    """Monthly principal + interest payment."""
    try:
        principal = max(float(loan_amount or 0), 0)
        annual_rate = max(float(annual_rate_pct or 0), 0) / 100
        n = max(int(years or 0) * 12, 1)
    except Exception:
        return 0.0
    if principal <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / n
    factor = (1 + monthly_rate) ** n
    return principal * monthly_rate * factor / (factor - 1)


def latest_property_tax(property_record):
    taxes = (property_record or {}).get("propertyTaxes") or {}
    if not taxes:
        return 0.0, None
    for year, values in sorted(taxes.items(), reverse=True):
        if isinstance(values, dict) and values.get("total") is not None:
            try:
                return float(values.get("total")), str(year)
            except Exception:
                pass
    return 0.0, None


def market_trend_pct(sale_data):
    hist = (sale_data or {}).get("history") or {}
    rows = []
    if isinstance(hist, dict):
        for period, values in sorted(hist.items()):
            if isinstance(values, dict) and values.get("medianPrice") not in (None, 0):
                try:
                    rows.append((period, float(values.get("medianPrice"))))
                except Exception:
                    pass
    if len(rows) < 2:
        return None
    first, last = rows[0][1], rows[-1][1]
    if not first:
        return None
    return (last - first) / first


def brrrr_model(
    purchase_price,
    arv_value,
    monthly_rent,
    rehab_cost,
    acquisition_closing_pct,
    holding_cost,
    contingency_pct,
    refi_ltv_pct,
    refi_rate_pct,
    refi_term_years,
    refi_closing_pct,
    annual_taxes,
    annual_insurance,
    monthly_hoa,
    vacancy_pct,
    management_pct,
    maintenance_pct,
    capex_pct,
    monthly_other,
):
    purchase_price = max(float(purchase_price or 0), 0)
    arv_value = max(float(arv_value or 0), 0)
    monthly_rent = max(float(monthly_rent or 0), 0)
    rehab_cost = max(float(rehab_cost or 0), 0)

    acquisition_closing = purchase_price * float(acquisition_closing_pct or 0) / 100
    rehab_contingency = rehab_cost * float(contingency_pct or 0) / 100
    total_project_cost = purchase_price + acquisition_closing + rehab_cost + float(holding_cost or 0) + rehab_contingency

    refi_loan = arv_value * float(refi_ltv_pct or 0) / 100
    refi_closing_cost = refi_loan * float(refi_closing_pct or 0) / 100
    net_refi_proceeds = max(refi_loan - refi_closing_cost, 0)
    cash_left_raw = total_project_cost - net_refi_proceeds
    cash_left = max(cash_left_raw, 0)
    cash_out = max(-cash_left_raw, 0)

    equity_after_refi = max(arv_value - refi_loan, 0)
    equity_pct = (equity_after_refi / arv_value) if arv_value else None
    equity_created_vs_cost = arv_value - total_project_cost
    equity_created_pct = (equity_created_vs_cost / total_project_cost) if total_project_cost else None

    gross_rent = monthly_rent
    vacancy = gross_rent * float(vacancy_pct or 0) / 100
    management = gross_rent * float(management_pct or 0) / 100
    maintenance = gross_rent * float(maintenance_pct or 0) / 100
    capex = gross_rent * float(capex_pct or 0) / 100
    taxes_monthly = float(annual_taxes or 0) / 12
    insurance_monthly = float(annual_insurance or 0) / 12
    hoa_monthly = float(monthly_hoa or 0)
    other_monthly = float(monthly_other or 0)

    monthly_predebt = (
        gross_rent
        - vacancy
        - management
        - maintenance
        - capex
        - taxes_monthly
        - insurance_monthly
        - hoa_monthly
        - other_monthly
    )
    monthly_debt_service = monthly_pi_payment(refi_loan, refi_rate_pct, refi_term_years)
    monthly_cash_flow = monthly_predebt - monthly_debt_service

    annual_predebt = monthly_predebt * 12
    annual_debt_service = monthly_debt_service * 12
    dscr = annual_predebt / annual_debt_service if annual_debt_service else None
    cap_rate_on_cost = annual_predebt / total_project_cost if total_project_cost else None
    cash_on_cash = (monthly_cash_flow * 12 / cash_left) if cash_left > 0 else None
    gross_yield_on_cost = (gross_rent * 12 / total_project_cost) if total_project_cost else None
    recovered_pct = net_refi_proceeds / total_project_cost if total_project_cost else None

    return {
        "purchase_price": purchase_price,
        "arv": arv_value,
        "rent": monthly_rent,
        "acquisition_closing": acquisition_closing,
        "rehab": rehab_cost,
        "rehab_contingency": rehab_contingency,
        "holding": float(holding_cost or 0),
        "total_project_cost": total_project_cost,
        "refi_loan": refi_loan,
        "refi_closing_cost": refi_closing_cost,
        "net_refi_proceeds": net_refi_proceeds,
        "cash_left": cash_left,
        "cash_out": cash_out,
        "equity_after_refi": equity_after_refi,
        "equity_pct": equity_pct,
        "equity_created_vs_cost": equity_created_vs_cost,
        "equity_created_pct": equity_created_pct,
        "monthly_predebt": monthly_predebt,
        "monthly_debt_service": monthly_debt_service,
        "monthly_cash_flow": monthly_cash_flow,
        "annual_cash_flow": monthly_cash_flow * 12,
        "dscr": dscr,
        "cap_rate_on_cost": cap_rate_on_cost,
        "cash_on_cash": cash_on_cash,
        "gross_yield_on_cost": gross_yield_on_cost,
        "recovered_pct": recovered_pct,
        "monthly_taxes": taxes_monthly,
        "monthly_insurance": insurance_monthly,
        "monthly_hoa": hoa_monthly,
        "monthly_vacancy": vacancy,
        "monthly_management": management,
        "monthly_maintenance": maintenance,
        "monthly_capex": capex,
        "monthly_other": other_monthly,
    }


def brrrr_underwriting_summary(
    model,
    offer_ceiling,
    min_cash_flow,
    max_cash_left,
    min_dscr,
    zip_median_dom,
    same_zip_comp_count,
    listing_price=None,
):
    criteria = []

    def add(name, passed, value, note):
        criteria.append({"Criterion": name, "Result": "PASS" if passed else "REVIEW", "Value": value, "Why it matters": note})

    add(
        "Purchase vs modeled ceiling",
        model["purchase_price"] <= float(offer_ceiling or 0),
        money(model["purchase_price"]),
        f"Modeled ceiling is {money(offer_ceiling)}."
    )
    add(
        "Monthly cash flow",
        model["monthly_cash_flow"] >= float(min_cash_flow or 0),
        money(model["monthly_cash_flow"]) + "/mo",
        f"Target is at least {money(min_cash_flow)}/mo."
    )
    dscr = model.get("dscr")
    add(
        "Debt coverage",
        dscr is not None and dscr >= float(min_dscr or 0),
        f"{dscr:.2f}x" if dscr is not None else "—",
        f"Target DSCR is at least {float(min_dscr or 0):.2f}x."
    )
    add(
        "Cash left after refinance",
        model["cash_left"] <= float(max_cash_left or 0),
        money(model["cash_left"]),
        f"Target is no more than {money(max_cash_left)} left in the deal."
    )
    if zip_median_dom is not None:
        add(
            "Market liquidity",
            float(zip_median_dom) <= 90,
            f"{float(zip_median_dom):.0f} days",
            "ZIP median DOM of 90 days or less is treated as the model's liquidity threshold."
        )
    if same_zip_comp_count is not None:
        add(
            "Same-ZIP comp support",
            int(same_zip_comp_count) >= 3,
            f"{int(same_zip_comp_count)} comps",
            "At least 3 same-ZIP comps gives the underwriting model more local support."
        )
    if listing_price not in (None, 0):
        try:
            gap = float(listing_price) - float(offer_ceiling or 0)
            add(
                "Current asking price",
                float(listing_price) <= float(offer_ceiling or 0),
                money(listing_price),
                f"Asking price is {money(abs(gap))} {'below' if gap <= 0 else 'above'} the modeled ceiling."
            )
        except Exception:
            pass

    core = criteria[:4]
    core_pass = sum(1 for c in core if c["Result"] == "PASS")
    if core_pass == 4:
        status = "Meets current BRRRR criteria"
    elif core_pass >= 2:
        status = "Needs negotiation / review"
    else:
        status = "Does not meet current BRRRR criteria"

    return status, pd.DataFrame(criteria)


def brrrr_reason_lines(model, sd, rd, same_zip_comp_count, same_zip_indicated_arv, listing_price, offer_ceiling):
    positives = []
    watch = []

    if model["monthly_cash_flow"] > 0:
        positives.append(f"Modeled post-refinance cash flow is {money(model['monthly_cash_flow'])}/month.")
    else:
        watch.append(f"Modeled post-refinance cash flow is {money(model['monthly_cash_flow'])}/month.")

    if model["cash_left"] <= 25000:
        positives.append(f"Modeled cash left in the deal is {money(model['cash_left'])}.")
    else:
        watch.append(f"Modeled cash left in the deal is {money(model['cash_left'])}, so more capital remains tied up.")

    if model["equity_created_vs_cost"] > 0:
        positives.append(f"ARV exceeds modeled total project cost by {money(model['equity_created_vs_cost'])}.")
    else:
        watch.append(f"Modeled total project cost is above the selected ARV by {money(abs(model['equity_created_vs_cost']))}.")

    if model.get("dscr") is not None:
        if model["dscr"] >= 1.20:
            positives.append(f"Modeled DSCR is {model['dscr']:.2f}x.")
        else:
            watch.append(f"Modeled DSCR is {model['dscr']:.2f}x, leaving thinner debt-service coverage.")

    if same_zip_comp_count >= 3:
        positives.append(f"{same_zip_comp_count} same-ZIP AVM comps support the local valuation review.")
    else:
        watch.append(f"Only {same_zip_comp_count} same-ZIP AVM comps are currently available in the returned comp set.")

    dom = (sd or {}).get("medianDaysOnMarket")
    if dom is not None:
        if float(dom) <= 60:
            positives.append(f"ZIP median marketing time is about {float(dom):.0f} days.")
        elif float(dom) > 90:
            watch.append(f"ZIP median marketing time is about {float(dom):.0f} days, which is slower in this model.")

    zip_rent = (rd or {}).get("medianRent")
    if zip_rent not in (None, 0) and model["rent"]:
        if model["rent"] >= float(zip_rent):
            positives.append(f"Subject rent estimate ({money(model['rent'])}) is at or above the ZIP median rent ({money(zip_rent)}).")
        else:
            watch.append(f"Subject rent estimate ({money(model['rent'])}) is below the ZIP median rent ({money(zip_rent)}).")

    if listing_price not in (None, 0):
        if float(listing_price) <= float(offer_ceiling or 0):
            positives.append(f"Current asking price is within the modeled purchase ceiling of {money(offer_ceiling)}.")
        else:
            watch.append(f"Current asking price is {money(float(listing_price)-float(offer_ceiling or 0))} above the modeled purchase ceiling.")

    if same_zip_indicated_arv:
        diff = model["arv"] - float(same_zip_indicated_arv)
        if abs(diff) / max(model["arv"], 1) > 0.10:
            watch.append(
                f"Selected ARV ({money(model['arv'])}) differs materially from the same-ZIP $/sqft indication ({money(same_zip_indicated_arv)})."
            )

    return positives, watch


def friendly_profitability_status(model, offer_ceiling, min_cash_flow, max_cash_left, min_dscr):
    checks = {
        "price": model["purchase_price"] <= float(offer_ceiling or 0),
        "cash_flow": model["monthly_cash_flow"] >= float(min_cash_flow or 0),
        "cash_left": model["cash_left"] <= float(max_cash_left or 0),
        "dscr": model.get("dscr") is not None and model["dscr"] >= float(min_dscr or 0),
        "equity": model["equity_created_vs_cost"] > 0,
    }
    passed = sum(bool(v) for v in checks.values())

    if passed >= 5:
        return (
            "good",
            "Looks profitable under your current assumptions",
            "The purchase price, monthly cash flow, rent cushion, cash left in the deal, and equity creation all meet the targets you entered.",
            checks,
        )
    if passed >= 3:
        return (
            "warn",
            "Close — but I would negotiate or verify a few things",
            "Several numbers work, but at least one important target is thin. Use the suggestions below before treating this as a strong BRRRR candidate.",
            checks,
        )
    return (
        "bad",
        "Does not look profitable under your current assumptions",
        "The current numbers miss several of your targets. The deal may improve with a lower purchase price, different financing, lower rehab, or stronger verified rent/ARV.",
        checks,
    )


def friendly_actions(
    model,
    offer_ceiling,
    min_cash_flow,
    max_cash_left,
    min_dscr,
    same_zip_comp_count,
    same_zip_indicated_arv,
    listing_price,
    insurance_amount,
    zip_median_dom,
):
    actions = []

    if model["purchase_price"] > float(offer_ceiling or 0):
        gap = model["purchase_price"] - float(offer_ceiling or 0)
        actions.append((
            "Negotiate the purchase price",
            f"Your scenario is {money(gap)} above the modeled ceiling. Underwrite an offer at or below {money(offer_ceiling)} and see whether the seller will move."
        ))

    if model["cash_left"] > float(max_cash_left or 0):
        excess = model["cash_left"] - float(max_cash_left or 0)
        actions.append((
            "Reduce the cash left in the deal",
            f"You would leave about {money(model['cash_left'])} invested, which is {money(excess)} above your target. The main levers are purchase price, rehab cost, refinance terms, and verified ARV."
        ))

    if model["monthly_cash_flow"] < float(min_cash_flow or 0):
        shortfall = float(min_cash_flow or 0) - model["monthly_cash_flow"]
        actions.append((
            "Improve monthly cash flow",
            f"Cash flow is about {money(shortfall)}/month below your target. Verify rent with rental comps, get a real insurance quote, and test a lower refinance rate/LTV or lower operating costs."
        ))

    if model.get("dscr") is None or model["dscr"] < float(min_dscr or 0):
        if model.get("dscr") is not None:
            copy = (
                f"Your rent cushion is {model['dscr']:.2f}x versus your {float(min_dscr):.2f}x target. "
                "A smaller refinance loan, better rate, or stronger verified rent can improve this."
            )
        else:
            copy = "Debt coverage could not be calculated. Verify the financing assumptions and rent."
        actions.append(("Strengthen the rent cushion", copy))

    if insurance_amount <= 0:
        actions.append((
            "Get an insurance quote",
            "Insurance is currently entered as $0, so the cash-flow result is too optimistic until you add a real annual insurance estimate."
        ))

    if same_zip_comp_count < 3:
        actions.append((
            "Verify the ARV before relying on it",
            f"Only {same_zip_comp_count} same-ZIP AVM comps are currently in the returned set. Manually verify sold comps before using the ARV for an offer or refinance assumption."
        ))

    if same_zip_indicated_arv and model["arv"]:
        gap_pct = abs(model["arv"] - float(same_zip_indicated_arv)) / max(float(model["arv"]), 1)
        if gap_pct > 0.10:
            actions.append((
                "Reconcile the two ARV signals",
                f"Your selected ARV is {money(model['arv'])}, while the same-ZIP $/sqft indication is about {money(same_zip_indicated_arv)}. That difference deserves a manual comp review."
            ))

    if zip_median_dom is not None and float(zip_median_dom) > 90:
        actions.append((
            "Budget for a slower exit",
            f"The ZIP median days on market is about {float(zip_median_dom):.0f} days. Use a longer holding-period assumption if your backup plan is to sell."
        ))

    if listing_price not in (None, 0) and float(listing_price) > float(offer_ceiling or 0):
        actions.append((
            "Do not anchor to the asking price",
            f"The current ask is {money(listing_price)}, above your modeled ceiling of {money(offer_ceiling)}. Underwrite from your numbers first, then negotiate."
        ))

    if not actions:
        actions.append((
            "Verify the deal before committing",
            "The current model meets your targets. Next verify title, flood exposure, repair bids, taxes, insurance, lender terms, rental comps, and sold comps."
        ))

    return actions[:6]


def render_friendly_status(kind, headline, body):
    st.markdown(
        f'<div class="friendly-status {kind}">'
        f'<div class="eyebrow">Profitability snapshot</div>'
        f'<div class="headline">{headline}</div>'
        f'<div class="body">{body}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_action_card(title, copy):
    st.markdown(
        f'<div class="action-card">'
        f'<div class="title">{title}</div>'
        f'<div class="copy">{copy}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

def comp_df(comps):
    rows=[]
    for c in comps or []:
        sqft, price = c.get("squareFootage"), c.get("price")
        rows.append({
            "Address":c.get("formattedAddress"),"City":c.get("city"),"ZIP":c.get("zipCode"),
            "Property Type":c.get("propertyType"),"Status":c.get("status"),"Price":price,
            "Beds":c.get("bedrooms"),"Baths":c.get("bathrooms"),"Sq Ft":sqft,
            "$/Sq Ft":(float(price)/float(sqft) if price and sqft else None),
            "DOM":c.get("daysOnMarket"),"Distance (mi)":c.get("distance"),"Similarity":c.get("correlation"),
            "Listed":c.get("listedDate"),"Removed":c.get("removedDate"),
            "Latitude":c.get("latitude"),"Longitude":c.get("longitude")})
    return pd.DataFrame(rows)


def rental_comp_df(comps):
    rows=[]
    for c in comps or []:
        sqft, rent = c.get("squareFootage"), c.get("price")
        rows.append({
            "Address":c.get("formattedAddress"),"Status":c.get("status"),"Rent":rent,
            "Beds":c.get("bedrooms"),"Baths":c.get("bathrooms"),"Sq Ft":sqft,
            "Rent/Sq Ft":(float(rent)/float(sqft) if rent and sqft else None),
            "DOM":c.get("daysOnMarket"),"Distance (mi)":c.get("distance"),"Similarity":c.get("correlation"),
            "Listed":c.get("listedDate"),"Removed":c.get("removedDate"),
            "Latitude":c.get("latitude"),"Longitude":c.get("longitude")})
    return pd.DataFrame(rows)


def numeric_series(df, col):
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").dropna()


def median_or_none(df, col):
    s=numeric_series(df,col)
    return float(s.median()) if not s.empty else None


def mean_or_none(df, col):
    s=numeric_series(df,col)
    return float(s.mean()) if not s.empty else None


def pct_diff(a, b):
    try:
        if b in (None, 0): return None
        return (float(a)-float(b))/float(b)
    except Exception:
        return None


def pct_text(v):
    if v is None: return "—"
    return f"{v*100:+.1f}%"


def speed_label(dom):
    try:
        d=float(dom)
    except Exception:
        return "Not enough data"
    if d <= 30: return "Fast-moving"
    if d <= 60: return "Moderate"
    if d <= 90: return "Slower"
    return "Longer marketing time"


def segment_for_property_type(data, subject_type):
    if not subject_type: return None
    target=str(subject_type).strip().lower()
    for row in data or []:
        if str(row.get("propertyType","")).strip().lower()==target:
            return row
    return None


def history_df(data):
    hist=(data or {}).get("history") or {}
    rows=[]
    if isinstance(hist,dict):
        for period,v in hist.items():
            if isinstance(v,dict):
                rows.append({
                    "Period":period,
                    "Median Price":v.get("medianPrice"),
                    "Average Price":v.get("averagePrice"),
                    "Median $/Sq Ft":v.get("medianPricePerSquareFoot"),
                    "Average DOM":v.get("averageDaysOnMarket"),
                    "Median DOM":v.get("medianDaysOnMarket"),
                    "New Listings":v.get("newListings"),
                    "Total Listings":v.get("totalListings"),
                })
    return pd.DataFrame(rows).sort_values("Period") if rows else pd.DataFrame()

st.markdown('<div class="k">NORVIM 13 LLC</div><div class="t">Deal Analyzer</div><div class="s">Address → ARV → comps → market speed → rent → maximum offer.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Property data")
    key = get_key()
    if not key:
        entered = st.text_input("RentCast API key", type="password", help="For testing. Use Streamlit Secrets on the live site.")
        if entered:
            st.session_state["rentcast_api_key"] = entered; key = entered
    else: st.success("Property-data API connected")
    st.caption("Core analysis: about 5 API requests the first time. The optional neighborhood map uses 2 more requests once, then stays cached for 30 days.")
    st.divider(); st.subheader("Deal assumptions")
    strategy = st.selectbox("Strategy", ["Flip","Wholesale","BRRRR","Rental"])
    rehab = st.number_input("Rehab budget", 0.0, value=40000.0, step=5000.0)
    closing = st.number_input("Purchase/closing costs (% of ARV)", 0.0, 20.0, 2.0, .5)
    selling = st.number_input("Selling costs (% of ARV)", 0.0, 20.0, 8.0, .5)
    holding = st.number_input("Holding + financing", 0.0, value=12000.0, step=1000.0)
    contingency = st.number_input("Rehab contingency (%)", 0.0, 50.0, 10.0, 1.0)
    target_profit, assignment, refi_ltv, vacancy, opex, cap = 35000.0,10000.0,75.0,5.0,35.0,8.0
    if strategy in ("Flip","Wholesale"):
        target_profit = st.number_input("End-buyer target profit", 0.0, value=35000.0, step=5000.0)
    if strategy == "Wholesale": assignment = st.number_input("Your assignment fee", 0.0, value=10000.0, step=1000.0)
    if strategy == "BRRRR": refi_ltv = st.number_input("Refinance LTV (% of ARV)", 1.0, 100.0, 75.0, 1.0)
    if strategy == "Rental":
        vacancy = st.number_input("Vacancy allowance (%)", 0.0, 50.0, 5.0, 1.0)
        opex = st.number_input("Operating expenses (% of effective rent)", 0.0, 90.0, 35.0, 1.0)
        cap = st.number_input("Target cap rate (%)", .1, 30.0, 8.0, .25)

with st.form("address_form"):
    address = st.text_input("Property address", placeholder="1234 Example St, Houston, TX 77021")
    submitted = st.form_submit_button("Run deal analysis", type="primary", use_container_width=True)

if submitted:
    if not address.strip(): st.error("Enter a property address first.")
    elif not key: st.error("Add a RentCast API key in the sidebar or Streamlit Secrets.")
    else:
        with st.spinner("Pulling valuation, comps, rent and market data..."):
            try:
                address_clean = address.strip()
                address_key = normalize_address(address_clean)
                val, rent_data, market, property_record, listing_record, fetched_at = analyze_cached(address_key, key, address_clean)
                st.session_state["analysis"] = {
                    "input": address_clean,
                    "address_key": address_key,
                    "valuation": val,
                    "rent": rent_data,
                    "market": market,
                    "property_record": property_record,
                    "listing_record": listing_record,
                    "time": fetched_at,
                }
            except Exception as e: st.error(str(e))

A = st.session_state.get("analysis")
if not A:
    st.info("Enter an address to start. The app can analyze listed or off-market properties when the data provider has a record for the address.")
    st.stop()

val, rent_data, market = A["valuation"], A["rent"], A["market"]
property_record = A.get("property_record") or {}
listing_record = A.get("listing_record") or {}
subj = val.get("subjectProperty") or {}; arv = val.get("price") or 0; rent_m = rent_data.get("rent") or 0
ceiling, label, note = offer_math(strategy, arv, rent_m, rehab, closing, selling, holding, contingency, target_profit, assignment, refi_ltv, vacancy, opex, cap)

st.subheader(subj.get("formattedAddress") or A["input"])
bits=[subj.get("propertyType"), f'{subj.get("bedrooms")} bd' if subj.get("bedrooms") is not None else None, f'{subj.get("bathrooms")} ba' if subj.get("bathrooms") is not None else None, f'{subj.get("squareFootage"):,} sf' if isinstance(subj.get("squareFootage"),(int,float)) else None, f'Built {subj.get("yearBuilt")}' if subj.get("yearBuilt") else None]
st.caption(" · ".join([str(x) for x in bits if x]))

area_bits = [
    subj.get("city") or property_record.get("city"),
    property_record.get("subdivision"),
    f'ZIP {subj.get("zipCode") or property_record.get("zipCode")}' if (subj.get("zipCode") or property_record.get("zipCode")) else None,
    f'{property_record.get("county")} County' if property_record.get("county") else None,
]
st.caption("Area: " + " · ".join([str(x) for x in area_bits if x]))

m1,m2,m3,m4=st.columns(4)
with m1: result_card("Estimated ARV", money(arv))
with m2: result_card("ARV range", f'{money(val.get("priceRangeLow"))} – {money(val.get("priceRangeHigh"))}')
with m3: result_card("Estimated rent", f'{money(rent_m)}/mo')
with m4: result_card(label, money(ceiling))
st.caption(note)
st.info(f'Data snapshot saved: {A["time"]}. The same normalized address will reuse this snapshot for up to 30 days, avoiding another RentCast charge/request.')
st.warning("Underwriting estimate only. Verify title, condition, flood risk, taxes, liens, repair scope and local comps before contracting.")

tabs=st.tabs(["Overview","Property record","Listing","Deal","BRRRR","Sales comps","Neighborhood map","Area market","Rental","Export"])

# Precompute reusable tables and summary statistics from the three API responses.
cdf_all=comp_df(val.get("comparables") or [])
rdf=rental_comp_df(rent_data.get("comparables") or [])
sd=market.get("saleData") or {}
rd=market.get("rentalData") or {}
zip_code=str(subj.get("zipCode") or market.get("zipCode") or "—")

# Houston-area ZIPs can change materially within a short distance.
# Default investor comp set is therefore restricted to the subject ZIP.
if not cdf_all.empty and "ZIP" in cdf_all.columns and zip_code != "—":
    cdf_same_zip = cdf_all[cdf_all["ZIP"].astype(str) == zip_code].copy()
else:
    cdf_same_zip = cdf_all.copy()

# Use same-ZIP comps when available; fall back to all AVM comps only when RentCast
# did not return any same-ZIP records.
cdf = cdf_same_zip.copy() if not cdf_same_zip.empty else cdf_all.copy()
comp_scope_fallback = cdf_same_zip.empty and not cdf_all.empty

subject_ppsf=(float(arv)/float(subj.get("squareFootage")) if arv and subj.get("squareFootage") else None)
comp_median_price=median_or_none(cdf,"Price")
comp_median_ppsf=median_or_none(cdf,"$/Sq Ft")
comp_avg_dom=mean_or_none(cdf,"DOM")
comp_median_distance=median_or_none(cdf,"Distance (mi)")
comp_avg_similarity=mean_or_none(cdf,"Similarity")
same_zip_indicated_arv = (
    comp_median_ppsf * float(subj.get("squareFootage"))
    if comp_median_ppsf and subj.get("squareFootage")
    else None
)

with tabs[0]:
    if strategy == "BRRRR":
        st.info("Want the simple answer? Open **BRRRR Deal Coach** for profitability, monthly profit, equity, cash left in the deal, rent cushion, and suggested next moves.")
    st.markdown("#### Property & neighborhood snapshot")
    p1,p2,p3,p4=st.columns(4)
    with p1: result_card("ZIP code", zip_code)
    with p2: result_card("Lot size", f'{subj.get("lotSize"):,} sf' if isinstance(subj.get("lotSize"),(int,float)) else "—")
    with p3: result_card("Last sale", money(subj.get("lastSalePrice")), str(subj.get("lastSaleDate") or "Date not available"))
    with p4: result_card("Subject $/Sq Ft", f'${subject_ppsf:,.0f}' if subject_ppsf else "—")

    st.markdown(f"#### Sales comp snapshot — ZIP {zip_code}")
    if comp_scope_fallback:
        st.warning(f"RentCast did not return a comp inside ZIP {zip_code}, so this snapshot is temporarily using nearby ZIPs. Review those comps manually.")
    else:
        st.caption(f"Investor comp view is restricted to the subject ZIP ({zip_code}) by default. Nearby ZIPs are excluded unless you choose them in the Sales comps tab.")
    q1,q2,q3,q4=st.columns(4)
    with q1: result_card("Sale comps returned", len(cdf))
    with q2: result_card("Median comp price", money(comp_median_price))
    with q3: result_card("Median comp $/Sq Ft", f'${comp_median_ppsf:,.0f}' if comp_median_ppsf else "—")
    with q4: result_card("Average comp DOM", f'{comp_avg_dom:.0f} days' if comp_avg_dom is not None else "—")

    if same_zip_indicated_arv is not None:
        st.caption(f"Same-ZIP comp indication: {money(same_zip_indicated_arv)} based on median displayed comp $/Sq Ft × subject square footage. This is a comp check, not an appraisal.")

    if sd:
        st.markdown("#### Area market snapshot")
        z1,z2,z3,z4=st.columns(4)
        with z1: result_card("ZIP median asking price", money(sd.get("medianPrice")), f'ARV vs ZIP: {pct_text(pct_diff(arv,sd.get("medianPrice")))}')
        with z2: result_card("ZIP median $/Sq Ft", f'${sd.get("medianPricePerSquareFoot"):,.0f}' if sd.get("medianPricePerSquareFoot") else "—", f'Subject vs ZIP: {pct_text(pct_diff(subject_ppsf,sd.get("medianPricePerSquareFoot")))}')
        with z3: result_card("Median days on market", f'{sd.get("medianDaysOnMarket","—")} days', speed_label(sd.get("medianDaysOnMarket")))
        with z4: result_card("Listings seen", sd.get("totalListings","—"), f'{sd.get("newListings","—")} new listings')

    if not cdf.empty:
        top=cdf.sort_values(["Similarity","Distance (mi)"],ascending=[False,True]).head(5)
        st.markdown(f"#### Top 5 comparable houses in ZIP {zip_code}")
        top_cols=[c for c in ["Address","ZIP","Price","Beds","Baths","Sq Ft","$/Sq Ft","DOM","Distance (mi)","Similarity"] if c in top.columns]
        st.dataframe(top[top_cols].style.format({"Price":"${:,.0f}","$/Sq Ft":"${:,.0f}","Distance (mi)":"{:.2f}","Similarity":"{:.0%}"},na_rep="—"),use_container_width=True,hide_index=True)


with tabs[1]:
    st.markdown("#### Public-record property profile")
    if not property_record:
        st.info("No public-record property profile was returned for this address.")
    else:
        owner = property_record.get("owner") or {}
        owner_names = owner.get("names") or []
        mailing = owner.get("mailingAddress") or {}
        hoa = property_record.get("hoa") or {}

        p1,p2,p3,p4=st.columns(4)
        with p1: result_card("Last sale price", money(property_record.get("lastSalePrice")))
        with p2: result_card("Last sale date", str(property_record.get("lastSaleDate") or "—")[:10])
        with p3: result_card("HOA", money(hoa.get("fee")) if hoa.get("fee") is not None else "—")
        with p4:
            occ = "Yes" if property_record.get("ownerOccupied") is True else ("No" if property_record.get("ownerOccupied") is False else "—")
            result_card("Owner occupied", occ)

        c1,c2=st.columns(2)
        with c1:
            st.markdown("##### Property details")
            details = [
                ("County", property_record.get("county")),
                ("Subdivision", property_record.get("subdivision")),
                ("Zoning", property_record.get("zoning")),
                ("Lot size", f'{property_record.get("lotSize"):,} sf' if isinstance(property_record.get("lotSize"),(int,float)) else None),
                ("Assessor ID", property_record.get("assessorID")),
                ("Legal description", property_record.get("legalDescription")),
            ]
            for k,v in details:
                st.write(f"**{k}:** {v if v not in (None,'') else '—'}")

        with c2:
            st.markdown("##### Owner / mailing")
            st.write(f"**Owner:** {', '.join(owner_names) if owner_names else '—'}")
            st.write(f"**Owner type:** {owner.get('type') or '—'}")
            st.write(f"**Mailing address:** {mailing.get('formattedAddress') or '—'}")

        st.markdown("##### Property features")
        features = property_record.get("features") or {}
        feature_rows=[]
        for raw_key, value in features.items():
            if value not in (None,"",False):
                label_text = re.sub(r"(?<!^)(?=[A-Z])"," ",str(raw_key)).replace("_"," ").title()
                feature_rows.append({"Feature":label_text,"Value":value})
        if feature_rows:
            st.dataframe(pd.DataFrame(feature_rows),use_container_width=True,hide_index=True)
        else:
            st.caption("No feature details returned.")

        st.markdown("##### Tax assessment history")
        assessments = property_record.get("taxAssessments") or {}
        if assessments:
            assessment_rows=[]
            for year, values in sorted(assessments.items()):
                values=values or {}
                assessment_rows.append({
                    "Year":year,
                    "Assessed value":values.get("value"),
                    "Land":values.get("land"),
                    "Improvements":values.get("improvements"),
                })
            adf=pd.DataFrame(assessment_rows)
            st.dataframe(
                adf.style.format({"Assessed value":"${:,.0f}","Land":"${:,.0f}","Improvements":"${:,.0f}"},na_rep="—"),
                use_container_width=True,hide_index=True
            )
        else:
            st.caption("No assessment history returned.")

        st.markdown("##### Property tax history")
        taxes = property_record.get("propertyTaxes") or {}
        if taxes:
            tax_rows=[]
            for year, values in sorted(taxes.items()):
                values=values or {}
                tax_rows.append({"Year":year,"Property tax":values.get("total")})
            tdf=pd.DataFrame(tax_rows)
            st.dataframe(tdf.style.format({"Property tax":"${:,.0f}"},na_rep="—"),use_container_width=True,hide_index=True)
        else:
            st.caption("No property-tax history returned.")

        st.markdown("##### Sale history")
        sale_history = property_record.get("history") or {}
        if sale_history:
            sale_rows=[]
            for _,values in sorted(sale_history.items()):
                values=values or {}
                sale_rows.append({
                    "Date":str(values.get("date") or "")[:10],
                    "Event":values.get("event"),
                    "Price":values.get("price"),
                })
            sdf_hist=pd.DataFrame(sale_rows)
            st.dataframe(sdf_hist.style.format({"Price":"${:,.0f}"},na_rep="—"),use_container_width=True,hide_index=True)
        else:
            st.caption("No sale history returned.")

with tabs[2]:
    st.markdown("#### Sale listing / market history")
    if not listing_record:
        st.info("No exact sale-listing record was returned. The property may be off-market or may not have listing coverage.")
    else:
        l1,l2,l3,l4=st.columns(4)
        with l1: result_card("Listing status", listing_record.get("status") or "—")
        with l2: result_card("Current / last ask", money(listing_record.get("price")))
        with l3: result_card("Days on market", f'{listing_record.get("daysOnMarket")} days' if listing_record.get("daysOnMarket") is not None else "—")
        with l4: result_card("Listed date", str(listing_record.get("listedDate") or "—")[:10])

        d1,d2=st.columns(2)
        with d1:
            st.markdown("##### MLS / listing")
            st.write(f"**Listing type:** {listing_record.get('listingType') or '—'}")
            st.write(f"**MLS:** {listing_record.get('mlsName') or '—'}")
            st.write(f"**MLS number:** {listing_record.get('mlsNumber') or '—'}")
            st.write(f"**Last seen:** {str(listing_record.get('lastSeenDate') or '—')[:10]}")
            st.write(f"**Removed date:** {str(listing_record.get('removedDate') or '—')[:10] if listing_record.get('removedDate') else '—'}")

        with d2:
            st.markdown("##### Listing contacts")
            agent = listing_record.get("listingAgent") or {}
            office = listing_record.get("listingOffice") or {}
            st.write(f"**Agent:** {agent.get('name') or '—'}")
            st.write(f"**Agent phone:** {agent.get('phone') or '—'}")
            st.write(f"**Agent email:** {agent.get('email') or '—'}")
            st.write(f"**Office:** {office.get('name') or '—'}")
            st.write(f"**Office phone:** {office.get('phone') or '—'}")

        st.markdown("##### Listing history")
        listing_history = listing_record.get("history") or {}
        if listing_history:
            listing_rows=[]
            for _,values in sorted(listing_history.items()):
                values=values or {}
                listing_rows.append({
                    "Listed":str(values.get("listedDate") or "")[:10],
                    "Removed":str(values.get("removedDate") or "")[:10] if values.get("removedDate") else "—",
                    "Event":values.get("event"),
                    "Price":values.get("price"),
                    "DOM":values.get("daysOnMarket"),
                    "Type":values.get("listingType"),
                })
            ldf=pd.DataFrame(listing_rows)
            st.dataframe(ldf.style.format({"Price":"${:,.0f}"},na_rep="—"),use_container_width=True,hide_index=True)
        else:
            st.caption("No listing history returned.")


with tabs[3]:
    st.markdown("#### Deal math")
    rows=[["ARV",arv],["Rehab",rehab],["Purchase/closing allowance",arv*closing/100],["Selling-cost allowance",arv*selling/100],["Holding + financing",holding],["Rehab contingency",rehab*contingency/100],["Target profit",target_profit if strategy in ("Flip","Wholesale") else None],["Assignment fee",assignment if strategy=="Wholesale" else None],["Offer ceiling",ceiling]]
    df=pd.DataFrame(rows,columns=["Item","Amount"]).dropna()
    st.dataframe(df.style.format({"Amount":"${:,.0f}"}),use_container_width=True,hide_index=True)

    if strategy == "BRRRR":
        gross_refi = arv * refi_ltv / 100
        post_refi_equity = arv - gross_refi
        d1,d2,d3,d4=st.columns(4)
        with d1: result_card("Gross refi @ selected LTV", money(gross_refi))
        with d2: result_card("Equity after refi", money(post_refi_equity), f'{100-refi_ltv:.0f}% of ARV')
        with d3: result_card("Estimated rent", money(rent_m) + "/mo")
        with d4: result_card("BRRRR offer ceiling", money(ceiling))
        st.info("Open the **BRRRR** tab for monthly cash flow, refinance proceeds, cash left in the deal, DSCR, equity capture, stress testing and the underwriting criteria check.")


with tabs[4]:
    st.markdown("#### BRRRR Deal Coach")
    st.caption(
        "Simple view first: Is it profitable under your assumptions? How much cash stays in the deal? What equity do you create? What could make the deal better?"
    )

    latest_tax, latest_tax_year = latest_property_tax(property_record)
    hoa_default = float(((property_record.get("hoa") or {}).get("fee")) or 0)
    listing_price = listing_record.get("price")
    default_purchase = float(ceiling or 0)
    if listing_price not in (None, 0):
        try:
            default_purchase = min(float(listing_price), float(ceiling or listing_price))
        except Exception:
            pass

    st.markdown("##### Deal scenario")
    s1,s2,s3,s4=st.columns(4)
    with s1:
        b_purchase = st.number_input(
            "Purchase price scenario",
            min_value=0.0,
            value=float(round(default_purchase, 0)),
            step=5000.0,
            key="brrrr_purchase",
        )
    with s2:
        b_arv = st.number_input(
            "After-repair value (ARV)",
            min_value=0.0,
            value=float(round(arv or 0, 0)),
            step=5000.0,
            key="brrrr_arv",
            help="You can override the AVM with your own comp-supported ARV."
        )
    with s3:
        b_rent = st.number_input(
            "Monthly rent",
            min_value=0.0,
            value=float(round(rent_m or 0, 0)),
            step=100.0,
            key="brrrr_rent",
        )
    with s4:
        b_rehab = st.number_input(
            "Rehab",
            min_value=0.0,
            value=float(round(rehab or 0, 0)),
            step=5000.0,
            key="brrrr_rehab",
        )

    with st.expander("Advanced assumptions — lender, expenses & reserves", expanded=False):
        q1,q2,q3,q4=st.columns(4)
        with q1:
            b_refi_ltv = st.number_input("Refi LTV (% of ARV)", 1.0, 100.0, float(refi_ltv), 1.0, key="brrrr_ltv")
            b_refi_rate = st.number_input("Refi interest rate (%)", 0.0, 25.0, 7.5, 0.25, key="brrrr_rate")
            b_term = st.number_input("Refi term (years)", 1, 40, 30, 1, key="brrrr_term")
        with q2:
            b_acq_close = st.number_input("Acquisition closing costs (%)", 0.0, 20.0, float(closing), 0.25, key="brrrr_close")
            b_refi_close = st.number_input("Refi closing costs (%)", 0.0, 10.0, 2.0, 0.25, key="brrrr_refi_close")
            b_hold = st.number_input("Holding + pre-refi financing", 0.0, value=float(holding), step=1000.0, key="brrrr_holding")
        with q3:
            b_vacancy = st.number_input("Vacancy (%)", 0.0, 50.0, 5.0, 1.0, key="brrrr_vacancy")
            b_mgmt = st.number_input("Property management (%)", 0.0, 30.0, 8.0, 1.0, key="brrrr_mgmt")
            b_maint = st.number_input("Maintenance reserve (%)", 0.0, 30.0, 5.0, 1.0, key="brrrr_maint")
            b_capex = st.number_input("CapEx reserve (%)", 0.0, 30.0, 5.0, 1.0, key="brrrr_capex")
        with q4:
            b_taxes = st.number_input(
                f"Annual property taxes{' ('+latest_tax_year+')' if latest_tax_year else ''}",
                0.0,
                value=float(round(latest_tax or 0, 0)),
                step=250.0,
                key="brrrr_taxes",
            )
            b_insurance = st.number_input(
                "Annual insurance",
                0.0,
                value=0.0,
                step=250.0,
                key="brrrr_insurance",
                help="Enter an actual insurance quote when possible. Zero will overstate cash flow."
            )
            b_hoa = st.number_input(
                "Monthly HOA / assessment",
                0.0,
                value=float(round(hoa_default, 0)),
                step=10.0,
                key="brrrr_hoa",
                help="Verify whether the public-record HOA fee is monthly or another assessment frequency."
            )
            b_other = st.number_input("Monthly utilities / other", 0.0, value=0.0, step=25.0, key="brrrr_other")

        b_contingency = st.number_input("Rehab contingency (%)", 0.0, 50.0, float(contingency), 1.0, key="brrrr_contingency")

    if b_insurance <= 0:
        st.warning("Insurance is currently $0. Enter an insurance estimate/quote before relying on the cash-flow result.")

    model = brrrr_model(
        b_purchase, b_arv, b_rent, b_rehab, b_acq_close, b_hold, b_contingency,
        b_refi_ltv, b_refi_rate, b_term, b_refi_close,
        b_taxes, b_insurance, b_hoa, b_vacancy, b_mgmt, b_maint, b_capex, b_other
    )

    st.markdown("##### Value, refinance & equity")
    v1,v2,v3,v4=st.columns(4)
    with v1: result_card("Selected ARV", money(model["arv"]), f'AVM range {money(val.get("priceRangeLow"))} – {money(val.get("priceRangeHigh"))}')
    with v2: result_card("Total project cost", money(model["total_project_cost"]), "Purchase + closing + rehab + holding + contingency")
    with v3: result_card("Refinance loan", money(model["refi_loan"]), f'{b_refi_ltv:.0f}% of selected ARV')
    with v4: result_card("Equity you still own after refinance", money(model["equity_after_refi"]), f'{model["equity_pct"]*100:.1f}% of ARV' if model["equity_pct"] is not None else None)

    v5,v6,v7,v8=st.columns(4)
    with v5: result_card("Cash received from refinance", money(model["net_refi_proceeds"]), f'After {b_refi_close:.1f}% refi closing costs')
    if model["cash_out"] > 0:
        with v6: result_card("Cash out at refi", money(model["cash_out"]), "Modeled net refi proceeds exceed project cost")
    else:
        with v6: result_card("Cash left in deal", money(model["cash_left"]), "Capital still invested after refinance")
    with v7: result_card("Equity created by the deal", money(model["equity_created_vs_cost"]), f'{model["equity_created_pct"]*100:+.1f}%' if model["equity_created_pct"] is not None else None)
    with v8: result_card("Project cash recovered", f'{model["recovered_pct"]*100:.1f}%' if model["recovered_pct"] is not None else "—", "Net refi proceeds ÷ total project cost")

    if same_zip_indicated_arv is not None:
        st.caption(
            f"Valuation cross-check: RentCast AVM {money(arv)} · same-ZIP $/sqft indication {money(same_zip_indicated_arv)} · selected BRRRR ARV {money(b_arv)}."
        )

    st.markdown("##### Monthly rental cash flow")
    c1,c2,c3,c4=st.columns(4)
    with c1: result_card("Estimated rent", money(model["rent"]) + "/mo")
    with c2: result_card("Rent left before mortgage", money(model["monthly_predebt"]) + "/mo", "After vacancy, management, reserves, taxes, insurance, HOA & other")
    with c3: result_card("Refinance mortgage payment", money(model["monthly_debt_service"]) + "/mo", f'{b_refi_rate:.2f}% · {int(b_term)} years')
    with c4: result_card("Modeled cash flow", money(model["monthly_cash_flow"]) + "/mo", money(model["annual_cash_flow"]) + "/yr")

    st.markdown(
        '<div class="explain-box"><strong>What does “rent cushion” mean?</strong><br>'
        'DSCR compares the property income left before the mortgage with the mortgage payment. '
        'A 1.25x DSCR means the property produces about 25% more pre-debt income than the modeled debt payment. '
        'Below 1.00x means the modeled property income does not fully cover the debt.</div>',
        unsafe_allow_html=True,
    )

    c5,c6,c7,c8=st.columns(4)
    with c5: result_card("Rent cushion (DSCR)", f'{model["dscr"]:.2f}x' if model["dscr"] is not None else "—")
    with c6: result_card("Return before mortgage (cap rate)", f'{model["cap_rate_on_cost"]*100:.2f}%' if model["cap_rate_on_cost"] is not None else "—")
    with c7: result_card("Return on cash left in deal", f'{model["cash_on_cash"]*100:.1f}%' if model["cash_on_cash"] is not None else "N/M", "Shown only when cash remains in the deal")
    with c8: result_card("Gross rent ÷ total cost", f'{model["gross_yield_on_cost"]*100:.2f}%' if model["gross_yield_on_cost"] is not None else "—")

    with st.expander("Monthly cash-flow breakdown"):
        cf_rows = [
            ["Gross rent", model["rent"]],
            ["Vacancy", -model["monthly_vacancy"]],
            ["Management", -model["monthly_management"]],
            ["Maintenance reserve", -model["monthly_maintenance"]],
            ["CapEx reserve", -model["monthly_capex"]],
            ["Property taxes", -model["monthly_taxes"]],
            ["Insurance", -model["monthly_insurance"]],
            ["HOA / assessment", -model["monthly_hoa"]],
            ["Utilities / other", -model["monthly_other"]],
            ["Pre-debt operating cash", model["monthly_predebt"]],
            ["Principal & interest", -model["monthly_debt_service"]],
            ["Monthly cash flow", model["monthly_cash_flow"]],
        ]
        cfdf = pd.DataFrame(cf_rows, columns=["Item","Monthly Amount"])
        st.dataframe(cfdf.style.format({"Monthly Amount":"${:,.0f}"}), use_container_width=True, hide_index=True)

    st.markdown("##### Your profit targets")
    st.caption("Tell the app what a good BRRRR looks like to you. The summary below uses these targets.")
    t1,t2,t3=st.columns(3)
    with t1:
        min_cf = st.number_input("Minimum monthly cash flow", 0.0, value=250.0, step=50.0, key="criterion_cf")
    with t2:
        max_cash_left = st.number_input("Maximum cash left in deal", 0.0, value=25000.0, step=5000.0, key="criterion_cash_left")
    with t3:
        min_dscr = st.number_input("Minimum DSCR", 0.0, 5.0, 1.20, 0.05, key="criterion_dscr")

    status, criteria_df = brrrr_underwriting_summary(
        model,
        ceiling,
        min_cf,
        max_cash_left,
        min_dscr,
        sd.get("medianDaysOnMarket") if sd else None,
        len(cdf_same_zip),
        listing_price,
    )
    friendly_kind, friendly_headline, friendly_body, friendly_checks = friendly_profitability_status(
        model, ceiling, min_cf, max_cash_left, min_dscr
    )
    render_friendly_status(friendly_kind, friendly_headline, friendly_body)

    quick1,quick2,quick3,quick4=st.columns(4)
    with quick1:
        result_card(
            "Monthly profit after modeled expenses",
            money(model["monthly_cash_flow"]) + "/mo",
            "Rental cash flow after the modeled refinance mortgage."
        )
    with quick2:
        result_card(
            "Cash still tied up",
            money(model["cash_left"]),
            "Money that remains invested after the refinance."
        )
    with quick3:
        result_card(
            "Equity you own",
            money(model["equity_after_refi"]),
            "Selected ARV minus modeled refinance balance."
        )
    with quick4:
        result_card(
            "Rent cushion",
            f'{model["dscr"]:.2f}x' if model.get("dscr") is not None else "—",
            "1.25x means about 25% more pre-debt income than the mortgage payment."
        )

    st.markdown("##### Simple check")
    simple_df = criteria_df.copy()
    simple_df["Result"] = simple_df["Result"].replace({"PASS":"✅ Good","REVIEW":"⚠️ Review"})
    st.dataframe(simple_df, use_container_width=True, hide_index=True)

    st.markdown("##### Suggested next moves")
    action_items = friendly_actions(
        model,
        ceiling,
        min_cf,
        max_cash_left,
        min_dscr,
        len(cdf_same_zip),
        same_zip_indicated_arv,
        listing_price,
        b_insurance,
        sd.get("medianDaysOnMarket") if sd else None,
    )
    for action_title, action_copy in action_items:
        render_action_card(action_title, action_copy)

    positives, watch = brrrr_reason_lines(
        model, sd, rd, len(cdf_same_zip), same_zip_indicated_arv, listing_price, ceiling
    )
    pcol,wcol=st.columns(2)
    with pcol:
        st.markdown("##### What I like in the numbers")
        if positives:
            for line in positives:
                st.markdown(f"- {line}")
        else:
            st.caption("No strong positive signals under the current assumptions.")
    with wcol:
        st.markdown("##### What could hurt the deal")
        if watch:
            for line in watch:
                st.markdown(f"- {line}")
        else:
            st.caption("No major model warnings under the current assumptions.")

    st.markdown("##### Market context")
    m1,m2,m3,m4=st.columns(4)
    trend = market_trend_pct(sd)
    with m1: result_card("ZIP median DOM", f'{sd.get("medianDaysOnMarket","—")} days' if sd else "—", speed_label(sd.get("medianDaysOnMarket")) if sd else None)
    with m2: result_card("ZIP median rent", money(rd.get("medianRent")) if rd else "—")
    with m3: result_card("Same-ZIP comps", len(cdf_same_zip))
    with m4: result_card("Market price trend", pct_text(trend), "Oldest → newest month in returned market history" if trend is not None else None)

    st.markdown("##### What if things go worse than planned?")
    st.caption("Automatic tougher scenario: ARV -10%, rent -10%, rehab +15%, refinance rate +1%.")
    stress = brrrr_model(
        b_purchase,
        b_arv * 0.90,
        b_rent * 0.90,
        b_rehab * 1.15,
        b_acq_close,
        b_hold,
        b_contingency,
        b_refi_ltv,
        b_refi_rate + 1.0,
        b_term,
        b_refi_close,
        b_taxes,
        b_insurance,
        b_hoa,
        b_vacancy,
        b_mgmt,
        b_maint,
        b_capex,
        b_other,
    )
    z1,z2,z3,z4=st.columns(4)
    with z1: result_card("Stress ARV", money(stress["arv"]), "-10%")
    with z2: result_card("Stress rent", money(stress["rent"]) + "/mo", "-10%")
    with z3: result_card("Stress cash left", money(stress["cash_left"]), "Rehab +15% · rate +1%")
    with z4: result_card("Stress cash flow", money(stress["monthly_cash_flow"]) + "/mo", f'DSCR {stress["dscr"]:.2f}x' if stress["dscr"] is not None else None)

    st.caption(
        "Underwriting status is based only on the thresholds and assumptions shown above. Verify title, taxes, insurance, flood exposure, rehab scope, lender terms, rentability and comps before making an offer."
    )


with tabs[5]:
    st.markdown("#### Comparable houses around the subject")
    if cdf_all.empty:
        st.info("No sales comps returned.")
    else:
        scope = st.radio(
            "Comp geography",
            [f"Same ZIP only ({zip_code})", "Nearby radius (include other ZIPs)"],
            horizontal=True,
            help="For Houston investing, same-ZIP is the default because crossing a ZIP boundary can move you into a different submarket."
        )
        base_comps = cdf_same_zip.copy() if scope.startswith("Same ZIP") else cdf_all.copy()
        if base_comps.empty and scope.startswith("Same ZIP"):
            st.warning(f"No RentCast AVM comps were returned inside ZIP {zip_code}. Switch to Nearby radius to inspect surrounding ZIPs.")
        f1,f2=st.columns(2)
        with f1:
            max_distance=st.slider("Maximum distance (miles)",0.25,2.0,2.0,0.25,key="sale_radius")
        with f2:
            min_similarity=st.slider("Minimum similarity",0,100,0,5,key="sale_similarity")/100
        filtered=base_comps.copy()
        if "Distance (mi)" in filtered.columns:
            dist=pd.to_numeric(filtered["Distance (mi)"],errors="coerce")
            filtered=filtered[(dist.isna()) | (dist<=max_distance)]
        if "Similarity" in filtered.columns:
            sim=pd.to_numeric(filtered["Similarity"],errors="coerce")
            filtered=filtered[(sim.isna()) | (sim>=min_similarity)]
        if "Similarity" in filtered.columns:
            filtered=filtered.sort_values(["Similarity","Distance (mi)"],ascending=[False,True],na_position="last")

        s1,s2,s3,s4=st.columns(4)
        with s1: result_card("Comps shown",len(filtered))
        with s2: result_card("Median price",money(median_or_none(filtered,"Price")))
        with s3: result_card("Median $/Sq Ft",f'${median_or_none(filtered,"$/Sq Ft"):,.0f}' if median_or_none(filtered,"$/Sq Ft") else "—")
        with s4: result_card("Average DOM",f'{mean_or_none(filtered,"DOM"):.0f} days' if mean_or_none(filtered,"DOM") is not None else "—")

        cols=[c for c in ["Address","ZIP","Status","Price","Beds","Baths","Sq Ft","$/Sq Ft","DOM","Distance (mi)","Similarity","Listed","Removed"] if c in filtered.columns]
        st.dataframe(filtered[cols].style.format({"Price":"${:,.0f}","$/Sq Ft":"${:,.2f}","Distance (mi)":"{:.2f}","Similarity":"{:.0%}"},na_rep="—"),use_container_width=True,hide_index=True)

        map_rows=[]
        if subj.get("latitude") is not None and subj.get("longitude") is not None:
            map_rows.append({"lat":subj.get("latitude"),"lon":subj.get("longitude")})
        for _,r in filtered.dropna(subset=["Latitude","Longitude"]).iterrows():
            map_rows.append({"lat":r["Latitude"],"lon":r["Longitude"]})
        if map_rows:
            st.markdown("#### Subject + comp map")
            st.caption("The map includes the subject property when coordinates are available, plus the filtered comparable properties.")
            st.map(pd.DataFrame(map_rows),use_container_width=True)

        st.caption(f'Comp context: median distance {comp_median_distance:.2f} mi' if comp_median_distance is not None else "Comp distance unavailable")
        if comp_avg_similarity is not None:
            st.caption(f'Average similarity score across returned comps: {comp_avg_similarity:.0%}. RentCast sorts comparable listings by similarity/correlation.')


with tabs[6]:
    st.markdown("#### Neighborhood map & recent activity")
    st.caption("Fixed search area for this version: 1.5-mile radius. Recent recorded sales look back 12 months. This keeps API use predictable.")

    n_key = A.get("address_key")
    n_state = st.session_state.get("neighborhood_snapshot")
    same_neighborhood = isinstance(n_state, dict) and n_state.get("address_key") == n_key

    if not same_neighborhood:
        st.info("Load this only when you want the neighborhood map. It uses 2 additional RentCast requests for a new address and then caches the result for 30 days.")
        if st.button("Load neighborhood map & recent sales", type="primary", use_container_width=True):
            with st.spinner("Loading recent sales and active listings around the property..."):
                try:
                    nsales, nactive, ntime = neighborhood_cached(
                        n_key, key, A["input"], subj.get("propertyType")
                    )
                    st.session_state["neighborhood_snapshot"] = {
                        "address_key": n_key,
                        "recent_sales": nsales,
                        "active_listings": nactive,
                        "time": ntime,
                    }
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    else:
        recent_sales = n_state.get("recent_sales") or []
        active_listings = n_state.get("active_listings") or []
        rsdf_all = recent_sales_df(recent_sales, subj.get("latitude"), subj.get("longitude"))
        aldf_all = active_listing_df(active_listings, subj.get("latitude"), subj.get("longitude"))

        neighborhood_scope = st.radio(
            "Neighborhood geography",
            [f"Same ZIP only ({zip_code})", "1.5-mile radius (include other ZIPs)"],
            horizontal=True,
            key="neighborhood_geo_scope",
        )
        if neighborhood_scope.startswith("Same ZIP"):
            rsdf = rsdf_all[rsdf_all["ZIP"].astype(str) == zip_code].copy() if (not rsdf_all.empty and "ZIP" in rsdf_all.columns) else rsdf_all.copy()
            aldf = aldf_all[aldf_all["ZIP"].astype(str) == zip_code].copy() if (not aldf_all.empty and "ZIP" in aldf_all.columns) else aldf_all.copy()
        else:
            rsdf, aldf = rsdf_all.copy(), aldf_all.copy()

        # Exclude subject address from surrounding sales/listings if it appears.
        subject_addr = (subj.get("formattedAddress") or A["input"] or "").strip().lower()
        if not rsdf.empty and "Address" in rsdf.columns:
            rsdf = rsdf[rsdf["Address"].fillna("").str.strip().str.lower() != subject_addr]
        if not aldf.empty and "Address" in aldf.columns:
            aldf = aldf[aldf["Address"].fillna("").str.strip().str.lower() != subject_addr]

        n1,n2,n3,n4=st.columns(4)
        with n1: result_card("Recent sales", len(rsdf), f'ZIP {zip_code} · last 12 months' if neighborhood_scope.startswith("Same ZIP") else "Within 1.5 mi · last 12 months")
        with n2: result_card("Median sold price", money(median_or_none(rsdf,"Sold Price")))
        with n3: result_card("Active listings", len(aldf), f'ZIP {zip_code}' if neighborhood_scope.startswith("Same ZIP") else "Within 1.5 mi")
        with n4: result_card("Active median DOM", f'{median_or_none(aldf,"DOM"):.0f} days' if median_or_none(aldf,"DOM") is not None else "—")

        n5,n6,n7,n8=st.columns(4)
        with n5: result_card("Median sold $/Sq Ft", f'${median_or_none(rsdf,"$/Sq Ft"):,.0f}' if median_or_none(rsdf,"$/Sq Ft") else "—")
        with n6: result_card("Median active ask", money(median_or_none(aldf,"Ask Price")))
        with n7: result_card("Median active $/Sq Ft", f'${median_or_none(aldf,"$/Sq Ft"):,.0f}' if median_or_none(aldf,"$/Sq Ft") else "—")
        with n8:
            zip_dom = sd.get("medianDaysOnMarket") if sd else None
            result_card("ZIP median DOM", f'{zip_dom} days' if zip_dom is not None else "—", speed_label(zip_dom))

        map_df = neighborhood_map_rows(subj, rsdf, aldf, cdf)
        st.markdown("##### Interactive property map")
        render_neighborhood_map(map_df, subj.get("latitude"), subj.get("longitude"))

        st.markdown("##### Most recent recorded sales nearby")
        if rsdf.empty:
            st.info("No recorded sales were returned for this radius/lookback.")
        else:
            sale_cols=[c for c in ["Address","ZIP","Sold Price","Sale Date","Beds","Baths","Sq Ft","$/Sq Ft","Distance (mi)"] if c in rsdf.columns]
            st.dataframe(
                rsdf.head(30)[sale_cols].style.format({
                    "Sold Price":"${:,.0f}",
                    "$/Sq Ft":"${:,.0f}",
                    "Distance (mi)":"{:.2f}",
                },na_rep="—"),
                use_container_width=True,hide_index=True
            )

        st.markdown("##### Active competition nearby")
        if aldf.empty:
            st.info("No active listings were returned in the search area.")
        else:
            active_cols=[c for c in ["Address","ZIP","Ask Price","Beds","Baths","Sq Ft","$/Sq Ft","DOM","Listed","Distance (mi)"] if c in aldf.columns]
            st.dataframe(
                aldf.head(30)[active_cols].style.format({
                    "Ask Price":"${:,.0f}",
                    "$/Sq Ft":"${:,.0f}",
                    "Distance (mi)":"{:.2f}",
                },na_rep="—"),
                use_container_width=True,hide_index=True
            )
        st.caption(f'Neighborhood snapshot saved: {n_state.get("time","—")}. Reopening this address reuses cached neighborhood data while the 30-day cache remains available.')


with tabs[7]:
    st.markdown("#### ZIP / area market analysis")
    st.write(
        f"**Area:** {property_record.get('subdivision') or 'Subdivision unavailable'} · "
        f"{subj.get('city') or property_record.get('city') or 'City unavailable'}, "
        f"{subj.get('state') or property_record.get('state') or ''} · ZIP {zip_code} · "
        f"{(property_record.get('county') + ' County') if property_record.get('county') else 'County unavailable'}"
    )

    if not sd:
        st.info("No ZIP-level sale market statistics returned.")
    else:
        a1,a2,a3,a4=st.columns(4)
        with a1: result_card("Median asking price",money(sd.get("medianPrice")))
        with a2: result_card("Average asking price",money(sd.get("averagePrice")))
        with a3: result_card("Median $/Sq Ft",f'${sd.get("medianPricePerSquareFoot"):,.0f}' if sd.get("medianPricePerSquareFoot") else "—")
        with a4: result_card("Average $/Sq Ft",f'${sd.get("averagePricePerSquareFoot"):,.0f}' if sd.get("averagePricePerSquareFoot") else "—")
        b1,b2,b3,b4=st.columns(4)
        with b1: result_card("Median DOM",f'{sd.get("medianDaysOnMarket","—")} days',speed_label(sd.get("medianDaysOnMarket")))
        with b2: result_card("Average DOM",f'{sd.get("averageDaysOnMarket","—")} days')
        with b3: result_card("New listings",sd.get("newListings","—"))
        with b4: result_card("Total listings",sd.get("totalListings","—"))

        segment=segment_for_property_type(sd.get("dataByPropertyType"),subj.get("propertyType"))
        if segment:
            st.markdown(f'#### {subj.get("propertyType")} segment in ZIP {zip_code}')
            g1,g2,g3,g4=st.columns(4)
            with g1: result_card("Segment median price",money(segment.get("medianPrice")))
            with g2: result_card("Segment median $/Sq Ft",f'${segment.get("medianPricePerSquareFoot"):,.0f}' if segment.get("medianPricePerSquareFoot") else "—")
            with g3: result_card("Segment median DOM",f'{segment.get("medianDaysOnMarket","—")} days')
            with g4: result_card("Segment listings",segment.get("totalListings","—"))


        bedroom_segment=None
        subject_beds=subj.get("bedrooms")
        if subject_beds is not None:
            for row in sd.get("dataByBedrooms") or []:
                if row.get("bedrooms")==subject_beds:
                    bedroom_segment=row
                    break
        if bedroom_segment:
            st.markdown(f'#### {subject_beds}-bedroom segment in ZIP {zip_code}')
            y1,y2,y3,y4=st.columns(4)
            with y1: result_card("Median price",money(bedroom_segment.get("medianPrice")))
            with y2: result_card("Median $/Sq Ft",f'${bedroom_segment.get("medianPricePerSquareFoot"):,.0f}' if bedroom_segment.get("medianPricePerSquareFoot") else "—")
            with y3: result_card("Median DOM",f'{bedroom_segment.get("medianDaysOnMarket","—")} days')
            with y4: result_card("Listings",bedroom_segment.get("totalListings","—"),f'{bedroom_segment.get("newListings","—")} new')

        hdf=history_df(sd)
        if not hdf.empty:
            st.markdown("#### 12-month market history")
            st.dataframe(hdf.style.format({"Median Price":"${:,.0f}","Average Price":"${:,.0f}","Median $/Sq Ft":"${:,.2f}"},na_rep="—"),use_container_width=True,hide_index=True)
            chart=hdf[["Period","Median Price"]].dropna().set_index("Period")
            if not chart.empty:
                st.markdown("##### Median asking-price trend")
                st.line_chart(chart,use_container_width=True)
            dom_chart=hdf[["Period","Median DOM"]].dropna().set_index("Period")
            if not dom_chart.empty:
                st.markdown("##### Median days-on-market trend")
                st.line_chart(dom_chart,use_container_width=True)

with tabs[8]:
    st.markdown("#### Rental analysis")
    r1,r2,r3,r4=st.columns(4)
    with r1: result_card("Estimated monthly rent",money(rent_m))
    with r2: result_card("Rent range",f'{money(rent_data.get("rentRangeLow"))} – {money(rent_data.get("rentRangeHigh"))}')
    with r3: result_card("Gross annual rent",money(rent_m*12))
    with r4: result_card("Gross rent yield vs ARV",f'{(rent_m*12/arv)*100:.1f}%' if arv else "—")

    if rd:
        st.markdown("#### ZIP rental market")
        x1,x2,x3,x4=st.columns(4)
        with x1: result_card("ZIP median rent",money(rd.get("medianRent")))
        with x2: result_card("Median rental DOM",f'{rd.get("medianDaysOnMarket","—")} days')
        with x3: result_card("Average rental DOM",f'{rd.get("averageDaysOnMarket","—")} days')
        with x4: result_card("Rental listings",rd.get("totalListings","—"),f'{rd.get("newListings","—")} new')

    if not rdf.empty:
        st.markdown("#### Nearby rental comps")
        rcols=[c for c in ["Address","Status","Rent","Beds","Baths","Sq Ft","Rent/Sq Ft","DOM","Distance (mi)","Similarity"] if c in rdf.columns]
        st.dataframe(rdf[rcols].style.format({"Rent":"${:,.0f}","Rent/Sq Ft":"${:,.2f}","Distance (mi)":"{:.2f}","Similarity":"{:.0%}"},na_rep="—"),use_container_width=True,hide_index=True)

with tabs[9]:
    row={
        "analyzed_at_utc":A["time"],"address":subj.get("formattedAddress") or A["input"],"strategy":strategy,
        "property_type":subj.get("propertyType"),"beds":subj.get("bedrooms"),"baths":subj.get("bathrooms"),
        "sqft":subj.get("squareFootage"),"lot_size":subj.get("lotSize"),"year_built":subj.get("yearBuilt"),
        "last_sale_price":subj.get("lastSalePrice"),"last_sale_date":subj.get("lastSaleDate"),
        "arv":arv,"arv_low":val.get("priceRangeLow"),"arv_high":val.get("priceRangeHigh"),
        "rent_monthly":rent_m,"rehab":rehab,"offer_ceiling":ceiling,"zip_code":zip_code,
        "zip_median_price":sd.get("medianPrice") if sd else None,
        "zip_median_ppsf":sd.get("medianPricePerSquareFoot") if sd else None,
        "zip_median_dom":sd.get("medianDaysOnMarket") if sd else None,
        "zip_total_listings":sd.get("totalListings") if sd else None,
        "sales_comp_count_same_zip":len(cdf_same_zip),"sales_comp_count_all_avm":len(cdf_all),"sales_comp_median_price":comp_median_price,"sales_comp_median_ppsf":comp_median_ppsf,
        "owner_name":", ".join(((property_record.get("owner") or {}).get("names") or [])) or None,
        "owner_occupied":property_record.get("ownerOccupied"),
        "assessor_id":property_record.get("assessorID"),
        "subdivision":property_record.get("subdivision"),
        "zoning":property_record.get("zoning"),
        "hoa_fee":((property_record.get("hoa") or {}).get("fee")),
        "latest_property_tax":next((v.get("total") for _,v in sorted((property_record.get("propertyTaxes") or {}).items(), reverse=True) if isinstance(v,dict)),None),
        "listing_status":listing_record.get("status"),
        "listing_price":listing_record.get("price"),
        "listing_dom":listing_record.get("daysOnMarket"),
        "listing_date":listing_record.get("listedDate"),
        "mls_name":listing_record.get("mlsName"),
        "mls_number":listing_record.get("mlsNumber"),
    }
    csv=pd.DataFrame([row]).to_csv(index=False).encode("utf-8")
    st.download_button("Download deal summary CSV",csv,"norvim_deal_analysis.csv","text/csv",use_container_width=True)
    if not cdf.empty:
        st.download_button("Download sales comps CSV",cdf.to_csv(index=False).encode("utf-8"),"norvim_sales_comps.csv","text/csv",use_container_width=True)
    if not rdf.empty:
        st.download_button("Download rental comps CSV",rdf.to_csv(index=False).encode("utf-8"),"norvim_rental_comps.csv","text/csv",use_container_width=True)
    nstate = st.session_state.get("neighborhood_snapshot")
    if isinstance(nstate,dict) and nstate.get("address_key")==A.get("address_key"):
        rs_export = recent_sales_df(nstate.get("recent_sales") or [], subj.get("latitude"), subj.get("longitude"))
        al_export = active_listing_df(nstate.get("active_listings") or [], subj.get("latitude"), subj.get("longitude"))
        if not rs_export.empty:
            st.download_button("Download neighborhood recent sales CSV",rs_export.to_csv(index=False).encode("utf-8"),"norvim_neighborhood_recent_sales.csv","text/csv",use_container_width=True)
        if not al_export.empty:
            st.download_button("Download neighborhood active listings CSV",al_export.to_csv(index=False).encode("utf-8"),"norvim_neighborhood_active_listings.csv","text/csv",use_container_width=True)
    st.caption("v1.8 makes BRRRR analysis easier to read: a friendly profitability snapshot, plain-English cash flow and equity cards, simple checks, and suggested next moves.")
