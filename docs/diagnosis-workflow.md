# Diagnosis Workflow

This workflow reduces manual spread repair work without removing the human
review step.

## Phases

1. Open one PDF volume.
2. Click `Open Diagnose Window`.
3. Click `Run Cross-Page Scan`.
4. Review each candidate visually in the Diagnose preview and mark it true or
   false.
5. For a true spread that did not appear in the scan, select exactly two
   adjacent real pages in the Diagnose Spine order and click
   `Add Selected As Spread`.
6. Click `Check Damage Against Current Layout`.
7. Click `Run Insert-Point Scoring`.
8. Review green and red spine markers.
9. Select one suggested insert row and click `Insert Selected Blank`.
10. Click `Recheck Layout` before deciding on another insertion.

## Manual Gates

The GUI never performs scan, damage check, scoring, and insertion as one chained
operation. Scan results are candidates. Insert scores are suggestions. Only a
user click changes the layout.

The Diagnose window is linked to the main editor. Selecting a row in either
Spine order selects the same row in the other view, and both views read from the
same layout model and diagnosis session. Closing and reopening the Diagnose
window does not discard confirmed spreads or diagnosis state.

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

The normal workflow launches `manga-spread-continuity` for spread candidates and
`manga-insert-point-scorer` for insertion suggestions when those sibling
prototype environments are available. Insert scores can still be imported from a
`gaps.csv` file for prototype handoff. Spread candidate CSV import is retained as
an advanced command path, but the primary missed-spread workflow is selecting
pages directly from the Diagnose Spine order.
