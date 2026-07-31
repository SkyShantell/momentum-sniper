"""Momentum Sniper — Streamlit front-end for snipe.py.

Lets a VA pick a preset and run the hunt without touching the terminal
or ever seeing the underlying Kalodata/Firecrawl credentials.
"""
import os
import subprocess
import sys
import pathlib

import pandas as pd
import streamlit as st

BASE = pathlib.Path(__file__).parent
MOMENTUM_PRESETS = ["HighTicket", "Lurkers", "Hardcore", "100 GAP"]

st.set_page_config(page_title="Momentum Sniper", page_icon="🎯", layout="wide")


def check_password() -> bool:
    """Simple shared-password gate. Set APP_PASSWORD in Streamlit secrets."""
    if st.session_state.get("authed"):
        return True

    def on_submit():
        expected = st.secrets.get("APP_PASSWORD", "")
        if expected and st.session_state.get("pw_input") == expected:
            st.session_state["authed"] = True
        else:
            st.session_state["authed"] = False

    st.text_input("Password", type="password", key="pw_input", on_change=on_submit)
    if st.session_state.get("authed") is False:
        st.error("Wrong password.")
    return False


if not check_password():
    st.stop()

# On Streamlit Cloud there's no .env file — bridge secrets -> .env once so
# snipe.py (unchanged) can read credentials the same way it does locally.
env_path = BASE / ".env"
if not env_path.exists():
    required = ["KALODATA_EMAIL", "KALODATA_PASSWORD", "FIRECRAWL_API_KEY"]
    optional = ["DIRECTOR_INGEST_KEY", "DIRECTOR_INGEST_URL"]
    missing = [k for k in required if k not in st.secrets]
    if missing:
        st.error(f"Missing secret(s) in Streamlit Cloud settings: {', '.join(missing)}")
        st.stop()
    lines = [f"{k}={st.secrets[k]}" for k in required]
    lines += [f"{k}={st.secrets[k]}" for k in optional if k in st.secrets]
    env_path.write_text("\n".join(lines) + "\n")
    os.chmod(env_path, 0o600)

st.title("🎯 Momentum Sniper")
st.caption("Pick a preset, run the hunt, review the results before hitting Generate All in Bulk Factory.")

preset_choice = st.selectbox("Preset", MOMENTUM_PRESETS + ["Custom…"])
if preset_choice == "Custom…":
    preset = st.text_input("Custom preset name (must match a filter saved in Kalodata)").strip()
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
        for line in proc.stdout:
            lines.append(line.rstrip())
            log_box.code("\n".join(lines[-40:]))
        proc.wait()
    if proc.returncode == 0:
        st.success("Done — see results below.")
    else:
        st.error("Run failed — see log above for the error.")

st.divider()
st.subheader("Latest results")

csvs = sorted(BASE.glob("snipe-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
if not csvs:
    st.info("No runs yet. Pick a preset above and hit Run.")
else:
    latest = csvs[0]
    st.write(f"**{latest.name}**")
    df = pd.read_csv(latest)
    st.dataframe(df, use_container_width=True)
    st.download_button("Download CSV", latest.read_bytes(), file_name=latest.name)

    imgdir = BASE / "sniped-products"
    if imgdir.exists():
        wanted = set(df["image_file"].dropna())
        imgs = [imgdir / f for f in wanted if (imgdir / f).exists()]
        if imgs:
            cols = st.columns(4)
            for i, img in enumerate(imgs):
                with cols[i % 4]:
                    st.image(str(img), caption=img.stem, use_container_width=True)

    with st.expander("Past runs"):
        for p in csvs[1:]:
            st.write(p.name)
