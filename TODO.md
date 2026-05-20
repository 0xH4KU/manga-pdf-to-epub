# Manga PDF to EPUB TODO

This roadmap keeps the project focused on its current niche: lossless fixed-layout manga EPUB/CBZ workflows, Apple Books spread correction, and practical batch review for collectors.

Current verified baseline:

- `.venv/bin/python -m py_compile epub_layout_gui.py epub_layout_model.py epub_batch_model.py epub_series_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py`
- `.venv/bin/python -m unittest`
- Result on 2026-05-20: 130 tests passed with the project `.venv`.

Use `.venv/bin/python` for local verification. System `python3` may not have `fitz` / PyMuPDF installed.

## Priority Guide

- `P0`: Reliability or data-loss prevention. Do first.
- `P1`: High workflow value, low-to-medium risk.
- `P2`: Useful polish or automation.
- `P3`: Larger compatibility work that needs real sample PDFs.

## Working Rules

- Preserve source image bytes whenever the PDF stores usable JPEG streams.
- Prefer explicit errors or warnings over silent quality loss.
- Keep Apple Books behavior as a first-class preview/export target.
- Add tests before implementation for each behavior change.
- Keep generated EPUB internals deterministic where practical.
- Avoid broad "general converter" scope unless it directly improves manga workflows.

## Suggested Implementation Order

1. Series project save/load.
2. Series validation and safer export.
3. Background series export with progress.
4. CLI parity for GUI metadata/preset features.
5. Preview performance improvements.
6. EPUB validation upgrades.
7. PDF compatibility expansion with real samples.
8. Packaging and release polish.

## P0: Series Project Save/Load

Goal: allow a long manga series review session to be saved, closed, reopened, and continued without losing per-volume edits or ready state.

Why it matters:

- Current series state lives in memory.
- Long series may need multiple review sessions.
- Per-volume edits, inserted images, cover choices, and ready status are too valuable to lose.

Primary files:

- `epub_series_model.py`
- `epub_layout_model.py`
- `epub_layout_gui.py`
- `test_epub_series_model.py`
- `test_epub_layout_gui.py`

Proposed format:

- JSON file, e.g. `series-project.json`.
- Include a top-level `version: 1`.
- Store project title, author, language, output directory if known, and active volume number if useful.
- Store each volume's PDF path, volume number, status, output path, warnings, error, and serialized layout preset payload.
- Store paths relative to the project file where possible; preserve absolute paths when relative paths cannot be computed.
- Store inserted image paths using the same path policy as PDFs.

Tasks:

- [ ] Add `SeriesProject.to_payload(project_path: Path | None = None) -> dict`.
- [ ] Add `SeriesProject.from_payload(payload: dict, project_path: Path | None = None) -> SeriesProject`.
- [ ] Add helper functions for relative/absolute path serialization.
- [ ] Add `LayoutModel.to_preset_payload() -> dict` so save project does not need to write temporary preset files.
- [ ] Add `LayoutModel.from_preset_payload` or reuse `apply_preset_payload` after loading from PDF.
- [ ] Add GUI commands: `Save Project...`, `Open Project...`.
- [ ] Add command palette entries for project save/load.
- [ ] Update status bar after project load.
- [ ] Ensure active series selection is restored if the saved active volume still exists.

Acceptance criteria:

- [ ] User can import a series, edit multiple volumes, save a project file, restart the GUI, open the project, and see the same volume statuses.
- [ ] Ready/Edited/Failed/Unreviewed states survive round-trip.
- [ ] Per-volume blanks, deletions, inserted images, cover selection, cover-only mode, title/author/language survive round-trip.
- [ ] Missing PDFs or inserted images produce clear warnings instead of crashing the whole project load.
- [ ] Project files saved next to PDFs continue working if the folder is moved together.

Tests:

- [ ] Unit test project payload round-trip with two volumes and different statuses.
- [ ] Unit test relative path restoration.
- [ ] Unit test missing inserted image warning.
- [ ] GUI unit test that `Save Project...` calls the model serializer and updates status.
- [ ] GUI unit test that `Open Project...` refreshes series list, metadata fields, and preview.

## P0: Series Validation Before Export

Goal: prevent accidental bad batch exports by validating ready volumes before writing EPUBs.

Why it matters:

- `SeriesVolume` already has `warnings`, but series export does not yet use them deeply.
- Legacy batch validation checks page-count mismatch and filename collisions; series mode should regain that safety.

Primary files:

- `epub_series_model.py`
- `epub_layout_model.py`
- `epub_layout_gui.py`
- `test_epub_series_model.py`

Checks to add:

- [ ] Output filename collision after safe filename generation.
- [ ] Missing source PDF.
- [ ] Missing inserted image referenced by a volume layout.
- [ ] Zero image pages after edits.
- [ ] Cover-only export would remove all reading pages.
- [ ] Page count differs from first loaded volume or an optional baseline.
- [ ] Duplicate volume numbers after import.
- [ ] Unsupported image filter errors during lazy model load.

