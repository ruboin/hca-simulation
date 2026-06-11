import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sankey.heizkosten as hk  # noqa: E402

# App default inputs (mirrors the sidebar defaults in app.py)
SYSTEM_INPUTS = dict(
    brennstoff_kwh=44000.0,
    brennstoff_eur=5280.0,
    weitere_kosten_eur=980.0,
    geraetemiete_ww_eur=345.0,
    geraetemiete_hz_eur=265.0,
    warmwasser_kwh=9680.0,        # 22 % of brennstoff_kwh
    verteilung_ww=0.30,
    verteilung_hz=0.40,
)
CO2_VERMIETER_EUR = 128.0          # 320 € × 40 %


@pytest.fixture
def sc() -> "hk.SystemCosts":
    return hk.compute_system_costs(**SYSTEM_INPUTS, co2_vermieter_eur=CO2_VERMIETER_EUR)


def assert_flows_balanced(flows):
    """Every node that has both inflow and outflow must conserve value."""
    inflow, outflow = {}, {}
    for f in flows:
        outflow[f["source"]] = outflow.get(f["source"], 0.0) + f["weight"]
        inflow[f["target"]] = inflow.get(f["target"], 0.0) + f["weight"]
    for node in set(inflow) & set(outflow):
        assert abs(inflow[node] - outflow[node]) < 1e-6, (
            f"Imbalance at {node!r}: in={inflow[node]:.6f} out={outflow[node]:.6f}"
        )
    assert all(f["weight"] > 0 for f in flows)
