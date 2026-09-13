MOMENTUM SNIPER V23 — US + UK MARKET SUPPORT

A market selector is now available in the Streamlit sidebar.

Markets:
- United States (US): region US, USD, en-US
- United Kingdom (UK): region GB, GBP, en-GB

UK is selected by default for this release because it was the requested market.
You can switch back to US at any time.

The selected market applies to BOTH Product and Creator scans.
UK mode changes the actual Kalodata market requests; it does not convert US
results into pounds.

Vetting keeps the same numeric thresholds in local currency:
- US: average price >= $8 and commission per sale >= $3
- UK: average price >= £8 and commission per sale >= £3
- Both: at least 7 of the top 10 videos are ads

The output CSV is tagged with market + currency, and new run filenames are tagged
US/GB so same-day US and UK scans do not collide in run history.
