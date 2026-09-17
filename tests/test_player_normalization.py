from datetime import UTC, datetime

from soccer_engine.normalization.players import goal_interval, normalize_statsbomb_players


def test_real_schema_shape_normalizes_minutes_shots_and_goals() -> None:
    lineups = [
        {
            "team_id": 1,
            "team_name": "A",
            "lineup": [
                {
                    "player_id": 10,
                    "player_name": "Player One",
                    "player_nickname": None,
                    "positions": [
                        {
                            "position": "Center Forward",
                            "from": "00:00",
                            "to": "75:00",
                            "start_reason": "Starting XI",
                        }
                    ],
                }
            ],
        }
    ]
    events = [
        {
            "minute": 12,
            "type": {"name": "Shot"},
            "team": {"id": 1},
            "player": {"id": 10},
            "shot": {
                "statsbomb_xg": 0.4,
                "type": {"name": "Open Play"},
                "outcome": {"name": "Goal"},
            },
        }
    ]
    players, goals = normalize_statsbomb_players(
        "statsbomb:1",
        datetime(2024, 1, 1, tzinfo=UTC),
        lineups,
        events,
        "https://example.test/events/1.json",
    )
    assert players[0].started is True
    assert players[0].minutes == 75
    assert players[0].goals == 1
    assert players[0].expected_goals == 0.4
    assert players[0].first_goal is True
    assert goals[0].interval == "0-15"


def test_goal_interval_handles_stoppage_time() -> None:
    assert goal_interval(45) == "31-45+"
    assert goal_interval(90) == "76-90+"
    assert goal_interval(105) == "76-90+"
