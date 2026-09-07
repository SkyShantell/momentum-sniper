"""Momentum Sniper — Streamlit front-end for snipe.py.

Lets a VA pick a Kalodata preset, run the hunt, review the result, and send the
scraped product batch into the Seedance Studio inbox without re-pasting links.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd
import streamlit as st

BASE = pathlib.Path(__file__).parent
MOMENTUM_PRESETS = ["HighTicket", "Lurkers", "Hardcore", "100 GAP"]
QUEUE_SCHEMA = "momentum.seedance.batch.v1"

st.set_page_config(page_title="Momentum Sniper", page_icon="🎯", layout="wide")


def get_secret(key: str, default: str = "") -> str:
    """Read a Streamlit secret first, then fall back to an environment variable."""
    try:
        value = st.secrets.get(key, default)
    except (FileNotFoundError, KeyError):
        value = os.environ.get(key, default)
    return str(value or default)


def get_google_service_account_info() -> dict | None:
    """Load the same Google service-account format used by Creator Scanner / Flow Fashion."""
    try:
        raw = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    except Exception:
        raw = None
    if raw:
        if isinstance(raw, dict):
            return dict(raw)
        try:
            return json.loads(str(raw))
        except Exception:
            pass
    try:
        raw = st.secrets.get("gcp_service_account")
        if raw:
            return dict(raw)
    except Exception:
        pass
    env_raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if env_raw:
        try:
            return json.loads(env_raw)
        except Exception:
            pass
    return None


def _column_letter(index: int) -> str:
    out = ""
    n = int(index)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _scanner_queue_sheet():
    info = get_google_service_account_info()
    sheet_ref = get_secret("GOOGLE_SHEET_URL").strip()
    if not info or not sheet_ref:
        raise RuntimeError(
            "Google Sheets is not configured in Momentum Sniper. Add GOOGLE_SHEET_URL and the same Google service-account credential used by Flow Fashion."
        )
    try:
        import gspread
    except Exception as exc:
        raise RuntimeError(
            "gspread is missing. Add gspread to the Momentum Sniper requirements.txt."
        ) from exc
    gc = gspread.service_account_from_dict(info)
    book = gc.open_by_url(sheet_ref) if sheet_ref.startswith(("http://", "https://")) else gc.open_by_key(sheet_ref)
    try:
        ws = book.worksheet("Scanner Queue")
    except gspread.WorksheetNotFound:
        # Keep J:L exactly compatible with Flow Fashion's existing Scanner Queue importer.
        headers = [
            "Product Name", "Product Link", "Creators", "Creator Count",
            "Video Count", "Combined Views", "Product Image", "Seller",
            "Queued At", "Status", "Imported At", "Batch ID",
        ]
        ws = book.add_worksheet(title="Scanner Queue", rows=1000, cols=24)
        ws.update(range_name="A1", values=[headers], value_input_option="RAW")
    return ws


def send_run_to_fashion_flow_queue(
    df: pd.DataFrame,
    preset_name: str,
    source_file: str,
) -> tuple[bool, str]:
    """Append a saved Sniper run to the same Scanner Queue used by Creator Scanner."""
    if df.empty:
        return False, "This Sniper run has no products to queue."
    try:
        ws = _scanner_queue_sheet()
        values = ws.get_all_values()
        headers = list(values[0]) if values else []

        # These are appended AFTER the existing queue columns so Flow Fashion's
        # Status / Imported At / Batch ID columns remain J:K:L.
        extra_headers = [
            "Source", "Source Batch ID", "Preset", "Source File",
            "Ads Top10", "Avg Price", "Commission %", "Per Sale $",
            "Revenue 7d", "Growth %",
        ]
        missing = [h for h in extra_headers if h not in headers]
        if missing:
            start_col = len(headers) + 1
            ws.update(
                range_name=f"{_column_letter(start_col)}1",
                values=[missing],
                value_input_option="RAW",
            )
            headers.extend(missing)

        raw_rows = []
        product_links = []
        for raw in df.to_dict(orient="records"):
            row = {str(k): clean_value(v) for k, v in raw.items()}
            link = str(row.get("tiktok_link") or row.get("product_link") or "").strip()
            if not link.startswith(("http://", "https://")):
                continue
            product_links.append(link)
            raw_rows.append(row)
        if not raw_rows:
            return False, "This CSV does not contain any valid TikTok product links."

        identity = "|".join([str(preset_name or ""), str(source_file or "")] + product_links)
        source_batch_id = "momentum-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

        existing = set()
        if len(values) > 1:
            idx = {name: i for i, name in enumerate(headers)}
            for old in values[1:]:
                batch_id = old[idx["Source Batch ID"]] if idx.get("Source Batch ID") is not None and idx["Source Batch ID"] < len(old) else ""
                link = old[idx["Product Link"]] if idx.get("Product Link") is not None and idx["Product Link"] < len(old) else ""
                if batch_id == source_batch_id and link:
                    existing.add(link)

        queued_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        rows_to_append = []
        for row in raw_rows:
            link = str(row.get("tiktok_link") or row.get("product_link") or "").strip()
            if link in existing:
                continue
            record = {
                "Product Name": str(row.get("product") or row.get("product_name") or "Unknown Product").strip(),
                "Product Link": link,
                "Creators": row.get("creators") or "",
                "Creator Count": "",
                "Video Count": "",
                "Combined Views": "",
                "Product Image": row.get("image_url") or "",
                "Seller": row.get("shop") or "",
                "Queued At": queued_at,
                "Status": "Pending",
                "Imported At": "",
                "Batch ID": "",
                "Source": "Momentum Sniper",
                "Source Batch ID": source_batch_id,
                "Preset": preset_name or "Custom",
                "Source File": source_file,
                "Ads Top10": row.get("ads_top10") or "",
                "Avg Price": row.get("avg_price") or "",
                "Commission %": row.get("commission_pct") or "",
                "Per Sale $": row.get("per_sale_$") or "",
                "Revenue 7d": row.get("revenue_7d") or "",
                "Growth %": row.get("growth_pct") or "",
            }
            rows_to_append.append([record.get(h, "") for h in headers])

        if not rows_to_append:
            return True, f"This Sniper run is already waiting in Fashion Flow ({source_batch_id})."

        ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        return True, (
            f"Sent {len(rows_to_append)} product(s) to Fashion Flow via Scanner Queue. "
            f"Open Flow Fashion, choose the avatar, then choose an open avatar batch or start a new one."
        )
    except Exception as exc:
        return False, f"Could not send to Fashion Flow Scanner Queue: {exc}"


def check_password() -> bool:
    """Simple shared-password gate. Set APP_PASSWORD in Streamlit secrets."""
    if st.session_state.get("authed"):
        return True

    def on_submit() -> None:
        expected = get_secret("APP_PASSWORD")
        st.session_state["authed"] = bool(
            expected and st.session_state.get("pw_input") == expected
        )

    st.text_input("Password", type="password", key="pw_input", on_change=on_submit)
    if st.session_state.get("authed") is False:
        st.error("Wrong password.")
    return False


def clean_value(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-safe Python values."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def parse_image_candidates(value: Any) -> list[str]:
    """Read the optional JSON candidate list written by newer sniper runs."""
    if value is None:
        return []
    parsed: Any = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in text.split("|") if part.strip()]
    if not isinstance(parsed, list):
        return []
    result: list[str] = []
    for item in parsed:
        url = str(item or "").strip()
        if url.startswith(("http://", "https://")) and url not in result:
            result.append(url)
    return result


def dataframe_to_seedance_products(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Send only TikTok links plus Sniper research data to Seedance.

    Seedance deliberately re-scrapes every TikTok link with its normal product
    scraper so it can collect the same official listing photos and customer
    review photos that appear when links are pasted directly into Seedance.
    """
    products: list[dict[str, Any]] = []
    for raw_row in df.to_dict(orient="records"):
        row = {str(key): clean_value(value) for key, value in raw_row.items()}
        name = str(row.get("product") or row.get("product_name") or "Unknown Product").strip()
        source_url = str(row.get("tiktok_link") or row.get("product_link") or "").strip()
        if not source_url.startswith(("http://", "https://")):
            continue

        metadata = {
            key: value
            for key, value in row.items()
            if value not in (None, "")
        }
        products.append(
            {
                "name": name,
                "source_url": source_url,
                "caption": str(row.get("caption") or "").strip(),
                "scene_prompt": str(row.get("scene_prompt") or "").strip(),
                "sniper_meta": metadata,
                "transfer_mode": "tiktok_link_rescrape",
            }
        )
    return products


