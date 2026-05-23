# Diagnose Window UX Design

## Context

The current Diagnose tab lives inside the right inspector column of `EPUB Layout Lab`. It proves the diagnosis workflow, but the panel is too cramped for the actual HITL task: users must visually inspect candidate spreads, manually add missed spreads, recheck layout damage, inspect insert suggestions, and apply one repair at a time.

The intended workflow is a review workbench, not a compact inspector. The UI should make real page selection and visual verification central.

## Goals

- Move diagnosis review into a separate Diagnose window with enough space for spine selection, large preview, and workflow queues.
- Keep the Diagnose window fully linked to the main window. It must be a second view over the same app state, not a detached copy.
- Replace `Import Spread Candidates...` as the primary manual path with selecting two pages from Spine order and adding them as a confirmed spread.
- Preserve HITL behavior: no one-click scan/repair chain, and every stage remains manually triggered.
- Keep stale-state safety from the current implementation: old insert suggestions must become unavailable when layout assumptions change.

## Non-Goals

- Do not change the spread-continuity or insert-point prototype algorithms.
- Do not add automatic repair of all suggestions.
- Do not introduce a second layout model, second diagnosis session, or background project state for the Diagnose window.
- Do not make CSV import the main user-facing way to add missing spreads.

## Chosen Direction

Use a separate `tk.Toplevel` Diagnose window.

The main window keeps the core editing workflow and preview. Its inspector should no longer host the full diagnosis panel. Instead, it should provide a clear entry point such as `Open Diagnose Window`.

The Diagnose window contains:

- Left: a copied Spine order list used for diagnosis selection.
- Center: a large RTL spread preview driven by the selected row.
- Right: diagnosis workflow controls and lists for candidate review, damage reports, and insert suggestions.

The copied Spine order list is only a view. It reads and writes through the main app controller and the shared `LayoutModel`.

## Shared State

The main window and Diagnose window share these objects:

- `LayoutModel`
- `DiagnosisSession`
- `spread_damage`
- `insert_candidates`
- `insert_classification`
- `diagnosis_stale`
- `spine_markers`
- Apple Books preview-gap setting

The Diagnose window must not own its own persistent model/session. Closing the window only destroys widgets. Reopening it rebuilds the view from current app state.

## Selection Sync

Main and Diagnose spine selections are bidirectionally synchronized.

Rules:

- Selecting a row in the main Spine order selects the same row in the Diagnose window, if it is open.
- Selecting a row in the Diagnose window selects the same row in the main Spine order.
- Both selections refresh the visible preview for the active view.
- Synchronization uses a guard such as `_syncing_spine_selection` to prevent Tk selection-event loops.
- If a layout edit changes the entry count, refresh both spine lists. Preserve the selected index when possible; otherwise clamp to the last available row.
- Selection sync must not mark the layout edited and must not mutate diagnosis results by itself.

## Manual Confirmed Spread Addition

The main manual path is:

1. User selects exactly two rows in the Diagnose window Spine order.
2. User clicks `Add Selected As Spread`.
3. The app validates the selection.
4. If valid, it adds the pair to the shared `DiagnosisSession` as a confirmed spread.
5. Diagnosis damage and insert suggestions become stale; insert classification and markers are cleared.
6. Both main and Diagnose views refresh.

Validation:

- Exactly two rows must be selected.
- Both rows must represent real source pages, not blank pages or inserted images without source indexes.
- The source page numbers must be adjacent.
- The selected layout rows must be in the current spine order and represent the intended pair.

Failure behavior:

- Do not mutate state.
- Set a clear status message, for example `Select exactly two adjacent real pages.`
- Keep the current selection so the user can correct it.

## Candidate Review

`Run Cross-Page Scan` remains the automated candidate discovery entry point.

Candidate review stays manual:

- Scan/imported candidates appear in the workflow queue.
- User marks each candidate true or false.
- Marking true/false invalidates damage and insert suggestions.
- Users can add missed true spreads from the Diagnose spine list at any time.

`Import Spread Candidates...` should not appear as a primary workflow button.

Treatment:

- Remove it from the primary Diagnose window controls.
- Keep the underlying command callable for tests and prototype handoff.
- If exposed in the UI later, expose it only as an advanced/debug action, not as the normal path.
- Update unavailable-runner messages so they point users to manual review from the Spine order first.

## Damage And Insert Workflow

The current manual stages remain:

- `Check Damage Against Current Layout`
- `Run Insert-Point Scoring` or `Import Insert Scores...`
- Select one suggested insert point
- `Insert Selected Blank`
- Recheck layout before continuing

The Diagnose window should make these stages easier to scan:

- Candidate review list shows status: pending, true, false, manual.
- Damage list shows damaged, intact, missing.
- Insert suggestions show suggested and protected points.
- Green/red spine markers remain visible in both main and Diagnose spine lists.

## Apple Books Preview Gap

The Apple Books preview-gap setting remains shared.

When toggled:

- Mark diagnosis results stale.
- Clear insert classification and spine markers.
- Refresh both main and Diagnose previews.
- Refresh both spine lists while preserving current selection.

This matters because the preview-gap model can be the reason a confirmed spread appears damaged.

## Window Lifecycle

- Opening Diagnose creates the Toplevel if needed and focuses it if it already exists.
- Closing Diagnose destroys only widgets and clears the window reference.
- Reopening Diagnose rebuilds from the shared app state.
- If no PDF/model is loaded, opening Diagnose should not create a window and should set status to `Open a PDF before opening Diagnose.`
- Long-running scan/scoring still uses the existing background runner and busy-state behavior.

## Error Handling

- Invalid manual spread selection reports status and does not show a disruptive dialog.
- Prototype runner unavailability may still use an error dialog, because it is an external setup problem.
- CSV parse errors may still use an error dialog for advanced import actions.
- Insert execution failures continue to use an error dialog.

## Testing Requirements

Add focused tests for:

- Opening Diagnose creates/focuses a separate window rather than building the full panel in the inspector.
- Closing and reopening Diagnose preserves shared diagnosis state.
- Main spine selection updates Diagnose spine selection.
- Diagnose spine selection updates main spine selection and preview selection.
- Selection synchronization does not recurse.
- Layout edits refresh both spine lists and clamp/preserve selection.
- `Add Selected As Spread` succeeds for exactly two adjacent real source pages.
- `Add Selected As Spread` rejects blanks, inserted images, non-adjacent source pages, and wrong selection counts.
- Apple Books preview-gap toggle invalidates diagnosis and refreshes both views without losing selection.
- Existing HITL checks remain: no chained scan to damage check to scoring to insert.

## Implementation Boundaries

Prefer keeping Diagnose-window code outside `epub_layout_gui.py` where practical:

- Keep shared diagnosis behavior in `epub_layout_diagnosis_controller.py`.
- Put Diagnose window widgets in `epub_layout_diagnosis_gui.py` or a new small GUI module.
- Keep `EpubLayoutApp` under the current complexity guardrail.
- Reuse existing pure diagnosis functions and CSV adapters.

## Success Criteria

- The user can open a spacious Diagnose window and complete the whole review/repair loop without using the cramped inspector panel.
- The user can add a missed spread by selecting two adjacent real pages from the Diagnose spine list.
- Main and Diagnose windows stay visibly synchronized.
- No stale insert suggestion remains executable after confirmed-spread changes, layout edits, or preview-gap changes.
- Full test, lint, and smoke suites pass.
