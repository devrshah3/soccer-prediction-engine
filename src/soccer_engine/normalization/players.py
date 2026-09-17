"""StatsBomb lineup/event normalization for player-match and goal-event tables."""

from datetime import datetime
from typing import Any

from soccer_engine.schemas import GoalEventRecord, PlayerMatchRecord

GOAL_INTERVALS = ("0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+")
ON_TARGET_OUTCOMES = {"Goal", "Saved", "Saved To Post"}


def goal_interval(minute: int) -> str:
    """Map an event minute to a robust six-bin pre-match timing interval."""

    if minute <= 15:
        return "0-15"
    if minute <= 30:
        return "16-30"
    if minute <= 45:
        return "31-45+"
    if minute <= 60:
        return "46-60"
    if minute <= 75:
        return "61-75"
    return "76-90+"


def _clock_minutes(value: str | None, match_end: float) -> float:
    if value is None:
        return match_end
    minutes, seconds = value.split(":", maxsplit=1)
    return float(minutes) + float(seconds) / 60


def normalize_statsbomb_players(
    match_id: str,
    kickoff: datetime,
    lineups: list[dict[str, Any]],
    events: list[dict[str, Any]],
    source_url: str,
) -> tuple[list[PlayerMatchRecord], list[GoalEventRecord]]:
    """Create compact player-match rows from official StatsBomb JSON."""

    match_end = max((float(event.get("minute", 90)) for event in events), default=90.0)
    stats: dict[str, dict[str, Any]] = {}
    for team in lineups:
        team_id = f"statsbomb:{team['team_id']}"
        for player in team.get("lineup", []):
            player_id = f"statsbomb:{player['player_id']}"
            positions = player.get("positions") or []
            minutes = sum(
                max(
                    0.0,
                    _clock_minutes(position.get("to"), match_end)
                    - _clock_minutes(position.get("from"), match_end),
                )
                for position in positions
            )
            stats[player_id] = {
                "match_id": match_id,
                "kickoff": kickoff,
                "provider": "statsbomb_open_data",
                "provider_player_id": str(player["player_id"]),
                "player_id": player_id,
                "player_name": player.get("player_nickname") or player["player_name"],
                "team_id": team_id,
                "team_name": team["team_name"],
                "position": positions[0]["position"] if positions else None,
                "in_squad": True,
                "started": any(p.get("start_reason") == "Starting XI" for p in positions),
                "minutes": min(minutes, 130.0),
                "goals": 0,
                "non_penalty_goals": 0,
                "assists": 0,
                "expected_goals": 0.0,
                "shots": 0,
                "shots_on_target": 0,
                "penalties_taken": 0,
                "penalties_scored": 0,
                "first_goal": False,
                "source_url": source_url,
            }

    goal_events: list[GoalEventRecord] = []
    scorer_events: list[tuple[int, str]] = []
    for event in events:
        player = event.get("player") or {}
        event_player_id = f"statsbomb:{player['id']}" if player.get("id") is not None else None
        event_type = (event.get("type") or {}).get("name")
        minute = int(event.get("minute", 0))
        if event_type == "Shot" and event_player_id in stats:
            shot = event.get("shot") or {}
            outcome = (shot.get("outcome") or {}).get("name")
            shot_type = (shot.get("type") or {}).get("name")
            row = stats[event_player_id]
            row["shots"] += 1
            row["expected_goals"] += float(shot.get("statsbomb_xg") or 0.0)
            if outcome in ON_TARGET_OUTCOMES:
                row["shots_on_target"] += 1
            if shot_type == "Penalty":
                row["penalties_taken"] += 1
            if outcome == "Goal":
                row["goals"] += 1
                if shot_type == "Penalty":
                    row["penalties_scored"] += 1
                else:
                    row["non_penalty_goals"] += 1
                scorer_events.append((minute, event_player_id))
                team = event.get("team") or {}
                goal_events.append(
                    GoalEventRecord(
                        match_id=match_id,
                        kickoff=kickoff,
                        team_id=f"statsbomb:{team['id']}",
                        player_id=event_player_id,
                        minute=minute,
                        interval=goal_interval(minute),
                        penalty=shot_type == "Penalty",
                        source_url=source_url,
                    )
                )
        elif event_type == "Pass" and event_player_id in stats:
            pass_data = event.get("pass") or {}
            if pass_data.get("goal_assist"):
                stats[event_player_id]["assists"] += 1
        elif event_type == "Own Goal Against":
            team = event.get("possession_team") or event.get("team") or {}
            goal_events.append(
                GoalEventRecord(
                    match_id=match_id,
                    kickoff=kickoff,
                    team_id=f"statsbomb:{team['id']}",
                    player_id=event_player_id,
                    minute=minute,
                    interval=goal_interval(minute),
                    own_goal=True,
                    source_url=source_url,
                )
            )
    if scorer_events:
        first_player = min(scorer_events, key=lambda item: item[0])[1]
        stats[first_player]["first_goal"] = True
    return [PlayerMatchRecord(**row) for row in stats.values()], goal_events


def records_to_player_frames(
    player_records: list[PlayerMatchRecord], goal_records: list[GoalEventRecord]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Serialize records for stable JSON/Parquet output."""

    players = [record.model_dump(mode="json") for record in player_records]
    goals = [record.model_dump(mode="json") for record in goal_records]
    return players, goals