def queue_config() -> dict[str, str]:
    return {
        "token": get_secret("SEEDANCE_QUEUE_GITHUB_TOKEN").strip(),
        "repo": get_secret("SEEDANCE_QUEUE_REPO").strip().strip("/"),
        "branch": get_secret("SEEDANCE_QUEUE_BRANCH", "main").strip() or "main",
        "path": get_secret("SEEDANCE_QUEUE_PATH", "seedance_inbox").strip().strip("/") or "seedance_inbox",
        "history_path": get_secret("SNIPER_HISTORY_GITHUB_PATH", "sniper_history").strip().strip("/") or "sniper_history",
        "app_url": get_secret("SEEDANCE_APP_URL").strip(),
    }


def github_api_request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | None, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "momentum-sniper-seedance-bridge",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", "replace")
            parsed = json.loads(body) if body else None
            return response.status, parsed, ""
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        message = ""
        if isinstance(parsed, dict):
            message = str(parsed.get("message") or parsed)
        return exc.code, parsed, message or body[:500]
    except Exception as exc:
        return 0, None, str(exc)



def preset_from_csv_name(filename: str) -> str:
    """Recover the Kalodata preset from old and timestamped CSV filenames."""
    stem = pathlib.Path(filename).stem
    if stem.startswith("snipe-"):
        stem = stem[len("snipe-"):]
    stem = re.sub(
        r"-\d{4}-\d{2}-\d{2}(?:_\d{2}-\d{2}-\d{2})?$",
        "",
        stem,
    )
    return stem or "Unknown"


