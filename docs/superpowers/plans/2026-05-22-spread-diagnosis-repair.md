# Spread Diagnosis Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-volume GUI workflow that lets the user scan or import split-spread candidates, manually confirm true spreads, detect which confirmed spreads are broken by the current layout including the Apple Books virtual cover gap, review safe blank insertion points, and execute one user-approved blank insertion at a time.

**Architecture:** Keep the GUI as orchestration only. Put CSV parsing, review state, layout damage detection, and insertion suggestion logic in pure modules with unit tests; put optional prototype command resolution in a small runner module; put Tk widgets for the new tab in a focused panel module. The main `EpubLayoutApp` owns the current PDF/layout and calls these helpers, preserving the current `LayoutModel.insert_blank()` path, preview behavior, series edit marking, and export model.

**Tech Stack:** Python 3.11+, Tkinter, PyMuPDF already in the main app, CSV adapters for `manga-spread-continuity` and `manga-insert-point-scorer`, optional subprocess calls to sibling prototype repos, `unittest`.

---

## Scope And UX Rules

- MVP scope is single-volume GUI. In series mode, the Diagnose tab operates only on the active selected volume and does not scan every volume.
- No one-click diagnose-and-repair path. Each phase is a separate user action:
  - run or import spread candidates;
  - mark candidates true or false, or add a missing spread pair;
  - click damage check;
  - run or import insert-point scores;
  - click one suggested insertion;
  - click recheck after the layout changes.
- Pending spread candidates are allowed, but damage check uses only candidates explicitly marked true plus manually added spread pairs. The UI must show pending count so the user knows the confirmed spread set is incomplete.
- The Apple Books preview flag is part of damage detection. If `Preview Apple Books cover gap` is on, the virtual cover gap is included in spread pairing exactly like the existing preview.
- The insertion planner considers one blank page at a time. A suggested insertion must fix at least one currently damaged confirmed spread and must not damage any currently intact confirmed spread.
- Red/protected insert markers mean "do not insert here because this gap is inside a confirmed spread or would break a confirmed spread." Green/safe markers mean "this one-blank insertion fixes damage and passes the confirmed-spread protection check."
- Inserting a blank marks previous damage and suggestion results stale. The user must click Recheck Layout before trusting new results.

## File Structure

- Create `src/manga_pdf_to_epub/epub_layout_diagnosis.py`
  - Dataclasses for spread candidates, insert candidates, review state, damage reports, and insertion suggestions.
  - CSV readers for `adjacent_clusters.csv` and `gaps.csv`.
  - Pure functions for preview placement, spread damage detection, insertion candidate mapping, insertion simulation, and marker generation.
- Create `src/manga_pdf_to_epub/epub_layout_diagnosis_runner.py`
  - Resolves optional sibling prototype commands without making OpenCV, NumPy, or Pillow hard dependencies of the main package.
  - Runs commands with `subprocess.run()` and returns output paths.
- Create `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
  - Tkinter panel for the Diagnose inspector tab.
  - Owns widgets and display refresh only. It calls callback methods supplied by `EpubLayoutApp`.
- Modify `src/manga_pdf_to_epub/epub_layout_gui.py`
  - Add app-level diagnosis state, a Diagnose tab, callbacks, and spine row marker rendering.
  - Keep logic thin and delegate to the pure diagnosis module.
- Modify `src/manga_pdf_to_epub/epub_layout_gui_support.py` only if a shared GUI helper is genuinely needed. Prefer the new diagnosis GUI module for diagnosis-specific helpers.
- Modify `tests/gui_helpers.py`
  - Add fake listbox support for `itemconfig()`.
- Create tests:
  - `tests/test_epub_layout_diagnosis_state.py`
  - `tests/test_epub_layout_diagnosis_csv.py`
  - `tests/test_epub_layout_diagnosis_damage.py`
  - `tests/test_epub_layout_diagnosis_suggestions.py`
  - `tests/test_epub_layout_diagnosis_runner.py`
  - `tests/test_epub_layout_gui_diagnosis.py`
- Modify tests:
  - `tests/test_epub_layout_gui.py`
  - `tests/test_epub_layout_gui_editing.py`
  - `tests/test_project_guardrails.py` only if the existing line ceiling is exceeded after moving diagnosis logic into focused modules. Prefer keeping `EpubLayoutApp` at or below the current ceiling.
- Modify docs:
  - `README.md`
  - Create `docs/diagnosis-workflow.md`

---

### Task 1: Add Diagnosis Review State Model

**Files:**
- Create: `src/manga_pdf_to_epub/epub_layout_diagnosis.py`
- Create: `tests/test_epub_layout_diagnosis_state.py`

- [ ] **Step 1: Write failing state tests**

Create `tests/test_epub_layout_diagnosis_state.py`:

```python
import unittest

from manga_pdf_to_epub.epub_layout_diagnosis import (
    DiagnosisSession,
    SpreadCandidate,
    adjacent_pair_id,
)


class DiagnosisStateTests(unittest.TestCase):
    def test_candidates_start_pending_and_true_candidates_drive_confirmed_set(self):
        session = DiagnosisSession(source_page_count=200)
        session.load_spread_candidates(
            [
                SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review"),
                SpreadCandidate("071-072", 71, 72, 0.74, 0.79, "review"),
            ]
        )

        self.assertEqual(2, session.pending_count())
        session.mark_candidate("037-038", "true")
        session.mark_candidate("071-072", "false")

        self.assertEqual(0, session.pending_count())
        self.assertEqual([(37, 38)], [(item.start_page, item.end_page) for item in session.confirmed_spreads()])

    def test_manual_spread_is_added_as_confirmed_candidate(self):
        session = DiagnosisSession(source_page_count=200)

        manual = session.add_manual_spread(173, 174)

        self.assertEqual("173-174", manual.pair_id)
        self.assertEqual("manual", manual.source)
        self.assertEqual([(173, 174)], [(item.start_page, item.end_page) for item in session.confirmed_spreads()])

    def test_pair_validation_requires_adjacent_pages_inside_source_count(self):
        session = DiagnosisSession(source_page_count=50)

        with self.assertRaisesRegex(ValueError, "adjacent"):
            session.add_manual_spread(10, 12)
        with self.assertRaisesRegex(ValueError, "source page range"):
            session.add_manual_spread(0, 1)
        with self.assertRaisesRegex(ValueError, "source page range"):
            session.add_manual_spread(50, 51)

    def test_pair_id_is_zero_padded_for_sorting_and_display(self):
        self.assertEqual("007-008", adjacent_pair_id(7, 8))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_state -v
```

Expected: FAIL with `ModuleNotFoundError` or missing `DiagnosisSession`.

- [ ] **Step 3: Implement minimal diagnosis state**

Create `src/manga_pdf_to_epub/epub_layout_diagnosis.py` with this initial content:

```python
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
```

- [ ] **Step 4: Run state tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_state -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis.py tests/test_epub_layout_diagnosis_state.py
git commit -m "feat: add spread diagnosis review state"
```

---

### Task 2: Add CSV Adapters For Prototype Outputs

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis.py`
- Create: `tests/test_epub_layout_diagnosis_csv.py`

- [ ] **Step 1: Write failing CSV tests**

Create `tests/test_epub_layout_diagnosis_csv.py`:

```python
import tempfile
import unittest
from pathlib import Path

from manga_pdf_to_epub.epub_layout_diagnosis import (
    read_insert_candidates_csv,
    read_spread_candidates_csv,
    reviewable_insert_candidates,
)


