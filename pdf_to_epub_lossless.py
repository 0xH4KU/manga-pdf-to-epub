#!/usr/bin/env python3
"""Package PDF page images into fixed-layout EPUB files without re-encoding."""

from __future__ import annotations

import argparse
from pathlib import Path

from epub_validation import validate_epub_structure
from epub_writer import EpubPage, media_type_for_ext, write_epub_from_pages
from pdf_to_cbz_lossless import ImageStream, PdfImageError, image_to_archive_member, images_in_pdf_page_order


_validate_epub_structure = validate_epub_structure
_media_type_for_ext = media_type_for_ext


def convert_pdf_to_epub(
    pdf_path: Path,
    epub_path: Path,
    overwrite: bool = False,
    title: str | None = None,
    author: str | None = None,
    language: str = "zh-Hant",
    apple_books: bool = False,
    blank_pages_before_cover: int = 0,
    blank_pages_after_cover: int = 0,
    pair_first_two_pages: bool = False,
    cover_item_id: str | None = None,
    exclude_cover_from_reading: bool = False,
) -> dict[str, int]:
    if epub_path.exists() and not overwrite:
        raise PdfImageError(f"Refusing to overwrite existing file: {epub_path}")

    images = images_in_pdf_page_order(pdf_path)
    if not images:
        raise PdfImageError(f"No image streams found in {pdf_path}")

    book_title = title or pdf_path.stem
    pages, counts = _build_pages(
        images,
        blank_pages_before_cover=blank_pages_before_cover,
        blank_pages_after_cover=blank_pages_after_cover,
    )
    return write_epub_from_pages(
        pages,
        epub_path,
        source_path=pdf_path,
        title=book_title,
        author=author,
        language=language,
        overwrite=True,
        apple_books=apple_books,
        pair_first_two_pages=pair_first_two_pages,
        cover_item_id=cover_item_id,
        exclude_cover_from_reading=exclude_cover_from_reading,
        counts=counts,
    )


def _build_pages(
    images: list[ImageStream],
    blank_pages_before_cover: int = 0,
    blank_pages_after_cover: int = 0,
) -> tuple[list[EpubPage], dict[str, int]]:
    pages: list[EpubPage] = []
    counts = {"jpg": 0, "png": 0}
    padding = max(4, len(str(len(images))))
    for image in images:
        if image.index == 1:
            for blank_index in range(1, blank_pages_before_cover + 1):
                counts["blank"] = counts.get("blank", 0) + 1
                pages.append(_blank_page(image, blank_index, "before"))
        ext, payload = image_to_archive_member(image)
        counts[ext] = counts.get(ext, 0) + 1
        page_number = f"{image.index:0{padding}d}"
        image_href = f"images/page-{page_number}.{ext}"
        pages.append(
            EpubPage(
                index=image.index,
                width=image.width,
                height=image.height,
                image_href=image_href,
                image_media_type=media_type_for_ext(ext),
                image_data=payload,
                xhtml_href=f"xhtml/page-{page_number}.xhtml",
                item_id=f"page-{image.index:04d}",
                label=f"Page {image.index}",
            )
        )
        if image.index == 1:
            for blank_index in range(1, blank_pages_after_cover + 1):
                counts["blank"] = counts.get("blank", 0) + 1
                pages.append(_blank_page(image, blank_index, "after"))
    return pages, counts


def _blank_page(reference: ImageStream, blank_index: int, position: str) -> EpubPage:
    if position not in {"before", "after"}:
        raise PdfImageError(f"Unsupported blank page position: {position}")
    item_id = f"blank-{position}-cover-{blank_index:04d}"
    return EpubPage(
        index=blank_index,
        width=reference.width,
        height=reference.height,
        image_href=None,
        image_media_type=None,
        image_data=None,
        xhtml_href=f"xhtml/{item_id}.xhtml",
        item_id=item_id,
        label=f"Blank {position} cover {blank_index}",
        is_blank=True,
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    for pdf_path in args.pdfs:
        if pdf_path.suffix.lower() != ".pdf":
            raise PdfImageError(f"Not a PDF file: {pdf_path}")
        output_dir = args.output_dir or pdf_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        epub_path = output_dir / pdf_path.with_suffix(".epub").name
        counts = convert_pdf_to_epub(
            pdf_path,
            epub_path,
            overwrite=args.overwrite,
            apple_books=args.apple_books,
            blank_pages_before_cover=args.blank_pages_before_cover,
            blank_pages_after_cover=args.blank_pages_after_cover,
            pair_first_two_pages=args.pair_first_two_pages,
        )
        print(
            f"{pdf_path.name} -> {epub_path}: "
            f"{counts['total']} pages ({counts.get('jpg', 0)} jpg, {counts.get('png', 0)} png)"
        )
    return 0


class _EpubArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if parsed.apple_books and parsed.pair_first_two_pages:
            self.error("--apple-books cannot be used with --pair-first-two-pages")
        return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = _EpubArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", type=Path, help="PDF files to convert")
    parser.add_argument("--output-dir", type=Path, default=None, help="directory for EPUB output")
    parser.add_argument("--overwrite", action="store_true", help="replace existing EPUB files")
    parser.add_argument(
        "--blank-pages-after-cover",
        type=int,
        default=0,
        help="insert this many white XHTML pages immediately after the cover",
    )
    parser.add_argument(
        "--blank-pages-before-cover",
        type=int,
        default=0,
        help="insert this many white XHTML pages immediately before the cover",
    )
    parser.add_argument(
        "--pair-first-two-pages",
        action="store_true",
        help="mark source pages 1 and 2 as an explicit RTL spread pair",
    )
    parser.add_argument(
        "--apple-books",
        action="store_true",
        help="write OPF metadata that forces centered single-page spreads",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
