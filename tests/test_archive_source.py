import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from manga_pdf_to_epub.pdf.image_types import PdfImageError
from manga_pdf_to_epub.sources.archive import archive_images_in_page_order
from tests.helpers import tiny_png


class ArchiveSourceTests(unittest.TestCase):
    def test_archive_images_are_naturally_sorted_and_skip_junk_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "comic.cbz"
            png_bytes = tiny_png()
            jpeg_bytes = _render_sample_image("jpeg")
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("__MACOSX/._page-1.jpg", b"junk")
                archive.writestr(".DS_Store", b"junk")
                archive.writestr("notes.txt", b"not an image")
                archive.writestr("chapter/page-10.png", png_bytes)
                archive.writestr("chapter/page-2.jpg", jpeg_bytes)
                archive.writestr("chapter/page-1.png", png_bytes)

            images = archive_images_in_page_order(archive_path, load_payloads=False)

            self.assertEqual(["page-1", "page-2", "page-10"], [image.label for image in images])
            self.assertEqual([1, 2, 3], [image.source_index for image in images])
            self.assertEqual(["png", "jpg", "png"], [image.epub_ext for image in images])
            self.assertIsNone(images[0].data)
            self.assertIsNotNone(images[0].data_loader)
            self.assertEqual(png_bytes, images[0].load_data())
            self.assertEqual(jpeg_bytes, images[1].load_data())

    def test_archive_converts_wide_image_formats_to_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / "comic.zip"
            payloads = {
                "page-1.webp": _render_sample_image("webp"),
                "page-2.bmp": _render_sample_image("bmp"),
                "page-3.tiff": _render_sample_image("tiff"),
                "page-4.gif": _render_sample_image("gif"),
            }
            with ZipFile(archive_path, "w") as archive:
                for name, payload in payloads.items():
                    archive.writestr(name, payload)

            images = archive_images_in_page_order(archive_path)

            self.assertEqual(["png", "png", "png", "png"], [image.epub_ext for image in images])
            self.assertEqual([2, 3, 4, 5], [image.width for image in images])
            self.assertEqual([3, 4, 5, 6], [image.height for image in images])
            for image in images:
                self.assertTrue(image.load_data().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_empty_archive_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "empty.cbz"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("readme.txt", "hello")

            with self.assertRaisesRegex(PdfImageError, "No supported image files found"):
                archive_images_in_page_order(archive_path)


def _render_sample_image(fmt: str) -> bytes:
    width = {"jpeg": 2, "webp": 2, "bmp": 3, "tiff": 4, "gif": 5}[fmt]
    height = width + 1
    image = Image.new("RGB", (width, height), (255, 0, 0))
    stream = BytesIO()
    image.save(stream, format={"jpeg": "JPEG", "webp": "WEBP", "bmp": "BMP", "tiff": "TIFF", "gif": "GIF"}[fmt])
    return stream.getvalue()


if __name__ == "__main__":
    unittest.main()
