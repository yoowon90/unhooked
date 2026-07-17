"""Sales-tax helpers shared across views, api, and backfill.

Tax estimation rules (for clothing/accessories — this app's primary use case):

1. NYC zipcodes (24 specific 5-digit zips): 0% under $110, 8.75% at/above $110
   (NY clothing exemption + NYC combined state+local rate of 8.875% rounded down).
2. Per-zip override via OTHER_TAX_RATES (kept for backwards compat with the
   pre-existing 15206 = 0% entry, even though PA-state below also yields 0%).
3. Clothing-exempt states (PA, NJ, MN, RI, VT): 0% — clothing is fully exempt
   from sales tax in these states.
4. New York state (non-NYC zips): 0% under $110, 4% at/above $110 (state base
   only — local county rates may push the effective rate higher and are not
   modeled here).
5. All other states: STATE_TAX_RATES base rate, looked up via ZIP3 → state.
6. Unknown zip / unknown state: 0%.

Limitations: state base rates only. Local/county/city rates on top are not
included (e.g. Chicago's effective ~10.25% will be reported as IL's 6.25%).
ZIP-to-state mapping is by ZIP3 range — accurate for ~99% of US zips; a small
number of border-town zips may resolve to the wrong state.
"""

NYC_TAX_RATE = 0.0875
NYC_CLOTHING_EXEMPTION = 110.00
NY_STATE_TAX_RATE = 0.04

# Manhattan, Brooklyn, Queens, Bronx, Staten Island.
NYC_ZIPCODES = frozenset([
    '10001', '10011', '11019', '10023', '10128',
    '11201', '11211', '11217', '11231', '11238',
    '11101', '11354', '11375', '11432', '11691',
    '10451', '10452', '10463', '10467', '10469',
    '10301', '10304', '10306', '10314',
])

# Per-zipcode overrides (rare). Most per-state rules belong in STATE_TAX_RATES
# or CLOTHING_EXEMPT_STATES; use this only when a single zip needs to deviate.
OTHER_TAX_RATES = {
    '15206': 0.0,  # Pittsburgh — redundant with PA clothing exemption, kept for parity
}

# States where clothing is fully exempt from sales tax.
CLOTHING_EXEMPT_STATES = frozenset({'PA', 'NJ', 'MN', 'RI', 'VT'})

# State base sales-tax rates (state portion only — local rates not included).
# Approximate as of 2025; revisit when states adjust their rates.
STATE_TAX_RATES = {
    'AL': 0.04,    'AK': 0.0,     'AZ': 0.056,   'AR': 0.065,
    'CA': 0.0725,  'CO': 0.029,   'CT': 0.0635,  'DC': 0.06,
    'DE': 0.0,     'FL': 0.06,    'GA': 0.04,    'HI': 0.04,
    'ID': 0.06,    'IL': 0.0625,  'IN': 0.07,    'IA': 0.06,
    'KS': 0.065,   'KY': 0.06,    'LA': 0.0445,  'ME': 0.055,
    'MD': 0.06,    'MA': 0.0625,  'MI': 0.06,    'MS': 0.07,
    'MO': 0.04225, 'MT': 0.0,     'NE': 0.055,   'NV': 0.0685,
    'NH': 0.0,     'NM': 0.05125, 'NY': NY_STATE_TAX_RATE,
    'NC': 0.0475,  'ND': 0.05,    'OH': 0.0575,  'OK': 0.045,
    'OR': 0.0,     'SC': 0.06,    'SD': 0.045,   'TN': 0.07,
    'TX': 0.0625,  'UT': 0.0485,  'VA': 0.053,   'WA': 0.065,
    'WV': 0.06,    'WI': 0.05,    'WY': 0.04,
    # Clothing-exempt states (rate listed for completeness; CLOTHING_EXEMPT_STATES wins)
    'PA': 0.06,    'NJ': 0.06625, 'MN': 0.06875, 'RI': 0.07,    'VT': 0.06,
}

