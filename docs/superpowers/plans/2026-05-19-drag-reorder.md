# Single-Page Drag Reorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add single-page drag reorder to the EPUB Layout Lab spine list.

**Architecture:** Add `LayoutModel.move_entry(from_index, to_index)` as the source of truth for list reordering. Bind Tkinter listbox mouse events in `EpubLayoutApp` to call that model method, then refresh the existing spine list and RTL preview.

**Tech Stack:** Python 3.11+, Tkinter/ttk, `unittest`, PyMuPDF.

---

## File Structure

- Modify `epub_layout_model.py`: add a model-level reorder operation that validates indexes, adjusts downward moves, and keeps cover state valid.
- Modify `epub_layout_gui.py`: store drag source row and handle listbox press/release events for one-row moves.
- Modify `test_epub_layout_model.py`: cover model reorder behavior.
- Modify `test_epub_layout_gui.py`: cover GUI drag handler behavior with fakes.

## Task 1: Model Reorder Operation

**Files:**
- Modify: `test_epub_layout_model.py`
- Modify: `epub_layout_model.py`

- [ ] **Step 1: Write failing model tests**

Add tests to `EpubLayoutModelTests`:

```python
    def test_move_entry_reorders_source_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)

            final_index = model.move_entry(3, 1)

            self.assertEqual(1, final_index)
            self.assertEqual(["Page 1", "Page 4", "Page 2", "Page 3"], [entry.label for entry in model.entries])

    def test_move_entry_down_uses_final_visible_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)

            final_index = model.move_entry(1, 3)

            self.assertEqual(3, final_index)
            self.assertEqual(["Page 1", "Page 3", "Page 4", "Page 2"], [entry.label for entry in model.entries])

    def test_move_entry_allows_blank_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_blank(1)

            final_index = model.move_entry(1, 2)

            self.assertEqual(2, final_index)
            self.assertEqual(["Page 1", "Page 2", "Blank 1"], [entry.label for entry in model.entries])

    def test_move_cover_entry_keeps_cover_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)
            model.set_cover(3)

            model.move_entry(2, 0)

            self.assertEqual(3, model.cover_source_index)
            self.assertEqual("page-0001", model.normalized_cover_item_id())

    def test_move_entry_rejects_invalid_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)

            with self.assertRaises(IndexError):
                model.move_entry(-1, 0)
            with self.assertRaises(IndexError):
                model.move_entry(0, 2)
```

- [ ] **Step 2: Run model tests to verify failure**

Run:

```bash
./.venv/bin/python -m unittest test_epub_layout_model.EpubLayoutModelTests.test_move_entry_reorders_source_pages test_epub_layout_model.EpubLayoutModelTests.test_move_entry_down_uses_final_visible_index test_epub_layout_model.EpubLayoutModelTests.test_move_entry_allows_blank_pages test_epub_layout_model.EpubLayoutModelTests.test_move_cover_entry_keeps_cover_identity test_epub_layout_model.EpubLayoutModelTests.test_move_entry_rejects_invalid_indexes
```

Expected: fail with `AttributeError: 'LayoutModel' object has no attribute 'move_entry'`.

- [ ] **Step 3: Implement `LayoutModel.move_entry`**

Add this method near the delete methods in `epub_layout_model.py`:

```python
    def move_entry(self, from_index: int, to_index: int) -> int:
        if from_index < 0 or from_index >= len(self.entries):
            raise IndexError("Move source index out of range")
        if to_index < 0 or to_index >= len(self.entries):
            raise IndexError("Move destination index out of range")
        if from_index == to_index:
            return from_index
        entry = self.entries.pop(from_index)
        insert_index = to_index
        self.entries.insert(insert_index, entry)
        self._ensure_valid_cover()
        return insert_index
```

- [ ] **Step 4: Run focused model tests**

Run the same command from Step 2.

Expected: all five tests pass.

## Task 2: GUI Drag Handler

**Files:**
- Modify: `test_epub_layout_gui.py`
- Modify: `epub_layout_gui.py`

- [ ] **Step 1: Extend GUI fakes and add failing tests**

Update `_FakeListbox` with:

```python
    def nearest(self, y):
        if not self.items:
            return 0
        return min(max(int(y), 0), len(self.items) - 1)
```

Update `_FakeDeleteModel` with:

```python
    def move_entry(self, from_index, to_index):
        entry = self.entries.pop(from_index)
        self.entries.insert(to_index, entry)
        return to_index
```