def archive_csv_to_github(csv_path: pathlib.Path) -> tuple[bool, str]:
    """Persist one CSV in the same private GitHub repo used by the Seedance queue."""
    config = queue_config()
    if not config.get("token") or not config.get("repo"):
        return False, "Private CSV history is not configured."

    archive_path = f"{config['history_path']}/{csv_path.name}"
    encoded_path = urllib.parse.quote(archive_path, safe="/")
    endpoint = f"https://api.github.com/repos/{config['repo']}/contents/{encoded_path}"
    payload = {
        "message": f"Archive Momentum Sniper run {csv_path.name}",
        "content": base64.b64encode(csv_path.read_bytes()).decode("ascii"),
        "branch": config["branch"],
    }
    status, _response, error = github_api_request(
        "PUT", endpoint, config["token"], payload
    )
    if status in (200, 201):
        return True, f"Archived {csv_path.name} to private run history."
    if status == 422:
        get_url = endpoint + "?" + urllib.parse.urlencode({"ref": config["branch"]})
        get_status, _existing, _get_error = github_api_request(
            "GET", get_url, config["token"]
        )
        if get_status == 200:
            return True, f"{csv_path.name} is already in private run history."
    return False, f"Could not archive {csv_path.name}: {error or f'HTTP {status}'}"


def list_archived_csvs() -> tuple[list[dict[str, Any]], str | None]:
    """List CSVs stored in the private GitHub history folder."""
    config = queue_config()
    if not config.get("token") or not config.get("repo"):
        return [], None

    encoded_path = urllib.parse.quote(config["history_path"], safe="/")
    endpoint = (
        f"https://api.github.com/repos/{config['repo']}/contents/{encoded_path}?"
        + urllib.parse.urlencode({"ref": config["branch"]})
    )
    status, response, error = github_api_request(
        "GET", endpoint, config["token"]
    )
    if status == 404:
        return [], None
    if status != 200 or not isinstance(response, list):
        return [], error or f"HTTP {status}"

    entries = []
    for item in response:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if item.get("type") == "file" and name.lower().endswith(".csv"):
            entries.append({
                "name": name,
                "path": str(item.get("path") or ""),
                "sha": str(item.get("sha") or ""),
                "size": int(item.get("size") or 0),
            })
    entries.sort(key=lambda item: item["name"], reverse=True)
    return entries, None


def read_archived_csv_bytes(repo_path: str) -> tuple[bytes | None, str | None]:
    """Download one private archived CSV through the authenticated contents API."""
    config = queue_config()
    encoded_path = urllib.parse.quote(repo_path, safe="/")
    endpoint = (
        f"https://api.github.com/repos/{config['repo']}/contents/{encoded_path}?"
        + urllib.parse.urlencode({"ref": config["branch"]})
    )
    status, response, error = github_api_request(
        "GET", endpoint, config["token"]
    )
    if status != 200 or not isinstance(response, dict):
        return None, error or f"HTTP {status}"
    encoded = str(response.get("content") or "").replace("\n", "")
    if not encoded:
        return None, "GitHub returned an empty CSV."
    try:
        return base64.b64decode(encoded), None
    except Exception as exc:
        return None, f"Could not decode archived CSV: {exc}"



