"""Momentum Sniper V23 — market switching for US and UK scans.

This is a runtime patch over the proven Product engine + V22 Creator JSON engine.
It keeps the scanners intact and only switches Kalodata region/currency/language,
GBP parsing, product detail URLs, and output tagging.
"""
from __future__ import annotations

import csv
import os
import pathlib
import re
import urllib.parse

MARKETS = {
    "US": {
        "code": "US",
        "country": "US",
        "country_code": "us",
        "currency": "USD",
        "language": "en-US",
        "region": "US",
        "symbol": "$",
        "label": "United States",
    },
    "GB": {
        "code": "GB",
        "country": "GB",
        "country_code": "gb",
        "currency": "GBP",
        "language": "en-GB",
        "region": "GB",
        "symbol": "£",
        "label": "United Kingdom",
    },
}


def normalize_market(value: str | None) -> str:
    raw = str(value or "US").strip().upper()
    aliases = {
        "UK": "GB",
        "UNITED KINGDOM": "GB",
        "GREAT BRITAIN": "GB",
        "USA": "US",
        "UNITED STATES": "US",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in MARKETS else "US"


def _page_url(section: str, cfg: dict[str, str]) -> str:
    query = urllib.parse.urlencode(
        {
            "language": cfg["language"],
            "currency": cfg["currency"],
            "region": cfg["region"],
        }
    )
    return f"https://www.kalodata.com/{section}?{query}"


def _marketize_script(script: str, cfg: dict[str, str]) -> str:
    """Rewrite only market-specific values inside Firecrawl browser actions."""
    if not isinstance(script, str) or not script:
        return script

    product_url = _page_url("product", cfg)
    creator_url = _page_url("creator", cfg)

    replacements = {
        "location.assign('https://www.kalodata.com/product')": f"location.assign('{product_url}')",
        'location.assign("https://www.kalodata.com/product")': f'location.assign("{product_url}")',
        "location.assign('https://www.kalodata.com/creator')": f"location.assign('{creator_url}')",
        'location.assign("https://www.kalodata.com/creator")': f'location.assign("{creator_url}")',
        "'country':'US'": f"'country':'{cfg['country']}'",
        "'country': 'US'": f"'country': '{cfg['country']}'",
        '"country":"US"': f'"country":"{cfg["country"]}"',
        '"country": "US"': f'"country": "{cfg["country"]}"',
        "'currency':'USD'": f"'currency':'{cfg['currency']}'",
        "'currency': 'USD'": f"'currency': '{cfg['currency']}'",
        '"currency":"USD"': f'"currency":"{cfg["currency"]}"',
        '"currency": "USD"': f'"currency": "{cfg["currency"]}"',
        "'language':'en-US'": f"'language':'{cfg['language']}'",
        "'language': 'en-US'": f"'language': '{cfg['language']}'",
        '"language":"en-US"': f'"language":"{cfg["language"]}"',
        '"language": "en-US"': f'"language": "{cfg["language"]}"',
        '"country_code": "us"': f'"country_code": "{cfg["country_code"]}"',
        '"country_code":"us"': f'"country_code":"{cfg["country_code"]}"',
    }
    for old, new in replacements.items():
        script = script.replace(old, new)
    return script


def install(legacy, market: str | None = None):
    code = normalize_market(market or os.environ.get("SNIPER_MARKET"))
    cfg = MARKETS[code]
    legacy.SNIPER_MARKET = code
    legacy.SNIPER_MARKET_CFG = cfg

    # GBP values must parse through the existing Product-mode num() helper.
    original_num = legacy.num

    def market_num(value):
        if isinstance(value, str):
            value = re.sub(r"[£€]", "", value)
        return original_num(value)

    legacy.num = market_num

    # Product detail pages are the one normal Product-mode URL that explicitly
    # carried US/USD/en-US in the legacy engine.
    def market_detail_url(pid):
        today = legacy.datetime.date.today()
        dr = urllib.parse.quote(
            legacy.json.dumps(
                [
                    str(today - legacy.datetime.timedelta(days=7)),
                    str(today - legacy.datetime.timedelta(days=1)),
                ]
            )
        )
        return (
            f"https://www.kalodata.com/product/detail?id={pid}"
            f"&language={cfg['language']}&currency={cfg['currency']}&region={cfg['region']}"
            f"&dateRange={dr}&cateValue=%5B%5D"
        )

    legacy.detail_url = market_detail_url

    # All scanner paths ultimately pass browser actions through fc(). Rewriting
    # here lets us market-switch BOTH the legacy Product mode and V22 Creator
    # internal-JSON mode without duplicating either engine.
    original_fc = legacy.fc

    def market_fc(actions, label):
        patched = []
        for action in actions:
            item = dict(action)
            if item.get("type") == "executeJavascript" and isinstance(item.get("script"), str):
                item["script"] = _marketize_script(item["script"], cfg)
            patched.append(item)
        return original_fc(patched, label)

    legacy.fc = market_fc

    # Creator JSON metadata sometimes includes a convenience creator_page_url.
    # Keep that URL aligned with the selected market too.
    if hasattr(legacy, "_creator_from_json"):
        original_creator_from_json = legacy._creator_from_json

        def market_creator_from_json(row, rank=None):
            target = original_creator_from_json(row, rank=rank)
            cid = str(target.get("creator_id") or "").strip()
            if cid:
                target["creator_page_url"] = (
                    f"https://www.kalodata.com/creator/detail?id={cid}"
                    f"&language={cfg['language']}&currency={cfg['currency']}&region={cfg['region']}"
                )
            return target

        legacy._creator_from_json = market_creator_from_json

    # Keep logs readable in UK mode; numeric thresholds remain 8 / 3 in local currency.
    original_log = legacy.log

    def market_log(message):
        text = str(message)
        if code == "GB":
            text = text.replace("$", "£")
        return original_log(text)

    legacy.log = market_log
    legacy.log(f"market: {cfg['label']} ({code}) · {cfg['currency']}")
    return cfg


def tag_changed_csvs(base_dir: str | pathlib.Path, before: dict[str, float], market: str | None = None):
    """Add market/currency to CSVs created/overwritten by the just-finished run.

    Also inserts US/GB into the filename so a US and UK Product run on the same
    day cannot overwrite each other in Streamlit history.
    """
    code = normalize_market(market or os.environ.get("SNIPER_MARKET"))
    cfg = MARKETS[code]
    base = pathlib.Path(base_dir)
    changed = []
    for path in base.glob("snipe-*.csv"):
        old_mtime = before.get(path.name)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if old_mtime is None or mtime > old_mtime + 1e-6:
            changed.append(path)

    for path in changed:
        try:
            with path.open("r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                fields = list(reader.fieldnames or [])
                rows = list(reader)
            if "market" not in fields:
                fields.append("market")
            if "currency" not in fields:
                fields.append("currency")
            for row in rows:
                row["market"] = code
                row["currency"] = cfg["currency"]
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        except Exception:
            # Never turn a successful scan into a failed run just because metadata
            # tagging couldn't rewrite an output file.
            pass

        if re.search(rf"-{code}(?:-|$)", path.stem, flags=re.I):
            continue
        m = re.match(r"^(.*)(-\d{4}-\d{2}-\d{2}(?:_\d{2}-\d{2}-\d{2})?\.csv)$", path.name)
        new_name = f"{m.group(1)}-{code}{m.group(2)}" if m else f"{path.stem}-{code}.csv"
        target = path.with_name(new_name)
        try:
            if target.exists():
                target.unlink()
            path.replace(target)
        except OSError:
            pass
