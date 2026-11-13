# NORVIM Acquisition Workspace update

This updates the existing Streamlit application with the reference workspace's cream canvas, olive accents, serif headings and sidebar navigation. Existing provider integrations, cache and request-budget logic remain in place.

## Included

- Comparable ARV is calculated before the summary and the “Use NORVIM Comp ARV” button, fixing the startup NameError.
- Shared Mapbox configuration across eight maps, with Light, Streets, Satellite, Satellite + streets and Outdoors styles.
- Free Carto basemap fallback and optional custom Mapbox style.
- Section 8 support in the existing CRM strategy selector.
- Native Streamlit theme in `.streamlit/config.toml`.

## Existing deployment

Keep the current Streamlit Cloud Secrets, requirements, companion modules and database schema. The update does not contain credentials or migrate data. Streamlit Cloud can rebuild from the existing repository's `main` branch.

To activate Mapbox, add your own public token in **Manage app → Settings → Secrets**:

```toml
MAPBOX_ACCESS_TOKEN = "pk.YOUR_PUBLIC_TOKEN"
```

`MAPBOX_API_KEY` and `MAPBOX_TOKEN` are also supported. Secret `sk.` tokens are never passed to browser maps. Do not commit credentials. A custom published style can be configured with `MAPBOX_STYLE = "mapbox://styles/USERNAME/STYLE_ID"`.

Use **Map appearance** in the sidebar to change the provider or style. These controls do not make extra RentCast requests. Mapbox map loads are billed under the owner's Mapbox account terms.

## Validation

Run `python tests/run_offline_checks.py` with the existing dependencies installed. The offline suite covers startup, comparable ARV, its apply button, all five analysis strategies, navigation state, zero-request manual mode, cached maps and Mapbox token/style handling. It blocks outbound requests and uses illustrative fixtures. Live API authentication and Mapbox tiles require the existing deployment's credentials.

All 109 original functions other than the intentionally updated neighborhood-map renderer remain structurally unchanged. The companion Fast Exit and Research Hub modules are retained.