Tasks:

- [ ] Add `SeriesProject.validate_ready(output_dir: Path) -> dict[str, int]`.
- [ ] Add `SeriesProject.validate_all(output_dir: Path) -> dict[str, int]`.
- [ ] Store warnings on each `SeriesVolume`.
- [ ] Update `export_ready` to validate first.
- [ ] Decide whether warnings block export. Recommended first pass: warnings do not block, errors block.
- [ ] Show a summary dialog before export if warnings exist.
- [ ] Add a command palette item: `Validate Series`.

Acceptance criteria:

- [ ] Export summary distinguishes exported, failed, skipped, and warning counts.
- [ ] Filename collision is reported before any colliding EPUB is overwritten.
- [ ] Missing inserted image is tied to the exact volume and path.
- [ ] Failed volume does not stop later ready volumes from exporting.

Tests:

- [ ] Unit test filename collision warnings.
- [ ] Unit test missing PDF failure.
- [ ] Unit test missing inserted cover warning/failure.
- [ ] Unit test duplicate volume numbers.
- [ ] Unit test export skips invalid volumes and continues valid ones.

## P1: Background Series Export With Progress

Goal: keep the GUI responsive during multi-volume export and provide visible progress.

Why it matters:

- Single PDF open/export already uses background work.
- Series export currently runs synchronously and may freeze the GUI on large sets.

Primary files:

- `epub_layout_gui.py`
- `epub_series_model.py`
- `test_epub_layout_gui.py`

Tasks:

- [ ] Add an iterator-style export API, e.g. `SeriesProject.export_ready_iter(output_dir)`.
- [ ] Yield per-volume progress events: started, exported, skipped, failed.
- [ ] Add a small progress window with current volume, counts, and a disabled/enabled close button.
- [ ] Add cancel support if simple to wire safely.
- [ ] Keep `_busy` true during export and reject concurrent open/export operations.
- [ ] Refresh series list after each finished volume.
- [ ] Write the final summary to the status bar.

Acceptance criteria:

- [ ] GUI remains responsive during export.
- [ ] User sees current volume and aggregate progress.
- [ ] Failure in one volume is visible but does not hide the final summary.
- [ ] Reentrant export/open actions are blocked while export runs.

Tests:

- [ ] Unit test `_run_background` is used for series export.
- [ ] Unit test progress callback receives each volume.
- [ ] Unit test failed volume updates status and error.
- [ ] Unit test busy state blocks a second export.

## P1: CLI Parity for GUI Metadata and Presets

Goal: let power users automate the same high-value operations available in the GUI.

Why it matters:

- Current CLI supports basic conversion, cover blanks, Apple Books mode, and first-spread metadata.
- GUI supports richer metadata, selected cover, cover-only, layout presets, and inserted images.

Primary files:

- `pdf_to_epub_lossless.py`
- `epub_layout_model.py`
- `epub_series_model.py`
- `test_pdf_to_epub_lossless.py`
- `test_epub_layout_model.py`

Proposed CLI options:

- [ ] `--title TEXT`
- [ ] `--author TEXT`
- [ ] `--language CODE`
- [ ] `--cover-page N`
- [ ] `--cover-only`
- [ ] `--preset PATH`
- [ ] `--insert-image-before POSITION=PATH`
- [ ] `--insert-image-after POSITION=PATH`
- [ ] `--delete-first N`
- [ ] `--delete-last N`
- [ ] `--delete-range START-END`
- [ ] `--series-title TEXT`
- [ ] `--volume-number N` or automatic volume inference

Tasks:

- [ ] Route CLI conversions through `LayoutModel` when layout-changing options are used.
- [ ] Keep the existing fast direct path for simple conversion if no layout options are supplied.
- [ ] Validate mutually exclusive options in argparse.
- [ ] Print a clear summary of layout operations applied.
- [ ] Document examples in README.

Acceptance criteria:

- [ ] CLI can export an EPUB with title, author, language, selected cover, and cover-only behavior.
- [ ] CLI can apply a v2 preset to a PDF.
- [ ] CLI can delete first/last/range pages without GUI.
- [ ] Existing CLI examples continue working.

Tests:

- [ ] Unit test metadata args appear in OPF.
- [ ] Unit test invalid cover page fails before writing output.
- [ ] Unit test `--preset` applies blank/deleted page layout.
- [ ] Unit test delete range changes spine order and normalized filenames.
- [ ] Unit test conflicting options produce argparse errors.

## P1: Preview Performance and Thumbnail Cache

Goal: make large-volume navigation feel snappy while keeping memory bounded.

Why it matters:

