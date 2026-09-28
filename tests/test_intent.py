"""Deterministic question classification (works with Gemini off)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kickcast_api.assistant.intent import Intent, classify

NOW = datetime(2026, 9, 28, tzinfo=UTC)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # the real messages from real use
        ("Predict Real Madrid vs Barcelona", Intent.PREDICTION),
        ("Give em the most recent match highlights of Real Madrid vs barcelona", Intent.VIDEO),
        ("A video link I wanna watch the highlights", Intent.VIDEO),
        ("A video link I wanna watch the highlights for Real Madrid vs barcelona", Intent.VIDEO),
        # each intent
        ("When does Arsenal play next?", Intent.MATCH_LOOKUP),
        ("What was Liverpool's last result?", Intent.RESULT),
        ("who scored", Intent.RESULT),
        ("Where do Man City stand in the table?", Intent.TABLE),
        ("and the table?", Intent.TABLE),
        ("Who are the top scorers in La Liga?", Intent.TOP_SCORERS),
        ("golden boot race", Intent.TOP_SCORERS),
        ("who will win Arsenal vs Chelsea", Intent.PREDICTION),
        ("Tell me about the history of Real Madrid", Intent.HISTORY),
        ("When was Barcelona founded?", Intent.HISTORY),
        ("Who won the 2016 Champions League final?", Intent.HISTORY),
        ("What was the score of the 2016 Champions League final?", Intent.HISTORY),
        ("What's the meaning of life?", Intent.UNKNOWN),
        ("asdkjfh qwerty", Intent.UNKNOWN),
        ("", Intent.UNKNOWN),
    ],
)
def test_classify(question, expected):
    assert classify(question, NOW) == expected


@pytest.mark.parametrize("word", ["highlights", "video", "watch", "clip", "replay", "goal video"])
def test_every_video_keyword_wins_over_other_intents(word):
    # a video question that also names teams, results, fixtures or predictions is still VIDEO
    assert classify(f"the {word} of the last match, who won, when is the next one, predict it", NOW) == Intent.VIDEO


def test_current_season_years_do_not_turn_a_lookup_into_history():
    assert classify("What was Arsenal's result in 2026?", NOW) == Intent.RESULT
    assert classify("What was Arsenal's result in 2019?", NOW) == Intent.HISTORY