def send_batch_to_seedance(
    csv_path: pathlib.Path,
    df: pd.DataFrame,
    preset_name: str,
) -> tuple[bool, str, str | None]:
    """Create one JSON batch file in a dedicated private GitHub queue repo."""
    config = queue_config()
    missing = [
        key
        for key in ("token", "repo")
        if not config.get(key)
    ]
    if missing:
        return False, "Seedance queue is not configured in Streamlit Secrets.", None

    products = dataframe_to_seedance_products(df)
    if not products:
        return False, "The CSV does not contain any products to send.", None

    batch_id = hashlib.sha256(csv_path.read_bytes() + b"|tiktok-link-rescrape-v2").hexdigest()[:20]
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    payload = {
        "schema": QUEUE_SCHEMA,
        "batch_id": batch_id,
        "status": "pending",
        "source": "Momentum Sniper",
        "source_file": csv_path.name,
        "preset": preset_name,
        "created_at": created_at,
        "product_count": len(products),
        "transfer_mode": "tiktok_link_rescrape",
        "products": products,
    }

    queue_path = f"{config['path']}/{batch_id}.json"
    encoded_path = urllib.parse.quote(queue_path, safe="/")
    endpoint = f"https://api.github.com/repos/{config['repo']}/contents/{encoded_path}"
    put_payload = {
        "message": f"Queue Momentum Sniper batch {batch_id}",
        "content": base64.b64encode(
            json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        ).decode("ascii"),
        "branch": config["branch"],
    }
    status, response, error = github_api_request(
        "PUT", endpoint, config["token"], put_payload
    )

    if status in (200, 201):
        message = f"Sent {len(products)} product(s) to the Seedance inbox."
    elif status == 422:
        # A deterministic filename prevents duplicate queue entries. Treat an
        # existing path as already queued instead of creating a second batch.
        get_url = endpoint + "?" + urllib.parse.urlencode({"ref": config["branch"]})
        get_status, _existing, _get_error = github_api_request(
            "GET", get_url, config["token"]
        )
        if get_status == 200:
            message = f"This {len(products)}-product batch is already waiting in Seedance."
        else:
            return False, f"GitHub queue rejected the batch: {error or 'HTTP 422'}", None
    else:
        return False, f"Could not send to the Seedance queue: {error or f'HTTP {status}'}", None

    handoff_url = None
    if config.get("app_url"):
        separator = "&" if "?" in config["app_url"] else "?"
        handoff_url = (
            f"{config['app_url']}{separator}"
            + urllib.parse.urlencode({"sniper_batch": queue_path})
        )
    return True, message, handoff_url


if not check_password():
    st.stop()

# On Streamlit Cloud there's no .env file — bridge secrets -> .env once so
# snipe.py can read credentials the same way it does locally.
env_path = BASE / ".env"
if not env_path.exists():
    required = ["KALODATA_EMAIL", "KALODATA_PASSWORD", "FIRECRAWL_API_KEY"]
    optional = ["DIRECTOR_INGEST_KEY", "DIRECTOR_INGEST_URL"]
    missing = [key for key in required if not get_secret(key)]
    if missing:
        st.error(f"Missing secret(s) in Streamlit Cloud settings: {', '.join(missing)}")
        st.stop()
    lines = [f"{key}={get_secret(key)}" for key in required]
    lines += [f"{key}={get_secret(key)}" for key in optional if get_secret(key)]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)

st.title("🎯 Momentum Sniper")
st.caption(
    "Pick a preset, run the hunt, then send any current or older run to Seedance or Fashion Flow."
)

preset_choice = st.selectbox("Preset", MOMENTUM_PRESETS + ["Custom…"])
if preset_choice == "Custom…":
    preset = st.text_input(
        "Custom preset name (must match a filter saved in Kalodata)"
    ).strip()
else:
    preset = preset_choice

run_clicked = st.button("Run sniper", type="primary", disabled=not preset)

