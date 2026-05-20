from __future__ import annotations

from epub_layout_gui_support import VirtualBlank


def preview_index_for_selection(selected: int, uses_apple_cover_gap: bool) -> int:
    if uses_apple_cover_gap and selected >= 1:
        return selected + 1
    return selected


def spread_slots(pair_start: int, gap: int, page_w: int, uses_apple_cover_gap: bool) -> list[tuple[int, int]]:
    left = (gap, gap)
    right = (gap * 2 + page_w, gap)
    if uses_apple_cover_gap and pair_start == 0:
        return [left, right]
    return [right, left]


def preview_entries(entries: list, uses_apple_cover_gap: bool):
    if uses_apple_cover_gap and entries:
        cover_gap = VirtualBlank("Virtual Apple Books cover gap")
        return [entries[0], cover_gap, *entries[1:]]
    return list(entries)


def thumbnail_cache_key(entry, max_w: int, max_h: int):
    source_index = getattr(entry, "source_index", None)
    if source_index is not None:
        return ("source", source_index, max_w, max_h)
    page = getattr(entry, "page", None)
    item_id = getattr(page, "item_id", None)
    if item_id is not None:
        return ("entry", item_id, max_w, max_h)
    return ("entry", id(entry), max_w, max_h)
