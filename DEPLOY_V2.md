# NORVIM DealFinder 2.0 — deployment steps

## Fast update
Upload/replace these files in the GitHub repository:
- `app.py`
- `requirements.txt`
- `.streamlit/config.toml`
- `.streamlit/secrets.example.toml`
- `supabase_schema.sql`
- `README.md`

Streamlit Community Cloud should redeploy after the commit.

## Required secret
In Streamlit → App settings → Secrets:

```toml
RENTCAST_API_KEY = "YOUR_RENTCAST_KEY"
RENTCAST_MONTHLY_LIMIT = 50
RENTCAST_USAGE_OFFSET = 0
```

`RENTCAST_USAGE_OFFSET` is the number of successful requests already used this month before DealFinder started tracking them.

## Optional free Census intelligence
Request a free Census Data API key, then add:

```toml
CENSUS_API_KEY = "YOUR_FREE_CENSUS_KEY"
```

Without it, the rest of Neighborhood Intelligence still works.

## Permanent database + CRM
1. Create a Supabase project.
2. Open SQL Editor.
3. Run `supabase_schema.sql`.
4. Add these Streamlit secrets:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "YOUR_SERVER_SIDE_SERVICE_ROLE_KEY"
NORVIM_ORG_ID = "norvim"
```

Never commit the service-role key to GitHub.

Once connected:
- RentCast snapshots can persist through Streamlit redeploys.
- API usage is stored.
- CRM pipeline is stored.
- Underwriting runs are stored.

## Optional prototype access code
Until real account authentication is added:

```toml
APP_ACCESS_CODE = "choose-a-private-code"
```

This is only a prototype gate. It is not a substitute for Supabase Auth.

## Public SaaS launch
Before charging outside users, add:
- Supabase Auth
- organization-scoped RLS policies
- Stripe Checkout / Billing Portal / webhooks
- plan-level search quotas
- terms/privacy/data-provider attribution
- monitoring/backups
