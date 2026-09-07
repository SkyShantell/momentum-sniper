Momentum Sniper V17 — old-run "Send to Fashion Flow" button

Replace app.py in your Momentum Sniper repo with this version.
snipe.py is included unchanged from V16 for convenience.

New Run History button:
  👗 Send to Fashion Flow

How it works:
- Select ANY old CSV run in Run History.
- Click Send to Fashion Flow.
- The run is placed in Flow Fashion's Momentum Sniper Inbox.
- It does NOT append directly to an open production batch.
- In Flow Fashion, choose the saved avatar name before creating the batch.
- If the same run was already auto-pushed, the deterministic batch ID prevents a duplicate.

Required Streamlit Secret:
  FLOW_FASHION_API_KEY = "<same value as Flow Fashion PHASE1_API_KEY>"

Recommended:
  FLOW_FASHION_API_URL = "<same Railway backend URL as Flow Fashion RAILWAY_API_BASE_URL>"