- Preview currently opens the PDF during thumbnail generation.
- Cache keys include rendered size, so resizing can create many thumbnails.
- Large series review benefits from fast neighboring-page preview.

Primary files:

- `epub_layout_gui.py`
- `test_epub_layout_gui.py`

Tasks:

- [ ] Replace plain dict thumbnail cache with a bounded LRU cache.
- [ ] Normalize preview render size into buckets to reduce cache fragmentation.
- [ ] Reuse an open `fitz.Document` per active volume, closing it when switching PDFs.
- [ ] Preload previous/next spread thumbnails after current preview renders.
- [ ] Add a status message when preview rendering fails for a page.
- [ ] Add cache clearing when volume changes, project closes, or source file changes.

Acceptance criteria:

- [ ] Repeated preview navigation does not repeatedly open the same PDF.
- [ ] Cache memory remains bounded.
- [ ] Switching volumes closes stale documents and clears stale thumbnails.
- [ ] Inserted image previews still render correctly.

Tests:

- [ ] Unit test LRU eviction.
- [ ] Unit test cache key bucketing.
- [ ] Unit test PDF document handle is reused for same source.
- [ ] Unit test document/cache reset on volume switch.

## P1: EPUB Validation Upgrades

Goal: catch more malformed EPUB output before reporting success.

Why it matters:

- Current lightweight validation checks mimetype, container/OPF presence, manifest hrefs, spine idrefs, and cover-image media type.
- More checks can improve confidence without requiring external tools.

Primary files:

- `pdf_to_epub_lossless.py`
- `test_pdf_to_epub_lossless.py`

Tasks:

- [ ] Check duplicate ZIP entries.
- [ ] Parse every generated XHTML file as XML.
- [ ] Verify `nav.xhtml` is present and marked with `properties="nav"`.
- [ ] Verify all image media types match filename extensions.
- [ ] Verify every non-blank reading page has an image manifest item.
- [ ] Verify cover image appears exactly once.
- [ ] Verify OPF language and XHTML `lang` / `xml:lang` are consistent.
- [ ] Optionally add `--epubcheck PATH` or `--strict-epubcheck` later.

Acceptance criteria:

- [ ] Invalid generated or hand-mutated EPUBs fail with actionable error messages.
- [ ] Existing valid outputs still pass.
- [ ] Validation remains deterministic and does not require network access.

Tests:

- [ ] Unit test duplicate ZIP entry rejection.
- [ ] Unit test malformed XHTML rejection.
- [ ] Unit test missing nav item rejection.
- [ ] Unit test wrong image media type rejection.
- [ ] Unit test language propagation into nav/page XHTML.

## P2: GUI Workflow Polish

Goal: reduce repetitive manual work during page review without changing core conversion behavior.

Primary files:

- `epub_layout_gui.py`
- `test_epub_layout_gui.py`

Ideas:

- [ ] Add keyboard shortcuts for next/previous page or spread.
- [ ] Add toolbar buttons for first/previous/next/last spread.
- [ ] Add search/jump-to-spine-position.
- [ ] Add "Mark reviewed and go next volume".
- [ ] Add visual badges for cover, blank, inserted image, deleted/recovered operations.
- [ ] Add a compact export summary panel instead of only message boxes.
- [ ] Add recent project/recent PDF menu.

Acceptance criteria:

- [ ] Reviewing a volume can be done mostly from the keyboard.
- [ ] Series users can mark a volume ready and advance with one command.
- [ ] Current command palette remains useful and includes new commands.

Tests:

- [ ] Unit test shortcut bindings call expected methods.
- [ ] Unit test mark-ready-and-next selects next volume.
- [ ] Unit test jump-to-position selects correct spine item and refreshes preview.

## P2: Preset Portability Improvements

Goal: make presets robust when shared across folders or moved with assets.

Why it matters:

- v2 presets reference inserted images by path.
- If the image moves, preset application currently fails.

Primary files:

- `epub_layout_model.py`
- `epub_layout_gui.py`
- `test_epub_layout_model.py`

Tasks:

- [ ] Store inserted image paths relative to preset file when possible.
- [ ] Store image fingerprint metadata: size, byte length, maybe SHA-256.
- [ ] On missing inserted image, search next to preset file before failing.
- [ ] Show a GUI prompt to locate a missing inserted image.
- [ ] Preserve current strict failure behavior for CLI unless a replacement path is supplied.

Acceptance criteria:

- [ ] Moving preset and inserted cover together keeps preset usable.
- [ ] Missing image error says which entry and path failed.
- [ ] User can relink a missing image in GUI.

Tests:

- [ ] Unit test relative inserted path round-trip.
- [ ] Unit test fallback search beside preset.
- [ ] Unit test fingerprint mismatch warning.

## P2: Metadata and Filename Controls

Goal: make exported books easier to organize in Apple Books and filesystems.

Primary files:

