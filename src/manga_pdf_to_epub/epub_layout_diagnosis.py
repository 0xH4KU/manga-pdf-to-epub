from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CandidateStatus = Literal["pending", "true", "false"]


def adjacent_pair_id(start_page: int, end_page: int) -> str:
    return f"{start_page:03d}-{end_page:03d}"


@dataclass(frozen=True)
class SpreadCandidate:
    pair_id: str
    start_page: int
    end_page: int
    score: float
    review_score: float
    decision: str
    source: str = "scan"
    reasons: tuple[str, ...] = ()


@dataclass
class ReviewedSpreadCandidate:
    candidate: SpreadCandidate
    status: CandidateStatus = "pending"


class DiagnosisSession:
    def __init__(self, source_page_count: int):
        self.source_page_count = source_page_count
        self._candidates: dict[str, ReviewedSpreadCandidate] = {}

    def load_spread_candidates(self, candidates: list[SpreadCandidate]) -> None:
        self._candidates = {}
        for candidate in sorted(candidates, key=lambda item: (-item.score, item.start_page, item.end_page)):
            self._validate_pair(candidate.start_page, candidate.end_page)
            self._candidates[candidate.pair_id] = ReviewedSpreadCandidate(candidate)

    def spread_candidates(self) -> list[ReviewedSpreadCandidate]:
        return list(self._candidates.values())

    def mark_candidate(self, pair_id: str, status: CandidateStatus) -> None:
        if status not in {"pending", "true", "false"}:
            raise ValueError("Unsupported spread candidate status")
        if pair_id not in self._candidates:
            raise KeyError(pair_id)
        self._candidates[pair_id].status = status

    def add_manual_spread(self, start_page: int, end_page: int) -> SpreadCandidate:
        self._validate_pair(start_page, end_page)
        pair_id = adjacent_pair_id(start_page, end_page)
        candidate = SpreadCandidate(pair_id, start_page, end_page, 1.0, 1.0, "manual", source="manual")
        self._candidates[pair_id] = ReviewedSpreadCandidate(candidate, "true")
        return candidate

    def pending_count(self) -> int:
        return sum(1 for item in self._candidates.values() if item.status == "pending")

    def confirmed_spreads(self) -> list[SpreadCandidate]:
        confirmed = [item.candidate for item in self._candidates.values() if item.status == "true"]
        return sorted(confirmed, key=lambda item: (item.start_page, item.end_page))

    def _validate_pair(self, start_page: int, end_page: int) -> None:
        if start_page < 1 or end_page > self.source_page_count:
            raise ValueError("Spread pair is outside the source page range")
        if end_page != start_page + 1:
            raise ValueError("Spread pair must use adjacent source pages")
