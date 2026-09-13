"""Momentum Sniper V24 — keep rejected candidates at the bottom of every scan CSV.

The proven Product / Creator engines still decide what PASSES. This patch only
tracks the full candidate pools and appends rejected products after a clear
"THESE WERE CUT" divider, with the exact near-miss reason where possible.

Cut rows deliberately leave ``tiktok_link`` blank so existing automatic
Fashion Flow / Seedance handoffs continue to send PASSED products only.
The usable product URL is kept in ``cut_tiktok_link`` for manual review.
"""
from __future__ import annotations

import csv
import pathlib
import re


def _pid(product) -> str:
    return str((product or {}).get("id") or "").strip()


def _brand_ok(legacy, product) -> bool:
    name_l = str(product.get("name") or "").lower()
    shop = str(product.get("shop") or "").strip()
    if not shop:
        return True
    return (
        any(t in shop.lower() for t in legacy.TRUSTED)
        or any(
            t in set(re.findall(r"[a-z]{3,}", shop.lower()))
            for t in re.findall(r"[a-z]{3,}", name_l)[:6]
        )
        or not any(
            b in name_l
            for b in [
                "dyson", "apple", "stanley", "elf", "tarte",
                "medicube", "goli", "lemme", "nike", "adidas",
            ]
        )
    )


def _infer_reason(legacy, product, *, creator_mode: bool, vetted: bool, symbol: str) -> str:
    reasons = []
    name = str(product.get("name") or "")
    name_l = name.lower()

    if any(b in name_l for b in legacy.RESTRICTED):
        reasons.append("Restricted product/name rule")

    price_raw = product.get("avg_price")
    price = float(price_raw) if isinstance(price_raw, (int, float)) else 0.0
    if price < 8:
        reasons.append(f"Avg price {symbol}{price:.2f} (< {symbol}8)")

    # Creator mode only learns commission + ad data after the pre-check.
    # Product mode already has commission from the ranking table before vetting.
    if (not creator_mode) or vetted:
        commission = product.get("commission")
        if isinstance(commission, (int, float)):
            per_sale = product.get("per_sale")
            if not isinstance(per_sale, (int, float)):
                per_sale = round(price * float(commission) / 100, 2)
            if per_sale < 3:
                reasons.append(f"Commission {symbol}{per_sale:.2f}/sale (< {symbol}3)")
        elif vetted:
            reasons.append("Commission/detail data unreadable")

    if vetted:
        ads = product.get("ads")
        if isinstance(ads, (int, float)):
            if int(ads) < 7:
                reasons.append(f"Ads {int(ads)}/10 (< 7/10)")
        else:
            reasons.append("Ad count unreadable")

        if not _brand_ok(legacy, product):
            shop = str(product.get("shop") or "").strip()
            reasons.append(f"Brand/shop safety ({shop or 'shop unknown'})")

    if not reasons:
        reasons.append("Did not pass final vet")

    out = []
    for reason in reasons:
        if reason not in out:
            out.append(reason)
    return "; ".join(out)


def install(legacy):
    """Track Product + Creator candidate pools without changing pass/fail behavior."""
    state = {
        "product_pool": [],
        "creator_pool": [],
        "product_vetted_ids": set(),
        "creator_vetted_ids": set(),
    }
    legacy._v24_cut_state = state

    original_pull = legacy.pull

    def tracked_pull(preset):
        rows = original_pull(preset)
        state["product_pool"] = list(rows or [])
        return rows

    legacy.pull = tracked_pull

    original_creator_pull = legacy.pull_top_creator_products

    def tracked_creator_pull(creator):
        rows = original_creator_pull(creator)
        if rows:
            state["creator_pool"].extend(rows)
        return rows

    legacy.pull_top_creator_products = tracked_creator_pull

    original_vet = legacy.vet

    def tracked_vet(cands):
        for p in cands or []:
            if _pid(p):
                state["product_vetted_ids"].add(_pid(p))
        return original_vet(cands)

    legacy.vet = tracked_vet

    original_creator_vet = legacy.vet_creator_products

    def tracked_creator_vet(cands):
        for p in cands or []:
            if _pid(p):
                state["creator_vetted_ids"].add(_pid(p))
        return original_creator_vet(cands)

    legacy.vet_creator_products = tracked_creator_vet
    return state


def _changed_csvs(base: pathlib.Path, before: dict[str, float]):
    changed = []
    for path in base.glob("snipe-*.csv"):
        old = before.get(path.name)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if old is None or mtime > old + 1e-6:
            changed.append(path)
    return sorted(changed, key=lambda p: p.stat().st_mtime)