Add tests to `EpubLayoutGuiActionTests`:

```python
    def test_drag_release_moves_pressed_row_to_target_row(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app._page_drag_source = None
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app._page_drag_start(SimpleNamespace(y=0))
        app._page_drag_release(SimpleNamespace(y=2))

        self.assertEqual(["Page 2", "Page 3", "Page 1"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Moved Page 1 to position 3.", app.status.value)

    def test_drag_release_on_same_row_does_not_move(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app._page_drag_source = None
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app._page_drag_start(SimpleNamespace(y=1))
        app._page_drag_release(SimpleNamespace(y=1))

        self.assertEqual(["Page 1", "Page 2"], [entry.label for entry in app.model.entries])
        self.assertFalse(hasattr(app, "preview_refreshed"))
        self.assertIsNone(app.status.value)

    def test_drag_uses_pressed_row_when_selection_differs(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.workspace_status = _FakeStatus()
        app._page_drag_source = None
        app.refresh_preview = lambda: None

        app._page_drag_start(SimpleNamespace(y=1))
        app._page_drag_release(SimpleNamespace(y=2))

        self.assertEqual(["Page 1", "Page 3", "Page 2"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)
```

- [ ] **Step 2: Run GUI tests to verify failure**

Run:

```bash
./.venv/bin/python -m unittest test_epub_layout_gui.EpubLayoutGuiActionTests.test_drag_release_moves_pressed_row_to_target_row test_epub_layout_gui.EpubLayoutGuiActionTests.test_drag_release_on_same_row_does_not_move test_epub_layout_gui.EpubLayoutGuiActionTests.test_drag_uses_pressed_row_when_selection_differs
```

Expected: fail with missing `_page_drag_start` or `_page_drag_release`.

- [ ] **Step 3: Implement drag bindings and handlers**

In `EpubLayoutApp.__init__`, add:

```python
        self._page_drag_source: int | None = None
```

In `_build_ui`, after the existing listbox selection binding, add:

```python
        self.page_list.bind("<ButtonPress-1>", self._page_drag_start)
        self.page_list.bind("<ButtonRelease-1>", self._page_drag_release)
```

Add methods near `selected_indexes`:

```python
    def _page_drag_start(self, event) -> None:
        if self.model is None or not self.model.entries:
            self._page_drag_source = None
            return
        index = self.page_list.nearest(event.y)
        if index < 0 or index >= len(self.model.entries):
            self._page_drag_source = None
            return
        self._page_drag_source = index

    def _page_drag_release(self, event) -> None:
        if self.model is None or self._page_drag_source is None:
            return
        from_index = self._page_drag_source
        self._page_drag_source = None
        if not self.model.entries:
            return
        to_index = self.page_list.nearest(event.y)
        to_index = min(max(to_index, 0), len(self.model.entries) - 1)
        if from_index == to_index:
            return
        try:
            label = self.model.entries[from_index].label
            final_index = self.model.move_entry(from_index, to_index)
            self.refresh_list(preserve_yview=True)
            self.page_list.selection_clear(0, tk.END)
            self.page_list.selection_set(final_index)
            self.refresh_preview()
            self.status.set(f"Moved {label} to position {final_index + 1}.")
        except Exception as exc:
            messagebox.showerror("Move page failed", str(exc))
```

- [ ] **Step 4: Run focused GUI tests**

Run the same command from Step 2.

Expected: all three tests pass.

## Task 3: Full Verification And Commit

**Files:**
- Verify all touched files.

- [ ] **Step 1: Run full verification**

Run:

```bash
./.venv/bin/python -m py_compile epub_layout_gui.py epub_layout_model.py epub_batch_model.py pdf_to_epub_lossless.py pdf_to_cbz_lossless.py
./.venv/bin/python -m unittest
```

Expected: compile succeeds and the full unittest suite passes.

- [ ] **Step 2: Review diff**

Run:

```bash
git diff -- epub_layout_model.py epub_layout_gui.py test_epub_layout_model.py test_epub_layout_gui.py docs/superpowers/plans/2026-05-19-drag-reorder.md
git status --short
```

Expected: only the drag reorder implementation, tests, and plan are changed.

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-05-19-drag-reorder.md epub_layout_model.py epub_layout_gui.py test_epub_layout_model.py test_epub_layout_gui.py
git commit -m "feat: add single-page drag reorder"
```
