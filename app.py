import os
import re
from datetime import datetime
from urllib.parse import quote
import pandas as pd
import requests
import streamlit as st

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


def comp_df(comps):
    rows=[]
    for c in comps or []:
        sqft, price = c.get("squareFootage"), c.get("price")
        rows.append({
            "Address":c.get("formattedAddress"),"Status":c.get("status"),"Price":price,
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
    st.caption("About 5 API requests the first time. Re-running the same address reuses the saved 30-day snapshot and does not call RentCast again.")
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

m1,m2,m3,m4=st.columns(4)
with m1: result_card("Estimated ARV", money(arv))
with m2: result_card("ARV range", f'{money(val.get("priceRangeLow"))} – {money(val.get("priceRangeHigh"))}')
with m3: result_card("Estimated rent", f'{money(rent_m)}/mo')
with m4: result_card(label, money(ceiling))
st.caption(note)
st.info(f'Data snapshot saved: {A["time"]}. The same normalized address will reuse this snapshot for up to 30 days, avoiding another RentCast charge/request.')
st.warning("Underwriting estimate only. Verify title, condition, flood risk, taxes, liens, repair scope and local comps before contracting.")

tabs=st.tabs(["Overview","Property record","Listing","Deal","Sales comps","Area market","Rental","Export"])

# Precompute reusable tables and summary statistics from the three API responses.
cdf=comp_df(val.get("comparables") or [])
rdf=rental_comp_df(rent_data.get("comparables") or [])
sd=market.get("saleData") or {}
rd=market.get("rentalData") or {}
zip_code=subj.get("zipCode") or market.get("zipCode") or "—"
subject_ppsf=(float(arv)/float(subj.get("squareFootage")) if arv and subj.get("squareFootage") else None)
comp_median_price=median_or_none(cdf,"Price")
comp_median_ppsf=median_or_none(cdf,"$/Sq Ft")
comp_avg_dom=mean_or_none(cdf,"DOM")
comp_median_distance=median_or_none(cdf,"Distance (mi)")
comp_avg_similarity=mean_or_none(cdf,"Similarity")

with tabs[0]:
    st.markdown("#### Property & neighborhood snapshot")
    p1,p2,p3,p4=st.columns(4)
    with p1: result_card("ZIP code", zip_code)
    with p2: result_card("Lot size", f'{subj.get("lotSize"):,} sf' if isinstance(subj.get("lotSize"),(int,float)) else "—")
    with p3: result_card("Last sale", money(subj.get("lastSalePrice")), str(subj.get("lastSaleDate") or "Date not available"))
    with p4: result_card("Subject $/Sq Ft", f'${subject_ppsf:,.0f}' if subject_ppsf else "—")

    st.markdown("#### Nearby sales comp snapshot")
    q1,q2,q3,q4=st.columns(4)
    with q1: result_card("Sale comps returned", len(cdf))
    with q2: result_card("Median comp price", money(comp_median_price))
    with q3: result_card("Median comp $/Sq Ft", f'${comp_median_ppsf:,.0f}' if comp_median_ppsf else "—")
    with q4: result_card("Average comp DOM", f'{comp_avg_dom:.0f} days' if comp_avg_dom is not None else "—")

    if sd:
        st.markdown("#### Area market snapshot")
        z1,z2,z3,z4=st.columns(4)
        with z1: result_card("ZIP median asking price", money(sd.get("medianPrice")), f'ARV vs ZIP: {pct_text(pct_diff(arv,sd.get("medianPrice")))}')
        with z2: result_card("ZIP median $/Sq Ft", f'${sd.get("medianPricePerSquareFoot"):,.0f}' if sd.get("medianPricePerSquareFoot") else "—", f'Subject vs ZIP: {pct_text(pct_diff(subject_ppsf,sd.get("medianPricePerSquareFoot")))}')
        with z3: result_card("Median days on market", f'{sd.get("medianDaysOnMarket","—")} days', speed_label(sd.get("medianDaysOnMarket")))
        with z4: result_card("Listings seen", sd.get("totalListings","—"), f'{sd.get("newListings","—")} new listings')

    if not cdf.empty:
        top=cdf.sort_values(["Similarity","Distance (mi)"],ascending=[False,True]).head(5)
        st.markdown("#### Top 5 comparable houses")
        top_cols=[c for c in ["Address","Price","Beds","Baths","Sq Ft","$/Sq Ft","DOM","Distance (mi)","Similarity"] if c in top.columns]
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

with tabs[4]:
    st.markdown("#### Comparable houses around the subject")
    if cdf.empty:
        st.info("No sales comps returned.")
    else:
        f1,f2=st.columns(2)
        with f1:
            max_distance=st.slider("Maximum distance (miles)",0.25,2.0,2.0,0.25,key="sale_radius")
        with f2:
            min_similarity=st.slider("Minimum similarity",0,100,0,5,key="sale_similarity")/100
        filtered=cdf.copy()
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

        cols=[c for c in ["Address","Status","Price","Beds","Baths","Sq Ft","$/Sq Ft","DOM","Distance (mi)","Similarity","Listed","Removed"] if c in filtered.columns]
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

with tabs[5]:
    st.markdown("#### ZIP / area market analysis")
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

with tabs[6]:
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

with tabs[7]:
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
        "sales_comp_count":len(cdf),"sales_comp_median_price":comp_median_price,"sales_comp_median_ppsf":comp_median_ppsf,
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
    st.caption("This version adds public-record ownership/tax/sale history and exact listing history to the cached NORVIM snapshot. Persistent CRM storage can be added next.")