def _winner_ids(rows):
    ids = set()
    for row in rows:
        link = str(row.get("tiktok_link") or "")
        m = re.search(r"/product/(\d+)", link)
        if m:
            ids.add(m.group(1))
    return ids


def _dedupe_candidates(products):
    unique = {}
    for p in products or []:
        if not isinstance(p, dict):
            continue
        key = _pid(p) or ("name:" + str(p.get("name") or "").strip().lower())
        if not key or key == "name:":
            continue

        if key not in unique:
            q = dict(p)
            q["_v24_sources"] = []
            src = str(p.get("source_creator") or "").strip()
            if src:
                q["_v24_sources"].append(src)
            unique[key] = q
        else:
            src = str(p.get("source_creator") or "").strip()
            if src and src not in unique[key]["_v24_sources"]:
                unique[key]["_v24_sources"].append(src)

    return list(unique.values())


def append_cut_sections(base_dir, before, legacy, market="US"):
    """Append a divider + rejected products to every CSV created by this run."""
    state = getattr(legacy, "_v24_cut_state", None) or {}
    base = pathlib.Path(base_dir)
    code = str(market or "US").upper()
    symbol = "£" if code in ("GB", "UK") else "$"

    for path in _changed_csvs(base, before):
        creator_mode = path.name.startswith("snipe-creator-products-")
        candidates = _dedupe_candidates(
            state.get("creator_pool") if creator_mode else state.get("product_pool")
        )
        vetted_ids = set(
            state.get("creator_vetted_ids") if creator_mode else state.get("product_vetted_ids")
        )

        try:
            with path.open("r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                fields = list(reader.fieldnames or [])
                rows = list(reader)
        except Exception:
            continue

        if any(str(r.get("scan_status") or "").upper() == "SECTION" for r in rows):
            continue

        winners = _winner_ids(rows)
        cuts = [p for p in candidates if _pid(p) not in winners]

        for field in ("scan_status", "cut_reason", "cut_tiktok_link"):
            if field not in fields:
                fields.append(field)

        for row in rows:
            row["scan_status"] = "PASSED"
            row["cut_reason"] = ""
            row["cut_tiktok_link"] = ""

        if cuts:
            divider = {field: "" for field in fields}
            divider["product"] = "THESE WERE CUT"
            divider["scan_status"] = "SECTION"
            rows.append(divider)

            for p in cuts:
                pid = _pid(p)
                vetted = pid in vetted_ids
                price = p.get("avg_price")
                commission = p.get("commission")
                per_sale = p.get("per_sale")
                if not isinstance(per_sale, (int, float)) and isinstance(price, (int, float)) and isinstance(commission, (int, float)):
                    per_sale = round(float(price) * float(commission) / 100, 2)

                name = str(p.get("name") or (f"Product {pid}" if pid else "Unknown Product"))
                actual_link = f"https://shop.tiktok.com/view/product/{pid}" if pid else ""
                source_all = ", ".join(p.get("_v24_sources") or []) or str(p.get("source_creator") or "")

                cut_row = {field: "" for field in fields}
                values = {
                    "product": name,
                    "image_file": "",
                    "image_url": p.get("img") or "",
                    "avg_price": price,
                    "revenue_7d": p.get("revenue"),
                    "growth_pct": p.get("growth"),
                    "commission_pct": commission,
                    "per_sale_$": per_sale,
                    "creators": p.get("creators"),
                    "ads_top10": p.get("ads"),
                    "shop": p.get("shop") or "",
                    "tiktok_link": "",
                    "source_creator": p.get("source_creator") or "",
                    "source_creator_name": p.get("source_creator_name") or "",
                    "source_creator_revenue": p.get("source_creator_revenue"),
                    "source_creator_rank": p.get("source_creator_rank"),
                    "source_creators_all": source_all,
                    "creator_item_sold": p.get("item_sold"),
                    "caption": legacy.caption(pid, name) if hasattr(legacy, "caption") else "",
                    "scene_prompt": getattr(legacy, "SCENE_PROMPT", ""),
                    "scan_status": "CUT",
                    "cut_reason": _infer_reason(
                        legacy,
                        p,
                        creator_mode=creator_mode,
                        vetted=vetted,
                        symbol=symbol,
                    ),
                    "cut_tiktok_link": actual_link,
                }
                for key, value in values.items():
                    if key in cut_row:
                        cut_row[key] = value if value is not None else ""
                rows.append(cut_row)

        try:
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            if cuts:
                legacy.log(
                    f"added {len(cuts)} cut candidate(s) at the bottom under THESE WERE CUT"
                )
        except Exception as exc:
            legacy.log(f"could not append cut section to {path.name}: {exc}")
