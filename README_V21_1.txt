MOMENTUM SNIPER V21.1 — DIRECT CREATOR SEARCH FIX

Fixes the runtime error:
  No Kalodata Creator results were returned for '@handle'

What changed:
- @handles are searched without the leading @ (e.g. @torijflow -> torijflow).
- Direct Creator mode no longer assumes Kalodata renders search results as a normal table.
- After submitting the search, Sniper looks for the matching creator in:
    creator detail links
    visible table rows
    autocomplete/options
    visible matching handle/name text
- It clicks the matching result and verifies that Kalodata actually opened /creator/detail.
- If an @handle was supplied, it verifies the opened handle matches before scanning products.
- Existing saved-filter Creator mode and Product mode are unchanged.

Replace:
  app.py
  snipe.py