- `epub_series_model.py`
- `pdf_to_epub_lossless.py`
- `epub_layout_gui.py`
- `test_epub_series_model.py`
- `test_pdf_to_epub_lossless.py`

Tasks:

- [ ] Add configurable volume title template, e.g. `{series} Vol.{volume:02d}`.
- [ ] Add configurable output filename template.
- [ ] Add optional publisher field.
- [ ] Add optional description/summary field.
- [ ] Add optional series metadata if a reader supports it safely.
- [ ] Keep deterministic UUID behavior unless user explicitly requests random identifiers.

Acceptance criteria:

- [ ] User can choose title and filename templates for series export.
- [ ] Illegal filename characters are sanitized.
- [ ] Metadata fields are XML-escaped and appear in OPF.

Tests:

- [ ] Unit test title template formatting.
- [ ] Unit test filename sanitization.
- [ ] Unit test OPF escaping for metadata fields.

## P2: Developer Experience

Goal: make setup, testing, and release less dependent on memory.

Files:

- `README.md`
- `pyproject.toml`
- New: `Makefile` or `justfile`
- New: `.github/workflows/test.yml` if GitHub Actions is desired.

Tasks:

- [ ] Add `make setup`, `make test`, `make lint` or equivalent.
- [ ] Add a clear error path when `fitz` is missing from GUI imports.
- [ ] Add optional formatting/linting config if desired.
- [ ] Add GitHub Actions for Python 3.11+.
- [ ] Add a tiny smoke test command for CLI conversion.

Acceptance criteria:

- [ ] New contributor can run one documented command to create venv and install requirements.
- [ ] CI runs py_compile and unittest.
- [ ] Dependency-missing errors explain `.venv/bin/python -m pip install -r requirements.txt`.

Tests:

- [ ] CI must pass py_compile and unittest.
- [ ] Manual smoke test documented in README.

## P3: PDF Compatibility Expansion

Goal: support more real-world manga PDFs while preserving explicit quality behavior.

Why this is P3:

- It needs representative sample PDFs.
- Silent image conversion mistakes are worse than unsupported-file errors.

Primary files:

- `pdf_to_cbz_lossless.py`
- `pdf_to_epub_lossless.py`
- `test_pdf_to_cbz_lossless.py`
- `test_pdf_to_epub_lossless.py`

Candidates:

- [ ] JPXDecode / JPEG2000 extraction or PNG fallback.
- [ ] CMYK JPEG handling with explicit warning or conversion mode.
- [ ] Soft mask / alpha handling for images that require transparency.
- [ ] Multi-image PDF page detection and warnings.
- [ ] Optional full-page raster fallback for pages that cannot be represented as one lossless source image.
- [ ] Better handling of indirect PDF dictionary objects beyond current ColorSpace normalization.

Acceptance criteria:

- [ ] Each supported filter has at least one synthetic or fixture-backed test.
- [ ] Any fallback that recompresses or rasterizes is opt-in and clearly reported.
- [ ] Unsupported filters still fail with actionable messages.

Tests:

- [ ] Unit test each new filter path.
- [ ] Golden-file style test for output extension and dimensions.
- [ ] Regression test that JPEG streams remain byte-identical when supported.

## P3: Optional CBZ Enhancements

Goal: improve CBZ output while keeping EPUB as the main workflow.

Primary files:

- `pdf_to_cbz_lossless.py`
- `test_pdf_to_cbz_lossless.py`
- `README.md`

Tasks:

- [ ] Add optional `ComicInfo.xml` metadata.
- [ ] Add `--output-dir` to CBZ CLI for parity with EPUB CLI.
- [ ] Add optional cover filename marker if useful for readers.
- [ ] Add validation for duplicate archive names.

Acceptance criteria:

- [ ] Existing CBZ output remains unchanged by default.
- [ ] Metadata is added only when requested.
- [ ] Output directory behavior matches EPUB CLI expectations.

Tests:

- [ ] Unit test `--output-dir`.
- [ ] Unit test optional `ComicInfo.xml`.
- [ ] Unit test default archive contains only page images.

## Future Nice-to-Haves

- [ ] Drag-and-drop PDF import in GUI.
- [ ] Drag-and-drop inserted cover/image pages.
- [ ] Apple Books import checklist after export.
- [ ] Side-by-side comparison of "with virtual cover gap" and "without".
- [ ] Export a small HTML preview report for a series.
- [ ] App bundle for macOS if distribution becomes important.

## Done Definition

For each completed item:

- [ ] Behavior is covered by focused unit tests.
- [ ] `.venv/bin/python -m py_compile ...` passes.
- [ ] `.venv/bin/python -m unittest` passes.
- [ ] README is updated when user-facing behavior changes.
- [ ] Manual GUI smoke test is performed for GUI changes.
- [ ] Existing lossless JPEG behavior is not regressed.