class DiagnosisCsvTests(unittest.TestCase):
    def test_reads_spread_candidates_from_adjacent_clusters_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "adjacent_clusters.csv"
            path.write_text(
                "\n".join(
                    [
                        "cluster,rank_in_cluster,decision,start_page,end_page,right,left,spread,review_score,raw_spread,raw_review_score,margin_to_next,local_margin,context_penalty,stability_score,relative_score,reliability_penalty,reliability_boost,composition,patch,seam_activity,seam_contact,barrier,page_panel,inner_gutter",
                        "1,1,review,37,38,page-037,page-038,0.910000,0.880000,0.900000,0.870000,0.100000,0.060000,0.000000,1.000000,0.900000,0.000000,0.020000,0.700000,0.800000,0.500000,0.520000,0.200000,0.300000,0.100000",
                        "2,1,auto,115,116,page-115,page-116,0.930000,0.910000,0.920000,0.900000,0.120000,0.080000,0.000000,1.000000,0.920000,0.000000,0.010000,0.720000,0.830000,0.550000,0.560000,0.210000,0.310000,0.110000",
                    ]
                ),
                encoding="utf-8",
            )

            candidates = read_spread_candidates_csv(path)

        self.assertEqual(["115-116", "037-038"], [item.pair_id for item in candidates])
        self.assertEqual(115, candidates[0].start_page)
        self.assertEqual("auto", candidates[0].decision)
        self.assertEqual(0.93, candidates[0].score)

    def test_reads_insert_candidates_from_gaps_csv_and_filters_reviewable_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gaps.csv"
            path.write_text(
                "\n".join(
                    [
                        "gap,after_page,before_page,safe_insert_score,label,visual_difference,continuity_risk,reasons",
                        "034-035,34,35,0.940000,C scene_change,0.700000,0.200000,dark pause page; visual discontinuity",
                        "037-038,37,38,0.110000,F do_not_insert,0.100000,0.900000,high continuity risk",
                    ]
                ),
                encoding="utf-8",
            )

            candidates = read_insert_candidates_csv(path)
            reviewable = reviewable_insert_candidates(candidates)

        self.assertEqual([34, 37], [item.after_page for item in candidates])
        self.assertEqual(["034-035"], [item.gap_id for item in reviewable])
        self.assertEqual(("dark pause page", "visual discontinuity"), reviewable[0].reasons)

    def test_missing_required_csv_columns_raise_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("start_page,end_page\n37,38\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                read_spread_candidates_csv(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_csv -v
```

Expected: FAIL with missing CSV reader functions.

- [ ] **Step 3: Implement CSV readers**

Add these imports and dataclass to `src/manga_pdf_to_epub/epub_layout_diagnosis.py`:

```python
import csv
from pathlib import Path
```

```python
@dataclass(frozen=True)
class InsertCandidate:
    gap_id: str
    after_page: int
    before_page: int
    safe_insert_score: float
    label: str
    visual_difference: float
    continuity_risk: float
    reasons: tuple[str, ...] = ()
```

Add these functions:

```python
SPREAD_CLUSTER_REQUIRED_COLUMNS = {
    "start_page",
    "end_page",
    "decision",
    "spread",
    "review_score",
}

INSERT_GAP_REQUIRED_COLUMNS = {
    "gap",
    "after_page",
    "before_page",
    "safe_insert_score",
    "label",
    "visual_difference",
    "continuity_risk",
    "reasons",
}

REVIEWABLE_INSERT_LABEL_PREFIXES = ("A ", "B ", "C ", "D ")


def read_spread_candidates_csv(path: Path) -> list[SpreadCandidate]:
    rows = _read_dict_rows(path, SPREAD_CLUSTER_REQUIRED_COLUMNS)
    candidates: list[SpreadCandidate] = []
    for row in rows:
        start_page = int(row["start_page"])
        end_page = int(row["end_page"])
        candidates.append(
            SpreadCandidate(
                adjacent_pair_id(start_page, end_page),
                start_page,
                end_page,
                float(row["spread"]),
                float(row["review_score"]),
                row["decision"],
                source="spread-continuity",
            )
        )
    return sorted(candidates, key=lambda item: (-item.score, item.start_page, item.end_page))


def read_insert_candidates_csv(path: Path) -> list[InsertCandidate]:
    rows = _read_dict_rows(path, INSERT_GAP_REQUIRED_COLUMNS)
    candidates: list[InsertCandidate] = []
    for row in rows:
        reasons = tuple(part.strip() for part in row["reasons"].split(";") if part.strip())
        candidates.append(
            InsertCandidate(
                row["gap"],
                int(row["after_page"]),
                int(row["before_page"]),
                float(row["safe_insert_score"]),
                row["label"],
                float(row["visual_difference"]),
                float(row["continuity_risk"]),
                reasons,
            )
        )
    return sorted(candidates, key=lambda item: (-item.safe_insert_score, item.after_page, item.before_page))


def reviewable_insert_candidates(candidates: list[InsertCandidate]) -> list[InsertCandidate]:
    return [item for item in candidates if item.label.startswith(REVIEWABLE_INSERT_LABEL_PREFIXES)]


def _read_dict_rows(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required_columns - fieldnames)
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")
        return list(reader)
```

- [ ] **Step 4: Run CSV tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_csv -v
```

Expected: PASS.

- [ ] **Step 5: Run state tests again**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_state tests.test_epub_layout_diagnosis_csv -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis.py tests/test_epub_layout_diagnosis_csv.py
git commit -m "feat: read diagnosis prototype csv outputs"
```

---

### Task 3: Detect Confirmed Spread Damage With Apple Books Cover Gap

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis.py`
- Create: `tests/test_epub_layout_diagnosis_damage.py`

- [ ] **Step 1: Write failing damage tests**

Create `tests/test_epub_layout_diagnosis_damage.py`:

```python
import unittest
from types import SimpleNamespace

from manga_pdf_to_epub.epub_layout_diagnosis import (
    SpreadCandidate,
    diagnose_spread_damage,
    source_preview_placements,
)


def page(source_index: int):
    return SimpleNamespace(label=f"Page {source_index}", source_index=source_index, is_blank=False)


def blank(label: str = "Blank"):
    return SimpleNamespace(label=label, source_index=None, is_blank=True)


class SpreadDamageTests(unittest.TestCase):
    def test_source_preview_placements_include_virtual_apple_cover_gap(self):
        placements = source_preview_placements([page(1), page(2), page(3)], uses_apple_cover_gap=True)

        self.assertEqual(0, placements[1].preview_index)
        self.assertEqual(2, placements[2].preview_index)
        self.assertEqual(3, placements[3].preview_index)

    def test_spread_is_intact_without_virtual_cover_gap(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 41)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=False)

        self.assertEqual("intact", damage.status)
        self.assertEqual("037-038", damage.pair_id)

    def test_virtual_cover_gap_can_damage_otherwise_adjacent_spread(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 41)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=True)

        self.assertEqual("damaged", damage.status)
        self.assertIn("different preview spreads", damage.reason)

    def test_inserted_blank_before_first_page_can_repair_cover_gap_damage(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 37)] + [blank()] + [page(index) for index in range(37, 41)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=True)

        self.assertEqual("intact", damage.status)

    def test_missing_source_page_reports_missing_instead_of_damaged(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 38)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=True)

        self.assertEqual("missing", damage.status)
        self.assertIn("Page 38", damage.reason)

    def test_reversed_source_order_is_damaged(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 37)] + [page(38), page(37), page(39)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=False)

        self.assertEqual("damaged", damage.status)
        self.assertIn("wrong order", damage.reason)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_damage -v
```

Expected: FAIL with missing `diagnose_spread_damage`.

- [ ] **Step 3: Implement placement and damage detection**

Add these dataclasses and functions to `src/manga_pdf_to_epub/epub_layout_diagnosis.py`:

```python
@dataclass(frozen=True)
class SourcePlacement:
    source_index: int
    entry_index: int
    preview_index: int
    preview_pair_index: int


@dataclass(frozen=True)
class SpreadDamage:
    pair_id: str
    start_page: int
    end_page: int
    status: Literal["intact", "damaged", "missing"]
    reason: str
    start_entry_index: int | None
    end_entry_index: int | None


def source_preview_placements(entries: list, uses_apple_cover_gap: bool) -> dict[int, SourcePlacement]:
    placements: dict[int, SourcePlacement] = {}
    for entry_index, entry in enumerate(entries):
        source_index = getattr(entry, "source_index", None)
        if source_index is None or getattr(entry, "is_blank", False):
            continue
        preview_index = entry_index
        if uses_apple_cover_gap and entry_index >= 1:
            preview_index += 1
        placements[source_index] = SourcePlacement(
            source_index=source_index,
            entry_index=entry_index,
            preview_index=preview_index,
            preview_pair_index=preview_index // 2,
        )
    return placements


def diagnose_spread_damage(
    entries: list,
    confirmed_spreads: list[SpreadCandidate],
    uses_apple_cover_gap: bool,
) -> list[SpreadDamage]:
    placements = source_preview_placements(entries, uses_apple_cover_gap)
    reports: list[SpreadDamage] = []
    for spread in confirmed_spreads:
        start = placements.get(spread.start_page)
        end = placements.get(spread.end_page)
        if start is None or end is None:
            missing = []
            if start is None:
                missing.append(f"Page {spread.start_page}")
            if end is None:
                missing.append(f"Page {spread.end_page}")
            reports.append(
                SpreadDamage(
                    spread.pair_id,
                    spread.start_page,
                    spread.end_page,
                    "missing",
                    f"{' and '.join(missing)} missing from current layout",
                    start.entry_index if start else None,
                    end.entry_index if end else None,
                )
            )
            continue
        if start.preview_index + 1 != end.preview_index:
            reports.append(
                SpreadDamage(
                    spread.pair_id,
                    spread.start_page,
                    spread.end_page,
                    "damaged",
                    "Confirmed pages are in different preview spreads or wrong order",
                    start.entry_index,
                    end.entry_index,
                )
            )
            continue
        if start.preview_pair_index != end.preview_pair_index:
            reports.append(
                SpreadDamage(
                    spread.pair_id,
                    spread.start_page,
                    spread.end_page,
                    "damaged",
                    "Confirmed pages are in different preview spreads",
                    start.entry_index,
                    end.entry_index,
                )
            )
            continue
        reports.append(
            SpreadDamage(
                spread.pair_id,
                spread.start_page,
                spread.end_page,
                "intact",
                "Confirmed spread is paired in the current preview",
                start.entry_index,
                end.entry_index,
            )
        )
    return reports
```

- [ ] **Step 4: Run damage tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_damage -v
```

Expected: PASS.

- [ ] **Step 5: Run diagnosis unit tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_epub_layout_diagnosis_state \
  tests.test_epub_layout_diagnosis_csv \
  tests.test_epub_layout_diagnosis_damage -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis.py tests/test_epub_layout_diagnosis_damage.py
git commit -m "feat: detect confirmed spread layout damage"
```

---

### Task 4: Suggest Safe One-Blank Insertion Points

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis.py`
- Create: `tests/test_epub_layout_diagnosis_suggestions.py`

- [ ] **Step 1: Write failing suggestion tests**

Create `tests/test_epub_layout_diagnosis_suggestions.py`:

```python
import unittest
from types import SimpleNamespace

from manga_pdf_to_epub.epub_layout_diagnosis import (
    InsertCandidate,
    SpreadCandidate,
    classify_insert_points,
)


def page(source_index: int):
    return SimpleNamespace(label=f"Page {source_index}", source_index=source_index, is_blank=False)


class InsertSuggestionTests(unittest.TestCase):
    def test_high_scoring_gap_before_damaged_spread_is_suggested(self):
        entries = [page(index) for index in range(1, 41)]
        confirmed = [SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ("scene change",)),
            InsertCandidate("037-038", 37, 38, 0.99, "B low_content_pause", 0.8, 0.1, ("low content",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=True)

        self.assertEqual([34], [item.after_page for item in result.suggestions])
        self.assertEqual(35, result.suggestions[0].insertion_index)
        self.assertEqual(("037-038",), result.suggestions[0].fixes)

    def test_gap_inside_confirmed_spread_is_protected_even_with_high_score(self):
        entries = [page(index) for index in range(1, 41)]
        confirmed = [SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("037-038", 37, 38, 0.99, "B low_content_pause", 0.8, 0.1, ("low content",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=True)

        self.assertEqual([], result.suggestions)
        self.assertEqual([37], [item.after_page for item in result.protected])
        self.assertIn("inside confirmed spread", result.protected[0].reason)

    def test_candidate_that_breaks_currently_intact_spread_is_protected(self):
        entries = [page(index) for index in range(1, 8)]
        confirmed = [SpreadCandidate("001-002", 1, 2, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("001-002", 1, 2, 0.91, "C scene_change", 0.7, 0.2, ("scene change",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=False)

        self.assertEqual([], result.suggestions)
        self.assertEqual("protected", result.protected[0].kind)

    def test_stale_candidate_with_missing_source_page_is_ignored(self):
        entries = [page(index) for index in range(1, 6)]
        confirmed = [SpreadCandidate("003-004", 3, 4, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("009-010", 9, 10, 0.80, "C scene_change", 0.7, 0.2, ("scene change",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=False)

        self.assertEqual([], result.suggestions)
        self.assertEqual([], result.protected)
        self.assertEqual(["009-010"], result.stale_gap_ids)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_suggestions -v
```

Expected: FAIL with missing `classify_insert_points`.

- [ ] **Step 3: Implement insertion classification**

Add these dataclasses and helper functions to `src/manga_pdf_to_epub/epub_layout_diagnosis.py`:

```python
@dataclass(frozen=True)
class InsertReviewPoint:
    kind: Literal["suggested", "protected"]
    gap_id: str
    after_page: int
    before_page: int
    insertion_index: int
    marker_entry_index: int
    score: float
    label: str
    reason: str
    fixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class InsertClassification:
    suggestions: list[InsertReviewPoint]
    protected: list[InsertReviewPoint]
    stale_gap_ids: list[str]


class _DiagnosticBlank:
    label = "Diagnostic blank"
    source_index = None
    is_blank = True


def classify_insert_points(
    entries: list,
    confirmed_spreads: list[SpreadCandidate],
    insert_candidates: list[InsertCandidate],
    uses_apple_cover_gap: bool,
) -> InsertClassification:
    current_damage = diagnose_spread_damage(entries, confirmed_spreads, uses_apple_cover_gap)
    current_by_id = {item.pair_id: item for item in current_damage}
    intact_before = {item.pair_id for item in current_damage if item.status == "intact"}
    damaged_before = {item.pair_id for item in current_damage if item.status == "damaged"}
    suggestions: list[InsertReviewPoint] = []
    protected: list[InsertReviewPoint] = []
    stale: list[str] = []
    source_to_entry = _source_to_entry_index(entries)

    for candidate in reviewable_insert_candidates(insert_candidates):
        insertion_index = _insertion_index_for_candidate(candidate, source_to_entry)
        if insertion_index is None:
            stale.append(candidate.gap_id)
            continue
        marker_entry_index = max(0, insertion_index - 1)
        inside_pair = _confirmed_pair_for_gap(candidate, confirmed_spreads)
        if inside_pair is not None:
            protected.append(
                InsertReviewPoint(
                    "protected",
                    candidate.gap_id,
                    candidate.after_page,
                    candidate.before_page,
                    insertion_index,
                    marker_entry_index,
                    candidate.safe_insert_score,
                    candidate.label,
                    f"Gap is inside confirmed spread {inside_pair.pair_id}",
                )
            )
            continue

        simulated = list(entries)
        simulated.insert(insertion_index, _DiagnosticBlank())
        after_damage = diagnose_spread_damage(simulated, confirmed_spreads, uses_apple_cover_gap)
        after_by_id = {item.pair_id: item for item in after_damage}
        breaks = sorted(pair_id for pair_id in intact_before if after_by_id[pair_id].status != "intact")
        if breaks:
            protected.append(
                InsertReviewPoint(
                    "protected",
                    candidate.gap_id,
                    candidate.after_page,
                    candidate.before_page,
                    insertion_index,
                    marker_entry_index,
                    candidate.safe_insert_score,
                    candidate.label,
                    f"Insertion would damage confirmed spread {breaks[0]}",
                )
            )
            continue
        fixes = tuple(
            pair_id
            for pair_id in sorted(damaged_before)
            if current_by_id[pair_id].status != "intact" and after_by_id[pair_id].status == "intact"
        )
        if fixes:
            suggestions.append(
                InsertReviewPoint(
                    "suggested",
                    candidate.gap_id,
                    candidate.after_page,
                    candidate.before_page,
                    insertion_index,
                    marker_entry_index,
                    candidate.safe_insert_score,
                    candidate.label,
                    f"Repairs confirmed spread {fixes[0]}",
                    fixes,
                )
            )

    suggestions.sort(key=lambda item: (-item.score, item.insertion_index))
    protected.sort(key=lambda item: (item.insertion_index, -item.score))
    return InsertClassification(suggestions, protected, stale)


def _source_to_entry_index(entries: list) -> dict[int, int]:
    result: dict[int, int] = {}
    for index, entry in enumerate(entries):
        source_index = getattr(entry, "source_index", None)
        if source_index is not None and not getattr(entry, "is_blank", False):
            result[source_index] = index
    return result


def _insertion_index_for_candidate(candidate: InsertCandidate, source_to_entry: dict[int, int]) -> int | None:
    after_index = source_to_entry.get(candidate.after_page)
    before_index = source_to_entry.get(candidate.before_page)
    if after_index is None or before_index is None:
        return None
    if after_index > before_index:
        return None
    return after_index + 1


def _confirmed_pair_for_gap(candidate: InsertCandidate, confirmed_spreads: list[SpreadCandidate]) -> SpreadCandidate | None:
    for spread in confirmed_spreads:
        if spread.start_page == candidate.after_page and spread.end_page == candidate.before_page:
            return spread
    return None
```

- [ ] **Step 4: Run suggestion tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_suggestions -v
```

Expected: PASS.

- [ ] **Step 5: Run all diagnosis tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_epub_layout_diagnosis_state \
  tests.test_epub_layout_diagnosis_csv \
  tests.test_epub_layout_diagnosis_damage \
  tests.test_epub_layout_diagnosis_suggestions -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis.py tests/test_epub_layout_diagnosis_suggestions.py
git commit -m "feat: suggest protected spread repair insertions"
```

---

### Task 5: Add Optional Prototype Runner Resolution

**Files:**
- Create: `src/manga_pdf_to_epub/epub_layout_diagnosis_runner.py`
- Create: `tests/test_epub_layout_diagnosis_runner.py`

- [ ] **Step 1: Write failing runner tests**

Create `tests/test_epub_layout_diagnosis_runner.py`:

```python
import tempfile
import unittest
from pathlib import Path

from manga_pdf_to_epub.epub_layout_diagnosis_runner import (
    DiagnosisCommand,
    default_diagnosis_output_dir,
    resolve_insert_score_command,
    resolve_spread_scan_command,
)


class DiagnosisRunnerTests(unittest.TestCase):
    def test_default_output_dir_is_inside_gui_exports(self):
        root = Path("/repo/manga-pdf-to-epub")
        pdf = Path("/books/Vol 01.pdf")

        self.assertEqual(
            root / "epub_layout_gui_exports" / "diagnostics" / "Vol 01" / "spread",
            default_diagnosis_output_dir(root, pdf, "spread"),
        )

    def test_resolves_sibling_spread_continuity_command_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            manga_root = Path(tmp)
            main_root = manga_root / "manga-pdf-to-epub"
            spread_root = manga_root / "manga-spread-continuity"
            python_path = spread_root / ".venv" / "bin" / "python"
            script_path = spread_root / "tools" / "scan_pdf_adjacent.py"
            python_path.parent.mkdir(parents=True)
            script_path.parent.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")
            script_path.write_text("", encoding="utf-8")
            output_dir = main_root / "out"

            command = resolve_spread_scan_command(main_root, Path("/books/book.pdf"), output_dir)

        self.assertIsInstance(command, DiagnosisCommand)
        self.assertEqual(spread_root, command.cwd)
        self.assertIn("scan_pdf_adjacent.py", command.argv[1])
        self.assertIn("--reading", command.argv)

    def test_missing_sibling_spread_command_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = resolve_spread_scan_command(Path(tmp) / "manga-pdf-to-epub", Path("/books/book.pdf"), Path(tmp) / "out")

        self.assertIsNone(command)

    def test_resolves_sibling_insert_point_command_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            manga_root = Path(tmp)
            main_root = manga_root / "manga-pdf-to-epub"
            insert_root = manga_root / "manga-insert-point-scorer"
            python_path = insert_root / ".venv" / "bin" / "python"
            package_dir = insert_root / "src" / "manga_insert_point_scorer"
            python_path.parent.mkdir(parents=True)
            package_dir.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")
            (package_dir / "cli.py").write_text("", encoding="utf-8")
            output_dir = main_root / "out"

            command = resolve_insert_score_command(main_root, Path("/books/book.pdf"), output_dir)

        self.assertIsInstance(command, DiagnosisCommand)
        self.assertEqual(insert_root, command.cwd)
        self.assertEqual("-m", command.argv[1])
        self.assertIn("manga_insert_point_scorer.cli", command.argv)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_runner -v
```

Expected: FAIL with missing runner module.

- [ ] **Step 3: Implement runner resolution**

Create `src/manga_pdf_to_epub/epub_layout_diagnosis_runner.py`:

```python
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiagnosisCommand:
    argv: tuple[str, ...]
    cwd: Path
    output_dir: Path


@dataclass(frozen=True)
class DiagnosisRunResult:
    output_dir: Path
    stdout: str
    stderr: str


def default_diagnosis_output_dir(project_root: Path, pdf_path: Path, kind: str) -> Path:
    return Path(project_root) / "epub_layout_gui_exports" / "diagnostics" / Path(pdf_path).stem / kind


def resolve_spread_scan_command(project_root: Path, pdf_path: Path, output_dir: Path) -> DiagnosisCommand | None:
    spread_root = Path(project_root).resolve().parent / "manga-spread-continuity"
    python_path = spread_root / ".venv" / "bin" / "python"
    script_path = spread_root / "tools" / "scan_pdf_adjacent.py"
    if not python_path.exists() or not script_path.exists():
        return None
    return DiagnosisCommand(
        (
            str(python_path),
            str(script_path),
            str(pdf_path),
            "--output",
            str(output_dir),
            "--reading",
            "rtl",
            "--spread-threshold",
            "0.53",
            "--debug-limit",
            "80",
        ),
        spread_root,
        Path(output_dir),
    )


def resolve_insert_score_command(project_root: Path, pdf_path: Path, output_dir: Path) -> DiagnosisCommand | None:
    insert_root = Path(project_root).resolve().parent / "manga-insert-point-scorer"
    python_path = insert_root / ".venv" / "bin" / "python"
    package_cli = insert_root / "src" / "manga_insert_point_scorer" / "cli.py"
    if not python_path.exists() or not package_cli.exists():
        return None
    return DiagnosisCommand(
        (
            str(python_path),
            "-m",
            "manga_insert_point_scorer.cli",
            str(pdf_path),
            "--output",
            str(output_dir),
        ),
        insert_root,
        Path(output_dir),
    )


def run_diagnosis_command(command: DiagnosisCommand) -> DiagnosisRunResult:
    command.output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command.argv,
        cwd=command.cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return DiagnosisRunResult(command.output_dir, completed.stdout, completed.stderr)
```

- [ ] **Step 4: Run runner tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_diagnosis_runner -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis_runner.py tests/test_epub_layout_diagnosis_runner.py
git commit -m "feat: resolve optional diagnosis prototype runners"
```

---

### Task 6: Build A Focused Diagnose Tab Panel

**Files:**
- Create: `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
- Create: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing panel tests**

Create `tests/test_epub_layout_gui_diagnosis.py` with panel-independent tests first:

```python
import unittest
from types import SimpleNamespace

from manga_pdf_to_epub.epub_layout_diagnosis import (
    DiagnosisSession,
    InsertCandidate,
    SpreadCandidate,
    classify_insert_points,
    diagnose_spread_damage,
)
from manga_pdf_to_epub.epub_layout_diagnosis_gui import diagnosis_summary_texts


def page(source_index: int):
    return SimpleNamespace(label=f"Page {source_index}", source_index=source_index, is_blank=False)


class DiagnosisGuiTextTests(unittest.TestCase):
    def test_summary_text_counts_manual_review_state(self):
        session = DiagnosisSession(source_page_count=120)
        session.load_spread_candidates(
            [
                SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review"),
                SpreadCandidate("071-072", 71, 72, 0.72, 0.70, "review"),
            ]
        )
        session.mark_candidate("037-038", "true")
        damage = diagnose_spread_damage([page(index) for index in range(1, 121)], session.confirmed_spreads(), True)
        insert_result = classify_insert_points(
            [page(index) for index in range(1, 121)],
            session.confirmed_spreads(),
            [InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ())],
            True,
        )

        summary = diagnosis_summary_texts(session, damage, insert_result, stale=False)

        self.assertEqual("Candidates: 2 total, 1 true, 0 false, 1 pending.", summary.candidates)
        self.assertEqual("Damage: 1 damaged, 0 intact, 0 missing.", summary.damage)
        self.assertEqual("Insert points: 1 suggested, 0 protected, 0 stale.", summary.insert_points)

    def test_stale_summary_requires_manual_recheck(self):
        session = DiagnosisSession(source_page_count=120)

        summary = diagnosis_summary_texts(session, [], None, stale=True)

        self.assertEqual("Results are stale. Click Recheck Layout before using suggestions.", summary.staleness)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: FAIL with missing diagnosis GUI module.

- [ ] **Step 3: Implement summary helpers and panel skeleton**

Create `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`:

```python
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from .epub_layout_diagnosis import DiagnosisSession, InsertClassification, SpreadDamage


@dataclass(frozen=True)
class DiagnosisSummaryTexts:
    candidates: str
    damage: str
    insert_points: str
    staleness: str


def diagnosis_summary_texts(
    session: DiagnosisSession,
    damage: list[SpreadDamage],
    insert_result: InsertClassification | None,
    stale: bool,
) -> DiagnosisSummaryTexts:
    candidates = session.spread_candidates()
    true_count = sum(1 for item in candidates if item.status == "true")
    false_count = sum(1 for item in candidates if item.status == "false")
    pending_count = sum(1 for item in candidates if item.status == "pending")
    damaged = sum(1 for item in damage if item.status == "damaged")
    intact = sum(1 for item in damage if item.status == "intact")
    missing = sum(1 for item in damage if item.status == "missing")
    suggested = len(insert_result.suggestions) if insert_result is not None else 0
    protected = len(insert_result.protected) if insert_result is not None else 0
    stale_gaps = len(insert_result.stale_gap_ids) if insert_result is not None else 0
    return DiagnosisSummaryTexts(
        f"Candidates: {len(candidates)} total, {true_count} true, {false_count} false, {pending_count} pending.",
        f"Damage: {damaged} damaged, {intact} intact, {missing} missing.",
        f"Insert points: {suggested} suggested, {protected} protected, {stale_gaps} stale.",
        "Results are stale. Click Recheck Layout before using suggestions." if stale else "",
    )


@dataclass(frozen=True)
class DiagnosisPanelCallbacks:
    run_spread_scan: Callable[[], None]
    import_spread_candidates: Callable[[], None]
    mark_true: Callable[[], None]
    mark_false: Callable[[], None]
    add_missing_spread: Callable[[], None]
    check_damage: Callable[[], None]
    run_insert_scores: Callable[[], None]
    import_insert_scores: Callable[[], None]
    insert_selected: Callable[[], None]
    recheck_layout: Callable[[], None]


class DiagnosisPanel:
    def __init__(self, parent: ttk.Frame, callbacks: DiagnosisPanelCallbacks):
        self.callbacks = callbacks
        self.summary_var = tk.StringVar(value="Run or import spread candidates to begin.")
        self.damage_var = tk.StringVar(value="")
        self.insert_var = tk.StringVar(value="")
        self.stale_var = tk.StringVar(value="")
        self.candidate_list = tk.Listbox(parent, exportselection=False, height=8)
        self.damage_list = tk.Listbox(parent, exportselection=False, height=6)
        self.insert_list = tk.Listbox(parent, exportselection=False, height=6)
        self._build(parent)

    def _build(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Spread Candidates").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.summary_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Run Cross-Page Scan", command=self.callbacks.run_spread_scan).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Import Spread Candidates...", command=self.callbacks.import_spread_candidates).pack(fill=tk.X, pady=(6, 0))
        self.candidate_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Button(parent, text="Mark Selected True", command=self.callbacks.mark_true).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Mark Selected False", command=self.callbacks.mark_false).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Add Missing Spread...", command=self.callbacks.add_missing_spread).pack(fill=tk.X, pady=(6, 0))
        ttk.Separator(parent).pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="Damage Check").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.damage_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Check Damage Against Current Layout", command=self.callbacks.check_damage).pack(fill=tk.X, pady=(6, 0))
        self.damage_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Separator(parent).pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="Insert Points").pack(anchor=tk.W)
        ttk.Label(parent, textvariable=self.insert_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(parent, textvariable=self.stale_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(parent, text="Run Insert-Point Scoring", command=self.callbacks.run_insert_scores).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Import Insert Scores...", command=self.callbacks.import_insert_scores).pack(fill=tk.X, pady=(6, 0))
        self.insert_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        ttk.Button(parent, text="Insert Selected Blank", command=self.callbacks.insert_selected).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(parent, text="Recheck Layout", command=self.callbacks.recheck_layout).pack(fill=tk.X, pady=(6, 0))
```

- [ ] **Step 4: Run panel tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: add diagnosis inspector panel"
```

---

### Task 7: Wire Diagnose Tab Into Main GUI

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `tests/test_epub_layout_gui.py`
- Modify: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing GUI tab tests**

Modify `tests/test_epub_layout_gui.py`:

```python
def test_inspector_tabs_group_workbench_controls(self):
    self.assertEqual(("Edit", "Diagnose", "Book", "Series"), EpubLayoutApp._inspector_tab_titles())
```

Add a test to `tests/test_epub_layout_gui_diagnosis.py`:

```python
from manga_pdf_to_epub.epub_layout_gui import EpubLayoutApp


class DiagnosisGuiIntegrationTests(unittest.TestCase):
    def test_new_pdf_resets_diagnosis_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = None
        app.series_project = "old"
        app.active_series_volume = "old"
        app._sync_navigation_mode = lambda: None
        app._reset_deleted_history = lambda: None
        app._reset_preview_cache = lambda: None
        app._load_metadata_fields = lambda: None
        app.refresh_list = lambda: None
        app.refresh_workspace_status = lambda: None
        app.refresh_preview = lambda: None
        app.page_list = SimpleNamespace(selection_clear=lambda *_args: None, selection_set=lambda *_args: None)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.pdf_path = Path("/tmp/book.pdf")
        app.diagnosis_session = None
        app.spread_damage = ["old"]
        app.insert_classification = "old"
        app.diagnosis_stale = True

        app._open_pdf_done(SimpleNamespace(entries=[page(1), page(2)], source_page_count=2))

        self.assertEqual(2, app.diagnosis_session.source_page_count)
        self.assertEqual([], app.spread_damage)
        self.assertIsNone(app.insert_classification)
        self.assertFalse(app.diagnosis_stale)
```

Make sure the test imports `Path` and `SimpleNamespace` at the top.

- [ ] **Step 2: Run GUI tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui tests.test_epub_layout_gui_diagnosis -v
```

Expected: FAIL because Diagnose is not wired and diagnosis state is not reset.

- [ ] **Step 3: Implement GUI state and tab creation**

Modify imports in `src/manga_pdf_to_epub/epub_layout_gui.py`:

```python
from .epub_layout_diagnosis import (
    DiagnosisSession,
    InsertClassification,
    InsertCandidate,
    SpreadDamage,
)
from .epub_layout_diagnosis_gui import DiagnosisPanel, DiagnosisPanelCallbacks
```

Add fields in `__init__` after `self._page_drag_source`:

```python
self.diagnosis_session: DiagnosisSession | None = None
self.spread_damage: list[SpreadDamage] = []
self.insert_candidates: list[InsertCandidate] = []
self.insert_classification: InsertClassification | None = None
self.diagnosis_stale = False
self.diagnosis_panel: DiagnosisPanel | None = None
self.spine_markers: dict[int, object] = {}
```

Change `_inspector_tab_titles`:

```python
@staticmethod
def _inspector_tab_titles() -> tuple[str, str, str, str]:
    return ("Edit", "Diagnose", "Book", "Series")
```

In `_build_ui`, create and build the Diagnose tab between Edit and Book:

```python
edit_tab = self._add_inspector_tab(content, "Edit")
diagnose_tab = self._add_inspector_tab(content, "Diagnose")
book_tab = self._add_inspector_tab(content, "Book")
series_tab = self._add_inspector_tab(content, "Series")
self._build_edit_tab(edit_tab)
self._build_diagnose_tab(diagnose_tab)
self._build_book_tab(book_tab)
self._build_series_tab(series_tab)
```

Add `_build_diagnose_tab`:

```python
def _build_diagnose_tab(self, parent: ttk.Frame) -> None:
    callbacks = DiagnosisPanelCallbacks(
        self.run_spread_diagnosis,
        self.import_spread_candidates,
        self.mark_selected_spread_true,
        self.mark_selected_spread_false,
        self.add_missing_spread,
        self.check_confirmed_spread_damage,
        self.run_insert_point_scoring,
        self.import_insert_scores,
        self.insert_selected_diagnosis_blank,
        self.recheck_diagnosis_layout,
    )
    self.diagnosis_panel = DiagnosisPanel(parent, callbacks)
```

Add a reset helper:

```python
def _reset_diagnosis_state(self) -> None:
    page_count = self.model.source_page_count if self.model is not None else 0
    self.diagnosis_session = DiagnosisSession(page_count)
    self.spread_damage = []
    self.insert_candidates = []
    self.insert_classification = None
    self.diagnosis_stale = False
    self.spine_markers = {}
```

Call `_reset_diagnosis_state()` inside `_open_pdf_done()` after `self.model = model` and before refreshing the list.

Add stub callback methods that set a clear status for now:

```python
def run_spread_diagnosis(self) -> None:
    self.status.set("Spread scan action is inactive in the Diagnose tab shell.")

def import_spread_candidates(self) -> None:
    self.status.set("Spread candidate import action is inactive in the Diagnose tab shell.")

def mark_selected_spread_true(self) -> None:
    self.status.set("Select a spread candidate to mark true.")

def mark_selected_spread_false(self) -> None:
    self.status.set("Select a spread candidate to mark false.")

def add_missing_spread(self) -> None:
    self.status.set("Manual spread entry action is inactive in the Diagnose tab shell.")

def check_confirmed_spread_damage(self) -> None:
    self.status.set("Damage check action is inactive in the Diagnose tab shell.")

def run_insert_point_scoring(self) -> None:
    self.status.set("Insert-point scoring action is inactive in the Diagnose tab shell.")

def import_insert_scores(self) -> None:
    self.status.set("Insert score import action is inactive in the Diagnose tab shell.")

def insert_selected_diagnosis_blank(self) -> None:
    self.status.set("Select an insert suggestion first.")

def recheck_diagnosis_layout(self) -> None:
    self.check_confirmed_spread_damage()
```

- [ ] **Step 4: Run GUI tab tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 5: Run guardrail test**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_guardrails -v
```

Expected: PASS. If the `EpubLayoutApp` class exceeds 1450 lines, move callback-heavy code into `epub_layout_diagnosis_gui.py` or a new `epub_layout_diagnosis_controller.py` before changing the guardrail.

- [ ] **Step 6: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py tests/test_epub_layout_gui.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: add diagnosis tab shell"
```

---

### Task 8: Implement Candidate Import, Review, And Manual Add

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
- Modify: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing review workflow tests**

Add tests to `tests/test_epub_layout_gui_diagnosis.py`:

```python
class DiagnosisReviewWorkflowTests(unittest.TestCase):
    def test_imported_candidates_replace_existing_session_candidates(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=200)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)

        app._load_spread_candidates(
            [
                SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review"),
                SpreadCandidate("115-116", 115, 116, 0.90, 0.89, "review"),
            ]
        )

        self.assertEqual(2, len(app.diagnosis_session.spread_candidates()))
        self.assertEqual("Loaded 2 spread candidates for review.", app.status_value)
        self.assertTrue(app.panel_refreshed)

    def test_mark_selected_candidate_true_updates_session(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=200)
        app.diagnosis_session.load_spread_candidates([SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review")])
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app._selected_spread_candidate_id = lambda: "037-038"
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)

        app.mark_selected_spread_true()

        self.assertEqual([(37, 38)], [(item.start_page, item.end_page) for item in app.diagnosis_session.confirmed_spreads()])
        self.assertEqual("Marked 037-038 as true spread.", app.status_value)

    def test_manual_missing_spread_is_confirmed(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.diagnosis_session = DiagnosisSession(source_page_count=200)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: None

        app._add_missing_spread_pair(173, 174)

        self.assertEqual([(173, 174)], [(item.start_page, item.end_page) for item in app.diagnosis_session.confirmed_spreads()])
        self.assertEqual("Added confirmed spread 173-174.", app.status_value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: FAIL with missing helper methods.

- [ ] **Step 3: Implement panel refresh and app review helpers**

In `epub_layout_diagnosis_gui.py`, add a `refresh()` method to `DiagnosisPanel`:

```python
def refresh(
    self,
    session: DiagnosisSession | None,
    damage: list[SpreadDamage],
    insert_result: InsertClassification | None,
    stale: bool,
) -> None:
    if session is None:
        self.summary_var.set("Open a PDF to begin diagnosis.")
        self.damage_var.set("")
        self.insert_var.set("")
        self.stale_var.set("")
        return
    summary = diagnosis_summary_texts(session, damage, insert_result, stale)
    self.summary_var.set(summary.candidates)
    self.damage_var.set(summary.damage)
    self.insert_var.set(summary.insert_points)
    self.stale_var.set(summary.staleness)
    self.candidate_list.delete(0, tk.END)
    for item in session.spread_candidates():
        self.candidate_list.insert(
            tk.END,
            f"{item.candidate.pair_id} [{item.status}] spread={item.candidate.score:.3f}",
        )
    self.damage_list.delete(0, tk.END)
    for item in damage:
        self.damage_list.insert(tk.END, f"{item.pair_id} [{item.status}] {item.reason}")
    self.insert_list.delete(0, tk.END)
    if insert_result is not None:
        for item in insert_result.suggestions:
            self.insert_list.insert(tk.END, f"{item.gap_id} [suggested] {item.score:.3f} {item.reason}")
        for item in insert_result.protected:
            self.insert_list.insert(tk.END, f"{item.gap_id} [protected] {item.reason}")
```

In `epub_layout_gui.py`, add app helpers:

```python
def refresh_diagnosis_panel(self) -> None:
    panel = getattr(self, "diagnosis_panel", None)
    if panel is not None:
        panel.refresh(self.diagnosis_session, self.spread_damage, self.insert_classification, self.diagnosis_stale)

def _selected_spread_candidate_id(self) -> str | None:
    panel = getattr(self, "diagnosis_panel", None)
    if panel is None:
        return None
    selection = panel.candidate_list.curselection()
    if not selection or self.diagnosis_session is None:
        return None
    candidates = self.diagnosis_session.spread_candidates()
    index = selection[0]
    if index < 0 or index >= len(candidates):
        return None
    return candidates[index].candidate.pair_id

def _load_spread_candidates(self, candidates: list[SpreadCandidate]) -> None:
    if self.diagnosis_session is None:
        return
    self.diagnosis_session.load_spread_candidates(candidates)
    self.spread_damage = []
    self.insert_classification = None
    self.diagnosis_stale = False
    self.spine_markers = {}
    self.refresh_list(preserve_yview=True)
    self.refresh_diagnosis_panel()
    self.status.set(f"Loaded {len(candidates)} spread candidates for review.")

def mark_selected_spread_true(self) -> None:
    pair_id = self._selected_spread_candidate_id()
    if self.diagnosis_session is None or pair_id is None:
        self.status.set("Select a spread candidate to mark true.")
        return
    self.diagnosis_session.mark_candidate(pair_id, "true")
    self.diagnosis_stale = True
    self.refresh_diagnosis_panel()
    self.status.set(f"Marked {pair_id} as true spread.")

def mark_selected_spread_false(self) -> None:
    pair_id = self._selected_spread_candidate_id()
    if self.diagnosis_session is None or pair_id is None:
        self.status.set("Select a spread candidate to mark false.")
        return
    self.diagnosis_session.mark_candidate(pair_id, "false")
    self.diagnosis_stale = True
    self.refresh_diagnosis_panel()
    self.status.set(f"Marked {pair_id} as false positive.")

def _add_missing_spread_pair(self, start_page: int, end_page: int) -> None:
    if self.diagnosis_session is None:
        return
    candidate = self.diagnosis_session.add_manual_spread(start_page, end_page)
    self.diagnosis_stale = True
    self.refresh_diagnosis_panel()
    self.status.set(f"Added confirmed spread {candidate.pair_id}.")
```

Implement `import_spread_candidates()` with `filedialog.askopenfilename()` and `read_spread_candidates_csv()`. Implement `add_missing_spread()` using two `simpledialog.askinteger()` prompts, then `_add_missing_spread_pair()`. Show `messagebox.showerror()` on `ValueError`.

- [ ] **Step 4: Run review workflow tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 5: Run related GUI tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui tests.test_epub_layout_gui_editing tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: support manual spread candidate review"
```

---

### Task 9: Wire Spread Scan Runner And Damage Check

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing damage workflow tests**

Add tests to `tests/test_epub_layout_gui_diagnosis.py`:

```python
class DiagnosisDamageWorkflowTests(unittest.TestCase):
    def test_damage_check_uses_confirmed_spreads_and_apple_preview_flag(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 41)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_session = DiagnosisSession(source_page_count=40)
        app.diagnosis_session.add_manual_spread(37, 38)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)

        app.check_confirmed_spread_damage()

        self.assertEqual("damaged", app.spread_damage[0].status)
        self.assertEqual("Checked 1 confirmed spreads: 1 damaged, 0 missing.", app.status_value)
        self.assertFalse(app.diagnosis_stale)

    def test_damage_check_requires_confirmed_spreads(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.apple_preview = SimpleNamespace(get=lambda: False)
        app.diagnosis_session = DiagnosisSession(source_page_count=2)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.check_confirmed_spread_damage()

        self.assertEqual("Mark at least one true spread before checking damage.", app.status_value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: FAIL because `check_confirmed_spread_damage()` is still a stub.

- [ ] **Step 3: Implement damage check and runner callback**

In `epub_layout_gui.py`, replace `check_confirmed_spread_damage()`:

```python
def check_confirmed_spread_damage(self) -> None:
    if self.model is None or self.diagnosis_session is None:
        return
    confirmed = self.diagnosis_session.confirmed_spreads()
    if not confirmed:
        self.status.set("Mark at least one true spread before checking damage.")
        return
    self.spread_damage = diagnose_spread_damage(self.model.entries, confirmed, self.apple_preview.get())
    self.insert_classification = None
    self.spine_markers = {}
    self.diagnosis_stale = False
    damaged = sum(1 for item in self.spread_damage if item.status == "damaged")
    missing = sum(1 for item in self.spread_damage if item.status == "missing")
    self.refresh_list(preserve_yview=True)
    self.refresh_diagnosis_panel()
    self.status.set(f"Checked {len(confirmed)} confirmed spreads: {damaged} damaged, {missing} missing.")
```

Implement `run_spread_diagnosis()`:

```python
def run_spread_diagnosis(self) -> None:
    if self.model is None or self.pdf_path is None:
        return
    output_dir = default_diagnosis_output_dir(Path(__file__).resolve().parents[2], self.pdf_path, "spread")
    command = resolve_spread_scan_command(Path(__file__).resolve().parents[2], self.pdf_path, output_dir)
    if command is None:
        messagebox.showerror(
            "Spread scan unavailable",
            "Could not find sibling manga-spread-continuity environment. Use Import Spread Candidates instead.",
        )
        return
    self._run_background(
        "Running cross-page scan. This can take a few minutes.",
        lambda: run_diagnosis_command(command),
        self._spread_scan_done,
    )
```

Add `_spread_scan_done()`:

```python
def _spread_scan_done(self, result) -> None:
    candidates = read_spread_candidates_csv(result.output_dir / "adjacent_clusters.csv")
    self._load_spread_candidates(candidates)
```

Add the needed imports:

```python
from .epub_layout_diagnosis import diagnose_spread_damage, read_spread_candidates_csv
from .epub_layout_diagnosis_runner import (
    default_diagnosis_output_dir,
    resolve_spread_scan_command,
    run_diagnosis_command,
)
```

- [ ] **Step 4: Run damage workflow tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 5: Run GUI and runner tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_epub_layout_gui_diagnosis \
  tests.test_epub_layout_diagnosis_runner -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: check confirmed spread damage"
```

---

### Task 10: Import/Run Insert Scores And Render Spine Markers

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `tests/gui_helpers.py`
- Modify: `tests/test_epub_layout_gui_diagnosis.py`
- Modify: `tests/test_epub_layout_gui_editing.py`

- [ ] **Step 1: Extend fake listbox for marker assertions**

Modify `tests/gui_helpers.py` `FakeListbox`:

```python
def __init__(self, selection=0, yview=(0.4, 0.7)):
    self.items = []
    self.selection = selection
    self.current_yview = yview
    self.moved_to = None
    self.item_options = {}

def itemconfig(self, index, **kwargs):
    self.item_options[index] = kwargs
```

- [ ] **Step 2: Write failing marker workflow tests**

Add tests to `tests/test_epub_layout_gui_diagnosis.py`:

```python
class DiagnosisInsertWorkflowTests(unittest.TestCase):
    def test_insert_scores_classify_and_refresh_spine_markers(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(index) for index in range(1, 41)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_session = DiagnosisSession(source_page_count=40)
        app.diagnosis_session.add_manual_spread(37, 38)
        app.spread_damage = diagnose_spread_damage(app.model.entries, app.diagnosis_session.confirmed_spreads(), True)
        app.page_list = FakeListbox(selection=0)
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)
        app.refresh_workspace_status = lambda: None
        app._is_cover_entry = lambda _entry: False

        app._load_insert_candidates(
            [
                InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ("scene change",)),
                InsertCandidate("037-038", 37, 38, 0.99, "B low_content_pause", 0.8, 0.1, ("low content",)),
            ]
        )

        self.assertEqual(1, len(app.insert_classification.suggestions))
        self.assertIn("insert +0.94", app.page_list.items[34])
        self.assertIn("protected", app.page_list.items[37])
        self.assertEqual("Loaded 2 insert scores: 1 suggested, 1 protected.", app.status_value)

    def test_insert_score_import_requires_damage_check_first(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[page(1), page(2)])
        app.spread_damage = []
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app._load_insert_candidates([InsertCandidate("001-002", 1, 2, 0.9, "C scene_change", 0.7, 0.2, ())])

        self.assertEqual("Check confirmed spread damage before loading insert scores.", app.status_value)
```

Import `FakeListbox`, `InsertCandidate`, and `diagnose_spread_damage` in the test file.

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: FAIL with missing `_load_insert_candidates`.

- [ ] **Step 4: Implement insert loading and markers**

In `epub_layout_gui.py`, add imports:

```python
from .epub_layout_diagnosis import classify_insert_points, read_insert_candidates_csv
from .epub_layout_diagnosis_runner import resolve_insert_score_command
```

Add helper methods:

```python
def _load_insert_candidates(self, candidates: list[InsertCandidate]) -> None:
    if self.model is None or self.diagnosis_session is None:
        return
    if not self.spread_damage:
        self.status.set("Check confirmed spread damage before loading insert scores.")
        return
    self.insert_candidates = candidates
    self.insert_classification = classify_insert_points(
        self.model.entries,
        self.diagnosis_session.confirmed_spreads(),
        candidates,
        self.apple_preview.get(),
    )
    self._sync_spine_markers_from_insert_classification()
    self.diagnosis_stale = False
    self.refresh_list(preserve_yview=True)
    self.refresh_diagnosis_panel()
    suggested = len(self.insert_classification.suggestions)
    protected = len(self.insert_classification.protected)
    self.status.set(f"Loaded {len(candidates)} insert scores: {suggested} suggested, {protected} protected.")

def _sync_spine_markers_from_insert_classification(self) -> None:
    self.spine_markers = {}
    if self.insert_classification is None:
        return
    for item in self.insert_classification.protected:
        self.spine_markers[item.marker_entry_index] = item
    for item in self.insert_classification.suggestions:
        self.spine_markers[item.marker_entry_index] = item

def _marker_text_for_entry(self, entry_index: int) -> str:
    marker = self.spine_markers.get(entry_index)
    if marker is None:
        return ""
    if marker.kind == "suggested":
        return f" [insert +{marker.score:.2f}]"
    return " [protected]"

def _apply_spine_marker_color(self, row_index: int) -> None:
    marker = self.spine_markers.get(row_index)
    if marker is None:
        return
    try:
        if marker.kind == "suggested":
            self.page_list.itemconfig(row_index, foreground="#0b6b2b")
        else:
            self.page_list.itemconfig(row_index, foreground="#9f1d20")
    except tk.TclError:
        pass
```

Modify `refresh_list()` row insertion:

```python
for i, entry in enumerate(self.model.entries, start=1):
    row_index = i - 1
    marker = "[blank]" if entry.is_blank else "[page]"
    cover = " [cover]" if self._is_cover_entry(entry) else ""
    diagnosis_marker = self._marker_text_for_entry(row_index)
    self.page_list.insert(tk.END, f"{i:04d} {marker}{cover} {entry.label}{diagnosis_marker}")
    self._apply_spine_marker_color(row_index)
```

Implement `import_insert_scores()` with `filedialog.askopenfilename()` and `read_insert_candidates_csv()`. Implement `run_insert_point_scoring()` with `resolve_insert_score_command()`, `run_diagnosis_command()`, and `_insert_scoring_done()` mirroring spread scan.

- [ ] **Step 5: Run marker tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 6: Run editing tests to catch marker refresh regressions**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_editing tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py tests/gui_helpers.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: display diagnosis insert markers"
```

---

### Task 11: Execute One User-Approved Blank Insertion

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py`
- Modify: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing insertion execution tests**

Add tests to `tests/test_epub_layout_gui_diagnosis.py`:

```python
class DiagnosisInsertionExecutionTests(unittest.TestCase):
    def test_insert_selected_suggestion_calls_layout_model_once_and_marks_results_stale(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([page(index) for index in range(1, 41)])
        app.apple_preview = SimpleNamespace(get=lambda: True)
        app.diagnosis_session = DiagnosisSession(source_page_count=40)
        app.diagnosis_session.add_manual_spread(37, 38)
        app.spread_damage = diagnose_spread_damage(app.model.entries, app.diagnosis_session.confirmed_spreads(), True)
        app._load_insert_candidates(
            [InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ("scene change",))]
        )
        app.diagnosis_panel = SimpleNamespace(insert_list=FakeListbox(selection=0))
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))
        app._refresh_after_layout_edit = lambda select_index: setattr(app, "selected_after_insert", select_index)
        app.refresh_diagnosis_panel = lambda: setattr(app, "panel_refreshed", True)

        app.insert_selected_diagnosis_blank()

        self.assertEqual("Blank 36", app.model.entries[35].label)
        self.assertTrue(app.diagnosis_stale)
        self.assertEqual({}, app.spine_markers)
        self.assertEqual("Inserted blank for suggested gap 034-035. Click Recheck Layout before continuing.", app.status_value)

    def test_insert_selected_requires_suggested_row(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.insert_classification = None
        app.status = SimpleNamespace(set=lambda value: setattr(app, "status_value", value))

        app.insert_selected_diagnosis_blank()

        self.assertEqual("Select an insert suggestion first.", app.status_value)
```

Import `FakeDeleteModel` from `tests.gui_helpers`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: FAIL because insertion callback is still a stub.

- [ ] **Step 3: Implement selected suggestion lookup and insertion**

In `epub_layout_gui.py`, add:

```python
def _selected_insert_suggestion(self):
    if self.insert_classification is None:
        return None
    panel = getattr(self, "diagnosis_panel", None)
    if panel is None:
        return None
    selection = panel.insert_list.curselection()
    if not selection:
        return None
    index = selection[0]
    if index < 0 or index >= len(self.insert_classification.suggestions):
        return None
    return self.insert_classification.suggestions[index]

def insert_selected_diagnosis_blank(self) -> None:
    if self.model is None:
        return
    suggestion = self._selected_insert_suggestion()
    if suggestion is None:
        self.status.set("Select an insert suggestion first.")
        return
    try:
        self.model.insert_blank(suggestion.insertion_index)
        self.spread_damage = []
        self.insert_classification = None
        self.spine_markers = {}
        self.diagnosis_stale = True
        self._refresh_after_layout_edit(select_index=suggestion.insertion_index)
        self.refresh_diagnosis_panel()
        self.status.set(
            f"Inserted blank for suggested gap {suggestion.gap_id}. Click Recheck Layout before continuing."
        )
    except Exception as exc:
        messagebox.showerror("Diagnosis insert failed", str(exc))
```

In `epub_layout_diagnosis_gui.py`, keep protected rows after suggestions in `insert_list`, but document in code by ordering suggestions first so `_selected_insert_suggestion()` can map list index directly to suggestions.

- [ ] **Step 4: Run insertion execution tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 5: Run editing and preview tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_epub_layout_gui_editing \
  tests.test_epub_layout_gui_preview \
  tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py src/manga_pdf_to_epub/epub_layout_diagnosis_gui.py tests/test_epub_layout_gui_diagnosis.py
git commit -m "feat: insert approved diagnosis blank"
```

---

### Task 12: Handle Layout Changes And Stale Diagnosis State

**Files:**
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py`
- Modify: `tests/test_epub_layout_gui_editing.py`
- Modify: `tests/test_epub_layout_gui_diagnosis.py`

- [ ] **Step 1: Write failing stale-state tests**

Add to `tests/test_epub_layout_gui_editing.py`:

```python
def test_layout_edit_marks_diagnosis_stale_and_clears_markers(self):
    app = EpubLayoutApp.__new__(EpubLayoutApp)
    app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
    app.page_list = FakeListbox(selection=0)
    app.spine_markers = {0: object()}
    app.diagnosis_stale = False
    app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
    app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
    app.refresh_diagnosis_panel = lambda: setattr(app, "diagnosis_refreshed", True)

    app._refresh_after_layout_edit(select_index=1)

    self.assertTrue(app.diagnosis_stale)
    self.assertEqual({}, app.spine_markers)
    self.assertTrue(app.diagnosis_refreshed)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_editing -v
```

Expected: FAIL because `_refresh_after_layout_edit()` does not mark diagnosis stale yet.

- [ ] **Step 3: Implement stale-state helper**

Add to `epub_layout_gui.py`:

```python
def _mark_diagnosis_stale(self) -> None:
    if not hasattr(self, "diagnosis_stale"):
        return
    self.diagnosis_stale = True
    self.insert_classification = None
    self.spine_markers = {}
    self.refresh_diagnosis_panel()
```

Modify `_refresh_after_layout_edit()`:

```python
if mark_edited:
    self._mark_active_volume_edited()
    self._mark_diagnosis_stale()
```

In `insert_selected_diagnosis_blank()`, keep explicit stale status and avoid double-refresh by accepting the duplicated refresh. The duplicated refresh is cheap and keeps the shared edit path honest.

- [ ] **Step 4: Run editing tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_epub_layout_gui_editing tests.test_epub_layout_gui_diagnosis -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/manga_pdf_to_epub/epub_layout_gui.py tests/test_epub_layout_gui_editing.py
git commit -m "feat: mark diagnosis stale after layout edits"
```

---

### Task 13: Documentation And User-Facing Copy

**Files:**
- Modify: `README.md`
- Create: `docs/diagnosis-workflow.md`
- Modify: `src/manga_pdf_to_epub/epub_layout_gui.py` only for final button/status copy adjustments

- [ ] **Step 1: Update README feature list and GUI workflow**

Add these bullets to the README feature list:

```markdown
- Diagnose possible split double-page spreads from a single-volume GUI workflow.
- Manually confirm true spreads, add missed spread pairs, and check whether the current Apple Books preview layout damages them.
- Review color-marked blank insertion suggestions before executing one insertion at a time.
```

Add a short section after "GUI Workflow":

```markdown
## Diagnosis Workflow

The `Diagnose` tab is a human-in-the-loop repair workflow. It can run or import
cross-page spread candidates, but it does not trust them automatically. Mark each
true spread manually, mark false positives as false when useful, and add any
missed adjacent spread pair before checking damage.

Damage checking uses the same Apple Books cover-gap preview flag as the main
spread preview. When the flag is enabled, the virtual blank page beside the cover
is included in the pairing check because it can shift later spreads.

Insert-point scoring is a second manual step. Green spine markers show suggested
one-blank insertions that repair at least one damaged confirmed spread without
breaking currently intact confirmed spreads. Red markers show protected gaps.
The tool inserts only the selected suggestion, then marks diagnosis results stale
until you click `Recheck Layout`.
```

- [ ] **Step 2: Create detailed workflow doc**

Create `docs/diagnosis-workflow.md`:

```markdown
# Diagnosis Workflow

This workflow reduces manual spread repair work without removing the human
review step.

## Phases

1. Open one PDF volume.
2. Open the `Diagnose` tab.
3. Run `Run Cross-Page Scan` or import an `adjacent_clusters.csv` file from
   `manga-spread-continuity`.
4. Review each candidate visually in the main preview and mark it true or false.
5. Use `Add Missing Spread...` for true spreads that did not appear in the scan.
6. Click `Check Damage Against Current Layout`.
7. Run `Run Insert-Point Scoring` or import a `gaps.csv` file from
   `manga-insert-point-scorer`.
8. Review green and red spine markers.
9. Select one suggested insert row and click `Insert Selected Blank`.
10. Click `Recheck Layout` before deciding on another insertion.

## Manual Gates

The GUI never performs scan, damage check, scoring, and insertion as one chained
operation. Scan results are candidates. Insert scores are suggestions. Only a
user click changes the layout.

## Apple Books Cover Gap

The damage check uses the current `Preview Apple Books cover gap` checkbox. This
matters because Apple Books can place a virtual blank page beside the cover and
shift every following pair. A spread such as `037-038` can be intact with the
flag off and damaged with the flag on.

## Marker Meaning

Green `insert +score` markers show one-blank insertion points that repair one or
more damaged confirmed spreads and do not break currently intact confirmed
spreads.

Red `protected` markers show gaps inside confirmed spreads or gaps where a blank
would break an intact confirmed spread.

## Prototype Outputs

The spread scan consumes `adjacent_clusters.csv` from `manga-spread-continuity`.
The insert review consumes `gaps.csv` from `manga-insert-point-scorer`.
```

- [ ] **Step 3: Run doc-adjacent tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_guardrails -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/diagnosis-workflow.md
git commit -m "docs: describe spread diagnosis workflow"
```

---

### Task 14: Full Verification And Manual Smoke

**Files:**
- No source changes expected unless verification finds a defect.

- [ ] **Step 1: Run all unit tests**

Run:

```bash
make test
```

Expected: `Ran ... tests` and `OK`.

- [ ] **Step 2: Run lint/compile smoke**

Run:

```bash
make lint
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run CLI smoke**

Run:

```bash
make smoke
```

Expected: no output and exit code 0.

- [ ] **Step 4: Manual GUI smoke**

Run:

```bash
.venv/bin/python epub_layout_gui.py
```

Manual checks:

- Open a small PDF.
- Confirm inspector tabs show `Edit`, `Diagnose`, `Book`, `Series`.
- Import a handmade `adjacent_clusters.csv` with one candidate.
- Mark the candidate true.
- Toggle `Preview Apple Books cover gap` and click `Check Damage Against Current Layout`.
- Import a handmade `gaps.csv`.
- Confirm green and red spine row markers render as text suffixes and colors.
- Click one green suggestion and verify exactly one blank page appears in spine order.
- Verify the Diagnose tab shows stale results until `Recheck Layout` is clicked.

- [ ] **Step 5: Final status**

Run:

```bash
git status --short
git log --oneline --decorate -5
```

Expected: worktree clean after commits; recent commits match the task commits above.

---

## Self-Review Checklist

- Spec coverage:
  - Single-volume GUI first: Tasks 6-12.
  - Manual spread candidate review: Tasks 1, 6, 8.
  - Manual add missing spread: Tasks 1 and 8.
  - Damage detection includes Apple Books cover gap: Task 3 and Task 9.
  - Insert-point suggestions from scorer output: Tasks 2, 4, 10.
  - Minimum one-blank change and protect confirmed spreads: Task 4.
  - Green/red spine markers: Task 10.
  - User-click-only insertion: Task 11.
  - Stale/recheck flow: Task 12.
  - Docs: Task 13.
- Type consistency:
  - `SpreadCandidate`, `InsertCandidate`, `DiagnosisSession`, `SpreadDamage`, `InsertClassification`, and `InsertReviewPoint` are defined before GUI tasks use them.
  - GUI callback names in `DiagnosisPanelCallbacks` match stub and final methods in `EpubLayoutApp`.
  - `FakeListbox.itemconfig()` is added before marker tests assert item color options.
- Risk notes:
  - The existing `EpubLayoutApp` line-count guardrail is already tight. Keep heavy logic out of the app class and move callbacks to a controller module if Task 7 or later pushes the class above the current ceiling.
  - The sibling prototype runners are optional. Users can always import CSV outputs if sibling repos or virtual environments are unavailable.
  - The first implementation sorts suggestions by scorer score. If real use shows "closest repair before target spread" matters more than score, add a later scoring tie-break task with labeled examples.
