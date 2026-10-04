import os
import re
import math
from datetime import datetime, timezone
from urllib.parse import quote, quote_plus
import pandas as pd
import requests
import streamlit as st
import pydeck as pdk

API_BASE = "https://api.rentcast.io/v1"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

st.set_page_config(page_title="NORVIM DealFinder 2.2", page_icon="🏠", layout="wide")
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

.map-legend {display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin:8px 0 12px;padding:10px 12px;background:#FFFDF7;border:1px solid #D8D1C2;border-radius:10px;}
.map-legend-item {display:flex;align-items:center;gap:7px;font-size:.88rem;color:#394039 !important;}
.map-dot {width:12px;height:12px;border-radius:50%;display:inline-block;border:1px solid rgba(255,255,255,.95);box-shadow:0 0 0 1px rgba(0,0,0,.12);}
.map-dot.subject {background:rgb(89,99,79);}
.map-dot.sale {background:rgb(61,120,184);}
.map-dot.active {background:rgb(214,137,63);}
.map-dot.comp {background:rgb(126,92,120);}

.strategy-card {
    background:#FFFDF7;
    border:1px solid #D8D1C2;
    border-radius:14px;
    padding:15px 16px;
    min-height:180px;
    margin-bottom:10px;
}
.strategy-card.good { border-left:6px solid #6F8A63; }
.strategy-card.warn { border-left:6px solid #C89D4A; }
.strategy-card.bad { border-left:6px solid #B87569; }
.strategy-card .strategy-name {font-family:Georgia,serif;font-size:1.25rem;font-weight:700;color:#172019 !important;}
.strategy-card .strategy-status {font-size:.85rem;font-weight:700;margin:5px 0 8px;color:#59634F !important;}
.strategy-card .strategy-copy {font-size:.88rem;line-height:1.45;color:#596058 !important;}
.source-pill {display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid #D8D1C2;background:#FFFDF7;font-size:.76rem;margin:2px 3px 2px 0;color:#596058 !important;}
.big-decision {
    padding:18px 20px;border-radius:15px;background:#FFFDF7;border:1px solid #D8D1C2;margin:6px 0 18px;
}
.big-decision .title {font-family:Georgia,serif;font-size:1.65rem;font-weight:700;color:#172019 !important;}
.big-decision .copy {margin-top:5px;color:#596058 !important;line-height:1.45;}

@media (max-width: 700px) {
    .norvim-card .value { font-size:1.45rem; }
}
</style>
""", unsafe_allow_html=True)


def money(v):
    try: return f"${float(v):,.0f}"
    except: return "—"


def parse_money_input(value, default=0.0):
    """Parse user-entered dollar text such as 320,000 or $320,000."""
    try:
        cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
        return float(cleaned) if cleaned not in ("", "-", ".") else float(default)
    except Exception:
        return float(default)


def _format_money_state(key):
    value = parse_money_input(st.session_state.get(key, "0"), 0)
    st.session_state[key] = f"{value:,.0f}"


def money_input(label, default=0.0, key=None, help=None):
    """Dollar input that keeps thousands separators visible for easier underwriting."""
    if not key:
        key = "money_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    if key not in st.session_state:
        st.session_state[key] = f"{float(default):,.0f}"
    raw = st.text_input(
        label,
        key=key,
        help=help,
        on_change=_format_money_state,
        args=(key,),
    )
    return parse_money_input(raw, default)


def state_number(key, default):
    try:
        return float(st.session_state.get(key, default))
    except Exception:
        return float(default)


def state_int(key, default):
    try:
        return int(st.session_state.get(key, default))
    except Exception:
        return int(default)


def result_card(label, value, sub=None):
    safe_label = str(label or "")
    safe_value = str(value or "—")
    safe_sub = f'<div class="sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="norvim-card"><div class="label">{safe_label}</div><div class="value">{safe_value}</div>{safe_sub}</div>',
        unsafe_allow_html=True,
    )



def get_setting(name, default=None):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def supabase_config():
    url = str(get_setting("SUPABASE_URL", "") or "").strip().rstrip("/")
    service_key = str(get_setting("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
    org_id = str(get_setting("NORVIM_ORG_ID", "norvim") or "norvim").strip()
    return url, service_key, org_id


def db_enabled():
    url, key, _ = supabase_config()
    return bool(url and key)


def db_request(method, table, params=None, payload=None, prefer=None, timeout=20):
    url, key, _ = supabase_config()
    if not url or not key:
        raise RuntimeError("Supabase is not configured.")
    headers = {
        "apikey": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    if prefer:
        headers["Prefer"] = prefer
    r = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        params=params or {},
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    if not r.ok:
        raise RuntimeError(f"Database request failed ({r.status_code}): {r.text[:300]}")
    if not r.text.strip():
        return []
    try:
        return r.json()
    except Exception:
        return []


def db_get_cached_snapshot(address_key, max_age_days=None):
    """Return the latest saved snapshot. If max_age_days is None, return it regardless of age."""
    if not db_enabled():
        return None
    _, _, org_id = supabase_config()
    try:
        rows = db_request(
            "GET",
            "analysis_snapshots",
            params={
                "select": "snapshot,fetched_at",
                "org_id": f"eq.{org_id}",
                "normalized_address": f"eq.{address_key}",
                "order": "fetched_at.desc",
                "limit": 1,
            },
        )
        if not rows:
            return None
        row = rows[0]
        fetched_at = row.get("fetched_at")
        if not fetched_at:
            return None
        dt = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        if max_age_days is not None and age_days > float(max_age_days):
            return None
        snap = row.get("snapshot") or {}
        if not isinstance(snap, dict):
            return None
        snap = dict(snap)
        snap["_db_cache_age_days"] = age_days
        return snap
    except Exception as e:
        st.session_state["db_last_error"] = str(e)
        return None


def iso_age_days(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return None


def snapshot_field_fresh(snapshot, timestamp_key, max_age_days, value_key=None, fallback_to_time=True):
    """Check freshness for one section inside a property snapshot."""
    if not isinstance(snapshot, dict):
        return False
    if value_key is not None and value_key not in snapshot:
        return False
    stamp = snapshot.get(timestamp_key)
    if not stamp and fallback_to_time:
        stamp = snapshot.get("time")
    age = iso_age_days(stamp)
    return age is not None and age <= float(max_age_days)


def db_save_snapshot(address_key, address, snapshot):
    if not db_enabled():
        return False
    _, _, org_id = supabase_config()
    try:
        db_request(
            "POST",
            "analysis_snapshots",
            payload={
                "org_id": org_id,
                "normalized_address": address_key,
                "address": address,
                "snapshot": snapshot,
                "fetched_at": snapshot.get("time") or utc_now_iso(),
            },
            prefer="return=minimal",
        )
        return True
    except Exception as e:
        st.session_state["db_last_error"] = str(e)
        return False


def db_merge_save_snapshot(address_key, address, updates):
    """Merge one optional/deep data section into the latest permanent snapshot."""
    if not db_enabled():
        return False
    current = db_get_cached_snapshot(address_key, max_age_days=None) or {}
    current.pop("_db_cache_age_days", None)
    current.update(updates or {})
    current["time"] = utc_now_iso()
    return db_save_snapshot(address_key, address, current)


def db_upsert_property(subject, property_record, address_key, fallback_address):
    if not db_enabled():
        return None
    _, _, org_id = supabase_config()
    payload = {
        "org_id": org_id,
        "normalized_address": address_key,
        "rentcast_id": property_record.get("id") or subject.get("id"),
        "address": subject.get("formattedAddress") or property_record.get("formattedAddress") or fallback_address,
        "city": subject.get("city") or property_record.get("city"),
        "state": subject.get("state") or property_record.get("state"),
        "zip_code": str(subject.get("zipCode") or property_record.get("zipCode") or "") or None,
        "property_type": subject.get("propertyType") or property_record.get("propertyType"),
        "bedrooms": subject.get("bedrooms") or property_record.get("bedrooms"),
        "bathrooms": subject.get("bathrooms") or property_record.get("bathrooms"),
        "square_footage": subject.get("squareFootage") or property_record.get("squareFootage"),
        "latitude": subject.get("latitude") or property_record.get("latitude"),
        "longitude": subject.get("longitude") or property_record.get("longitude"),
        "updated_at": utc_now_iso(),
    }
    try:
        rows = db_request(
            "POST",
            "properties",
            params={"on_conflict": "org_id,normalized_address"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        return rows[0] if rows else None
    except Exception as e:
        st.session_state["db_last_error"] = str(e)
        return None


def db_save_underwriting(property_id, address_key, selected_strategy, purchase_price, strategy_results, assumptions):
    if not db_enabled() or not property_id:
        return False
    _, _, org_id = supabase_config()
    try:
        db_request(
            "POST",
            "underwriting_runs",
            payload={
                "org_id": org_id,
                "property_id": property_id,
                "normalized_address": address_key,
                "selected_strategy": selected_strategy,
                "purchase_price": purchase_price,
                "strategy_results": strategy_results,
                "assumptions": assumptions,
                "created_at": utc_now_iso(),
            },
            prefer="return=minimal",
        )
        return True
    except Exception as e:
        st.session_state["db_last_error"] = str(e)
        return False


def db_save_lead(property_id, lead):
    if not db_enabled() or not property_id:
        return False
    _, _, org_id = supabase_config()
    payload = {
        "org_id": org_id,
        "property_id": property_id,
        "status": lead.get("status"),
        "lead_source": lead.get("lead_source"),
        "seller_name": lead.get("seller_name"),
        "seller_phone": lead.get("seller_phone"),
        "seller_email": lead.get("seller_email"),
        "partner": lead.get("partner"),
        "preferred_strategy": lead.get("preferred_strategy"),
        "seller_ask": lead.get("seller_ask"),
        "offer_amount": lead.get("offer_amount"),
        "follow_up_date": lead.get("follow_up_date"),
        "notes": lead.get("notes"),
        "updated_at": utc_now_iso(),
    }
    try:
        db_request(
            "POST",
            "leads",
            params={"on_conflict": "org_id,property_id"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        return True
    except Exception as e:
        st.session_state["db_last_error"] = str(e)
        return False


def db_get_pipeline():
    if not db_enabled():
        return []
    _, _, org_id = supabase_config()
    try:
        return db_request(
            "GET",
            "lead_pipeline",
            params={
                "select": "*",
                "org_id": f"eq.{org_id}",
                "order": "updated_at.desc",
                "limit": 250,
            },
        )
    except Exception as e:
        st.session_state["db_last_error"] = str(e)
        return []


def record_api_usage(endpoint, address_key=None):
    # Track only successful RentCast HTTP 200 responses.
    st.session_state["rentcast_usage_session"] = int(st.session_state.get("rentcast_usage_session", 0)) + 1
    if not db_enabled():
        return
    _, _, org_id = supabase_config()
    try:
        db_request(
            "POST",
            "api_usage",
            payload={
                "org_id": org_id,
                "provider": "RentCast",
                "endpoint": endpoint,
                "normalized_address": address_key,
                "occurred_at": utc_now_iso(),
            },
            prefer="return=minimal",
        )
    except Exception:
        pass


def db_monthly_api_usage():
    offset = int(float(get_setting("RENTCAST_USAGE_OFFSET", 0) or 0))
    if not db_enabled():
        return offset + int(st.session_state.get("rentcast_usage_session", 0))
    _, _, org_id = supabase_config()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        rows = db_request(
            "GET",
            "api_usage",
            params={
                "select": "id",
                "org_id": f"eq.{org_id}",
                "provider": "eq.RentCast",
                "occurred_at": f"gte.{month_start}",
                "limit": 5000,
            },
        )
        return offset + len(rows)
    except Exception:
        return offset + int(st.session_state.get("rentcast_usage_session", 0))


def safe_public_get(url, params=None, timeout=18):
    try:
        r = requests.get(url, params=params or {}, timeout=timeout, headers={"User-Agent": "NORVIM-DealFinder/2.2"})
        if not r.ok:
            return {"_error": f"HTTP {r.status_code}"}
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            return {"_error": str(data.get("error"))}
        return data
    except Exception as e:
        return {"_error": str(e)}


def arcgis_nearby_query(url, lat, lon, distance_miles, out_fields="*", limit=250):
    if lat is None or lon is None:
        return []
    payload = safe_public_get(
        url,
        {
            "where": "1=1",
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "distance": round(float(distance_miles) * 1609.344, 1),
            "units": "esriSRUnit_Meter",
            "outFields": out_fields,
            "returnGeometry": "false",
            "resultRecordCount": int(limit),
            "f": "json",
        },
    )
    if not isinstance(payload, dict) or payload.get("_error"):
        return []
    return payload.get("features") or []


def _first_attr(attrs, candidates):
    if not isinstance(attrs, dict):
        return None
    normalized = {str(k).lower().replace("_", "").replace(" ", ""): v for k, v in attrs.items()}
    for candidate in candidates:
        c = candidate.lower().replace("_", "").replace(" ", "")
        if c in normalized and normalized[c] not in (None, ""):
            return normalized[c]
    for key, value in normalized.items():
        for candidate in candidates:
            c = candidate.lower().replace("_", "").replace(" ", "")
            if c in key and value not in (None, ""):
                return value
    return None


def summarize_311(features):
    categories = {}
    rows = []
    for feature in features or []:
        attrs = feature.get("attributes") or {}
        category = _first_attr(attrs, ["srtype", "servicerequesttype", "type", "problem", "subject", "category"]) or "Other / unknown"
        status = _first_attr(attrs, ["status", "srstatus", "case_status"])
        case_no = _first_attr(attrs, ["casenumber", "case_no", "srnumber", "servicerequestnumber"])
        address = _first_attr(attrs, ["address", "incidentaddress", "streetaddress", "location"])
        categories[str(category)] = categories.get(str(category), 0) + 1
        rows.append({"Category": category, "Status": status, "Case": case_no, "Location": address})
    top = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    return top, pd.DataFrame(rows)


def summarize_plats(features):
    rows = []
    for feature in features or []:
        attrs = feature.get("attributes") or {}
        rows.append({
            "Subdivision": _first_attr(attrs, ["SubdivisionName", "DocName"]),
            "Application": _first_attr(attrs, ["AppNo", "AppId"]),
            "Status": _first_attr(attrs, ["AppStatus"]),
            "Type": _first_attr(attrs, ["AppCode"]),
            "Review Cycle": _first_attr(attrs, ["ReviewCycle"]),
            "Upload Date": _first_attr(attrs, ["UploadDate"]),
        })
    return pd.DataFrame(rows)


def census_zip_profile(zip_code, census_key):
    if not zip_code or not census_key:
        return {}
    vars_ = [
        "NAME",
        "B01003_001E",  # population
        "B19013_001E",  # median household income
        "B25002_001E",  # housing units
        "B25002_002E",  # occupied
        "B25002_003E",  # vacant
        "B25003_001E",  # occupied tenure total
        "B25003_002E",  # owner occupied
        "B25003_003E",  # renter occupied
        "B25064_001E",  # median gross rent
        "B25077_001E",  # median home value
        "B25035_001E",  # median year built
    ]
    data = safe_public_get(
        "https://api.census.gov/data/2024/acs/acs5",
        {
            "get": ",".join(vars_),
            "for": f"zip code tabulation area:{zip_code}",
            "key": census_key,
        },
    )
    if not isinstance(data, list) or len(data) < 2:
        return {}
    headers, values = data[0], data[1]
    row = dict(zip(headers, values))
    def num(key):
        try:
            v = float(row.get(key))
            return None if v < 0 else v
        except Exception:
            return None
    housing = num("B25002_001E")
    vacant = num("B25002_003E")
    tenure = num("B25003_001E")
    owner = num("B25003_002E")
    renter = num("B25003_003E")
    return {
        "name": row.get("NAME"),
        "population": num("B01003_001E"),
        "median_household_income": num("B19013_001E"),
        "housing_units": housing,
        "vacancy_rate": (vacant / housing) if housing else None,
        "owner_rate": (owner / tenure) if tenure else None,
        "renter_rate": (renter / tenure) if tenure else None,
        "median_gross_rent": num("B25064_001E"),
        "median_home_value": num("B25077_001E"),
        "median_year_built": num("B25035_001E"),
    }


@st.cache_data(ttl=7 * 24 * 60 * 60, show_spinner=False)
def public_intelligence_cached(address_key, lat, lon, zip_code, census_key):
    result = {"flood": {}, "311": [], "plat_apps": [], "final_plats": [], "census": {}, "fetched_at": utc_now_iso()}
    if lat is None or lon is None:
        return result

    flood = safe_public_get(
        "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query",
        {
            "where": "1=1",
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    if isinstance(flood, dict) and not flood.get("_error"):
        feats = flood.get("features") or []
        result["flood"] = (feats[0].get("attributes") or {}) if feats else {}

    result["311"] = arcgis_nearby_query(
        "https://mycity2.houstontx.gov/pubgis01/rest/services/311/Houston311_RecentServiceRequests/FeatureServer/4/query",
        lat, lon, 0.5, "*", 500
    )
    result["plat_apps"] = arcgis_nearby_query(
        "https://mycity2.houstontx.gov/geoplat01/rest/services/PlatTracker/PT365_PLAT_MAPPING/MapServer/1/query",
        lat, lon, 1.0, "DocName,AppId,UploadDate,AppNo,ReviewCycle,AppCode,AppStatus,SubdivisionName", 250
    )
    result["final_plats"] = arcgis_nearby_query(
        "https://mycity2.houstontx.gov/geoplat01/rest/services/PlatTracker/PT365_PLAT_MAPPING/MapServer/0/query",
        lat, lon, 1.0, "DocName,AppId,UploadDate", 250
    )
    if census_key:
        result["census"] = census_zip_profile(zip_code, census_key)
    return result

def get_key():
    try:
        if "RENTCAST_API_KEY" in st.secrets:
            return st.secrets["RENTCAST_API_KEY"]
    except Exception:
        pass
    return os.getenv("RENTCAST_API_KEY") or st.session_state.get("rentcast_api_key", "")


def api_get(path, params, key, address_key=None):
    r = requests.get(f"{API_BASE}{path}", params=params,
                     headers={"Accept":"application/json","X-Api-Key":key}, timeout=30)
    if r.status_code == 401: raise RuntimeError("RentCast rejected the API key.")
    if r.status_code == 429: raise RuntimeError("RentCast request limit reached.")
    if not r.ok:
        try: detail = r.json().get("message", "")
        except: detail = r.text[:250]
        raise RuntimeError(f"Property-data request failed ({r.status_code}). {detail}")
    record_api_usage(path, address_key)
    return r.json()



def api_get_optional(path, params, key, address_key=None):
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
    record_api_usage(path, address_key)
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
def quick_scan_cached(address_key, key, _address_for_api):
    """Default scan: exactly two RentCast endpoints — value AVM and long-term rent AVM."""
    val = api_get(
        "/avm/value",
        {"address": _address_for_api, "lookupSubjectAttributes": "true", "maxRadius": 2, "daysOld": 365, "compCount": 15},
        key,
        address_key,
    )
    rent = api_get(
        "/avm/rent/long-term",
        {"address": _address_for_api, "lookupSubjectAttributes": "true", "maxRadius": 3, "daysOld": 365, "compCount": 15},
        key,
        address_key,
    )
    return val, rent, utc_now_iso()


@st.cache_data(ttl=180 * 24 * 60 * 60, show_spinner=False)
def property_record_cached(address_key, key, _address_for_api):
    """Optional public-record profile. Loaded only when the user asks for it."""
    payload = api_get_optional("/properties", {"address": _address_for_api}, key, address_key)
    return first_record(payload), utc_now_iso()


@st.cache_data(ttl=7 * 24 * 60 * 60, show_spinner=False)
def listing_record_cached(address_key, key, property_id):
    """Optional exact sale-listing record. Loaded only when requested."""
    if not property_id:
        return {}, utc_now_iso()
    record = api_get_optional(
        f"/listings/sale/{quote(str(property_id), safe='')}",
        {},
        key,
        address_key,
    )
    return record or {}, utc_now_iso()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def market_zip_cached(zip_code, key):
    """Optional ZIP market data. One ZIP snapshot can be reused across many properties."""
    if not zip_code:
        return {}, utc_now_iso()
    market = api_get("/markets", {"zipCode": str(zip_code), "dataType": "All", "historyRange": 12}, key, f"zip::{zip_code}")
    return market or {}, utc_now_iso()



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

    recent_sales = api_get("/properties", params_sales, key, address_key)
    active_listings = api_get("/listings/sale", params_active, key, address_key)
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



def neighborhood_map_rows(
    subj,
    sales_df,
    active_df,
    comps_df,
    valuation=None,
    rent_data=None,
    property_record=None,
):
    valuation = valuation or {}
    rent_data = rent_data or {}
    property_record = property_record or {}

    rows = []
    slat, slon = subj.get("latitude"), subj.get("longitude")

    if slat is not None and slon is not None:
        rows.append({
            "lat": slat,
            "lon": slon,
            "type": "Subject property",
            "address": subj.get("formattedAddress") or property_record.get("formattedAddress") or "Subject property",
            "zip": subj.get("zipCode") or property_record.get("zipCode"),
            "price": valuation.get("price"),
            "price_label": "Estimated ARV",
            "rent": rent_data.get("rent"),
            "beds": subj.get("bedrooms") or property_record.get("bedrooms"),
            "baths": subj.get("bathrooms") or property_record.get("bathrooms"),
            "sqft": subj.get("squareFootage") or property_record.get("squareFootage"),
            "year_built": subj.get("yearBuilt") or property_record.get("yearBuilt"),
            "dom": None,
            "date": None,
            "distance": 0.0,
            "detail": "Property being analyzed",
        })

    for _, r in sales_df.dropna(subset=["Latitude","Longitude"]).iterrows() if not sales_df.empty else []:
        rows.append({
            "lat": r["Latitude"],
            "lon": r["Longitude"],
            "type": "Recent sale",
            "address": r.get("Address"),
            "zip": r.get("ZIP"),
            "price": r.get("Sold Price"),
            "price_label": "Sold price",
            "rent": None,
            "beds": r.get("Beds"),
            "baths": r.get("Baths"),
            "sqft": r.get("Sq Ft"),
            "year_built": None,
            "dom": None,
            "date": r.get("Sale Date"),
            "distance": r.get("Distance (mi)"),
            "detail": f"Recorded sale {r.get('Sale Date') or 'date unavailable'}",
        })

    for _, r in active_df.dropna(subset=["Latitude","Longitude"]).iterrows() if not active_df.empty else []:
        rows.append({
            "lat": r["Latitude"],
            "lon": r["Longitude"],
            "type": "Active listing",
            "address": r.get("Address"),
            "zip": r.get("ZIP"),
            "price": r.get("Ask Price"),
            "price_label": "Asking price",
            "rent": None,
            "beds": r.get("Beds"),
            "baths": r.get("Baths"),
            "sqft": r.get("Sq Ft"),
            "year_built": None,
            "dom": r.get("DOM"),
            "date": r.get("Listed"),
            "distance": r.get("Distance (mi)"),
            "detail": f"Listed {r.get('Listed') or 'date unavailable'}",
        })

    for _, r in comps_df.dropna(subset=["Latitude","Longitude"]).iterrows() if not comps_df.empty else []:
        rows.append({
            "lat": r["Latitude"],
            "lon": r["Longitude"],
            "type": "AVM comp",
            "address": r.get("Address"),
            "zip": r.get("ZIP"),
            "price": r.get("Price"),
            "price_label": "Comp price",
            "rent": None,
            "beds": r.get("Beds"),
            "baths": r.get("Baths"),
            "sqft": r.get("Sq Ft"),
            "year_built": None,
            "dom": r.get("DOM"),
            "date": r.get("Listed"),
            "distance": r.get("Distance (mi)"),
            "detail": f"{r.get('Distance (mi)'):.2f} mi away" if pd.notna(r.get("Distance (mi)")) else "Comparable property",
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out["price_text"] = out["price"].apply(lambda x: money(x) if pd.notna(x) and x not in (None, "") else "—")
        out["rent_text"] = out["rent"].apply(lambda x: money(x) + "/mo" if pd.notna(x) and x not in (None, "") else "—")
        out["dom_text"] = out["dom"].apply(lambda x: f"{int(x)} days" if pd.notna(x) else "—")
        out["distance_text"] = out["distance"].apply(lambda x: f"{float(x):.2f} mi" if pd.notna(x) else "—")
        out["beds_baths"] = out.apply(
            lambda r: f'{r["beds"] if pd.notna(r["beds"]) else "—"} bd · {r["baths"] if pd.notna(r["baths"]) else "—"} ba',
            axis=1,
        )
        out["sqft_text"] = out["sqft"].apply(lambda x: f"{int(x):,} sf" if pd.notna(x) else "—")
    return out


def render_neighborhood_map(map_df, subject_lat=None, subject_lon=None):
    if map_df.empty:
        st.info("No map coordinates were returned.")
        return None

    color_map = {
        "Subject property": [89, 99, 79, 255],
        "Recent sale": [61, 120, 184, 210],
        "Active listing": [214, 137, 63, 220],
        "AVM comp": [126, 92, 120, 190],
    }

    layer_ids = {
        "Subject property": "subject-property",
        "Recent sale": "recent-sales",
        "Active listing": "active-listings",
        "AVM comp": "avm-comps",
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
                id=layer_ids[category],
                data=layer_df,
                get_position="[lon, lat]",
                get_fill_color=rgba,
                get_line_color=[255,255,255,230],
                line_width_min_pixels=1,
                get_radius=radius,
                radius_min_pixels=8 if category == "Subject property" else 6,
                radius_max_pixels=18 if category == "Subject property" else 12,
                pickable=True,
                auto_highlight=True,
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
        controller=True,
    )

    tooltip = {
        "html": (
            "<b>{type}</b><br/>"
            "{address}<br/>"
            "<b>{price_label}:</b> {price_text}<br/>"
            "<b>ZIP:</b> {zip}<br/>"
            "<b>Home:</b> {beds_baths} · {sqft_text}<br/>"
            "<b>DOM:</b> {dom_text}<br/>"
            "<b>Distance:</b> {distance_text}<br/>"
            "{detail}<br/><br/>"
            "<b>Click this dot for full details below.</b>"
        ),
        "style": {"backgroundColor": "#252A24", "color": "white"},
    }

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip=tooltip,
    )

    st.markdown(
        """
        <div class="map-legend">
          <div class="map-legend-item"><span class="map-dot subject"></span><strong>Subject property</strong> — house being analyzed</div>
          <div class="map-legend-item"><span class="map-dot sale"></span><strong>Recent sale</strong> — recorded sold property</div>
          <div class="map-legend-item"><span class="map-dot active"></span><strong>Active listing</strong> — currently for sale</div>
          <div class="map-legend-item"><span class="map-dot comp"></span><strong>AVM comp</strong> — comparable used in valuation</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Click any property dot. A full detail card will open directly below the map.")
    event = st.pydeck_chart(
        deck,
        use_container_width=True,
        height=520,
        on_select="rerun",
        selection_mode="single-object",
        key="norvim_neighborhood_map",
    )

    selected = None
    try:
        objects = event.selection.get("objects", {})
        for layer_id in layer_ids.values():
            layer_objects = objects.get(layer_id, [])
            if layer_objects:
                selected = layer_objects[0]
                break
    except Exception:
        selected = None

    if selected:
        st.markdown("##### Selected property")
        st.markdown(
            f"**{selected.get('address') or 'Property'}**  \n"
            f"{selected.get('type') or 'Property'}"
            + (f" · ZIP {selected.get('zip')}" if selected.get("zip") else "")
        )

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            result_card(
                selected.get("price_label") or "Price",
                selected.get("price_text") or "—",
                selected.get("date") or selected.get("detail"),
            )
        with c2:
            result_card(
                "Beds / baths",
                selected.get("beds_baths") or "—",
                selected.get("sqft_text") or "—",
            )
        with c3:
            result_card(
                "Days on market",
                selected.get("dom_text") or "—",
                f'Distance {selected.get("distance_text") or "—"}',
            )
        with c4:
            if selected.get("type") == "Subject property":
                result_card(
                    "Estimated rent",
                    selected.get("rent_text") or "—",
                    f'Built {selected.get("year_built")}' if selected.get("year_built") else "Subject property",
                )
            else:
                ppsf = None
                try:
                    if selected.get("price") and selected.get("sqft"):
                        ppsf = float(selected["price"]) / float(selected["sqft"])
                except Exception:
                    pass
                result_card(
                    "$ / Sq Ft",
                    f'${ppsf:,.0f}' if ppsf else "—",
                    selected.get("detail"),
                )

        if selected.get("type") == "Subject property":
            st.info(
                "This is the house you are analyzing. Use the BRRRR Deal Coach, Property Record, "
                "Listing, Sales Comps, and Area Market tabs for the full investment analysis."
            )
        elif selected.get("type") == "Recent sale":
            st.success(
                "This is a nearby recorded sale. Compare its size, condition, sale date, distance, "
                "and ZIP with the subject before treating it as a strong comp."
            )
        elif selected.get("type") == "Active listing":
            st.info(
                "This is active competition, not a closed sale. It helps show current asking prices "
                "and market time, but an asking price is not the same as a verified sold price."
            )
        elif selected.get("type") == "AVM comp":
            st.info(
                "This is one of the AVM comparable properties returned by RentCast. Review its ZIP, "
                "distance, similarity, condition, and sale/listing status before relying on it."
            )
    else:
        st.info("Select a dot on the map to see that property's details here.")

    st.caption(
        "Map legend: subject property · recent recorded sales · active listings · AVM comparable properties."
    )
    return selected


def offer_math(strategy, arv, rent, rehab, closing, selling, holding, contingency, target_profit, assignment, refi_ltv, vacancy, opex, cap):
    arv, rent, rehab = max(float(arv or 0),0), max(float(rent or 0),0), max(float(rehab or 0),0)
    close_rate = max(float(closing or 0), 0) / 100
    sell_d = arv * max(float(selling or 0), 0) / 100
    cont_d = rehab * max(float(contingency or 0), 0) / 100

    # Closing costs are modeled as a percentage of the purchase price, so solve for purchase.
    flip_numerator = arv - rehab - sell_d - holding - cont_d - target_profit
    flip = max(0, flip_numerator / (1 + close_rate))
    if strategy == "Flip":
        return flip, "Maximum purchase price", "Solves for purchase price after rehab, selling costs, holding, contingency, target profit and purchase-based closing costs."
    if strategy == "Wholesale":
        return max(0, flip-assignment), "Maximum contract price", f"Leaves about {money(assignment)} for your assignment fee before the end buyer reaches the modeled flip ceiling."
    if strategy == "BRRRR":
        numerator = arv * refi_ltv / 100 - rehab - holding - cont_d
        ceiling = max(0, numerator / (1 + close_rate))
        return ceiling, "Max purchase for modeled refinance", f"Uses a {refi_ltv:.0f}% ARV refinance assumption and purchase-based acquisition closing costs."
    noi = rent*12*(1-vacancy/100)*(1-opex/100)
    value = noi/(cap/100) if cap else 0
    numerator = value - rehab - holding - cont_d
    return max(0, numerator / (1 + close_rate)), "Maximum purchase price", f"Uses a {cap:.1f}% target cap rate and modeled NOI of {money(noi)}."



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


def flip_scenario(purchase, arv, rehab, closing_pct, selling_pct, holding, contingency_pct):
    purchase = max(float(purchase or 0), 0)
    arv = max(float(arv or 0), 0)
    rehab = max(float(rehab or 0), 0)
    acquisition = purchase * float(closing_pct or 0) / 100
    selling_cost = arv * float(selling_pct or 0) / 100
    contingency = rehab * float(contingency_pct or 0) / 100
    total_cost = purchase + acquisition + rehab + selling_cost + float(holding or 0) + contingency
    profit = arv - total_cost
    invested_basis = purchase + acquisition + rehab + float(holding or 0) + contingency
    roi = profit / invested_basis if invested_basis else None
    margin = profit / arv if arv else None
    return {
        "profit": profit,
        "roi": roi,
        "margin": margin,
        "total_cost": total_cost,
        "acquisition_closing": acquisition,
        "selling_cost": selling_cost,
        "contingency": contingency,
    }


def rental_buy_hold_model(
    purchase, rent, rehab, closing_pct, down_payment_pct, rate_pct, term_years,
    annual_taxes, annual_insurance, monthly_hoa,
    vacancy_pct, management_pct, maintenance_pct, capex_pct, monthly_other=0
):
    purchase = max(float(purchase or 0), 0)
    rent = max(float(rent or 0), 0)
    rehab = max(float(rehab or 0), 0)
    down = purchase * float(down_payment_pct or 0) / 100
    loan = max(purchase - down, 0)
    acquisition = purchase * float(closing_pct or 0) / 100
    cash_in = down + acquisition + rehab
    payment = monthly_pi_payment(loan, rate_pct, term_years)

    vacancy = rent * float(vacancy_pct or 0) / 100
    management = rent * float(management_pct or 0) / 100
    maintenance = rent * float(maintenance_pct or 0) / 100
    capex = rent * float(capex_pct or 0) / 100
    taxes = float(annual_taxes or 0) / 12
    insurance = float(annual_insurance or 0) / 12
    hoa = float(monthly_hoa or 0)
    other = float(monthly_other or 0)

    noi_monthly = rent - vacancy - management - maintenance - capex - taxes - insurance - hoa - other
    cash_flow = noi_monthly - payment
    total_basis = purchase + acquisition + rehab
    dscr = noi_monthly / payment if payment else None
    cap_rate = (noi_monthly * 12 / total_basis) if total_basis else None
    cash_on_cash = (cash_flow * 12 / cash_in) if cash_in else None
    return {
        "loan": loan,
        "down_payment": down,
        "cash_in": cash_in,
        "payment": payment,
        "noi_monthly": noi_monthly,
        "cash_flow": cash_flow,
        "annual_cash_flow": cash_flow * 12,
        "dscr": dscr,
        "cap_rate": cap_rate,
        "cash_on_cash": cash_on_cash,
        "total_basis": total_basis,
    }


def strategy_match(
    purchase_price, arv, rent, rehab, closing, selling, holding, contingency,
    flip_target_profit, flip_min_roi,
    wholesale_fee_target,
    refi_ltv, refi_rate, refi_term, refi_closing,
    annual_taxes, annual_insurance, monthly_hoa,
    vacancy, management, maintenance, capex_reserve,
    brrrr_min_cf, brrrr_max_cash_left, min_dscr,
    rental_down, rental_rate, rental_term, rental_min_cf, rental_target_cap,
):
    flip = flip_scenario(purchase_price, arv, rehab, closing, selling, holding, contingency)
    flip_pass = flip["profit"] >= flip_target_profit and (flip["roi"] or -999) >= flip_min_roi / 100
    flip_checks = [
        flip["profit"] >= flip_target_profit,
        (flip["roi"] or -999) >= flip_min_roi / 100,
        flip["profit"] > 0,
    ]

    flip_ceiling, _, _ = offer_math(
        "Flip", arv, rent, rehab, closing, selling, holding, contingency,
        flip_target_profit, wholesale_fee_target, refi_ltv, vacancy, 35, rental_target_cap
    )
    wholesale_spread = max(flip_ceiling - float(purchase_price or 0), 0)
    wholesale_pass = wholesale_spread >= wholesale_fee_target
    wholesale_checks = [
        wholesale_spread >= wholesale_fee_target,
        purchase_price <= flip_ceiling,
    ]

    brrrr = brrrr_model(
        purchase_price, arv, rent, rehab, closing, holding, contingency,
        refi_ltv, refi_rate, refi_term, refi_closing,
        annual_taxes, annual_insurance, monthly_hoa,
        vacancy, management, maintenance, capex_reserve, 0
    )
    brrrr_checks = [
        brrrr["monthly_cash_flow"] >= brrrr_min_cf,
        brrrr["cash_left"] <= brrrr_max_cash_left,
        brrrr.get("dscr") is not None and brrrr["dscr"] >= min_dscr,
        brrrr["equity_created_vs_cost"] > 0,
    ]
    brrrr_pass = all(brrrr_checks)

    rental = rental_buy_hold_model(
        purchase_price, rent, rehab, closing, rental_down, rental_rate, rental_term,
        annual_taxes, annual_insurance, monthly_hoa,
        vacancy, management, maintenance, capex_reserve, 0
    )
    rental_checks = [
        rental["cash_flow"] >= rental_min_cf,
        rental.get("dscr") is not None and rental["dscr"] >= min_dscr,
        rental.get("cap_rate") is not None and rental["cap_rate"] >= rental_target_cap / 100,
    ]
    rental_pass = all(rental_checks)

    def status(checks, passed):
        count = sum(bool(x) for x in checks)
        if passed:
            return "Meets targets", "good", count
        if count >= max(1, len(checks) - 1):
            return "Close / review", "warn", count
        return "Doesn't meet targets", "bad", count

    fs, fk, fscore = status(flip_checks, flip_pass)
    ws, wk, wscore = status(wholesale_checks, wholesale_pass)
    bs, bk, bscore = status(brrrr_checks, brrrr_pass)
    rs, rk, rscore = status(rental_checks, rental_pass)

    rows = [
        {
            "strategy": "Flip", "status": fs, "kind": fk, "score": fscore, "max_score": len(flip_checks),
            "primary": flip["profit"], "primary_label": "Projected net profit",
            "secondary": flip["roi"], "secondary_label": "ROI",
            "max_purchase": flip_ceiling,
            "details": flip,
        },
        {
            "strategy": "Wholesale", "status": ws, "kind": wk, "score": wscore, "max_score": len(wholesale_checks),
            "primary": wholesale_spread, "primary_label": "Available spread",
            "secondary": None, "secondary_label": "",
            "max_purchase": max(flip_ceiling - wholesale_fee_target, 0),
            "details": {"spread": wholesale_spread, "end_buyer_max": flip_ceiling},
        },
        {
            "strategy": "BRRRR", "status": bs, "kind": bk, "score": bscore, "max_score": len(brrrr_checks),
            "primary": brrrr["monthly_cash_flow"], "primary_label": "Monthly cash flow",
            "secondary": brrrr["equity_after_refi"], "secondary_label": "Equity after refi",
            "max_purchase": offer_math("BRRRR", arv, rent, rehab, closing, selling, holding, contingency, flip_target_profit, wholesale_fee_target, refi_ltv, vacancy, 35, rental_target_cap)[0],
            "details": brrrr,
        },
        {
            "strategy": "Rental", "status": rs, "kind": rk, "score": rscore, "max_score": len(rental_checks),
            "primary": rental["cash_flow"], "primary_label": "Monthly cash flow",
            "secondary": rental["cap_rate"], "secondary_label": "Cap rate",
            "max_purchase": offer_math("Rental", arv, rent, rehab, closing, selling, holding, contingency, flip_target_profit, wholesale_fee_target, refi_ltv, vacancy, 35, rental_target_cap)[0],
            "details": rental,
        },
    ]
    # Rank by comparable, strategy-specific threshold strength rather than raw dollars.
    # This prevents a $40k flip profit from being mechanically compared with $400/mo BRRRR cash flow.
    for row in rows:
        row["fit_ratio"] = row["score"] / row["max_score"] if row["max_score"] else 0
        row["passed"] = row["status"] == "Meets targets"
        d = row["details"]
        if row["strategy"] == "Flip":
            profit_strength = max(d.get("profit", 0), 0) / max(float(flip_target_profit or 1), 1)
            roi_strength = max(d.get("roi") or 0, 0) / max(float(flip_min_roi or 1) / 100, 0.0001)
            row["strength"] = (min(profit_strength, 2.0) + min(roi_strength, 2.0)) / 2
        elif row["strategy"] == "Wholesale":
            row["strength"] = min(max(d.get("spread", 0), 0) / max(float(wholesale_fee_target or 1), 1), 2.0)
        elif row["strategy"] == "BRRRR":
            cf_strength = max(d.get("monthly_cash_flow", 0), 0) / max(float(brrrr_min_cf or 1), 1)
            dscr_strength = max(d.get("dscr") or 0, 0) / max(float(min_dscr or 1), 0.01)
            cash_left_strength = 2.0 if d.get("cash_left", 0) <= 0 else min(float(brrrr_max_cash_left or 1) / max(d.get("cash_left", 1), 1), 2.0)
            equity_strength = 1.5 if d.get("equity_created_vs_cost", 0) > 0 else 0
            row["strength"] = (min(cf_strength, 2.0) + min(dscr_strength, 2.0) + cash_left_strength + equity_strength) / 4
        else:
            cf_strength = max(d.get("cash_flow", 0), 0) / max(float(rental_min_cf or 1), 1)
            dscr_strength = max(d.get("dscr") or 0, 0) / max(float(min_dscr or 1), 0.01)
            cap_strength = max(d.get("cap_rate") or 0, 0) / max(float(rental_target_cap or 1) / 100, 0.0001)
            row["strength"] = (min(cf_strength, 2.0) + min(dscr_strength, 2.0) + min(cap_strength, 2.0)) / 3
    rows = sorted(rows, key=lambda r: (r["passed"], r["fit_ratio"], r.get("strength", 0)), reverse=True)
    return rows


def strategy_row_by_name(results, name):
    for r in results or []:
        if r.get("strategy") == name:
            return r
    return None


def strategy_explanation(row):
    if not row:
        return ""
    s = row["strategy"]
    d = row["details"]
    if s == "Flip":
        return f"{money(d.get('profit'))} projected net profit · {d.get('roi')*100:.1f}% ROI" if d.get("roi") is not None else f"{money(d.get('profit'))} projected net profit"
    if s == "Wholesale":
        return f"{money(d.get('spread'))} modeled spread before your assignment fee target."
    if s == "BRRRR":
        dscr = d.get("dscr")
        return f"{money(d.get('monthly_cash_flow'))}/mo cash flow · {money(d.get('cash_left'))} cash left · {money(d.get('equity_after_refi'))} equity" + (f" · {dscr:.2f}x rent cushion" if dscr is not None else "")
    if s == "Rental":
        dscr = d.get("dscr")
        return f"{money(d.get('cash_flow'))}/mo cash flow" + (f" · {d.get('cap_rate')*100:.2f}% cap rate" if d.get("cap_rate") is not None else "") + (f" · {dscr:.2f}x rent cushion" if dscr is not None else "")
    return ""


def render_strategy_card(row):
    if not row:
        return
    st.markdown(
        f'<div class="strategy-card {row["kind"]}">'
        f'<div class="strategy-name">{row["strategy"]}</div>'
        f'<div class="strategy-status">{row["status"]}</div>'
        f'<div class="strategy-copy">{strategy_explanation(row)}<br><br>'
        f'<strong>Modeled max purchase:</strong> {money(row.get("max_purchase"))}</div>'
        f'</div>',
        unsafe_allow_html=True
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

st.markdown('<div class="k">NORVIM 13 LLC</div><div class="t">DealFinder 2.2</div><div class="s">2-call Quick Scan → strategy match → optional deep research → pipeline.</div>', unsafe_allow_html=True)


app_access_code = str(get_setting("APP_ACCESS_CODE", "") or "").strip()
if app_access_code:
    if st.session_state.get("norvim_access_ok") is not True:
        st.subheader("NORVIM DealFinder")
        access_try = st.text_input("Access code", type="password")
        if st.button("Enter", type="primary"):
            if access_try == app_access_code:
                st.session_state["norvim_access_ok"] = True
                st.rerun()
            else:
                st.error("Incorrect access code.")
        st.stop()

with st.sidebar:
    st.subheader("Property data")
    key = get_key()
    if not key:
        entered = st.text_input("RentCast API key", type="password", help="For testing. Use Streamlit Secrets on the live site.")
        if entered:
            st.session_state["rentcast_api_key"] = entered
            key = entered
    else:
        st.success("Property-data API connected")

    monthly_limit = int(float(get_setting("RENTCAST_MONTHLY_LIMIT", 50) or 50))
    tracked_usage = db_monthly_api_usage()
    remaining = max(monthly_limit - tracked_usage, 0)
    st.markdown(f"**Estimated RentCast remaining:** {remaining} / {monthly_limit}")
    st.progress(min(max(tracked_usage / monthly_limit if monthly_limit else 0, 0), 1))
    if remaining >= 2:
        st.caption(f"At 2 calls per uncached Quick Scan, that is roughly {remaining // 2} new-property scans before optional deep research.")
    if db_enabled():
        st.caption("Usage counter is stored in the NORVIM database. It tracks successful requests made by this app plus any configured starting offset.")
    else:
        st.caption("Usage counter is session-only until Supabase is connected. Set RENTCAST_USAGE_OFFSET if you already used requests this month.")
    st.link_button("Open RentCast dashboard", "https://app.rentcast.io/app/api", use_container_width=True)
    st.caption("Quick Scan uses 2 successful RentCast requests on a new property and 0 when the NORVIM cache is fresh. Property record, listing, ZIP market and neighborhood data load only when you request them.")

    st.divider()
    if db_enabled():
        st.success("NORVIM database connected")
        st.caption("Permanent property snapshots, API usage and CRM pipeline are enabled.")
    else:
        st.info("Database not connected")
        st.caption("The app still works. Add Supabase later for permanent caching, CRM history and scaling.")

# Strategy-specific widgets use stable keys, so Streamlit preserves values when you switch strategies.
# Hidden strategies fall back to conservative defaults until you select and edit them.
st.markdown("### Deal setup")
st.caption("Choose the strategy you are evaluating. DealFinder keeps the setup at the top and only shows the assumptions that matter most for that strategy. Dollar inputs use thousands separators.")
with st.container(border=True):
    top1, top2, top3 = st.columns([1.0, 1.25, 1.25])
    with top1:
        strategy = st.selectbox(
            "Strategy",
            ["Flip", "Wholesale", "BRRRR", "Rental"],
            key="setup_strategy",
        )
    with top2:
        purchase_override = money_input(
            "Seller ask / purchase price ($)",
            0,
            key="setup_purchase",
            help="Enter the price you are evaluating. Leave 0 to use the active listing price when available; otherwise DealFinder uses the modeled ceiling.",
        )
    with top3:
        rehab = money_input("Rehab budget ($)", 40000, key="setup_rehab")

    core1, core2, core3 = st.columns(3)
    with core1:
        closing = st.number_input(
            "Acquisition closing costs (% of purchase)",
            0.0, 20.0, 2.0, 0.5,
            key="setup_closing",
        )
    with core2:
        holding = money_input("Holding + pre-exit financing ($)", 12000, key="setup_holding")
    with core3:
        contingency = st.number_input(
            "Rehab contingency (%)",
            0.0, 50.0, 10.0, 1.0,
            key="setup_contingency",
        )

    st.markdown(f"##### {strategy} assumptions")

    if strategy == "Flip":
        s1, s2, s3 = st.columns(3)
        with s1:
            selling = st.number_input("Selling costs (% of ARV)", 0.0, 20.0, state_number("setup_selling", 8.0), 0.5, key="setup_selling")
        with s2:
            target_profit = money_input("Target net profit ($)", 35000, key="setup_target_profit_money")
            st.session_state["setup_target_profit"] = target_profit
        with s3:
            flip_min_roi = st.number_input("Minimum flip ROI (%)", 0.0, 100.0, state_number("setup_flip_min_roi", 15.0), 1.0, key="setup_flip_min_roi")

    elif strategy == "Wholesale":
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            selling = st.number_input("End-buyer selling costs (% ARV)", 0.0, 20.0, state_number("setup_selling", 8.0), 0.5, key="setup_selling")
        with s2:
            target_profit = money_input("End-buyer target profit ($)", 35000, key="setup_target_profit_money")
            st.session_state["setup_target_profit"] = target_profit
        with s3:
            assignment = money_input("Your assignment target ($)", 10000, key="setup_assignment_money")
            st.session_state["setup_assignment"] = assignment
        with s4:
            flip_min_roi = st.number_input("End-buyer minimum ROI (%)", 0.0, 100.0, state_number("setup_flip_min_roi", 15.0), 1.0, key="setup_flip_min_roi")

    elif strategy == "BRRRR":
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            refi_ltv = st.number_input("Refi LTV (% of ARV)", 1.0, 100.0, state_number("setup_refi_ltv", 75.0), 1.0, key="setup_refi_ltv")
        with s2:
            refi_rate_match = st.number_input("Refi rate (%)", 0.0, 25.0, state_number("setup_refi_rate", 7.5), 0.25, key="setup_refi_rate")
        with s3:
            refi_term_match = st.number_input("Refi term (years)", 1, 40, state_int("setup_refi_term", 30), 1, key="setup_refi_term")
        with s4:
            refi_closing_match = st.number_input("Refi closing costs (%)", 0.0, 10.0, state_number("setup_refi_closing", 2.0), 0.25, key="setup_refi_closing")

        s5, s6, s7 = st.columns(3)
        with s5:
            brrrr_min_cf = money_input("Minimum monthly cash flow ($)", 250, key="setup_brrrr_min_cf_money")
            st.session_state["setup_brrrr_min_cf"] = brrrr_min_cf
        with s6:
            brrrr_max_cash_left = money_input("Maximum cash left after refi ($)", 25000, key="setup_brrrr_max_cash_left_money")
            st.session_state["setup_brrrr_max_cash_left"] = brrrr_max_cash_left
        with s7:
            min_dscr_global = st.number_input("Minimum DSCR", 0.0, 5.0, state_number("setup_min_dscr", 1.20), 0.05, key="setup_min_dscr")

        with st.expander("BRRRR operating assumptions", expanded=False):
            o1, o2, o3 = st.columns(3)
            with o1:
                taxes_override_match = money_input("Annual property taxes override ($)", 0, key="setup_taxes_money", help="Leave 0 to use loaded property-tax data when available.")
                st.session_state["setup_taxes_override"] = taxes_override_match
            with o2:
                insurance_match = money_input("Annual insurance estimate ($)", 3000, key="setup_insurance_money")
                st.session_state["setup_insurance"] = insurance_match
            with o3:
                vacancy = st.number_input("Vacancy allowance (%)", 0.0, 50.0, state_number("setup_vacancy", 5.0), 1.0, key="setup_vacancy")
            o4, o5, o6 = st.columns(3)
            with o4:
                management_match = st.number_input("Property management reserve (%)", 0.0, 30.0, state_number("setup_management", 8.0), 1.0, key="setup_management")
            with o5:
                maintenance_match = st.number_input("Maintenance reserve (%)", 0.0, 30.0, state_number("setup_maintenance", 5.0), 1.0, key="setup_maintenance")
            with o6:
                capex_match = st.number_input("CapEx reserve (%)", 0.0, 30.0, state_number("setup_capex", 5.0), 1.0, key="setup_capex")

    else:  # Rental
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            rental_down = st.number_input("Down payment (%)", 0.0, 100.0, state_number("setup_rental_down", 20.0), 1.0, key="setup_rental_down")
        with s2:
            rental_rate = st.number_input("Loan rate (%)", 0.0, 25.0, state_number("setup_rental_rate", 7.5), 0.25, key="setup_rental_rate")
        with s3:
            rental_term = st.number_input("Loan term (years)", 1, 40, state_int("setup_rental_term", 30), 1, key="setup_rental_term")
        with s4:
            cap = st.number_input("Target cap rate (%)", 0.1, 30.0, state_number("setup_cap", 6.0), 0.25, key="setup_cap")

        s5, s6 = st.columns(2)
        with s5:
            rental_min_cf = money_input("Minimum monthly cash flow ($)", 250, key="setup_rental_min_cf_money")
            st.session_state["setup_rental_min_cf"] = rental_min_cf
        with s6:
            min_dscr_global = st.number_input("Minimum DSCR", 0.0, 5.0, state_number("setup_min_dscr", 1.20), 0.05, key="setup_min_dscr")

        with st.expander("Rental operating assumptions", expanded=False):
            o1, o2, o3 = st.columns(3)
            with o1:
                taxes_override_match = money_input("Annual property taxes override ($)", 0, key="setup_taxes_money", help="Leave 0 to use loaded property-tax data when available.")
                st.session_state["setup_taxes_override"] = taxes_override_match
            with o2:
                insurance_match = money_input("Annual insurance estimate ($)", 3000, key="setup_insurance_money")
                st.session_state["setup_insurance"] = insurance_match
            with o3:
                vacancy = st.number_input("Vacancy allowance (%)", 0.0, 50.0, state_number("setup_vacancy", 5.0), 1.0, key="setup_vacancy")
            o4, o5, o6 = st.columns(3)
            with o4:
                management_match = st.number_input("Property management reserve (%)", 0.0, 30.0, state_number("setup_management", 8.0), 1.0, key="setup_management")
            with o5:
                maintenance_match = st.number_input("Maintenance reserve (%)", 0.0, 30.0, state_number("setup_maintenance", 5.0), 1.0, key="setup_maintenance")
            with o6:
                capex_match = st.number_input("CapEx reserve (%)", 0.0, 30.0, state_number("setup_capex", 5.0), 1.0, key="setup_capex")
            o7, _ = st.columns([1, 2])
            with o7:
                opex = st.number_input("Legacy operating expense (%)", 0.0, 90.0, state_number("setup_opex", 35.0), 1.0, key="setup_opex")

# Pull assumptions for strategies that are currently hidden. This lets Strategy Match
# continue comparing all four strategies while keeping the screen uncluttered.
selling = state_number("setup_selling", 8.0)
target_profit = parse_money_input(st.session_state.get("setup_target_profit_money", st.session_state.get("setup_target_profit", 35000)), 35000)
flip_min_roi = state_number("setup_flip_min_roi", 15.0)
assignment = parse_money_input(st.session_state.get("setup_assignment_money", st.session_state.get("setup_assignment", 10000)), 10000)
refi_ltv = state_number("setup_refi_ltv", 75.0)
refi_rate_match = state_number("setup_refi_rate", 7.5)
refi_term_match = state_int("setup_refi_term", 30)
refi_closing_match = state_number("setup_refi_closing", 2.0)
brrrr_min_cf = parse_money_input(st.session_state.get("setup_brrrr_min_cf_money", st.session_state.get("setup_brrrr_min_cf", 250)), 250)
brrrr_max_cash_left = parse_money_input(st.session_state.get("setup_brrrr_max_cash_left_money", st.session_state.get("setup_brrrr_max_cash_left", 25000)), 25000)
min_dscr_global = state_number("setup_min_dscr", 1.20)
rental_down = state_number("setup_rental_down", 20.0)
rental_rate = state_number("setup_rental_rate", 7.5)
rental_term = state_int("setup_rental_term", 30)
rental_min_cf = parse_money_input(st.session_state.get("setup_rental_min_cf_money", st.session_state.get("setup_rental_min_cf", 250)), 250)
cap = state_number("setup_cap", 6.0)
vacancy = state_number("setup_vacancy", 5.0)
management_match = state_number("setup_management", 8.0)
maintenance_match = state_number("setup_maintenance", 5.0)
capex_match = state_number("setup_capex", 5.0)
insurance_match = parse_money_input(st.session_state.get("setup_insurance_money", st.session_state.get("setup_insurance", 3000)), 3000)
taxes_override_match = parse_money_input(st.session_state.get("setup_taxes_money", st.session_state.get("setup_taxes_override", 0)), 0)
opex = state_number("setup_opex", 35.0)

with st.form("address_form"):
    address = st.text_input("Property address", placeholder="1234 Example St, Houston, TX 77021")
    submitted = st.form_submit_button("Run deal analysis", type="primary", use_container_width=True)

if submitted:
    if not address.strip(): st.error("Enter a property address first.")
    elif not key: st.error("Add a RentCast API key in the sidebar or Streamlit Secrets.")
    else:
        with st.spinner("Quick Scan: checking NORVIM cache first, then ARV + rent only if needed..."):
            try:
                address_clean = address.strip()
                address_key = normalize_address(address_clean)
                db_snapshot = db_get_cached_snapshot(address_key, max_age_days=None) or {}
                quick_fresh = (
                    bool(db_snapshot.get("valuation"))
                    and bool(db_snapshot.get("rent"))
                    and snapshot_field_fresh(db_snapshot, "quick_fetched_at", 30, fallback_to_time=True)
                )

                if quick_fresh:
                    st.session_state["analysis"] = {
                        "input": address_clean,
                        "address_key": address_key,
                        "valuation": db_snapshot.get("valuation") or {},
                        "rent": db_snapshot.get("rent") or {},
                        "market": db_snapshot.get("market") or {},
                        "property_record": db_snapshot.get("property_record") or {},
                        "listing_record": db_snapshot.get("listing_record") or {},
                        "quick_fetched_at": db_snapshot.get("quick_fetched_at") or db_snapshot.get("time"),
                        "market_fetched_at": db_snapshot.get("market_fetched_at"),
                        "property_record_fetched_at": db_snapshot.get("property_record_fetched_at"),
                        "listing_record_fetched_at": db_snapshot.get("listing_record_fetched_at"),
                        "time": db_snapshot.get("time") or utc_now_iso(),
                        "cache_source": "NORVIM database · 0 RentCast calls",
                    }
                else:
                    val, rent_data, fetched_at = quick_scan_cached(address_key, key, address_clean)
                    fresh_snapshot = dict(db_snapshot)
                    fresh_snapshot.pop("_db_cache_age_days", None)
                    fresh_snapshot.update({
                        "valuation": val,
                        "rent": rent_data,
                        "quick_fetched_at": fetched_at,
                        "time": fetched_at,
                    })
                    st.session_state["analysis"] = {
                        "input": address_clean,
                        "address_key": address_key,
                        "valuation": val,
                        "rent": rent_data,
                        "market": fresh_snapshot.get("market") or {},
                        "property_record": fresh_snapshot.get("property_record") or {},
                        "listing_record": fresh_snapshot.get("listing_record") or {},
                        "quick_fetched_at": fetched_at,
                        "market_fetched_at": fresh_snapshot.get("market_fetched_at"),
                        "property_record_fetched_at": fresh_snapshot.get("property_record_fetched_at"),
                        "listing_record_fetched_at": fresh_snapshot.get("listing_record_fetched_at"),
                        "time": fetched_at,
                        "cache_source": "Quick Scan · ARV + rent only",
                    }
                    db_save_snapshot(address_key, address_clean, fresh_snapshot)
            except Exception as e:
                st.error(str(e))

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
st.info(f'Quick Scan snapshot: {A.get("quick_fetched_at") or A["time"]} · source: {A.get("cache_source","cache")}. New addresses use ARV + rent only (2 RentCast endpoints); fresh NORVIM-cached addresses use 0.')
st.warning("Underwriting estimate only. Verify title, condition, flood risk, taxes, liens, repair scope and local comps before contracting.")

tabs=st.tabs(["DealFinder","Property record","Listing","Deal","BRRRR","Sales comps","Neighborhood map","Area market","Rental","Export","Strategy Match","Offer Lab","Neighborhood Intel","CRM"])

# Precompute reusable tables from Quick Scan. ZIP market data is optional and loaded separately.
cdf_all=comp_df(val.get("comparables") or [])
rdf=rental_comp_df(rent_data.get("comparables") or [])
zip_code=str(subj.get("zipCode") or market.get("zipCode") or "—")

# Reuse one permanent ZIP-market snapshot across every property in that ZIP.
market_fresh = bool(market) and snapshot_field_fresh(A, "market_fetched_at", 30, value_key="market", fallback_to_time=True)
if not market_fresh:
    market = {}
    if db_enabled() and zip_code != "—":
        zip_snapshot = db_get_cached_snapshot(f"zip::{zip_code}", max_age_days=30) or {}
        if zip_snapshot.get("market"):
            market = zip_snapshot.get("market") or {}
            A["market"] = market
            A["market_fetched_at"] = zip_snapshot.get("market_fetched_at") or zip_snapshot.get("time")
            st.session_state["analysis"] = A
sd=market.get("saleData") or {}
rd=market.get("rentalData") or {}

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

latest_tax_match, latest_tax_year_match = latest_property_tax(property_record)
effective_tax_match = float(taxes_override_match or latest_tax_match or 0)
hoa_match = float(((property_record.get("hoa") or {}).get("fee")) or 0)
listing_price_match = listing_record.get("price")
if purchase_override and purchase_override > 0:
    purchase_scenario = float(purchase_override)
elif listing_price_match not in (None, 0):
    purchase_scenario = float(listing_price_match)
else:
    purchase_scenario = float(ceiling or 0)

strategy_results = strategy_match(
    purchase_scenario, arv, rent_m, rehab, closing, selling, holding, contingency,
    target_profit, flip_min_roi,
    assignment,
    refi_ltv, refi_rate_match, refi_term_match, refi_closing_match,
    effective_tax_match, insurance_match, hoa_match,
    vacancy, management_match, maintenance_match, capex_match,
    brrrr_min_cf, brrrr_max_cash_left, min_dscr_global,
    rental_down, rental_rate, rental_term, rental_min_cf, cap,
)
preferred_result = strategy_row_by_name(strategy_results, strategy)
best_result = strategy_results[0] if strategy_results else None

strategy_results_json = []
for item in strategy_results:
    clean = {k:v for k,v in item.items() if k != "details"}
    clean["details"] = item.get("details") or {}
    strategy_results_json.append(clean)

with tabs[0]:
    st.markdown("#### DealFinder decision support")
    if preferred_result and preferred_result.get("status") == "Meets targets":
        decision_title = f"Your {strategy} plan meets the targets you entered"
        decision_copy = strategy_explanation(preferred_result)
    elif best_result and best_result.get("status") == "Meets targets":
        decision_title = f"{strategy} does not meet all targets at {money(purchase_scenario)}"
        decision_copy = (
            f"The strongest modeled alternative is {best_result['strategy']}, which currently meets your configured thresholds. "
            f"{strategy_explanation(best_result)}"
        )
    elif best_result:
        decision_title = f"No strategy fully meets your targets at {money(purchase_scenario)}"
        decision_copy = (
            f"{best_result['strategy']} is currently the closest modeled fit, but it still needs review. "
            f"{strategy_explanation(best_result)}"
        )
    else:
        decision_title = "Strategy analysis unavailable"
        decision_copy = "Review the assumptions and property data."

    st.markdown(
        f'<div class="big-decision"><div class="title">{decision_title}</div>'
        f'<div class="copy">{decision_copy}</div></div>',
        unsafe_allow_html=True,
    )

    d1,d2,d3,d4=st.columns(4)
    with d1: result_card("Purchase scenario", money(purchase_scenario), "Seller ask / target price being tested")
    with d2: result_card("Preferred strategy", strategy, preferred_result.get("status") if preferred_result else "—")
    with d3: result_card("Strongest modeled fit", best_result.get("strategy") if best_result else "—", best_result.get("status") if best_result else "—")
    with d4: result_card("Same-ZIP comps", len(cdf_same_zip), f"ZIP {zip_code}")

    st.caption("DealFinder compares Flip, Wholesale, BRRRR and Rental every time. Quick Scan uses ARV + rent only; optional records are loaded only when you request them. A result means the strategy meets or misses your configured thresholds; it is not a guarantee to buy or avoid the property.")
    if effective_tax_match <= 0:
        st.warning("Quick Scan currently has no annual property-tax amount. BRRRR/Rental cash flow may look stronger than reality. Enter a tax override in the Deal setup above or load the Property record.")
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
    property_profile_fresh = bool(property_record) and snapshot_field_fresh(
        A, "property_record_fetched_at", 180, value_key="property_record", fallback_to_time=True
    )
    if property_record:
        st.caption("Optional deep data. This profile is reused for up to 180 days and is not required for Quick Scan.")
        if st.button("Refresh property record (up to 1 RentCast call)", key="refresh_property_record"):
            with st.spinner("Loading property record..."):
                try:
                    rec, rec_time = property_record_cached(A["address_key"], key, A["input"])
                    A["property_record"] = rec or {}
                    A["property_record_fetched_at"] = rec_time
                    A["time"] = utc_now_iso()
                    st.session_state["analysis"] = A
                    db_merge_save_snapshot(A["address_key"], A["input"], {
                        "property_record": rec or {},
                        "property_record_fetched_at": rec_time,
                    })
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    else:
        st.info("Quick Scan intentionally skipped the full public-record profile to save an API request.")
        if st.button("Load full property record (up to 1 RentCast call)", type="primary", key="load_property_record"):
            with st.spinner("Loading property record..."):
                try:
                    rec, rec_time = property_record_cached(A["address_key"], key, A["input"])
                    A["property_record"] = rec or {}
                    A["property_record_fetched_at"] = rec_time
                    A["time"] = utc_now_iso()
                    st.session_state["analysis"] = A
                    db_merge_save_snapshot(A["address_key"], A["input"], {
                        "property_record": rec or {},
                        "property_record_fetched_at": rec_time,
                    })
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    property_record = A.get("property_record") or {}
    if not property_record:
        st.caption("No property record loaded yet, or the provider did not return one.")
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
    listing_record = A.get("listing_record") or {}
    listing_checked = bool(A.get("listing_record_fetched_at")) or bool(listing_record)
    property_id_for_listing = (A.get("property_record") or {}).get("id") or (val.get("subjectProperty") or {}).get("id")

    if not listing_checked:
        st.info("Quick Scan intentionally skipped the exact listing lookup to save an API request.")
        if property_id_for_listing:
            if st.button("Load exact listing record (up to 1 RentCast call)", type="primary", key="load_listing_record"):
                with st.spinner("Checking exact listing record..."):
                    try:
                        rec, rec_time = listing_record_cached(A["address_key"], key, property_id_for_listing)
                        A["listing_record"] = rec or {}
                        A["listing_record_fetched_at"] = rec_time
                        A["time"] = utc_now_iso()
                        st.session_state["analysis"] = A
                        db_merge_save_snapshot(A["address_key"], A["input"], {
                            "listing_record": rec or {},
                            "listing_record_fetched_at": rec_time,
                        })
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        else:
            st.caption("Load the Property record first so DealFinder can obtain the provider property ID for an exact listing lookup.")
    else:
        st.caption("Optional listing data is cached for 7 days. A 404/no listing does not count as a successful RentCast request in the app meter.")
        if st.button("Refresh listing check (up to 1 RentCast call)", key="refresh_listing_record") and property_id_for_listing:
            with st.spinner("Refreshing listing record..."):
                try:
                    rec, rec_time = listing_record_cached(A["address_key"], key, property_id_for_listing)
                    A["listing_record"] = rec or {}
                    A["listing_record_fetched_at"] = rec_time
                    A["time"] = utc_now_iso()
                    st.session_state["analysis"] = A
                    db_merge_save_snapshot(A["address_key"], A["input"], {
                        "listing_record": rec or {},
                        "listing_record_fetched_at": rec_time,
                    })
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    listing_record = A.get("listing_record") or {}
    if not listing_record:
        if listing_checked:
            st.info("No exact sale-listing record was found. The property may be off-market or outside current listing coverage.")
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
    rows=[["ARV",arv],["Rehab",rehab],["Acquisition closing @ offer ceiling",ceiling*closing/100],["Selling-cost allowance",arv*selling/100],["Holding + financing",holding],["Rehab contingency",rehab*contingency/100],["Target profit",target_profit if strategy in ("Flip","Wholesale") else None],["Assignment fee",assignment if strategy=="Wholesale" else None],["Offer ceiling",ceiling]]
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
    if not latest_tax and taxes_override_match:
        latest_tax = float(taxes_override_match)
        latest_tax_year = "manual"
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
        st.info("Load this only when you want deeper neighborhood activity. A new snapshot uses up to 2 RentCast requests; a saved 30-day NORVIM snapshot uses 0.")
        if st.button("Load neighborhood map & recent sales", type="primary", use_container_width=True):
            with st.spinner("Checking permanent cache, then loading recent sales and active listings only if needed..."):
                try:
                    neighborhood_db_key = f"neighborhood::{n_key}"
                    saved = db_get_cached_snapshot(neighborhood_db_key, max_age_days=30) or {}
                    if saved.get("recent_sales") is not None and saved.get("active_listings") is not None:
                        nsales = saved.get("recent_sales") or []
                        nactive = saved.get("active_listings") or []
                        ntime = saved.get("time") or utc_now_iso()
                    else:
                        nsales, nactive, ntime = neighborhood_cached(
                            n_key, key, A["input"], subj.get("propertyType")
                        )
                        db_save_snapshot(neighborhood_db_key, A["input"], {
                            "recent_sales": nsales,
                            "active_listings": nactive,
                            "time": ntime,
                        })
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

        map_df = neighborhood_map_rows(
            subj,
            rsdf,
            aldf,
            cdf,
            valuation=val,
            rent_data=rent_data,
            property_record=property_record,
        )
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
        st.caption(f'Neighborhood snapshot saved: {n_state.get("time","—")}. With Supabase connected, reopening this address can reuse the permanent 30-day NORVIM snapshot without new RentCast calls.')


with tabs[7]:
    st.markdown("#### ZIP / area market analysis")
    if not market and zip_code != "—":
        st.info("Quick Scan skipped the ZIP market endpoint. Load it only when you need market velocity, asking-price trends or ZIP-level rental statistics.")
        if st.button("Load ZIP market data (up to 1 RentCast call)", type="primary", key="load_zip_market"):
            with st.spinner(f"Loading ZIP {zip_code} market data..."):
                try:
                    zip_cache_key = f"zip::{zip_code}"
                    cached_zip = db_get_cached_snapshot(zip_cache_key, max_age_days=30) or {}
                    if cached_zip.get("market"):
                        mkt = cached_zip.get("market") or {}
                        mkt_time = cached_zip.get("market_fetched_at") or cached_zip.get("time") or utc_now_iso()
                    else:
                        mkt, mkt_time = market_zip_cached(zip_code, key)
                        db_save_snapshot(zip_cache_key, f"ZIP {zip_code} market", {
                            "market": mkt,
                            "market_fetched_at": mkt_time,
                            "time": mkt_time,
                        })
                    A["market"] = mkt
                    A["market_fetched_at"] = mkt_time
                    A["time"] = utc_now_iso()
                    st.session_state["analysis"] = A
                    db_merge_save_snapshot(A["address_key"], A["input"], {
                        "market": mkt,
                        "market_fetched_at": mkt_time,
                    })
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    elif market:
        st.caption(f"ZIP market data is cached for 30 days and can be reused by other properties in ZIP {zip_code}.")

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
        "purchase_scenario":purchase_scenario,
        "preferred_strategy_result":preferred_result.get("status") if preferred_result else None,
        "strongest_modeled_strategy":best_result.get("strategy") if best_result else None,
        "strongest_modeled_status":best_result.get("status") if best_result else None,
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
    st.caption("Deal summary export. Strategy Match, CRM and public-data intelligence are available in their dedicated tabs.")


with tabs[10]:
    st.markdown("#### Strategy Match")
    st.caption("All four strategies are evaluated at the same purchase price. Change the price in the sidebar or use Offer Lab to test negotiations.")

    st.markdown(f"**Purchase scenario:** {money(purchase_scenario)}")
    cols = st.columns(4)
    for col, row in zip(cols, [strategy_row_by_name(strategy_results, n) for n in ["Flip","Wholesale","BRRRR","Rental"]]):
        with col:
            render_strategy_card(row)

    preferred = strategy_row_by_name(strategy_results, strategy)
    if preferred and preferred["status"] != "Meets targets" and best_result and best_result["strategy"] != strategy:
        st.warning(
            f"You selected **{strategy}**, but it does not currently meet all of your targets. "
            f"**{best_result['strategy']}** has the strongest modeled fit at this price. "
            "Review the underlying assumptions before changing your plan."
        )
    elif preferred and preferred["status"] == "Meets targets":
        st.success(f"Your selected **{strategy}** strategy meets the thresholds you entered at this purchase scenario.")
    else:
        st.info("No strategy fully meets the current thresholds. Use Offer Lab to see whether a lower purchase price changes the result.")

    rows = []
    for r in strategy_results:
        secondary = r.get("secondary")
        if r["strategy"] in ("BRRRR","Rental"):
            secondary_text = strategy_explanation(r)
        elif r["strategy"] == "Flip":
            secondary_text = f'{r["details"].get("roi")*100:.1f}% ROI' if r["details"].get("roi") is not None else "—"
        else:
            secondary_text = "End-buyer spread model"
        rows.append({
            "Strategy": r["strategy"],
            "Result": r["status"],
            "Modeled max purchase": r["max_purchase"],
            r["primary_label"]: r["primary"],
            "Summary": secondary_text,
        })
    smdf = pd.DataFrame(rows)
    money_cols = [c for c in smdf.columns if c in ["Modeled max purchase","Projected net profit","Available spread","Monthly cash flow"]]
    fmt = {c:"${:,.0f}" for c in money_cols}
    st.dataframe(smdf.style.format(fmt, na_rep="—"), use_container_width=True, hide_index=True)

    st.markdown("##### How the match is decided")
    st.write(
        "Flip checks target net profit and ROI. Wholesale checks whether there is enough room below the modeled end-buyer flip ceiling. "
        "BRRRR checks monthly cash flow, cash left after refinance, rent cushion (DSCR), and equity creation. "
        "Rental checks monthly cash flow, rent cushion, and cap rate."
    )


with tabs[11]:
    st.markdown("#### Offer Lab")
    st.caption("This section recalculates locally. Moving the slider does **not** make another RentCast request.")

    base_price = max(float(purchase_scenario or 0), 50000)
    low_price = max(10000, int((base_price - 100000) // 5000 * 5000))
    high_price = max(low_price + 10000, int((base_price + 50000) // 5000 * 5000))
    test_price = st.slider(
        "Test purchase price",
        min_value=int(low_price),
        max_value=int(high_price),
        value=int(min(max(base_price, low_price), high_price)),
        step=5000,
        format="$%d",
    )
    lab = strategy_match(
        test_price, arv, rent_m, rehab, closing, selling, holding, contingency,
        target_profit, flip_min_roi, assignment,
        refi_ltv, refi_rate_match, refi_term_match, refi_closing_match,
        effective_tax_match, insurance_match, hoa_match,
        vacancy, management_match, maintenance_match, capex_match,
        brrrr_min_cf, brrrr_max_cash_left, min_dscr_global,
        rental_down, rental_rate, rental_term, rental_min_cf, cap,
    )
    lab_best = lab[0] if lab else None
    o1,o2,o3,o4=st.columns(4)
    flip_lab = strategy_row_by_name(lab,"Flip")
    brrrr_lab = strategy_row_by_name(lab,"BRRRR")
    rental_lab = strategy_row_by_name(lab,"Rental")
    wholesale_lab = strategy_row_by_name(lab,"Wholesale")
    with o1: result_card("Flip profit", money((flip_lab or {}).get("details",{}).get("profit")), (flip_lab or {}).get("status"))
    with o2: result_card("Wholesale spread", money((wholesale_lab or {}).get("details",{}).get("spread")), (wholesale_lab or {}).get("status"))
    with o3: result_card("BRRRR cash flow", money((brrrr_lab or {}).get("details",{}).get("monthly_cash_flow")) + "/mo", (brrrr_lab or {}).get("status"))
    with o4: result_card("Rental cash flow", money((rental_lab or {}).get("details",{}).get("cash_flow")) + "/mo", (rental_lab or {}).get("status"))

    if lab_best:
        st.info(f"At **{money(test_price)}**, the strongest modeled fit is **{lab_best['strategy']}** ({lab_best['status']}).")

    st.markdown("##### Price sensitivity")
    ladder = []
    step = 10000
    start_p = max(10000, int(base_price - 80000))
    end_p = int(base_price + 30000)
    for p in range(start_p, end_p + 1, step):
        rr = strategy_match(
            p, arv, rent_m, rehab, closing, selling, holding, contingency,
            target_profit, flip_min_roi, assignment,
            refi_ltv, refi_rate_match, refi_term_match, refi_closing_match,
            effective_tax_match, insurance_match, hoa_match,
            vacancy, management_match, maintenance_match, capex_match,
            brrrr_min_cf, brrrr_max_cash_left, min_dscr_global,
            rental_down, rental_rate, rental_term, rental_min_cf, cap,
        )
        f = strategy_row_by_name(rr,"Flip")
        w = strategy_row_by_name(rr,"Wholesale")
        b = strategy_row_by_name(rr,"BRRRR")
        r = strategy_row_by_name(rr,"Rental")
        ladder.append({
            "Purchase": p,
            "Flip Profit": (f or {}).get("details",{}).get("profit"),
            "Flip Result": (f or {}).get("status"),
            "Wholesale Spread": (w or {}).get("details",{}).get("spread"),
            "BRRRR Cash Flow": (b or {}).get("details",{}).get("monthly_cash_flow"),
            "BRRRR Cash Left": (b or {}).get("details",{}).get("cash_left"),
            "Rental Cash Flow": (r or {}).get("details",{}).get("cash_flow"),
            "Best Fit": rr[0]["strategy"] if rr else None,
        })
    ldf = pd.DataFrame(ladder)
    st.dataframe(
        ldf.style.format({
            "Purchase":"${:,.0f}",
            "Flip Profit":"${:,.0f}",
            "Wholesale Spread":"${:,.0f}",
            "BRRRR Cash Flow":"${:,.0f}",
            "BRRRR Cash Left":"${:,.0f}",
            "Rental Cash Flow":"${:,.0f}",
        }, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )


with tabs[12]:
    st.markdown("#### Neighborhood Intelligence")
    st.caption("These sources are separate from RentCast. Loading them does not consume RentCast requests.")

    census_key = str(get_setting("CENSUS_API_KEY", "") or "").strip()
    subject_lat = subj.get("latitude") or property_record.get("latitude")
    subject_lon = subj.get("longitude") or property_record.get("longitude")

    if st.button("Load free/public neighborhood data", type="primary", use_container_width=True, key="public_intel_load"):
        with st.spinner("Checking FEMA, City of Houston public GIS and Census data..."):
            st.session_state["public_intel"] = public_intelligence_cached(
                A["address_key"], subject_lat, subject_lon, zip_code, census_key
            )

    pintel = st.session_state.get("public_intel")
    if pintel:
        st.markdown('<span class="source-pill">FEMA NFHL</span><span class="source-pill">Houston 311 GIS</span><span class="source-pill">Houston PlatTracker</span><span class="source-pill">U.S. Census ACS (optional key)</span>', unsafe_allow_html=True)

        flood = pintel.get("flood") or {}
        st.markdown("##### Flood screening")
        f1,f2,f3,f4=st.columns(4)
        with f1: result_card("FEMA flood zone", flood.get("FLD_ZONE") or "No intersecting record")
        with f2: result_card("Special Flood Hazard Area", "Yes" if str(flood.get("SFHA_TF")).upper() in ("T","Y","TRUE") else ("No" if flood else "—"))
        with f3: result_card("Zone subtype", flood.get("ZONE_SUBTY") or "—")
        with f4: result_card("Static BFE", flood.get("STATIC_BFE") if flood.get("STATIC_BFE") not in (None,"") else "—")
        st.caption("Screening only. Flood maps and insurance requirements should be verified with FEMA, the lender and an insurance professional.")

        cases = pintel.get("311") or []
        top311, df311 = summarize_311(cases)
        st.markdown("##### Houston 311 activity — within 0.5 mile")
        st.write(f"Recent 311 cases returned: **{len(cases)}**")
        if top311:
            top_df = pd.DataFrame(top311[:10], columns=["Service request category","Count"])
            st.dataframe(top_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No recent 311 records were returned, or the City service was temporarily unavailable.")
        st.caption("The City's recent 311 layer contains open cases and recently closed cases, so this is a current-activity signal rather than a full 12-month history.")

        plat_apps = summarize_plats(pintel.get("plat_apps") or [])
        final_plats = summarize_plats(pintel.get("final_plats") or [])
        st.markdown("##### Development / plat activity — within 1 mile")
        p1,p2=st.columns(2)
        with p1: result_card("Plat applications", len(plat_apps), "Potential/current subdivision activity")
        with p2: result_card("Final plats", len(final_plats), "Approved plat records returned")
        if not plat_apps.empty:
            st.dataframe(plat_apps.head(30), use_container_width=True, hide_index=True)

        census = pintel.get("census") or {}
        st.markdown(f"##### ZIP {zip_code} housing & economic context")
        if census:
            c1,c2,c3,c4=st.columns(4)
            with c1: result_card("Population", f'{census.get("population"):,.0f}' if census.get("population") is not None else "—")
            with c2: result_card("Median household income", money(census.get("median_household_income")))
            with c3: result_card("Vacancy rate", f'{census.get("vacancy_rate")*100:.1f}%' if census.get("vacancy_rate") is not None else "—")
            with c4: result_card("Owner occupied", f'{census.get("owner_rate")*100:.1f}%' if census.get("owner_rate") is not None else "—")
            c5,c6,c7,c8=st.columns(4)
            with c5: result_card("Renter occupied", f'{census.get("renter_rate")*100:.1f}%' if census.get("renter_rate") is not None else "—")
            with c6: result_card("ACS median gross rent", money(census.get("median_gross_rent")))
            with c7: result_card("ACS median home value", money(census.get("median_home_value")))
            with c8: result_card("Median year built", f'{census.get("median_year_built"):.0f}' if census.get("median_year_built") is not None else "—")
        else:
            st.info("Census profile is optional. Add a free CENSUS_API_KEY in Streamlit Secrets to load ACS ZIP-level housing/economic data.")

    st.markdown("##### Research shortcuts — no paid property API")
    encoded_address = quote_plus(subj.get("formattedAddress") or A["input"])
    encoded_area = quote_plus(" ".join([str(x) for x in [property_record.get("subdivision"), zip_code, "Houston development"] if x]))
    r1,r2,r3,r4,r5=st.columns(5)
    with r1: st.link_button("Search exact address", f"https://www.google.com/search?q=%22{encoded_address}%22", use_container_width=True)
    with r2: st.link_button("Neighborhood development", f"https://www.google.com/search?q={encoded_area}", use_container_width=True)
    with r3: st.link_button("HCAD property search", "https://hcad.org/quicksearch/", use_container_width=True)
    with r4: st.link_button("Houston permits", "https://permits.houstontx.gov/", use_container_width=True)
    with r5: st.link_button("FEMA flood maps", "https://msc.fema.gov/portal/home", use_container_width=True)


with tabs[13]:
    st.markdown("#### NORVIM CRM / acquisition pipeline")
    if not db_enabled():
        st.warning("Connect Supabase to make the CRM permanent. Until then, analyses can still be exported but CRM changes will not survive redeploys.")
        st.code(
            'SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"\\n'
            'SUPABASE_SERVICE_ROLE_KEY = "YOUR_SERVER_SIDE_KEY"\\n'
            'NORVIM_ORG_ID = "norvim"'
        )
        st.caption("Run the included supabase_schema.sql in Supabase first. Keep the service-role key only in Streamlit Secrets; never put it in GitHub.")
    else:
        prop_row = db_upsert_property(subj, property_record, A["address_key"], A["input"])
        property_id = (prop_row or {}).get("id")
        st.success("Permanent CRM storage is connected.")

        with st.form("crm_form"):
            c1,c2,c3=st.columns(3)
            with c1:
                lead_status = st.selectbox("Pipeline status", ["New Lead","Researching","Contacted","Follow Up","Offer Sent","Negotiating","Under Contract","Rehab","Listed / Renting","Closed","Dead Lead"])
                lead_source = st.text_input("Lead source", placeholder="Driving for dollars, wholesaler, referral...")
                preferred_crm_strategy = st.selectbox("Preferred strategy", ["Flip","Wholesale","BRRRR","Rental"], index=["Flip","Wholesale","BRRRR","Rental"].index(strategy))
            with c2:
                seller_name = st.text_input("Seller / contact name")
                seller_phone = st.text_input("Phone")
                seller_email = st.text_input("Email")
            with c3:
                seller_ask = st.number_input("Seller ask", 0.0, value=float(listing_price_match or purchase_scenario or 0), step=5000.0)
                offer_amount = st.number_input("Your offer", 0.0, value=float(ceiling or 0), step=5000.0)
                follow_up = st.date_input("Follow-up date", value=None)
            partner = st.text_input("Partner / JV / buyer")
            notes = st.text_area("Notes", height=140)
            save_crm = st.form_submit_button("Save property + analysis + CRM", type="primary", use_container_width=True)

        if save_crm:
            if not property_id:
                st.error("Could not create the permanent property record.")
            else:
                lead_ok = db_save_lead(property_id, {
                    "status": lead_status,
                    "lead_source": lead_source,
                    "seller_name": seller_name,
                    "seller_phone": seller_phone,
                    "seller_email": seller_email,
                    "partner": partner,
                    "preferred_strategy": preferred_crm_strategy,
                    "seller_ask": seller_ask,
                    "offer_amount": offer_amount,
                    "follow_up_date": follow_up.isoformat() if follow_up else None,
                    "notes": notes,
                })
                assumptions = {
                    "rehab": rehab, "closing_pct": closing, "selling_pct": selling, "holding": holding,
                    "contingency_pct": contingency, "flip_target_profit": target_profit, "flip_min_roi": flip_min_roi,
                    "assignment_target": assignment, "refi_ltv": refi_ltv, "refi_rate": refi_rate_match,
                    "insurance": insurance_match, "vacancy_pct": vacancy, "management_pct": management_match,
                }
                run_ok = db_save_underwriting(
                    property_id, A["address_key"], strategy, purchase_scenario, strategy_results_json, assumptions
                )
                if lead_ok and run_ok:
                    st.success("Saved to the NORVIM pipeline.")
                else:
                    st.warning("Some CRM data did not save. Check the database configuration.")

        pipeline = db_get_pipeline()
        if pipeline:
            st.markdown("##### Pipeline")
            pdf = pd.DataFrame(pipeline)
            show_cols = [c for c in ["address","status","preferred_strategy","seller_ask","offer_amount","follow_up_date","partner","updated_at"] if c in pdf.columns]
            st.dataframe(pdf[show_cols] if show_cols else pdf, use_container_width=True, hide_index=True)
        else:
            st.caption("No saved pipeline records yet.")


st.caption("NORVIM DealFinder 2.2 · 2-call Quick Scan, optional deep data, permanent caching, strategy matching, offer sensitivity, neighborhood intelligence and CRM.")
