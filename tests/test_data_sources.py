import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from kickcast_engine.data.footballdata_uk import detect_columns, margin_removed_probs
from kickcast_engine.data.team_aliases import NO_OPENFOOTBALL_MATCH, canonical, canonical_id


def test_detect_columns_old_season_has_no_closing_odds():
    header = [
        "Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HS", "AS", "HST", "AST",
        "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR", "B365H", "B365D", "B365A",
    ]
    cols = detect_columns(header)
    assert cols["has_stats"] is True
    assert cols["has_cards"] is True
    assert cols["closing_odds_source"] is None


def test_detect_columns_modern_season_has_closing_odds():
    header = [
        "Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HS", "AS", "HST", "AST",
        "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR",
        "B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA", "PSCH", "PSCD", "PSCA",
        "AvgCH", "AvgCD", "AvgCA",
    ]
    cols = detect_columns(header)
    assert cols["has_stats"] is True
    assert cols["closing_odds_source"] == "market_average_closing"


def test_detect_columns_missing_stats_2005_06_style():
    header = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HY", "AY", "HR", "AR",
              "B365H", "B365D", "B365A"]
    cols = detect_columns(header)
    assert cols["has_stats"] is False
    assert cols["has_cards"] is True


def test_margin_removed_probs_sums_to_one_and_beats_raw_implied():
    # typical over-round market: raw implied probs sum to > 1
    probs = margin_removed_probs(2.0, 3.5, 4.0)
    assert abs(sum(probs) - 1.0) < 1e-9
    raw_sum = 1 / 2.0 + 1 / 3.5 + 1 / 4.0
    assert raw_sum > 1.0  # confirms there was a margin to remove
    assert probs[0] > probs[1] > probs[2]  # home favourite stays favourite after normalizing


def test_canonical_id_strips_club_type_prefix_and_suffix():
    assert canonical_id("Arsenal FC") == canonical_id("Arsenal")
    assert canonical_id("AFC Bournemouth") == canonical_id("Bournemouth")
    assert canonical_id("1. FC Köln") == canonical_id("FC Koln")


def test_canonical_resolves_openfootball_and_footballdata_short_names_to_same_id():
    assert canonical("Manchester United FC") == canonical("Man United")
    assert canonical("Tottenham Hotspur FC") == canonical("Spurs") == canonical("Tottenham")
    assert canonical("FC Internazionale Milano") == canonical("Inter")
    assert canonical("Paris Saint-Germain FC") == canonical("Paris SG")


def test_no_openfootball_match_teams_still_get_a_stable_canonical_id():
    # these teams have no openfootball counterpart in our downloaded window (confirmed by
    # scripts/crosscheck_sources.py), but canonical() must still return a usable, stable id
    for name in NO_OPENFOOTBALL_MATCH:
        cid = canonical(name)
        assert cid and cid == canonical(name)


def test_matchday_parsing():
    from backtest_openfootball import matchday_num

    assert matchday_num("Matchday 1") == 1
    assert matchday_num("Matchday 23") == 23
    assert matchday_num(None) is None
    assert matchday_num("") is None


def test_season_start_boundary():
    from backtest_openfootball import season_start

    assert season_start(date(2024, 8, 1)) == date(2024, 8, 1)
    assert season_start(date(2024, 9, 15)) == date(2024, 8, 1)
    assert season_start(date(2025, 5, 1)) == date(2024, 8, 1)  # still last season (before Aug)
    assert season_start(date(2025, 7, 31)) == date(2024, 8, 1)
