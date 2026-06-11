"""Heizkostenabrechnung domain package.

Import surface is kept compatible with the former single-module
``sankey.heizkosten`` so ``import sankey.heizkosten as hk`` keeps working.
"""

from . import fmt             # noqa: F401 — German number formatting helpers
from .constants import *      # noqa: F401,F403 — node names, layers, colors, limits
from .model import (          # noqa: F401
    CO2Ergebnis,
    ComputedResults,
    GewerkGroupCosts,
    GewerkResult,
    GroupConfig,
    Hinweis,
    NEConfig,
    NEResult,
    NutzerConfig,
    NutzerResult,
    ScenarioConfig,
    SystemCosts,
    WWEnergieErgebnis,
)
from .nutzerwechsel import (  # noqa: F401
    gradtag_gewicht,
    nutzer_perioden,
    split_ne_nutzer,
)
from .validate import (       # noqa: F401
    has_errors,
    validate_scenario,
)
from .compute import (        # noqa: F401
    GewerkPool,
    assemble_pools,
    co2_vermieteranteil,
    compute_all,
    compute_co2,
    compute_gewerk,
    compute_ne_results,
    compute_system_costs,
    compute_ww_energie,
    derive_group_kwh,
    pool_is_wmz_fixed,
    pool_meter_sum,
    sdiv,
)
from .report import build_report_html  # noqa: F401
