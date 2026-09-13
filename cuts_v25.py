"""Momentum Sniper V25 — commission-only near misses + no restricted-name exclusions.

PASSED behavior stays the same except the old RESTRICTED product-name list is
disabled across Product and Creator scans.

The "THESE WERE CUT" section is intentionally narrow:
- product was actually vetted
- avg price is still >= 8 in the selected local currency
- ad count is readable and >= 7/10
- brand/shop safety still passes
- commission is readable
- commission dollars per sale are BELOW 3

Nothing else is shown in the cut section.
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


def _commission_value(product):
    price = product.get("avg_price")
    commission = product.get("commission")
    if not isinstance(price, (int, float)) or not isinstance(commission, (int, float)):
        return None
    per_sale = product.get("per_sale")
    if not isinstance(per_sale, (int, float)):
        per_sale = round(float(price) * float(commission) / 100, 2)
    return float(per_sale)


def _is_commission_only_near_miss(legacy, product, *, vetted: bool) -> bool:
    if not vetted:
        return False

    price = product.get("avg_price")
    if not isinstance(price, (int, float)) or float(price) < 8:
        return False

    per_sale = _commission_value(product)
    if per_sale is None or per_sale >= 3:
        return False

    ads = product.get("ads")
    if not isinstance(ads, (int, float)) or int(ads) < 7:
        return False

    if not _brand_ok(legacy, product):
        return False

    return True


def install(legacy):
    """Disable restricted-name cuts and track useful commission near misses."""
    # Remove the old restricted-product/name list across every scan path.
    # Existing Product + Creator checks all reference this shared global.
    legacy.RESTRICTED = []

    state = {
        "product_pool": [],
        "creator_pool": [],
        "product_vetted_ids": set(),
        "creator_vetted_ids": set(),
    }
    legacy._v25_cut_state = state

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
        """Vet normal Product winners plus commission misses; return winners only."""
        originals = list(cands or [])
        original_ids = {_pid(p) for p in originals if _pid(p)}

        extras = []
        for p in state.get("product_pool") or []:
            pid = _pid(p)
            if not pid or pid in original_ids:
                continue

            price = p.get("avg_price")
            commission = p.get("commission")
            if not isinstance(price, (int, float)) or float(price) < 8:
                continue
            if not isinstance(commission, (int, float)):
                continue

            per_sale = round(float(price) * float(commission) / 100, 2)
            p["per_sale"] = per_sale
            if per_sale < 3:
                extras.append(p)

        combined = originals + extras
        for p in combined:
            pid = _pid(p)
            if pid:
                state["product_vetted_ids"].add(pid)

        vetted = original_vet(combined)

        # Extra products were passed to vet only to measure ads/shop safety.
        # Never promote them to PASSED if they failed the commission-dollar gate.
        return [p for p in (vetted or []) if _pid(p) in original_ids]

    legacy.vet = tracked_vet

    original_creator_vet = legacy.vet_creator_products

    def tracked_creator_vet(cands):
        for p in cands or []:
            pid = _pid(p)
            if pid:
                state["creator_vetted_ids"].add(pid)
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
            q["_v25_sources"] = []
            src = str(p.get("source_creator") or "").strip()
            if src:
                q["_v25_sources"].append(src)
            unique[key] = q
        else:
            current = unique[key]
            for field in (
                "avg_price", "commission", "per_sale", "ads", "shop",
                "img", "detail_imgs", "revenue", "growth", "item_sold",
            ):
                value = p.get(field)
                if value not in (None, "", []):
                    current[field] = value

            src = str(p.get("source_creator") or "").strip()
            if src and src not in current["_v25_sources"]:
                current["_v25_sources"].append(src)

    return list(unique.values())


def append_cut_sections(base_dir, before, legacy, market="US"):
    """Append ONLY commission-dollar near misses that still have 7/10+ ads."""
    state = getattr(legacy, "_v25_cut_state", None) or {}
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

        winners = _winner_ids(rows)
        cuts = []
        for p in candidates:
            pid = _pid(p)
            if not pid or pid in winners:
                continue
            if _is_commission_only_near_miss(
                legacy,
                p,
                vetted=(pid in vetted_ids),
            ):
                cuts.append(p)

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
                price = p.get("avg_price")
                commission = p.get("commission")
                per_sale = _commission_value(p)
                name = str(p.get("name") or f"Product {pid}")
                actual_link = f"https://shop.tiktok.com/view/product/{pid}"
                source_all = ", ".join(p.get("_v25_sources") or []) or str(
                    p.get("source_creator") or ""
                )

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
                    "cut_reason": (
                        f"Commission {symbol}{per_sale:.2f}/sale (< {symbol}3) — "
                        f"still has {int(p.get('ads'))}/10 ads"
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
                    f"added {len(cuts)} commission-only near miss(es) under THESE WERE CUT "
                    f"(all still have 7/10+ ads)"
                )
        except Exception as exc:
            legacy.log(f"could not append cut section to {path.name}: {exc}")
