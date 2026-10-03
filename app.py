import os
import re
from datetime import datetime
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
    market = api_get("/markets", {"zipCode":subj.get("zipCode")}, key) if subj.get("zipCode") else {}
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return val, rent, market, fetched_at


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

st.markdown('<div class="k">NORVIM 13 LLC</div><div class="t">Deal Analyzer</div><div class="s">Address → ARV → comps → market speed → rent → maximum offer.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Property data")
    key = get_key()
    if not key:
        entered = st.text_input("RentCast API key", type="password", help="For testing. Use Streamlit Secrets on the live site.")
        if entered:
            st.session_state["rentcast_api_key"] = entered; key = entered
    else: st.success("Property-data API connected")
    st.caption("About 3 API requests the first time. Re-running the same address reuses a saved 30-day snapshot and does not call RentCast again.")
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
                val, rent_data, market, fetched_at = analyze_cached(address_key, key, address_clean)
                st.session_state["analysis"] = {
                    "input": address_clean,
                    "address_key": address_key,
                    "valuation": val,
                    "rent": rent_data,
                    "market": market,
                    "time": fetched_at,
                }
            except Exception as e: st.error(str(e))

A = st.session_state.get("analysis")
if not A:
    st.info("Enter an address to start. The app can analyze listed or off-market properties when the data provider has a record for the address.")
    st.stop()

val, rent_data, market = A["valuation"], A["rent"], A["market"]
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

tabs=st.tabs(["Deal","Sales comps","Area","Rental","Export"])
with tabs[0]:
    st.markdown("#### Deal math")
    rows=[["ARV",arv],["Rehab",rehab],["Purchase/closing allowance",arv*closing/100],["Selling-cost allowance",arv*selling/100],["Holding + financing",holding],["Rehab contingency",rehab*contingency/100],["Target profit",target_profit if strategy in ("Flip","Wholesale") else None],["Assignment fee",assignment if strategy=="Wholesale" else None],["Offer ceiling",ceiling]]
    df=pd.DataFrame(rows,columns=["Item","Amount"]).dropna()
    st.dataframe(df.style.format({"Amount":"${:,.0f}"}),use_container_width=True,hide_index=True)

with tabs[1]:
    cdf=comp_df(val.get("comparables") or [])
    if cdf.empty: st.info("No sales comps returned.")
    else:
        cols=[c for c in ["Address","Status","Price","Beds","Baths","Sq Ft","$/Sq Ft","DOM","Distance (mi)","Similarity","Listed","Removed"] if c in cdf.columns]
        st.dataframe(cdf[cols].style.format({"Price":"${:,.0f}","$/Sq Ft":"${:,.2f}","Similarity":"{:.0%}"},na_rep="—"),use_container_width=True,hide_index=True)
        mdf=cdf.dropna(subset=["Latitude","Longitude"])[["Latitude","Longitude"]].rename(columns={"Latitude":"lat","Longitude":"lon"})
        if not mdf.empty: st.markdown("#### Comp map"); st.map(mdf,use_container_width=True)

with tabs[2]:
    sd=market.get("saleData") or {}
    if not sd: st.info("No ZIP-level sale market statistics returned.")
    else:
        a1,a2,a3,a4=st.columns(4)
        with a1: result_card("ZIP median price", money(sd.get("medianPrice")))
        with a2: result_card("Average DOM", f'{sd.get("averageDaysOnMarket","—")} days')
        with a3: result_card("Median DOM", f'{sd.get("medianDaysOnMarket","—")} days')
        with a4: result_card("Listings", sd.get("totalListings","—"))
        hist=sd.get("history") or {}
        if isinstance(hist,dict) and hist:
            h=[]
            for period,v in hist.items():
                if isinstance(v,dict): h.append({"Period":period,"Median Price":v.get("medianPrice"),"Average DOM":v.get("averageDaysOnMarket"),"Median DOM":v.get("medianDaysOnMarket"),"Listings":v.get("totalListings")})
            if h: st.dataframe(pd.DataFrame(h).sort_values("Period").style.format({"Median Price":"${:,.0f}"},na_rep="—"),use_container_width=True,hide_index=True)

with tabs[3]:
    r1,r2,r3=st.columns(3)
    with r1: result_card("Estimated monthly rent", money(rent_m))
    with r2: result_card("Rent range", f'{money(rent_data.get("rentRangeLow"))} – {money(rent_data.get("rentRangeHigh"))}')
    with r3: result_card("Gross annual rent", money(rent_m*12))
    rd=market.get("rentalData") or {}
    if rd:
        x1,x2,x3=st.columns(3)
        with x1: result_card("ZIP median rent", money(rd.get("medianRent")))
        with x2: result_card("Average rental DOM", f'{rd.get("averageDaysOnMarket","—")} days')
        with x3: result_card("Rental listings", rd.get("totalListings","—"))

with tabs[4]:
    row={"analyzed_at_utc":A["time"],"address":subj.get("formattedAddress") or A["input"],"strategy":strategy,"property_type":subj.get("propertyType"),"beds":subj.get("bedrooms"),"baths":subj.get("bathrooms"),"sqft":subj.get("squareFootage"),"year_built":subj.get("yearBuilt"),"arv":arv,"arv_low":val.get("priceRangeLow"),"arv_high":val.get("priceRangeHigh"),"rent_monthly":rent_m,"rehab":rehab,"offer_ceiling":ceiling,"zip_code":subj.get("zipCode")}
    csv=pd.DataFrame([row]).to_csv(index=False).encode("utf-8")
    st.download_button("Download deal summary CSV",csv,"norvim_deal_analysis.csv","text/csv",use_container_width=True)
    st.caption("Persistent deal saving and a branded PDF can be added next.")
