"""Canonical team IDs shared across data sources.

openfootball, football-data.co.uk (and later football-data.org / API-Football)
all spell team names differently, and openfootball itself is inconsistent
across its own seasons (e.g. "Aston Villa" vs "Aston Villa FC", "Inter" vs
"FC Internazionale Milano"). Every team gets ONE canonical_id; `canonical()`
maps any raw name from any source to it.

`canonical_id()` normalizes a name into a slug (strip accents/punctuation,
drop a club-type prefix/suffix like "FC"/"AC"/"1. "). That alone resolves
most cases (openfootball's own season-to-season variants, and short forms
like "Bournemouth" -> "bournemouth" matching "AFC Bournemouth" -> strip
prefix "afc " -> "bournemouth"). Where normalization still leaves two
spellings of the same club apart (e.g. "Inter" vs "internazionale milano",
"Spurs"-style historical abbreviations), `OVERRIDES` maps the raw name
straight to the chosen canonical id.
"""

from __future__ import annotations

import re
import unicodedata

_PREFIXES = [
    "1 fc ", "1 fsv ", "1899 ", "fc ", "afc ", "ac ", "acf ", "as ", "asd ", "ss ", "ssc ", "ssd ",
    "uc ", "us ", "usd ", "cd ", "sd ", "ud ", "rcd ", "rc ", "ca ", "cf ", "sc ", "sv ", "svg ",
    "vfb ", "vfl ", "tsg ", "tsv ", "ssv ", "sg ", "sv 07 ", "ea ", "aj ", "og ", "ogc ",
    "sm ", "es ", "estac ", "stade ", "club ", "real ", "racing club de ", "racing ", "de ",
]
_SUFFIXES = [
    " fc", " cf", " afc", " sc", " cd", " ac", " ud", " rc", " rcd", " ca", " sd", " cfc", " fk",
    " calcio", " balompie", " de futbol", " de madrid", " de barcelona", " barcelona",
    " alsace", " lorraine", " 1919", " 1913", " 1909", " 1907", " 1906", " 1901", " 1903", " 1846",
    " 1848", " 2013 ferrara", " 63", " 29", " 04", " 05", " 07", " 96", " 98",
]

# raw name (as it appears in ANY source) -> canonical_id, ONLY for names normalization can't unify
# on its own (verified against the actual openfootball_raw + football-data.co.uk team lists, not
# guessed: see the alias cross-check in reports/backtest_openfootball.json for match coverage).
OVERRIDES: dict[str, str] = {
    # England
    "Man United": "manchester united", "Man Utd": "manchester united",
    "Man City": "manchester city",
    "Spurs": "tottenham hotspur", "Tottenham": "tottenham hotspur",
    "Nott'm Forest": "nottingham forest", "Nottm Forest": "nottingham forest",
    "West Brom": "west bromwich albion",
    "QPR": "queens park rangers",
    "Wolves": "wolverhampton wanderers",
    "Birmingham": "birmingham city", "Blackburn": "blackburn rovers", "Bolton": "bolton wanderers",
    "Brighton": "brighton and hove albion", "Cardiff": "cardiff city", "Coventry": "coventry city",
    "Huddersfield": "huddersfield town", "Hull": "hull city", "Ipswich": "ipswich town",
    "Leeds": "leeds united", "Leicester": "leicester city", "Luton": "luton town",
    "Newcastle": "newcastle united", "Norwich": "norwich city", "Stoke": "stoke city",
    "Swansea": "swansea city", "West Ham": "west ham united", "Wigan": "wigan athletic",
    # Spain
    "Ath Bilbao": "athletic club", "Athletic Bilbao": "athletic club",
    "Ath Madrid": "atletico madrid",
    "La Coruna": "deportivo la coruna",
    "Espanol": "espanyol",
    "Sp Gijon": "sporting gijon",
    "Vallecano": "rayo vallecano",
    "Gimnastic": "gimnastic de tarragona",
    "Recreativo": "recreativo de huelva",
    "Pescara": "delfino pescara",
    # Italy
    "Inter": "internazionale milano",
    "Chievo": "chievo verona",
    "Verona": "hellas verona", "Catania": "calcio catania",
    # Germany
    "Bayern Munich": "bayern munchen",
    "M'gladbach": "bor monchengladbach",
    "Ein Frankfurt": "eintracht frankfurt",
    "FC Koln": "koln",
    "Bielefeld": "arminia bielefeld", "Braunschweig": "eintracht braunschweig",
    "Dortmund": "borussia dortmund", "Greuther Furth": "spvgg greuther furth",
    "Hamburg": "hamburger sv", "Heidenheim": "heidenheim", "Hertha": "hertha bsc",
    "Kaiserslautern": "kaiserslautern", "Leverkusen": "bayer 04 leverkusen",
    "Mainz": "mainz", "Nurnberg": "nurnberg", "Union Berlin": "union berlin",
    # France
    "Paris SG": "paris saint germain",
    "Marseille": "olympique de marseille",
    "Rennes": "rennais",
    "St Etienne": "saint etienne",
    "Ajaccio GFCO": "gazelec fc ajaccio",
    "Dijon": "dijon fco",
    "Sochaux": "sochaux montbeliard",
    "Sedan": "sedan ardennes",
    "Grenoble": "grenoble foot 38",
    "Arles": "arles avignon",
    "Angers": "angers sco", "Bordeaux": "girondins bordeaux", "Brest": "brestois",
    "Clermont": "clermont foot", "Lille": "lille osc", "Lyon": "olympique lyonnais",
    "Montpellier": "montpellier hsc", "Nimes": "nimes olympique",
}

# Teams present in football-data.co.uk with NO openfootball counterpart: they were out of the
# top flight (or relegated) in every season openfootball actually covers for that league.
# openfootball's own per-league start date varies: en.1/de.1 from 2010-11, es.1 from 2012-13,
# it.1 from 2013-14, fr.1 from 2014-15 (confirmed from the files on disk, not assumed) -- these
# teams all dropped out of their top flight before their league's openfootball window opens.
NO_OPENFOOTBALL_MATCH = {"Hercules", "Bari", "Novara", "Siena", "Arles", "Sochaux", "Valenciennes"}


def canonical_id(name: str) -> str:
    """Normalize a raw team name into a slug, WITHOUT applying OVERRIDES."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = n.lower().strip()
    n = n.replace("&", " and ").replace("-", " ").replace(".", " ").replace("'", "")
    n = re.sub(r"\s+", " ", n).strip()
    changed = True
    while changed:
        changed = False
        # longest match first, so e.g. "sv 07 " wins over "sv " on "SV 07 Elversberg"
        for pre in sorted(_PREFIXES, key=len, reverse=True):
            if n.startswith(pre) and n != pre.strip():
                n = n[len(pre):].strip()
                changed = True
                break
        for suf in sorted(_SUFFIXES, key=len, reverse=True):
            if n.endswith(suf) and n != suf.strip():
                n = n[: -len(suf)].strip()
                changed = True
                break
    return re.sub(r"\s+", " ", n).strip()


def canonical(name: str) -> str:
    """Canonical team id for a raw name from any source (openfootball, football-data.co.uk, ...)."""
    if name in OVERRIDES:
        return OVERRIDES[name]
    return canonical_id(name)
