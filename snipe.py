#!/usr/bin/env python3
"""Momentum Sniper V23 entrypoint — V22 Creator JSON + US/UK market switching."""
from __future__ import annotations

import os
from pathlib import Path

import snipe_legacy as _legacy
from creator_json_v22 import install as _install_creator_json_v22
from market_v23 import install as _install_market_v23, tag_changed_csvs

_install_creator_json_v22(_legacy)
_MARKET = os.environ.get("SNIPER_MARKET", "US")
_install_market_v23(_legacy, _MARKET)

if __name__ == "__main__":
    base = Path(__file__).parent
    before = {p.name: p.stat().st_mtime for p in base.glob("snipe-*.csv")}
    _legacy.main()
    tag_changed_csvs(base, before, _MARKET)
