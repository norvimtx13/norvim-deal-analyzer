# Property verification and foreclosure research — first test version

This change is for the existing GitHub Streamlit NORVIM app. It does not deploy the separate ChatGPT-hosted workspace.

## Test it before merging

1. Create a separate Streamlit Community Cloud test app using this pull request's branch and `app.py`. Leave the production app on `main`. Set an access code if this test app will hold your saved data.
2. Open **Legal & foreclosure desk → Test without API costs → Show Elysian test snapshot**. Expect the November 19 reference record to show county classification source-checked, City use Unknown, and current enforcement Unavailable. It is labeled a reference, is not a fresh lookup, and is not saved into the live property record.
3. Download the sample collector CSV, then import it in **Foreclosure & tax leads**. The demo row remains **Unclassified notice**, with no invented tax balance or completed-sale claim. Import it twice: one candidate should remain.
4. In **Deal analyzer**, search a real address with **Include free county classification check** enabled. The new panel appears beside that address. A Harris County record, found by coordinate or exact address, must match its street and city before its tax classification becomes Source checked. A county mismatch, unsupported address format, error or ambiguous result remains unresolved. The free county lookup adds at most one new public GIS request per explicit address submission; slider/navigation reruns do not run it again.
5. To test live AI, add the secrets below in the test app. Run one Elysian address review, then a small (1–3 candidate) Harris County sale-date search. Inspect each linked source. An empty search result is partial coverage, not proof that no notices exist.
6. Confirm the original underwriting inputs, comps, maps and saved property values are unchanged. With Supabase connected, reload and confirm verification and imported candidates persist. Without it, use the download backups; a session is not permanent storage.

## Configuration

The existing requirements already include `requests`; no new dependency is required.

Add only in Streamlit **App settings → Secrets**, never in GitHub:

```toml
OPENAI_API_KEY = "your-api-key"
OPENAI_RESEARCH_MODEL = "gpt-6.2-astra"
APP_ACCESS_CODE = "your-private-test-access-code"
```

ChatGPT Plus does not supply an API key or API billing for this app. OpenAI API usage is separate. Do not paste a key into a property note, CSV, repository, or public page. The live agent is disabled until a server-side key is configured. Free county checks, the reference demo, and CSV imports work without a key.

Each AI click issues one Responses API request: web search is required, limited to official county/City/FEMA domains, at most four tool calls and 6,000 output tokens, with no automatic paid retry. The only input is a public property address or Harris County/sale-date scope. Underwriting, lender terms, contacts and portfolio notes are excluded. Partial/refused/invalid responses do not overwrite prior findings. A timeout may still have used API credits; check usage before retrying.

## Collector compatibility

Import the UTF-8 CSV from the existing Windows foreclosure collector. Required: `address` (or `property_address`). Supported columns:

`address, city, state, zip, auction_date, source_url, document_id, account, tax_due, record_as_of, lead_type, notes`

Accepted lead types: **Trustee sale notice**, **Tax sale scheduled**, **Tax delinquent**, **Unclassified notice**. A notice/scheduled-sale label requires an official source link and valid sale date. Sparse collector files are still usable as candidates, but remain unclassified. Tax value is never treated as unpaid tax. Imports are limited to 500 rows / 2 MB and deduplicate by address, type, sale date and document ID. This initial version does not fetch scanned images or operate the Clerk's interactive document viewer; use your collector to supply those records and review them.

## Evidence rules

- County appraisal classification is not City-approved use. The direct county source can be checked only for its narrow tax-record claim.
- AI findings remain review items even when they cite an official source. Their links must appear in the API's returned source/citation list. Uncited conclusions become Unknown; uncited discovered leads are discarded.
- The panel distinguishes the research run time from a document/statement's date. Older source records are not silently described as current balances or current clearance.
- Historical permit final status is not current code/unsafe-building clearance.
- A trustee notice is not evidence of completed foreclosure, bank ownership, available equity, or seller intent. Delinquent taxes are separate from a scheduled tax sale.
- Failed, missing, partial or unavailable searches never become “clear.” Title, liens, restrictions and insurance can require documents and professional review.

## Persistence and deployment

Verification and distressed candidates use separate keys in the existing optional Supabase `analysis_snapshots` storage. They do not overwrite underwriting, portfolio or contact records; no schema migration is required. Persistence uses the existing app save mechanism and inherits its access/concurrency limitations. Test against a separate Supabase org/project if you want strict separation from production records. CSV/JSON downloads are available without Supabase.

The first version is **on demand**. No unattended browser worker, scheduled scraping, comprehensive delinquent-tax roll, outreach or automatic alerts are active. Complete county coverage may require a bulk feed or the existing browser collector; web search alone cannot guarantee it. A future scheduled worker can publish validated collector results into the same data model.

## Developer checks

```bash
python -m unittest discover -s tests -p 'test_verification.py' -v
python tests/run_offline_checks.py
python -m unittest discover -s tests -p 'test_verification_ui.py' -v
```

The offline checks mock outbound provider calls. They validate request shape, safeguards, imports, persistence and UI behavior; they do not establish live OpenAI billing/model access or complete county coverage. Live API testing requires the owner's configured test key.

Implementation follows the official OpenAI Responses web-search and structured-output documentation:
- https://developers.openai.com/api/docs/quickstart
- https://developers.openai.com/api/docs/guides/tools-web-search
- https://developers.openai.com/api/docs/guides/structured-outputs
