import zlib


def png_predict_none(rows):
    return zlib.compress(b"".join(b"\x00" + row for row in rows))


def minimal_pdf(streams):
    parts = [b"%PDF-1.6\n"]
    offsets = []
    for index, (dictionary, payload) in enumerate(streams, 1):
        offsets.append(sum(map(len, parts)))
        parts.extend(
            [
                f"{index} 0 obj\n".encode(),
                dictionary.replace(b"__LEN__", str(len(payload)).encode()),
                b"\nstream\n",
                payload,
                b"\nendstream\nendobj\n",
            ]
        )
    xref = sum(map(len, parts))
    parts.append(f"xref\n0 {len(streams) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        parts.append(f"{offset:010d} 00000 n \n".encode())
    parts.append(f"trailer << /Size {len(streams) + 1} >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return b"".join(parts)


def pdf_from_objects(objects):
    parts = [b"%PDF-1.6\n"]
    offsets = {}
    for obj_num, body in objects:
        offsets[obj_num] = sum(map(len, parts))
        parts.extend([f"{obj_num} 0 obj\n".encode(), body, b"\nendobj\n"])
    xref = sum(map(len, parts))
    max_obj = max(offsets)
    parts.append(f"xref\n0 {max_obj + 1}\n0000000000 65535 f \n".encode())
    for obj_num in range(1, max_obj + 1):
        offset = offsets.get(obj_num, 0)
        parts.append((f"{offset:010d} 00000 n \n" if offset else "0000000000 65535 f \n").encode())
    parts.append(f"trailer << /Root 1 0 R /Size {max_obj + 1} >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return b"".join(parts)


def stream_object(dictionary, payload):
    return b"".join(
        [
            dictionary.replace(b"__LEN__", str(len(payload)).encode()),
            b"\nstream\n",
            payload,
            b"\nendstream",
        ]
    )


def two_page_pdf_with_late_cover(cover_bytes=b"\xff\xd8COVER\xff\xd9", page2_bytes=b"\xff\xd8PAGE2\xff\xd9"):
    draw = b"q 2 0 0 1 0 0 cm /Im0 Do Q"
    image_template = (
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 1 "
        b"/BitsPerComponent 8 /ColorSpace /DeviceRGB /Filter /DCTDecode /Length __LEN__ >>"
    )
    return pdf_from_objects(
        [
            (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>"),
            (
                3,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 8 0 R >> >> /Contents 6 0 R >>",
            ),
            (
                4,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 7 0 R >>",
            ),
            (5, stream_object(image_template, page2_bytes)),
            (6, stream_object(b"<< /Length __LEN__ >>", draw)),
            (7, stream_object(b"<< /Length __LEN__ >>", draw)),
            (8, stream_object(image_template, cover_bytes)),
        ]
    )


def tiny_png():
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def four_page_pdf():
    draw = b"q 2 0 0 1 0 0 cm /Im0 Do Q"
    image_template = (
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 1 "
        b"/BitsPerComponent 8 /ColorSpace /DeviceRGB /Filter /DCTDecode /Length __LEN__ >>"
    )
    return pdf_from_objects(
        [
            (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, b"<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R 6 0 R] /Count 4 >>"),
            (
                3,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 11 0 R >> >> /Contents 7 0 R >>",
            ),
            (
                4,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 12 0 R >> >> /Contents 8 0 R >>",
            ),
            (
                5,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 13 0 R >> >> /Contents 9 0 R >>",
            ),
            (
                6,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 14 0 R >> >> /Contents 10 0 R >>",
            ),
            (7, stream_object(b"<< /Length __LEN__ >>", draw)),
            (8, stream_object(b"<< /Length __LEN__ >>", draw)),
            (9, stream_object(b"<< /Length __LEN__ >>", draw)),
            (10, stream_object(b"<< /Length __LEN__ >>", draw)),
            (11, stream_object(image_template, b"\xff\xd8PAGE1\xff\xd9")),
            (12, stream_object(image_template, b"\xff\xd8PAGE2\xff\xd9")),
            (13, stream_object(image_template, b"\xff\xd8PAGE3\xff\xd9")),
            (14, stream_object(image_template, b"\xff\xd8PAGE4\xff\xd9")),
        ]
    )


def one_page_pdf():
    draw = b"q 2 0 0 1 0 0 cm /Im0 Do Q"
    image_template = (
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 1 "
        b"/BitsPerComponent 8 /ColorSpace /DeviceRGB /Filter /DCTDecode /Length __LEN__ >>"
    )
    return pdf_from_objects(
        [
            (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
            (
                3,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>",
            ),
            (4, stream_object(b"<< /Length __LEN__ >>", draw)),
            (5, stream_object(image_template, b"\xff\xd8PAGE1\xff\xd9")),
        ]
    )
