"""Cutoff-safe, award-specific ranking and simulation engine."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from soccer_engine.awards.features import build_player_period_features
from soccer_engine.awards.registry import AwardRegistry
from soccer_engine.awards.schemas import (
    AwardCandidatePrediction,
    AwardCategory,
    AwardCoverage,
    AwardPrediction,
    MediaObservation,
)
from soccer_engine.storage import LocalStore

MODEL_VERSION = "0.4.0"


def _scale(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    lower, upper = float(numeric.min()), float(numeric.max())
    if upper <= lower:
        return pd.Series(0.5 if upper else 0.0, index=values.index)
    return (numeric - lower) / (upper - lower)


def _softmax(values: NDArray[Any]) -> NDArray[np.float64]:
    shifted = values - np.max(values)
    probabilities = np.exp(shifted)
    return np.asarray(probabilities / probabilities.sum(), dtype=np.float64)


class AwardEngine:
    """Central service for honest award coverage, rankings, imports, and snapshots."""

    def __init__(
        self,
        store: LocalStore | None = None,
        registry: AwardRegistry | None = None,
        snapshot_dir: Path = Path("data/predictions/awards"),
    ) -> None:
        self.store = store or LocalStore()
        self.registry = registry or AwardRegistry()
        self.snapshot_dir = snapshot_dir
        snapshot_dir.mkdir(parents=True, exist_ok=True)

    def _optional(self, name: str) -> pd.DataFrame:
        try:
            return self.store.read_frame(name)
        except FileNotFoundError:
            return pd.DataFrame()

    def list_awards(self) -> dict[str, object]:
        return self.registry.coverage()

    def media(self, award_id: str, edition: str, as_of: datetime) -> pd.DataFrame:
        frame = self._optional("journalist_rankings")
        if frame.empty:
            return frame
        frame = frame.copy()
        frame["article_date"] = pd.to_datetime(frame["article_date"], utc=True)
        frame["availability_cutoff"] = pd.to_datetime(frame["availability_cutoff"], utc=True)
        frame = frame[
            (frame["award_id"] == award_id)
            & (frame["edition"].astype(str) == str(edition))
            & (frame["article_date"] <= as_of)
            & (frame["availability_cutoff"] <= as_of)
        ]
        return frame.drop_duplicates(["url", "candidate_id", "article_date"], keep="last")

    def rank(
        self,
        award_id: str,
        as_of: datetime,
        edition: str | None = None,
        simulations: int = 5000,
        seed: int = 42,
        save_snapshot: bool = True,
    ) -> AwardPrediction:
        as_of = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        award = self.registry.get(award_id)
        edition_rule = self.registry.edition(award_id, edition, as_of)
        selected_edition = edition or (edition_rule.edition if edition_rule else None)
        if award_id == "wsl_golden_boot" and edition_rule:
            result = self._wsl_golden_boot(award_id, as_of, edition_rule, simulations, seed)
        elif award.category == AwardCategory.SCORING:
            result = self._rank_imported_scoring(
                award_id,
                as_of,
                selected_edition,
                simulations,
                seed,
                edition_rule.tie_break if edition_rule else "shared",
            )
        elif award.category == AwardCategory.GOAL:
            result = self._rank_goal_award(award_id, as_of, selected_edition)
        else:
            result = self._rank_imported(award_id, as_of, selected_edition)
        if save_snapshot:
            self._save_snapshot(result)
        return result

    def _unavailable(
        self, award_id: str, as_of: datetime, edition: str | None, warning: str
    ) -> AwardPrediction:
        award = self.registry.get(award_id)
        status = (
            AwardCoverage.CREDENTIAL_REQUIRED
            if award.coverage == AwardCoverage.CREDENTIAL_REQUIRED
            else AwardCoverage.UNAVAILABLE
        )
        return AwardPrediction(
            award_id=award_id,
            award_name=award.official_name,
            edition=edition,
            category=award.category,
            status=status,
            as_of=as_of,
            model_version=MODEL_VERSION,
            data_version="no-compatible-candidates",
            source_attribution=award.providers,
            warnings=[warning],
            generated_at=datetime.now(UTC),
        )

    def _wsl_golden_boot(
        self,
        award_id: str,
        as_of: datetime,
        edition: Any,
        simulations: int,
        seed: int,
    ) -> AwardPrediction:
        players = self._optional("player_match_stats")
        matches = self._optional("matches")
        if players.empty or matches.empty:
            return self._unavailable(
                award_id, as_of, edition.edition, "Player-match statistics are not ingested."
            )
        match_columns = [
            "match_id",
            "season",
            "competition_name",
            "kickoff",
            "home_team_id",
            "away_team_id",
            "status",
        ]
        joined = players.drop(columns=["kickoff"], errors="ignore").merge(
            matches[match_columns], on="match_id", how="inner"
        )
        joined["kickoff"] = pd.to_datetime(joined["kickoff"], utc=True)
        eligible = joined[
            (joined["season"].astype(str) == edition.edition)
            & (joined["competition_name"] == "FA Women's Super League")
            & (joined["kickoff"] >= edition.eligibility_start)
            & (joined["kickoff"] <= edition.eligibility_end)
        ].copy()
        observed = eligible[eligible["kickoff"] <= as_of]
        if observed.empty:
            return self._unavailable(
                award_id, as_of, edition.edition, "No eligible player records exist before cutoff."
            )
        aggregates = build_player_period_features(observed)
        season_matches = matches[
            (matches["season"].astype(str) == edition.edition)
            & (matches["competition_name"] == "FA Women's Super League")
        ].copy()
        season_matches["kickoff"] = pd.to_datetime(season_matches["kickoff"], utc=True)
        future = season_matches[
            (season_matches["kickoff"] > as_of)
            & (season_matches["kickoff"] <= edition.eligibility_end)
            & (season_matches["status"] != "canceled")
        ]
        remaining: dict[str, int] = {}
        for team_id in aggregates["team_id"].astype(str).unique():
            remaining[team_id] = int(
                (
                    (future["home_team_id"].astype(str) == team_id)
                    | (future["away_team_id"].astype(str) == team_id)
                ).sum()
            )
        aggregates["remaining_fixtures"] = (
            aggregates["team_id"].astype(str).map(remaining).fillna(0)
        )
        aggregates["minutes_per_appearance"] = aggregates["minutes"] / aggregates["appearances"]
        aggregates["start_probability"] = (aggregates["starts"] + 1) / (
            aggregates["appearances"] + 2
        )
        aggregates["expected_remaining_minutes"] = (
            aggregates["remaining_fixtures"]
            * aggregates["minutes_per_appearance"].clip(upper=90)
            * (0.6 + 0.4 * aggregates["start_probability"])
        )
        empirical_rate = (aggregates["goals"] + 1.0) / (aggregates["minutes"] / 90 + 8.0)
        xg_rate = (aggregates["expected_goals"] + 1.0) / (aggregates["minutes"] / 90 + 8.0)
        aggregates["goal_rate_90"] = 0.65 * empirical_rate + 0.35 * xg_rate
        aggregates["expected_additional_goals"] = (
            aggregates["goal_rate_90"] * aggregates["expected_remaining_minutes"] / 90
        )
        return self._simulate_scoring(
            award_id,
            edition.edition,
            as_of,
            aggregates,
            simulations,
            seed,
            complete_schedule=True,
            tie_break=edition.tie_break,
        )

    def _rank_imported_scoring(
        self,
        award_id: str,
        as_of: datetime,
        edition: str | None,
        simulations: int,
        seed: int,
        tie_break: str,
    ) -> AwardPrediction:
        frame = self._optional("award_candidates")
        if frame.empty or edition is None:
            return self._unavailable(
                award_id,
                as_of,
                edition,
                "A complete source-attributed scoring candidate pool is not available.",
            )
        frame = frame.copy()
        frame["availability_cutoff"] = pd.to_datetime(frame["availability_cutoff"], utc=True)
        frame = frame[
            (frame["award_id"] == award_id)
            & (frame["edition"].astype(str) == str(edition))
            & (frame["availability_cutoff"] <= as_of)
        ].drop_duplicates("candidate_id", keep="last")
        required = {"current_goals", "candidate_pool_complete"}
        if award_id == "european_golden_shoe":
            required.add("league_coefficient")
        if (
            frame.empty
            or not required.issubset(frame.columns)
            or not bool(frame["candidate_pool_complete"].all())
        ):
            return self._unavailable(
                award_id,
                as_of,
                edition,
                "Scoring candidates or current goal totals are incomplete.",
            )
        candidates = pd.DataFrame(
            {
                "player_id": frame["candidate_id"],
                "player_name": frame["candidate_name"],
                "team_name": frame.get("team_name", "Unknown"),
                "position": frame.get("position"),
                "goals": frame["current_goals"],
                "expected_additional_goals": frame.get("expected_additional_goals", 0.0),
                "expected_remaining_minutes": frame.get("expected_remaining_minutes", 0.0),
                "goal_rate_90": frame.get("goal_rate_90", 0.0),
                "assists": frame.get("assists", 0),
                "minutes": frame.get("minutes", 0.0),
                "award_points_multiplier": frame.get("league_coefficient", 1.0),
            }
        )
        complete_schedule = bool(frame.get("schedule_complete", pd.Series(False)).all())
        return self._simulate_scoring(
            award_id,
            edition,
            as_of,
            candidates,
            simulations,
            seed,
            complete_schedule,
            tie_break,
            source_attribution=sorted(set(frame["source"].astype(str))),
        )

    def _simulate_scoring(
        self,
        award_id: str,
        edition: str,
        as_of: datetime,
        candidates: pd.DataFrame,
        simulations: int,
        seed: int,
        complete_schedule: bool,
        tie_break: str = "shared",
        source_attribution: list[str] | None = None,
    ) -> AwardPrediction:
        generator = np.random.default_rng(seed)
        current = candidates["goals"].to_numpy(dtype=int)
        rates = candidates["expected_additional_goals"].to_numpy(dtype=float)
        final = current[:, None] + generator.poisson(
            rates[:, None], size=(len(candidates), simulations)
        )
        multipliers = candidates.get(
            "award_points_multiplier", pd.Series(1.0, index=candidates.index)
        ).to_numpy(dtype=float)
        award_totals = final * multipliers[:, None]
        winner_credit = np.zeros(len(candidates))
        tie_credit = np.zeros(len(candidates))
        top_three = np.zeros(len(candidates))
        top_five = np.zeros(len(candidates))
        for column in award_totals.T:
            leaders = np.flatnonzero(column == column.max())
            if len(leaders) > 1 and tie_break == "assists_then_minutes":
                assists = candidates.get("assists", pd.Series(0, index=candidates.index)).to_numpy()
                leaders = leaders[assists[leaders] == assists[leaders].max()]
                if len(leaders) > 1:
                    minutes = candidates.get(
                        "minutes", pd.Series(0.0, index=candidates.index)
                    ).to_numpy()
                    leaders = leaders[minutes[leaders] == minutes[leaders].min()]
            winner_credit[leaders] += 1 / len(leaders)
            if len(leaders) > 1:
                tie_credit[leaders] += 1
            order = np.lexsort((np.arange(len(column)), -column))
            top_three[order[: min(3, len(order))]] += 1
            top_five[order[: min(5, len(order))]] += 1
        winner = winner_credit / simulations
        rows = []
        statistical = _scale(
            candidates["goals"] + candidates["expected_additional_goals"]
        ).to_numpy()
        order = np.argsort(-winner)
        for rank, index in enumerate(order, 1):
            row = candidates.iloc[index]
            completeness = 0.85 if complete_schedule else 0.6
            rows.append(
                AwardCandidatePrediction(
                    rank=rank,
                    candidate_id=str(row["player_id"]),
                    candidate_name=str(row["player_name"]),
                    team_name=str(row["team_name"]),
                    position=None if pd.isna(row["position"]) else str(row["position"]),
                    winner_probability=float(winner[index]),
                    top_three_probability=float(top_three[index] / simulations),
                    top_five_probability=float(top_five[index] / simulations),
                    statistical_score=float(statistical[index]),
                    team_achievement_score=0,
                    international_score=0,
                    media_score=None,
                    combined_score=float(statistical[index]),
                    current_goals=int(row["goals"]),
                    expected_additional_goals=float(row["expected_additional_goals"]),
                    projected_final_goals=float(row["goals"] + row["expected_additional_goals"]),
                    expected_remaining_minutes=float(row["expected_remaining_minutes"]),
                    shared_award_probability=float(tie_credit[index] / simulations),
                    data_completeness=completeness,
                    confidence="medium" if complete_schedule else "low",
                    supporting_factors=[
                        f"{int(row['goals'])} goals before cutoff",
                        f"{float(row['goal_rate_90']):.2f} shrunk goals per 90",
                    ],
                    missing_evidence=["Current injury status is unavailable."],
                )
            )
        return AwardPrediction(
            award_id=award_id,
            award_name=self.registry.get(award_id).official_name,
            edition=edition,
            category=AwardCategory.SCORING,
            status=AwardCoverage.STATISTICAL_ONLY,
            as_of=as_of,
            model_version=MODEL_VERSION,
            data_version=self._data_version(candidates),
            candidates=rows,
            source_attribution=source_attribution or ["StatsBomb Open Data"],
            warnings=[
                "Simulation is statistics-only; injuries and confirmed future lineups "
                "are unavailable.",
                "Winner probabilities are uncertain estimates, not facts or betting advice.",
                *(
                    ["European Golden Shoe simulations apply imported league coefficients."]
                    if award_id == "european_golden_shoe"
                    else []
                ),
                *(
                    ["Edition-specific tie rules are unavailable; shared-lead fallback used."]
                    if tie_break == "shared" and award_id != "wsl_golden_boot"
                    else []
                ),
            ],
            generated_at=datetime.now(UTC),
        )

    def _rank_imported(
        self, award_id: str, as_of: datetime, edition: str | None
    ) -> AwardPrediction:
        award = self.registry.get(award_id)
        frame = self._optional("award_candidates")
        if frame.empty or edition is None:
            return self._unavailable(
                award_id,
                as_of,
                edition,
                "A complete, source-attributed candidate pool has not been imported.",
            )
        frame = frame.copy()
        frame["availability_cutoff"] = pd.to_datetime(frame["availability_cutoff"], utc=True)
        frame = frame[
            (frame["award_id"] == award_id)
            & (frame["edition"].astype(str) == str(edition))
            & (frame["availability_cutoff"] <= as_of)
        ].drop_duplicates("candidate_id", keep="last")
        completeness_flag = frame.get(
            "candidate_pool_complete", pd.Series(False, index=frame.index)
        )
        if frame.empty or not bool(completeness_flag.all()):
            return self._unavailable(
                award_id, as_of, edition, "Candidate pool is missing or explicitly incomplete."
            )
        numeric = {
            name: _scale(frame[name]) if name in frame else pd.Series(0.0, index=frame.index)
            for name in ("statistical_score", "team_achievement_score", "international_score")
        }
        if "position_group" in frame:
            position_adjusted = frame.groupby("position_group")["statistical_score"].transform(
                _scale
            )
            numeric["statistical_score"] = position_adjusted.fillna(numeric["statistical_score"])
        media = self.media(award_id, edition, as_of)
        media_scores: dict[str, float] = {}
        if not media.empty:

            def media_value(row: pd.Series) -> float:
                sentiment = row.get("sentiment_score")
                signal = (
                    float(sentiment) if pd.notna(sentiment) else 1 / float(row["extracted_rank"])
                )
                return float(row["reliability_weight"] * row["confidence"] * signal)

            raw = (
                media.assign(value=media.apply(media_value, axis=1))
                .groupby("candidate_id")["value"]
                .mean()
            )
            scaled = _scale(raw)
            media_scores = {str(key): float(value) for key, value in scaled.items()}
        weights = (
            (0.65, 0.2, 0.15, 0.0)
            if award.category == AwardCategory.TOURNAMENT_BEST_PLAYER
            else (0.45, 0.25, 0.15, 0.15 if media_scores else 0.0)
        )
        media_series = pd.Series(
            [media_scores.get(str(value), 0.0) for value in frame["candidate_id"]],
            index=frame.index,
        )
        score = (
            weights[0] * numeric["statistical_score"]
            + weights[1] * numeric["team_achievement_score"]
            + weights[2] * numeric["international_score"]
            + weights[3] * media_series
        )
        probabilities = _softmax(score.to_numpy(dtype=float) * 3)
        order = np.argsort(-probabilities)
        rows = []
        for rank, index in enumerate(order, 1):
            row = frame.iloc[index]
            completeness = float(row.get("data_completeness", 0.5))
            rows.append(
                AwardCandidatePrediction(
                    rank=rank,
                    candidate_id=str(row["candidate_id"]),
                    candidate_name=str(row["candidate_name"]),
                    team_name=row.get("team_name"),
                    position=row.get("position"),
                    winner_probability=float(probabilities[index]),
                    top_three_probability=float(min(1.0, probabilities[index] * 3)),
                    top_five_probability=float(min(1.0, probabilities[index] * 5)),
                    statistical_score=float(numeric["statistical_score"].iloc[index]),
                    team_achievement_score=float(numeric["team_achievement_score"].iloc[index]),
                    international_score=float(numeric["international_score"].iloc[index]),
                    media_score=media_scores.get(str(row["candidate_id"])),
                    combined_score=float(score.iloc[index]),
                    data_completeness=completeness,
                    confidence="medium" if completeness >= 0.75 else "low",
                    supporting_factors=["Cutoff-safe component ranking from imported evidence."],
                    missing_evidence=([] if media_scores else ["Media component is unavailable."]),
                )
            )
        sources = sorted(set(frame["source"].astype(str))) if "source" in frame else []
        return AwardPrediction(
            award_id=award_id,
            award_name=award.official_name,
            edition=edition,
            category=award.category,
            status=AwardCoverage.PARTIAL,
            as_of=as_of,
            model_version=MODEL_VERSION,
            data_version=self._data_version(frame),
            candidates=rows,
            source_attribution=sources,
            warnings=[
                "Imported candidate evidence is partial and must not be treated as an "
                "official forecast."
            ],
            generated_at=datetime.now(UTC),
        )

    def _rank_goal_award(
        self, award_id: str, as_of: datetime, edition: str | None
    ) -> AwardPrediction:
        frame = self._optional("goal_nominations")
        if frame.empty or edition is None:
            return self._unavailable(
                award_id,
                as_of,
                edition,
                "Official nominee metadata has not been imported; no beauty score is fabricated.",
            )
        frame = frame.copy()
        frame["goal_date"] = pd.to_datetime(frame["goal_date"], utc=True)
        frame["availability_cutoff"] = pd.to_datetime(frame["availability_cutoff"], utc=True)
        frame = frame[
            (frame["award_id"] == award_id)
            & (frame["edition"].astype(str) == str(edition))
            & (frame["goal_date"] <= as_of)
            & (frame["availability_cutoff"] <= as_of)
        ].drop_duplicates("nomination_id")
        if frame.empty:
            return self._unavailable(
                award_id, as_of, edition, "No official nominations were available by the cutoff."
            )
        default = pd.Series(0.0, index=frame.index)
        official = pd.to_numeric(frame.get("official_vote_share", default), errors="coerce").fillna(
            0
        )
        importance = pd.to_numeric(frame.get("match_importance", default), errors="coerce").fillna(
            0
        )
        metadata = 0.8 * _scale(official) + 0.2 * _scale(importance)
        probabilities = _softmax(metadata.to_numpy(dtype=float) * 2)
        order = np.argsort(-probabilities)
        rows = []
        for rank, index in enumerate(order, 1):
            row = frame.iloc[index]
            rows.append(
                AwardCandidatePrediction(
                    rank=rank,
                    candidate_id=str(row["player_id"]),
                    candidate_name=str(row["player_name"]),
                    winner_probability=float(probabilities[index]),
                    top_three_probability=float(min(1, probabilities[index] * 3)),
                    top_five_probability=float(min(1, probabilities[index] * 5)),
                    statistical_score=0,
                    team_achievement_score=0,
                    international_score=0,
                    media_score=float(metadata.iloc[index]),
                    combined_score=float(metadata.iloc[index]),
                    data_completeness=0.5,
                    confidence="low",
                    supporting_factors=[
                        "Official nomination metadata and attributed voting evidence."
                    ],
                    missing_evidence=["No licensed video-analysis features are available."],
                )
            )
        return AwardPrediction(
            award_id=award_id,
            award_name=self.registry.get(award_id).official_name,
            edition=edition,
            category=AwardCategory.GOAL,
            status=AwardCoverage.METADATA_ONLY,
            as_of=as_of,
            model_version=MODEL_VERSION,
            data_version=self._data_version(frame),
            candidates=rows,
            source_attribution=sorted(set(frame["source"].astype(str))),
            warnings=[
                "Metadata and sentiment ranking only; it is not an objective goal-quality model.",
                "No visual beauty or difficulty score is inferred from box-score data.",
            ],
            generated_at=datetime.now(UTC),
        )

    def import_media(self, path: Path) -> int:
        frame = pd.read_csv(path)
        validated = [
            MediaObservation.model_validate(row).model_dump(mode="json")
            for row in frame.to_dict("records")
        ]
        incoming = pd.DataFrame(validated)
        existing = self._optional("journalist_rankings")
        combined = pd.concat([existing, incoming], ignore_index=True)
        combined = combined.drop_duplicates(["url", "candidate_id", "article_date"], keep="last")
        self.store.write_frame("journalist_rankings", combined)
        return len(incoming)

    def import_results(self, path: Path) -> int:
        frame = pd.read_csv(path)
        required = {
            "award_id",
            "edition",
            "candidate_id",
            "candidate_name",
            "rank",
            "source",
            "publication_date",
            "retrieval_date",
            "availability_cutoff",
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"award results missing columns: {sorted(missing)}")
        for column in ("publication_date", "retrieval_date", "availability_cutoff"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        existing = self._optional("official_results")
        combined = pd.concat([existing, frame], ignore_index=True).drop_duplicates(
            ["award_id", "edition", "candidate_id"], keep="last"
        )
        self.store.write_frame("official_results", combined)
        return len(frame)

    def import_candidates(self, path: Path) -> int:
        frame = pd.read_csv(path)
        required = {
            "award_id",
            "edition",
            "candidate_id",
            "candidate_name",
            "candidate_pool_complete",
            "availability_cutoff",
            "publication_date",
            "retrieval_date",
            "source",
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"award candidates missing columns: {sorted(missing)}")
        for column in ("availability_cutoff", "publication_date", "retrieval_date"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        existing = self._optional("award_candidates")
        combined = pd.concat([existing, frame], ignore_index=True).drop_duplicates(
            ["award_id", "edition", "candidate_id", "availability_cutoff"], keep="last"
        )
        self.store.write_frame("award_candidates", combined)
        return len(frame)

    def import_goal_nominations(self, path: Path) -> int:
        frame = pd.read_csv(path)
        required = {
            "nomination_id",
            "award_id",
            "edition",
            "player_id",
            "player_name",
            "competition",
            "goal_date",
            "availability_cutoff",
            "publication_date",
            "retrieval_date",
            "source",
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"goal nominations missing columns: {sorted(missing)}")
        for column in (
            "goal_date",
            "availability_cutoff",
            "publication_date",
            "retrieval_date",
        ):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        existing = self._optional("goal_nominations")
        combined = pd.concat([existing, frame], ignore_index=True).drop_duplicates(
            "nomination_id", keep="last"
        )
        self.store.write_frame("goal_nominations", combined)
        return len(frame)

    def add_media_observations(self, observations: list[MediaObservation]) -> int:
        incoming = pd.DataFrame([item.model_dump(mode="json") for item in observations])
        existing = self._optional("journalist_rankings")
        combined = pd.concat([existing, incoming], ignore_index=True).drop_duplicates(
            ["url", "candidate_id", "article_date"], keep="last"
        )
        self.store.write_frame("journalist_rankings", combined)
        return len(incoming)

    def history(self, award_id: str) -> list[dict[str, Any]]:
        values = []
        for path in self.snapshot_dir.glob(f"{award_id}_*.json"):
            payload: dict[str, Any] = json.loads(path.read_text())
            values.append(payload)
        return sorted(values, key=lambda item: item["as_of"])

    def _save_snapshot(self, prediction: AwardPrediction) -> None:
        digest = hashlib.sha256(
            f"{prediction.award_id}|{prediction.edition}|{prediction.as_of.isoformat()}".encode()
        ).hexdigest()[:16]
        target = self.snapshot_dir / f"{prediction.award_id}_{digest}.json"
        if not target.exists():
            target.write_text(prediction.model_dump_json(indent=2))

    @staticmethod
    def _data_version(frame: pd.DataFrame) -> str:
        payload = frame.to_json(orient="records", date_format="iso")
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


class AwardModuleNotTrainedError(RuntimeError):
    """Backward-compatible error used by integrations that require trained labels."""
