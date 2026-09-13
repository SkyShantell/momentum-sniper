#!/usr/bin/env python3
"""Momentum Sniper V24 entrypoint — V23 markets + rejected-candidate review section."""
from __future__ import annotations

import os
from pathlib import Path

import snipe_legacy as _legacy
from creator_json_v22 import install as _install_creator_json_v22
from market_v23 import install as _install_market_v23, tag_changed_csvs
from cuts_v24 import install as _install_cuts_v24, append_cut_sections

_install_creator_json_v22(_legacy)
_MARKET = os.environ.get("SNIPER_MARKET", "US")
_install_market_v23(_legacy, _MARKET)
_install_cuts_v24(_legacy)

if __name__ == "__main__":
    base = Path(__file__).parent
    before = {p.name: p.stat().st_mtime for p in base.glob("snipe-*.csv")}
    _legacy.main()
    append_cut_sections(base, before, _legacy, _MARKET)
    tag_changed_csvs(base, before, _MARKET)
