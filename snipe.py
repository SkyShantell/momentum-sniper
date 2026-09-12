#!/usr/bin/env python3
"""Momentum Sniper V22 entrypoint."""
import snipe_legacy as _legacy
from creator_json_v22 import install as _install_creator_json_v22

_install_creator_json_v22(_legacy)

if __name__ == "__main__":
    _legacy.main()
