MOMENTUM SNIPER V19 — KALODATA CREATOR MODE

New Scan type selector:
  Product
  Creator

PRODUCT
- Existing working product flow is preserved.
- Existing product filters/vetting/Director/Seedance/Fashion Flow behavior remains.

CREATOR
- Opens https://www.kalodata.com/creator
- Applies the exact saved custom filter name entered in the UI
- Sets 50/Page
- Scrapes the Creator table as rendered by Kalodata
- Saves:
    creator
    handle
    creator_id
    creator_url
    profile_image
    plus every visible Kalodata creator-table column
- Output filename:
    snipe-creator-<filter>-<timestamp>.csv
- No product price/commission/ad vetting is applied.
- Creator CSVs can be previewed/downloaded in Run History.
- Product-only Seedance / Fashion Flow buttons are disabled for Creator CSVs.

NOTE
This first Creator mode mirrors the current Product pull size: up to 50 visible rows
from the saved filter. Pagination beyond the first 50 can be added separately.
