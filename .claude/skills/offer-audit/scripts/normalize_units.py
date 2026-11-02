#!/usr/bin/env python3
"""Deterministic unit conversion to the audit SI baseline.

Baseline units per dimension:
  force MN | power kW | gas flow Nm3/h | liquid flow m3/h | length mm
  pressure bar | mass rate kg/h | mass kg | time s | temperature degC
  specific gas Nm3/t | specific energy kWh/t | energy kWh | speed mm/s
  volume m3 | area m2 | currency is never converted here

Press convention: "MT", "MTon", "t" used as a force rating means metric
tonne-force (9.80665 kN). "US ton", "short ton", "UST" means short
ton-force (8.896443 kN). Ambiguous "ton" is refused, not guessed.

CLI (every call prints JSON, paste it into derivation.tool_output):
  normalize_units.py convert 25 MN
  normalize_units.py convert 2800 "US ton"
  normalize_units.py convert 85 kW --to hp
  normalize_units.py sum "120 Nm3/h" "430 Nm3/h"
  normalize_units.py per-tonne "430 Nm3/h" "4000 kg/h"
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# unit alias -> (dimension, factor to baseline, offset) ; baseline = value*factor + offset
_U: dict[str, tuple[str, float, float]] = {}


def _reg(dim: str, factor: float, *aliases: str, offset: float = 0.0) -> None:
    for al in aliases:
        _U[_key(al)] = (dim, factor, offset)


def _key(u: str) -> str:
    u = u.strip().replace("³", "3").replace("²", "2").replace("°", "deg").replace("º", "deg")
    u = u.replace("·", "").replace(" ", "").replace("_", "")
    return u.lower()


BASE = {
    "force": "MN", "power": "kW", "gas_flow": "Nm3/h", "liquid_flow": "m3/h", "length": "mm",
    "pressure": "bar", "mass_rate": "kg/h", "mass": "kg", "time": "s", "temperature": "degC",
    "specific_gas": "Nm3/t", "specific_energy": "kWh/t", "energy": "kWh", "speed": "mm/s",
    "volume": "m3", "area": "m2", "dimensionless": "",
}

TF = 9.80665e-3          # MN per metric tonne-force
STF = 8.896443230521e-3  # MN per short ton-force
LBF = 4.4482216152605e-6  # MN per lbf

_reg("force", 1.0, "MN", "meganewton")
_reg("force", 1e-3, "kN")
_reg("force", 1e-6, "N")
_reg("force", TF, "tf", "MT", "MTon", "MTons", "metric ton", "metric tons", "metric tonne", "tonne-force", "t-force", "tonnef", "Mton")
_reg("force", STF, "US ton", "US tons", "USton", "UST", "short ton", "short tons", "sh tn", "ton (US)")
_reg("force", LBF, "lbf")
_reg("force", 1e-3 * 9.80665e-3, "kgf")

_reg("power", 1.0, "kW")
_reg("power", 1e-3, "W")
_reg("power", 1e3, "MW")
_reg("power", 0.745699872, "hp", "HP", "bhp")
_reg("power", 0.73549875, "CV", "PS", "metric hp")
_reg("power", 1.0, "kVA_as_kW_pf1")  # explicit only

_reg("gas_flow", 1.0, "Nm3/h", "Nm3/hr", "Nmc/h", "Sm3/h_as_N")
_reg("gas_flow", 60.0, "Nm3/min")
_reg("gas_flow", 0.06, "Nl/min", "NL/min")
_reg("gas_flow", 1.60745, "scfm", "SCFM")
_reg("gas_flow", 1.60745 / 60.0, "scfh", "SCFH")

_reg("liquid_flow", 1.0, "m3/h", "mc/h")
_reg("liquid_flow", 0.06, "l/min", "L/min", "lpm")
_reg("liquid_flow", 3.6, "l/s", "L/s")
_reg("liquid_flow", 0.003785411784 * 60, "gpm", "GPM", "US gpm")

_reg("length", 1.0, "mm")
_reg("length", 10.0, "cm")
_reg("length", 1000.0, "m")
_reg("length", 25.4, "in", "inch", "inches", '"', "''")
_reg("length", 304.8, "ft", "feet", "'")

_reg("pressure", 1.0, "bar")
_reg("pressure", 10.0, "MPa")
_reg("pressure", 0.01, "kPa")
_reg("pressure", 1e-5, "Pa")
_reg("pressure", 0.0689475729, "psi", "psig")
_reg("pressure", 0.980665, "kg/cm2", "kgf/cm2", "at")
_reg("pressure", 1e-3, "mbar")

_reg("mass_rate", 1.0, "kg/h", "kg/hr")
_reg("mass_rate", 1000.0, "t/h", "T/h", "ton/h", "tonne/h")
_reg("mass_rate", 0.45359237, "lb/h", "lbs/h", "lb/hr")

_reg("mass", 1.0, "kg")
_reg("mass", 1000.0, "t_mass", "tonne_mass")
_reg("mass", 0.45359237, "lb", "lbs")

_reg("time", 1.0, "s", "sec", "seconds")
_reg("time", 60.0, "min", "minutes")
_reg("time", 3600.0, "h", "hr", "hours")

_reg("temperature", 1.0, "degC", "C", "celsius")
_reg("temperature", 1.0, "K", offset=-273.15)
_reg("temperature", 5.0 / 9.0, "degF", "F", offset=-32.0 * 5.0 / 9.0)

_reg("specific_gas", 1.0, "Nm3/t", "Nm3/T", "Nm3/ton", "Nm3/tonne")
_reg("specific_energy", 1.0, "kWh/t", "kWh/T", "kWh/ton")
_reg("energy", 1.0, "kWh")
_reg("energy", 1000.0, "MWh")
_reg("speed", 1.0, "mm/s")
_reg("speed", 1000.0 / 60.0, "m/min")
_reg("speed", 1000.0, "m/s")
_reg("volume", 1.0, "m3")
_reg("volume", 1e-3, "l", "L", "litre", "liter")
_reg("area", 1.0, "m2")
_reg("dimensionless", 1.0, "%_raw", "pcs", "nr", "qty", "count", "x")

AMBIGUOUS = {_key(x) for x in ("ton", "tons", "t", "T", "tonne", "tonnes")}


class UnitError(ValueError):
    pass


def lookup(unit: str) -> tuple[str, float, float]:
    k = _key(unit)
    if k in AMBIGUOUS:
        raise UnitError(f"ambiguous unit {unit!r}: specify 'MT' (metric tonne-force), 'US ton' (short ton-force) or 't_mass'")
    if k not in _U:
        raise UnitError(f"unknown unit {unit!r}")
    return _U[k]


def to_si(value: float, unit: str) -> dict:
    dim, factor, offset = lookup(unit)
    return {"value": value * factor + offset, "unit": BASE[dim], "dimension": dim}


def convert(value: float, unit: str, target: str | None = None) -> dict:
    si = to_si(value, unit)
    if target is None:
        return {"input": f"{value:g} {unit}", **si}
    tdim, tfac, toff = lookup(target)
    if tdim != si["dimension"]:
        raise UnitError(f"cannot convert {si['dimension']} to {tdim}")
    out = (si["value"] - toff) / tfac
    return {"input": f"{value:g} {unit}", "value": out, "unit": target, "dimension": tdim}


_QTY = re.compile(r"^\s*(-?[\d.,]+)\s*(.+?)\s*$")


def parse_qty(s: str) -> tuple[float, str]:
    m = _QTY.match(s)
    if not m:
        raise UnitError(f"cannot parse quantity {s!r}; expected '<number> <unit>'")
    num = m.group(1)
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", num):
        num = num.replace(",", "")
    elif "," in num and "." not in num:
        num = num.replace(",", ".")
    return float(num), m.group(2)


def sum_quantities(items: list[str]) -> dict:
    parts = []
    dim = None
    total = 0.0
    for it in items:
        v, u = parse_qty(it)
        si = to_si(v, u)
        if dim is None:
            dim = si["dimension"]
        elif si["dimension"] != dim:
            raise UnitError(f"dimension mismatch: {it!r} is {si['dimension']}, expected {dim}")
        if dim == "temperature":
            raise UnitError("temperatures cannot be summed")
        parts.append({"input": it, "si_value": si["value"], "si_unit": si["unit"]})
        total += si["value"]
    return {"operation": "sum", "parts": parts, "total": round(total, 6), "unit": BASE[dim or "dimensionless"]}


def per_tonne(flow: str, rate: str) -> dict:
    fv, fu = parse_qty(flow)
    rv, ru = parse_qty(rate)
    f = to_si(fv, fu)
    r = to_si(rv, ru)
    if r["dimension"] != "mass_rate":
        raise UnitError("second argument must be a mass rate such as '4000 kg/h'")
    tph = r["value"] / 1000.0
    if tph <= 0:
        raise UnitError("production rate must be positive")
    if f["dimension"] == "gas_flow":
        unit = "Nm3/t"
    elif f["dimension"] == "power":
        unit = "kWh/t"
    elif f["dimension"] == "liquid_flow":
        unit = "m3/t"
    else:
        raise UnitError(f"per-tonne not defined for {f['dimension']}")
    return {"operation": "per_tonne", "flow": flow, "rate": rate, "value": round(f["value"] / tph, 6), "unit": unit}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("value", type=float)
    c.add_argument("unit")
    c.add_argument("--to")
    s = sub.add_parser("sum")
    s.add_argument("items", nargs="+")
    p = sub.add_parser("per-tonne")
    p.add_argument("flow")
    p.add_argument("rate")
    sub.add_parser("units")
    a = ap.parse_args()
    try:
        if a.cmd == "convert":
            out = convert(a.value, a.unit, a.to)
        elif a.cmd == "sum":
            out = sum_quantities(a.items)
        elif a.cmd == "per-tonne":
            out = per_tonne(a.flow, a.rate)
        else:
            out = {dim: sorted(k for k, v in _U.items() if v[0] == dim) for dim in BASE}
    except UnitError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
