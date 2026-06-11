"""German number formatting (1.234,56) without a locale dependency."""


def num(value: float, decimals: int = 2) -> str:
    s = f"{value:,.{decimals}f}"                       # 1,234,567.89
    return s.translate(str.maketrans({",": ".", ".": ","}))


def eur(value: float, decimals: int = 2) -> str:
    return f"{num(value, decimals)} €"


def kwh(value: float, decimals: int = 0) -> str:
    return f"{num(value, decimals)} kWh"


def m2(value: float, decimals: int = 1) -> str:
    return f"{num(value, decimals)} m²"


def pct(fraction: float, decimals: int = 0) -> str:
    """0.305 → '30,5 %' (input is a 0..1 fraction)."""
    return f"{num(fraction * 100, decimals)} %"
