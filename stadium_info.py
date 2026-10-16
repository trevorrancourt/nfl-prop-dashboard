"""
Lat/lon and roof type for every stadium that shows up in the nflverse
schedule for the current NFL slate, keyed by the exact "stadium" string
nflverse uses (including its legacy/sponsor-name quirks, e.g. Houston's
venue is still listed as "Reliant Stadium" in the schedule data even
though it's actually NRG Stadium today, and Kansas City's is listed with
its full sponsor name).

"dome": True means the field is fully enclosed or roofed for essentially
every game (fixed dome, or a retractable roof that's closed the large
majority of the time) -- weather forecasts aren't meaningful there, so
the dashboard shows "Dome" instead of pulling a forecast.

International/one-off venues are included too, since the NFL plays a
handful of games abroad every season.
"""

STADIUM_INFO = {
    # AFC/NFC home stadiums
    "State Farm Stadium": {"lat": 33.5276, "lon": -112.2626, "dome": True},   # ARI, retractable
    "Mercedes-Benz Stadium": {"lat": 33.7554, "lon": -84.4008, "dome": True},  # ATL, retractable
    "M&T Bank Stadium": {"lat": 39.2780, "lon": -76.6227, "dome": False},      # BAL
    "Highmark Stadium": {"lat": 42.7738, "lon": -78.7870, "dome": False},      # BUF
    "Bank of America Stadium": {"lat": 35.2258, "lon": -80.8528, "dome": False},  # CAR
    "Soldier Field": {"lat": 41.8623, "lon": -87.6167, "dome": False},         # CHI
    "Paycor Stadium": {"lat": 39.0954, "lon": -84.5160, "dome": False},        # CIN
    "Huntington Bank Field": {"lat": 41.5061, "lon": -81.6995, "dome": False},  # CLE
    "AT&T Stadium": {"lat": 32.7473, "lon": -97.0945, "dome": True},           # DAL, retractable
    "Empower Field at Mile High": {"lat": 39.7439, "lon": -105.0201, "dome": False},  # DEN
    "Ford Field": {"lat": 42.3400, "lon": -83.0456, "dome": True},             # DET
    "Lambeau Field": {"lat": 44.5013, "lon": -88.0622, "dome": False},         # GB
    "Reliant Stadium": {"lat": 29.6847, "lon": -95.4107, "dome": True},        # HOU (aka NRG Stadium), retractable
    "Lucas Oil Stadium": {"lat": 39.7601, "lon": -86.1639, "dome": True},      # IND, retractable
    "EverBank Stadium": {"lat": 30.3239, "lon": -81.6373, "dome": False},      # JAX
    "GEHA Field at Arrowhead Stadium": {"lat": 39.0489, "lon": -94.4839, "dome": False},  # KC
    "SoFi Stadium": {"lat": 33.9535, "lon": -118.3392, "dome": True},          # LA/LAC, fixed roof
    "Allegiant Stadium": {"lat": 36.0909, "lon": -115.1833, "dome": True},     # LV
    "Hard Rock Stadium": {"lat": 25.9580, "lon": -80.2389, "dome": False},     # MIA
    "U.S. Bank Stadium": {"lat": 44.9737, "lon": -93.2577, "dome": True},      # MIN
    "Gillette Stadium": {"lat": 42.0909, "lon": -71.2643, "dome": False},      # NE
    "Caesars Superdome": {"lat": 29.9509, "lon": -90.0815, "dome": True},      # NO
    "MetLife Stadium": {"lat": 40.8135, "lon": -74.0745, "dome": False},       # NYG/NYJ
    "Lincoln Financial Field": {"lat": 39.9008, "lon": -75.1675, "dome": False},  # PHI
    "Acrisure Stadium": {"lat": 40.4468, "lon": -80.0158, "dome": False},      # PIT
    "Lumen Field": {"lat": 47.5952, "lon": -122.3316, "dome": False},          # SEA
    "Levi's Stadium": {"lat": 37.4032, "lon": -121.9698, "dome": False},       # SF
    "Raymond James Stadium": {"lat": 27.9759, "lon": -82.5033, "dome": False},  # TB
    "Nissan Stadium": {"lat": 36.1665, "lon": -86.7713, "dome": False},        # TEN
    "Northwest Stadium": {"lat": 38.9076, "lon": -76.8645, "dome": False},     # WAS

    # International one-off venues
    "Wembley Stadium": {"lat": 51.5560, "lon": -0.2795, "dome": False},        # London
    "Tottenham Hotspur Stadium": {"lat": 51.6043, "lon": -0.0665, "dome": False},  # London
    "Bernabeu": {"lat": 40.4531, "lon": -3.6883, "dome": True},                # Madrid, retractable
    "FC Bayern Munich Stadium": {"lat": 48.2188, "lon": 11.6247, "dome": False},  # Munich (Allianz Arena)
    "Melbourne Cricket Ground": {"lat": -37.8199, "lon": 144.9834, "dome": False},  # Melbourne
    "Stade de France": {"lat": 48.9244, "lon": 2.3601, "dome": False},         # Paris
    "Estadio Banorte": {"lat": 25.6893, "lon": -100.2957, "dome": False},      # Monterrey, Mexico
    "Maracana Stadium": {"lat": -22.9121, "lon": -43.2302, "dome": False},     # Rio de Janeiro
}


def lookup(stadium_name):
    """Returns the stadium's info dict, or None if it's not in our table
    (a brand-new or very obscure venue we haven't added yet)."""
    return STADIUM_INFO.get(stadium_name)
