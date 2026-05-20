import unittest

from tests.gui_helpers import app_for_preview, entry


class EpubLayoutGuiPreviewTests(unittest.TestCase):
    def test_apple_cover_gap_is_drawn_on_right_of_cover(self):
        app = app_for_preview([entry("Page 1"), entry("Page 2")], selected=0)

        app.refresh_preview()

        self.assertEqual(
            [("Page 1", 12), ("Virtual Apple Books cover gap", 206)],
            app.draws,
        )

    def test_selected_pages_after_cover_map_past_virtual_apple_gap(self):
        app = app_for_preview([entry("Page 1"), entry("Page 2"), entry("Page 3")], selected=1)

        app.refresh_preview()

        self.assertEqual(
            [("Page 2", 206), ("Page 3", 12)],
            app.draws,
        )

    def test_blank_before_cover_does_not_remove_virtual_apple_gap(self):
        app = app_for_preview([entry("Blank 1", is_blank=True), entry("Page 1"), entry("Page 2")], selected=0)

        app.refresh_preview()

        self.assertEqual(
            [("Blank 1", 12), ("Virtual Apple Books cover gap", 206)],
            app.draws,
        )

    def test_cover_after_inserted_blank_maps_past_virtual_apple_gap(self):
        app = app_for_preview([entry("Blank 1", is_blank=True), entry("Page 1"), entry("Page 2")], selected=1)

        app.refresh_preview()

        self.assertEqual(
            [("Page 1", 206), ("Page 2", 12)],
            app.draws,
        )
