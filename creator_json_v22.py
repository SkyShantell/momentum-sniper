"""Install Momentum Sniper V22 Creator JSON overrides."""
from creator_v22_common import install as _install_common
from creator_v22_lookup import install as _install_lookup
from creator_v22_vet import install as _install_vet

def install(legacy):
    _install_common(legacy)
    _install_lookup(legacy)
    _install_vet(legacy)
