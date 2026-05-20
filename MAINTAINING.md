# Maintaining This Project

This project should stay small, explicit, and workflow-driven. When adding behavior, prefer the existing model modules over growing the GUI class.

## Boundaries

- Keep PDF image extraction in `pdf_to_cbz_lossless.py`.
- Keep EPUB archive structure in `epub_writer.py` and validation in `epub_validation.py`.
- Keep shared naming rules in `epub_naming.py`.
- Keep `ImageStream` to `EpubPage` conversion in `epub_page_factory.py`.
- Keep layout state, presets, and export glue in `epub_layout_model.py`.
- Keep series status, validation, and export policy in `epub_series_model.py`.
- Keep GUI-only event wiring in `epub_layout_gui.py`.

## Legacy Code

`epub_batch_model.py` is deprecated. It remains only for old tests and migration reference. Do not add new features to it; add or adapt `SeriesProject` behavior instead.

## Guardrails

- Add a failing test before behavior changes.
- Avoid new parallel state lists in the GUI. Use small helper models like `DeleteHistory`.
- If `EpubLayoutApp` grows, extract a controller/helper before adding more workflow state.
- Keep `make test` green before committing.
