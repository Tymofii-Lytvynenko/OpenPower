"""Scenario defaults shared by authoritative simulation and read-only UI."""

PAYLOAD_PROFILES = {
    1: (100.0, 3.25),
    2: (200.0, 4.25),
    3: (400.0, 6.0),
    4: (750.0, 7.5),
    5: (1500.0, 9.5),
    6: (2500.0, 11.5),
    7: (5000.0, 14.0),
    8: (20000.0, 18.0),
    9: (50000.0, 23.0),
    10: (100000.0, 30.0),
}

DEFAULT_DEFENSE = {
    "long_range": (0.60, 0.50),
    "short_range": (0.50, 0.0),
}
