"""Bitcoin constants and cycle data."""
from datetime import date

SATOSHIS_PER_BTC = 100_000_000
MAX_SUPPLY = 21_000_000

# Halving dates (era → date)
HALVING_DATES = {
    0: date(2009, 1, 3),    # Genesis
    1: date(2012, 11, 28),
    2: date(2016, 7, 9),
    3: date(2020, 5, 11),
    4: date(2024, 4, 20),
    5: date(2028, 4, 17),   # Estimated
}

# Block reward per era (BTC)
BLOCK_REWARDS = {
    0: 50,
    1: 25,
    2: 12.5,
    3: 6.25,
    4: 3.125,
    5: 1.5625,
}

# Approximate price at each halving
HALVING_PRICES = {
    1: 12,
    2: 650,
    3: 8_700,
    4: 63_963,
}

# Cycle all-time highs
CYCLE_ATH = {
    1: {"price": 1_150, "date": date(2013, 11, 30)},
    2: {"price": 19_800, "date": date(2017, 12, 17)},
    3: {"price": 69_000, "date": date(2021, 11, 10)},
    4: {"price": 126_000, "date": date(2025, 10, 1)},  # Approximate
}

# Key price levels for dashboard reference
KEY_LEVELS = [60_000, 65_000, 70_000, 85_000, 100_000, 120_000, 150_000]

# Reference cost bases for comparison
REFERENCE_COST_BASES = {
    "MicroStrategy": 76_000,
}


def get_current_halving_era():
    """Return current halving era number."""
    today = date.today()
    era = 0
    for e, d in sorted(HALVING_DATES.items()):
        if today >= d:
            era = e
    return era


def days_since_last_halving():
    """Days since the most recent halving."""
    era = get_current_halving_era()
    halving_date = HALVING_DATES.get(era, HALVING_DATES[4])
    return (date.today() - halving_date).days


def days_until_next_halving():
    """Days until the next estimated halving."""
    era = get_current_halving_era()
    next_date = HALVING_DATES.get(era + 1)
    if next_date is None:
        return None
    return (next_date - date.today()).days


def get_current_block_reward():
    """Current block reward in BTC."""
    era = get_current_halving_era()
    return BLOCK_REWARDS.get(era, 3.125)
