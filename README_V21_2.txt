MOMENTUM SNIPER V21.2 — TOP-N CREATOR RANK CLICK FIX

Fixes:
  Kalodata Creator filter returned no usable creator detail links

Why it happened:
Kalodata's Creator ranking table was visible and had the correct rows/headers,
but Firecrawl's DOM did not expose /creator/detail hrefs for those rows.

New behavior:
- Saved Creator filter still applies normally.
- For Top N Creator mode, Sniper now clicks rank 1, rank 2, rank 3, etc. directly.
- It prefers a creator-detail link if one exists.
- Otherwise it clicks the visible @handle / clickable wrapper / row.
- After every click it verifies the browser actually reached /creator/detail.
- It then scans that creator's Product section and performs the same strict product vet:
    Avg price >= $8
    Commission >= $3 per sale
    Ads >= 7/10
- Specific Creator search from V21.1 is unchanged.
- Normal Product mode is unchanged.

Replace:
  app.py
  snipe.py
