import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile
from unittest.mock import patch

from manga_pdf_to_epub.pdf_to_cbz_lossless import (
    ImageStream,
    PdfImageError,
    _image_from_xref,
    convert_pdf_to_cbz,
    image_to_archive_member,
    flate_image_to_png,
    images_in_pdf_page_order,
    iter_image_streams,
)
from tests.helpers import (
    minimal_pdf,
    pdf_from_objects,
    png_predict_none,
    stream_object,
    two_page_pdf_with_late_cover,
)


class PdfToCbzLosslessTests(unittest.TestCase):
    def test_dct_image_stream_is_copied_to_cbz_without_reencoding(self):
        jpeg = b"\xff\xd8JPEG-DATA\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            cbz_path = Path(tmp) / "comic.cbz"
            pdf_path.write_bytes(two_page_pdf_with_late_cover(jpeg, page2))

            counts = convert_pdf_to_cbz(pdf_path, cbz_path)

            self.assertEqual({"jpg": 2, "png": 0, "total": 2}, counts)
            with ZipFile(cbz_path) as archive:
                self.assertEqual(["0001.jpg", "0002.jpg"], archive.namelist())
                self.assertEqual(jpeg, archive.read("0001.jpg"))
                self.assertEqual(ZIP_STORED, archive.getinfo("0001.jpg").compress_type)

    def test_archive_order_follows_pdf_page_tree_not_image_object_order(self):
        cover = b"\xff\xd8COVER\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            cbz_path = Path(tmp) / "comic.cbz"
            pdf_path.write_bytes(two_page_pdf_with_late_cover(cover, page2))

            convert_pdf_to_cbz(pdf_path, cbz_path)

            with ZipFile(cbz_path) as archive:
                self.assertEqual(["0001.jpg", "0002.jpg"], archive.namelist())
                self.assertEqual(cover, archive.read("0001.jpg"))
                self.assertEqual(page2, archive.read("0002.jpg"))

    def test_page_order_extraction_requires_pymupdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            with patch("manga_pdf_to_epub.pdf_to_cbz_lossless._load_fitz", return_value=None):
                with self.assertRaisesRegex(PdfImageError, "PyMuPDF is required"):
                    images_in_pdf_page_order(pdf_path)

    def test_named_jbig2_filter_falls_back_to_decoded_png_image(self):
        class FakeDoc:
            def xref_get_key(self, _xref, key):
                values = {
                    "Subtype": ("name", "/Image"),
                    "Filter": ("name", "/JBIG2Decode"),
                }
                return values.get(key, ("null", "null"))

            def extract_image(self, xref):
                self.extracted_xref = xref
                return {
                    "ext": "png",
                    "width": 2,
                    "height": 3,
                    "image": b"PNG-DATA",
                }

        doc = FakeDoc()

        image = _image_from_xref(doc, xref=351, index=7)

        self.assertEqual(351, doc.extracted_xref)
        self.assertEqual("PNG", image.filter_name)
        self.assertEqual(7, image.index)
        self.assertEqual(2, image.width)
        self.assertEqual(3, image.height)
        self.assertEqual(b"PNG-DATA", image.data)

    def test_already_extracted_png_stream_is_archive_ready_without_rewrapping(self):
        image = ImageStream(
            index=1,
            width=2,
            height=3,
            bits_per_component=8,
            color_space=b"/DeviceRGB",
            filter_name="PNG",
            decode_parms=None,
            data=b"PNG-DATA",
        )

        self.assertEqual(("png", b"PNG-DATA"), image_to_archive_member(image))

    def test_flate_indexed_png_predictor_image_is_wrapped_as_png(self):
        rows = [bytes([0x12]), bytes([0x34])]
        payload = png_predict_none(rows)
        pdf = minimal_pdf(
            [
                (
                    b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
                    b"/BitsPerComponent 4 /ColorSpace [/Indexed /DeviceRGB 3 ("
                    b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff"
                    b")] /DecodeParms << /Predictor 15 /Colors 1 /Columns 2 /BitsPerComponent 4 >> "
                    b"/Filter /FlateDecode /Length __LEN__ >>",
                    payload,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(pdf)
            image = iter_image_streams(pdf_path)[0]

        png = flate_image_to_png(image)

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        chunks = _png_chunks(png)
        self.assertEqual((2, 2, 4, 3), struct.unpack(">IIBB", chunks[b"IHDR"][:10]))
        self.assertEqual(b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff", chunks[b"PLTE"])
        self.assertEqual(b"\x00\x12\x00\x34", zlib.decompress(chunks[b"IDAT"]))

    def test_flate_png_predictor_reuses_original_zlib_stream_as_png_idat(self):
        payload = png_predict_none([bytes([0x12]), bytes([0x34])])
        pdf = minimal_pdf(
            [
                (
                    b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
                    b"/BitsPerComponent 4 /ColorSpace [/Indexed /DeviceRGB 3 ("
                    b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff"
                    b")] /DecodeParms << /Predictor 15 /Colors 1 /Columns 2 /BitsPerComponent 4 >> "
                    b"/Filter /FlateDecode /Length __LEN__ >>",
                    payload,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(pdf)
            image = iter_image_streams(pdf_path)[0]

        chunks = _png_chunks(flate_image_to_png(image))

        self.assertEqual(payload, chunks[b"IDAT"])

    def test_flate_indexed_image_accepts_indirect_palette_object_from_page_order_extraction(self):
        rows = [bytes([0x12]), bytes([0x34])]
        payload = png_predict_none(rows)
        palette = b"\x00\x00\x00\x55\x55\x55\xaa\xaa\xaa\xff\xff\xff"
        pdf = pdf_from_objects(
            [
                (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
                (2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
                (
                    3,
                    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 2] "
                    b"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>",
                ),
                (4, stream_object(b"<< /Length __LEN__ >>", b"q 2 0 0 2 0 0 cm /Im0 Do Q")),
                (
                    5,
                    stream_object(
                        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
                        b"/BitsPerComponent 4 /ColorSpace [/Indexed /DeviceRGB 3 6 0 R] "
                        b"/DecodeParms << /Predictor 15 /Colors 1 /Columns 2 /BitsPerComponent 4 >> "
                        b"/Filter /FlateDecode /Length __LEN__ >>",
                        payload,
                    ),
                ),
                (6, stream_object(b"<< /Length __LEN__ >>", palette)),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(pdf)

            image = images_in_pdf_page_order(pdf_path)[0]
            png = flate_image_to_png(image)

        self.assertEqual(b"[/Indexed /DeviceRGB 3 <000000555555aaaaaaffffff>]", image.color_space)
        self.assertEqual(palette, _png_chunks(png)[b"PLTE"])


def _png_chunks(data):
    chunks = {}
    stream = io.BytesIO(data[8:])
    while True:
        length_data = stream.read(4)
        if not length_data:
            break
        length = struct.unpack(">I", length_data)[0]
        kind = stream.read(4)
        payload = stream.read(length)
        stream.read(4)
        chunks[kind] = payload
        if kind == b"IEND":
            break
    return chunks


if __name__ == "__main__":
    unittest.main()
