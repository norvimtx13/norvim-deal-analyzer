# NORVIM Deal Analyzer — MVP

A Streamlit web app for evaluating listed or off-market residential properties.

## Included
- Address lookup
- ARV/value estimate and sales comps
- Long-term rent estimate
- ZIP-level sale/rental market statistics
- Average and median days on market
- Flip, wholesale, BRRRR and rental offer calculations
- Comp map when coordinates are available
- CSV deal-summary export

The MVP uses the RentCast API and normally makes about 3 API requests per analyzed address.

## Run locally
1. Install Python 3.11+.
2. Run `pip install -r requirements.txt`.
3. Create `.streamlit/secrets.toml` containing:
   `RENTCAST_API_KEY = "your_key_here"`
4. Run `streamlit run app.py`.

## Put it online
1. Create a GitHub repository such as `norvim-deal-analyzer`.
2. Upload this project folder's files.
3. Go to https://share.streamlit.io and connect GitHub.
4. Click **Create app**, select the repo, and use `app.py` as the entrypoint.
5. In **Advanced settings → Secrets**, add:
   `RENTCAST_API_KEY = "your_key_here"`
6. Deploy. Streamlit gives you a shareable `streamlit.app` URL.

## Security
Never commit your real API key to GitHub. The `.gitignore` file blocks `.streamlit/secrets.toml`.

## Suggested V2
Private login, persistent deal database, manual comp include/exclude, FEMA flood data, Harris County/HCAD links, repair estimator, branded PDF reports, deal pipeline, and driving-for-dollars workflow.