if run_clicked:
    log_box = st.empty()
    lines: list[str] = []
    with st.spinner(f"Running sniper on '{preset}'… this usually takes 5–10 minutes."):
        proc = subprocess.Popen(
            [sys.executable, str(BASE / "snipe.py"), preset],
            cwd=str(BASE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip())
            log_box.code("\n".join(lines[-40:]))
        proc.wait()
    if proc.returncode == 0:
        st.success("Done — see results below.")
        completed_csvs = sorted(
            BASE.glob("snipe-*.csv"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if completed_csvs:
            archived, archive_message = archive_csv_to_github(completed_csvs[0])
            if archived:
                st.session_state["history_archive_message"] = archive_message
            else:
                st.session_state["history_archive_warning"] = archive_message
            try:
                latest_df = pd.read_csv(completed_csvs[0])
                queued, queue_message = send_run_to_fashion_flow_queue(
                    latest_df, preset, completed_csvs[0].name
                )
                key = "fashion_flow_queue_message" if queued else "fashion_flow_queue_warning"
                st.session_state[key] = queue_message
            except Exception as exc:
                st.session_state["fashion_flow_queue_warning"] = f"Automatic Fashion Flow queue push failed: {exc}"
    else:
        st.error("Run failed — see log above for the error.")

st.divider()
st.subheader("Run history")
st.caption(
    "Open, preview, download, and resend any saved CSV. New runs use a timestamped filename, "
    "so running the same preset twice in one day no longer overwrites the earlier file."
)

if st.session_state.pop("history_archive_message", None):
    st.success("The newest CSV was also saved to the private GitHub run archive.")
archive_warning = st.session_state.pop("history_archive_warning", None)
if archive_warning:
    st.warning(archive_warning)
fashion_queue_message = st.session_state.pop("fashion_flow_queue_message", None)
if fashion_queue_message:
    st.success(fashion_queue_message)
fashion_queue_warning = st.session_state.pop("fashion_flow_queue_warning", None)
if fashion_queue_warning:
    st.warning(fashion_queue_warning)

local_csvs = sorted(
    BASE.glob("snipe-*.csv"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)
archived_csvs, archive_list_error = list_archived_csvs()

# Combine local and private-history copies by filename. Prefer the local copy when both exist.
history_by_name: dict[str, dict[str, Any]] = {}
for path in local_csvs:
    history_by_name[path.name] = {
        "name": path.name,
        "source": "Local",
        "local_path": path,
        "repo_path": None,
        "size": path.stat().st_size,
        "modified": path.stat().st_mtime,
    }
for item in archived_csvs:
    existing = history_by_name.get(item["name"])
    if existing:
        existing["repo_path"] = item["path"]
        existing["source"] = "Local + private archive"
    else:
        history_by_name[item["name"]] = {
            "name": item["name"],
            "source": "Private archive",
            "local_path": None,
            "repo_path": item["path"],
            "size": item.get("size", 0),
            "modified": 0,
        }

history_entries = sorted(
    history_by_name.values(),
    key=lambda entry: (entry.get("modified", 0), entry["name"]),
    reverse=True,
)

if archive_list_error:
    st.warning(f"Could not load the private CSV archive: {archive_list_error}")

if not history_entries:
    st.info("No runs yet. Pick a preset above and hit Run sniper.")
else:
    controls_col_1, controls_col_2 = st.columns([2.4, 1])
    with controls_col_1:
        selected_name = st.selectbox(
            "Choose a run",
            options=[entry["name"] for entry in history_entries],
            key="selected_csv_history",
        )
    with controls_col_2:
        st.write("")
        sync_clicked = st.button(
            "☁️ Archive local CSVs",
            use_container_width=True,
            disabled=not bool(queue_config().get("token") and queue_config().get("repo")),
            help="Copies every local CSV into the private GitHub queue repository so it survives Streamlit restarts and redeploys.",
        )

    if sync_clicked:
        synced = 0
        failures = []
        progress = st.progress(0, text="Archiving local CSVs…")
        for index, csv_path in enumerate(local_csvs, start=1):
            progress.progress((index - 1) / max(1, len(local_csvs)), text=f"Archiving {csv_path.name}")
            ok, message = archive_csv_to_github(csv_path)
            if ok:
                synced += 1
            else:
                failures.append(message)
        progress.progress(1.0, text="Archive sync complete")
        if synced:
            st.success(f"Archived {synced} local CSV run(s).")
        for failure in failures:
            st.error(failure)
        st.rerun()

    selected_entry = next(
        entry for entry in history_entries if entry["name"] == selected_name
    )
    selected_bytes: bytes | None = None
    selected_error: str | None = None
    local_path = selected_entry.get("local_path")
    if isinstance(local_path, pathlib.Path) and local_path.exists():
        selected_bytes = local_path.read_bytes()
    elif selected_entry.get("repo_path"):
        selected_bytes, selected_error = read_archived_csv_bytes(
            str(selected_entry["repo_path"])
        )

    st.caption(
        f"Storage: {selected_entry['source']} · "
        f"{int(selected_entry.get('size') or 0):,} bytes"
    )

    if selected_error or not selected_bytes:
        st.error(selected_error or "This CSV could not be loaded.")
    else:
        try:
            selected_df = pd.read_csv(io.BytesIO(selected_bytes))
        except Exception as exc:
            selected_df = pd.DataFrame()
            st.error(f"Could not read this CSV: {exc}")

        if not selected_df.empty:
            st.dataframe(selected_df, use_container_width=True)

            action_col_1, action_col_2, action_col_3 = st.columns(3)
            with action_col_1:
                st.download_button(
                    "⬇️ Download selected CSV",
                    selected_bytes,
                    file_name=selected_entry["name"],
                    use_container_width=True,
                )
            with action_col_2:
                config = queue_config()
                queue_ready = bool(config["token"] and config["repo"])
                send_clicked = st.button(
                    "🚀 Send selected run to Seedance",
                    type="primary",
                    use_container_width=True,
                    disabled=not queue_ready,
                    help=(
                        "Queues the TikTok links, names, captions, scene prompts, and Sniper metrics. "
                        "Seedance then re-scrapes every link for official and review photos."
                    ),
                )
            with action_col_3:
                flow_sheet_ready = bool(
                    get_secret("GOOGLE_SHEET_URL").strip()
                    and get_google_service_account_info()
                )
                flow_send_clicked = st.button(
                    "👗 Send to Fashion Flow",
                    use_container_width=True,
                    disabled=not flow_sheet_ready,
                    help=(
                        "Queues this saved run into the same Scanner Queue used by Creator Scanner. "
                        "In Flow Fashion you choose the saved avatar and destination batch before importing."
                    ),
                )

            if not queue_ready:
                st.info(
                    "To enable Seedance handoff and permanent CSV history, add "
                    "`SEEDANCE_QUEUE_GITHUB_TOKEN` and `SEEDANCE_QUEUE_REPO` to this app's Streamlit Secrets."
                )

            if not flow_sheet_ready:
                st.info(
                    "To enable **Send to Fashion Flow**, give Momentum Sniper the same `GOOGLE_SHEET_URL` "
                    "and Google service-account credential used by Creator Scanner / Flow Fashion."
                )

            if flow_send_clicked:
                with st.spinner("Sending this saved run to the Fashion Flow Scanner Queue…"):
                    flow_ok, flow_message = send_run_to_fashion_flow_queue(
                        selected_df,
                        preset_from_csv_name(selected_entry["name"]),
                        selected_entry["name"],
                    )
                if flow_ok:
                    st.success(flow_message)
                else:
                    st.error(flow_message)

            if send_clicked:
                send_path = local_path
                if not isinstance(send_path, pathlib.Path) or not send_path.exists():
                    cache_dir = BASE / ".csv_history_cache"
                    cache_dir.mkdir(exist_ok=True)
                    send_path = cache_dir / selected_entry["name"]
                    send_path.write_bytes(selected_bytes)
                with st.spinner("Sending TikTok links and Sniper data to Seedance Studio…"):
                    ok, message, handoff_url = send_batch_to_seedance(
                        send_path,
                        selected_df,
                        preset_from_csv_name(selected_entry["name"]),
                    )
                if ok:
                    st.success(message)
                    st.session_state["latest_seedance_handoff_url"] = handoff_url
                else:
                    st.error(message)

            handoff_url = st.session_state.get("latest_seedance_handoff_url")
            if handoff_url:
                try:
                    st.link_button(
                        "Open this batch in Seedance Studio ↗",
                        handoff_url,
                        use_container_width=True,
                    )
                except AttributeError:
                    st.markdown(f"[Open this batch in Seedance Studio ↗]({handoff_url})")

            # Show locally downloaded product photos when they still exist.
            imgdir = BASE / "sniped-products"
            if imgdir.exists() and "image_file" in selected_df.columns:
                wanted = set(selected_df["image_file"].dropna().astype(str))
                imgs = [
                    imgdir / filename
                    for filename in wanted
                    if (imgdir / filename).exists()
                ]
                if imgs:
                    st.markdown("#### Downloaded product images")
                    cols = st.columns(4)
                    for index, image_path in enumerate(imgs):
                        with cols[index % 4]:
                            st.image(
                                str(image_path),
                                caption=image_path.stem,
                                use_container_width=True,
                            )

