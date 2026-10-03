# NORVIM DealFinder 2.0

A Houston-first property acquisition operating system built in Streamlit.

## What changed in 2.0

### DealFinder
Every property is evaluated across:
- Flip
- Wholesale
- BRRRR
- Rental

The app no longer assumes the user's preferred strategy is automatically the best modeled fit. It shows whether that strategy meets the user's thresholds and identifies the strongest alternative model when it does not.

### Offer Lab
Move the purchase-price slider without making new property-data requests. It recalculates:
- flip profit
- wholesale spread
- BRRRR cash flow / cash left
- rental cash flow
- strongest modeled strategy

### Neighborhood Intelligence
Separate from RentCast:
- FEMA National Flood Hazard Layer point screening
- Houston 311 recent service-request activity within 0.5 mile
- Houston PlatTracker applications/final plats within 1 mile
- optional U.S. Census ACS ZIP profile with a free Census key
- research shortcuts for exact-address search, development search, Houston permits and FEMA maps

Public GIS services can be temporarily unavailable; the app fails gracefully.

### Permanent cache + CRM
Optional Supabase integration adds:
- persistent property snapshots
- persistent RentCast usage tracking
- saved underwriting runs
- acquisition pipeline / notes / follow-up dates

Run `supabase_schema.sql` and add Supabase credentials to Streamlit Secrets.

### RentCast usage meter
Tracks successful RentCast HTTP 200 responses made by the app.
This is an app-side estimate, not the provider's official billing meter.
Use `RENTCAST_USAGE_OFFSET` to account for requests made before DealFinder started tracking.

## Important underwriting notes

- Strategy statuses mean **meets / misses the thresholds entered in the app**.
- They are not guarantees and are not a substitute for inspection, title, lender, appraisal, insurance, tax, flood, legal or contractor verification.
- Acquisition closing costs in 2.0 are modeled as a percentage of the **purchase price**, rather than ARV.
- Active asking prices are not the same as closed-sale evidence.
- Public-data layers may have different update cadences and geographic coverage.

## Files

- `app.py` — application
- `requirements.txt` — Python dependencies
- `.streamlit/config.toml` — theme
- `.streamlit/secrets.example.toml` — secrets template
- `supabase_schema.sql` — permanent cache / CRM schema
- `DEPLOY_V2.md` — deployment instructions
