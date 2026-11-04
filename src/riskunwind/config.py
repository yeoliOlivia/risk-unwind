"""
Settings shared by every module

Limits and Params class
- Variables can be fine-tuned
"""
from __future__ import annotations
import math
from dataclasses import dataclass

CAPITAL = 10_000_000.0  # starting NAV 

@dataclass(frozen=True)
class Limits:
    single_name: float = 0.05 # max |weight| of one stock
    sector: float = 0.25 # max |longs - shorts|
    var: float = 0.03   # max 1-day VaR
    days_to_liquidate: float = 5.0

@dataclass(frozen=True)
class Params:
    adv_window: int = 20 
    participation: float = 0.20 # max share of a day volume 
    var_window: int = 250   # days of history
    var_confidence: float = 0.95

# SIC = 4-digit industry code from CRSP
# no match --> 2-digit group
PREFIXES = {
    "3674": "Semiconductors", # own sector for cascade tests
    "367": "Electronic Components",
    "357": "Computer Hardware",
    "737": "Software & IT Services",
    "283": "Pharma & Biotech",
    "384": "Medical Devices",
    "80": "Healthcare Services",
    "13": "Oil & Gas",
    "29": "Oil & Gas",
    "60": "Banks",
    "61": "Credit & Lending",
    "62": "Brokers & Asset Mgmt",
    "63": "Insurance",
    "64": "Insurance",
    "65": "Real Estate",
    "67": "Investment Vehicles",
    "49": "Utilities",
    "48": "Telecom & Media",
    "35": "Industrial Machinery",
    "371": "Autos",
    "36": "Electrical Equipment",
    "37": "Transport Equipment",
    "20": "Food & Beverage",
    "52": "Retail",
    "53": "Retail",
    "54": "Retail",
    "56": "Retail",
    "57": "Retail",
    "59": "Retail",
    "40": "Transportation",
    "41": "Transportation",
    "42": "Transportation",
    "44": "Transportation",
    "45": "Transportation",
    "28": "Chemicals",
}

def sic_to_sector(sic: float | None) -> str:
    if sic is None or (isinstance(sic, float) and math.isnan(sic)):
        return "Unknown"
    code = f"{int(sic):04d}"  # pad with zeros
    for n_digits in (4, 3, 2):
        prefix = code[:n_digits]
        if prefix in PREFIXES:
            return PREFIXES[prefix]
    return f"SIC{code[:2]}"
