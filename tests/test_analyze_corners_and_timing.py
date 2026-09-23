from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_corners_and_timing import _window, analyze


def test_window_buckets_first_half_by_minute():
    assert _window(0, 1) == "0-15"
    assert _window(14, 1) == "0-15"
    assert _window(15, 1) == "15-30"
    assert _window(44, 1) == "30-45"


def test_window_buckets_first_half_stoppage_as_added_time():
    assert _window(45, 1) == "90+"
    assert _window(47, 1) == "90+"


def test_window_buckets_second_half_by_continuous_clock():
    # StatsBomb's minute field is continuous - period 2 starts at 45, not 0.
    assert _window(45, 2) == "45-60"
    assert _window(74, 2) == "60-75"
    assert _window(89, 2) == "75-90"


def test_window_buckets_second_half_stoppage_as_added_time():
    assert _window(90, 2) == "90+"
    assert _window(95, 2) == "90+"


def test_analyze_computes_real_counts_not_just_shares(tmp_path):
    summaries = tmp_path / "s.jsonl"
    rows = [
        {
            "goals": [{"minute": 10, "period": 1}, {"minute": 46, "period": 1}, {"minute": 80, "period": 2}],
            "corners": [{"goal": True}, {"goal": False}, {"goal": False}],
            "timeline_matches_score": True,
        },
        {
            "goals": [{"minute": 50, "period": 2}],
            "corners": [{"goal": False}],
            "timeline_matches_score": False,
        },
    ]
    summaries.write_text("\n".join(json.dumps(r) for r in rows))
    result = analyze(summaries)
    assert result["n_matches"] == 2
    assert result["n_matches_with_timeline_mismatch"] == 1
    assert result["goal_timing"]["total_goals"] == 4
    windows = {w["window"]: w["goals"] for w in result["goal_timing"]["windows"]}
    assert windows["0-15"] == 1 and windows["90+"] == 1 and windows["75-90"] == 1 and windows["45-60"] == 1
    assert result["corner_goal_rate"]["total_corners"] == 4
    assert result["corner_goal_rate"]["corners_leading_to_goal"] == 1
    assert result["corner_goal_rate"]["rate"] == 0.25