# ZIP3-range to state mapping. Each tuple is (state_code, low_5_digit, high_5_digit).
# Sorted ascending by low for clarity. Unmapped ranges fall through to 0% tax.
STATE_ZIP_RANGES = [
    ('MA',  1000,  2799),  # 010-027
    ('RI',  2800,  2999),  # 028-029
    ('NH',  3000,  3899),  # 030-038
    ('ME',  3900,  4999),  # 039-049
    ('VT',  5000,  5999),  # 050-059
    ('CT',  6000,  6999),  # 060-069
    ('NJ',  7000,  8999),  # 070-089
    ('NY', 10000, 14999),  # 100-149 (NYC zips override above)
    ('PA', 15000, 19699),  # 150-196
    ('DE', 19700, 19999),  # 197-199
    ('DC', 20000, 20599),  # 200-205
    ('MD', 20600, 21999),  # 206-219
    ('VA', 22000, 24699),  # 220-246
    ('WV', 24700, 26899),  # 247-268
    ('NC', 27000, 28999),  # 270-289
    ('SC', 29000, 29999),  # 290-299
    ('GA', 30000, 31999),  # 300-319
    ('FL', 32000, 34999),  # 320-349
    ('AL', 35000, 36999),  # 350-369
    ('TN', 37000, 38599),  # 370-385
    ('MS', 38600, 39799),  # 386-397
    ('GA', 39800, 39999),  # 398-399 (Atlanta annexed)
    ('KY', 40000, 42799),  # 400-427
    ('OH', 43000, 45899),  # 430-458
    ('IN', 46000, 47999),  # 460-479
    ('MI', 48000, 49999),  # 480-499
    ('IA', 50000, 52899),  # 500-528
    ('WI', 53000, 54999),  # 530-549
    ('MN', 55000, 56799),  # 550-567
    ('SD', 57000, 57799),  # 570-577
    ('ND', 58000, 58899),  # 580-588
    ('MT', 59000, 59999),  # 590-599
    ('IL', 60000, 62999),  # 600-629
    ('MO', 63000, 65899),  # 630-658
    ('KS', 66000, 67999),  # 660-679
    ('NE', 68000, 69399),  # 680-693
    ('LA', 70000, 71499),  # 700-714
    ('AR', 71600, 72999),  # 716-729
    ('OK', 73000, 74999),  # 730-749
    ('TX', 75000, 79999),  # 750-799
    ('CO', 80000, 81699),  # 800-816
    ('WY', 82000, 83199),  # 820-831
    ('ID', 83200, 83899),  # 832-838
    ('UT', 84000, 84799),  # 840-847
    ('AZ', 85000, 86599),  # 850-865
    ('NM', 87000, 88499),  # 870-884
    ('TX', 88500, 88599),  # 885 (El Paso)
    ('NV', 88900, 89899),  # 889-898
    ('CA', 90000, 96199),  # 900-961
    ('HI', 96700, 96899),  # 967-968
    ('OR', 97000, 97999),  # 970-979
    ('WA', 98000, 99499),  # 980-994
    ('AK', 99500, 99999),  # 995-999
]


from .cache import TTLCache


_zip_cache = TTLCache(default_ttl=3600)


def state_for_zip(zipcode):
    """Return the 2-letter US state code for a 5-digit zipcode, or None if unknown."""
    if not zipcode or len(zipcode) != 5 or not zipcode.isdigit():
        return None
    return _zip_cache.get(zipcode, lambda: _resolve_state(zipcode))


def _resolve_state(zipcode):
    z = int(zipcode)
    for state, low, high in STATE_ZIP_RANGES:
        if low <= z <= high:
            return state
    return None


def tax_rate(zipcode, price):
    """Return the effective sales-tax rate (a float, e.g. 0.0875) for a given zipcode and item price.

    See module docstring for the rule order.
    """
    if zipcode in NYC_ZIPCODES:
        return 0.0 if price < NYC_CLOTHING_EXEMPTION else NYC_TAX_RATE
    if zipcode in OTHER_TAX_RATES:
        return OTHER_TAX_RATES[zipcode]
    state = state_for_zip(zipcode)
    if state in CLOTHING_EXEMPT_STATES:
        return 0.0
    if state == 'NY':
        # NY-state-but-not-NYC: same $110 threshold for the state portion.
        return 0.0 if price < NYC_CLOTHING_EXEMPTION else NY_STATE_TAX_RATE
    if state in STATE_TAX_RATES:
        return STATE_TAX_RATES[state]
    return 0.0


def taxed_price(zipcode, price, round_to=2):
    """Return the price after applying the appropriate tax rate, rounded to `round_to` decimals."""
    return round(price * (1 + tax_rate(zipcode, price)), round_to)
