from __future__ import annotations

from collections import Counter
import mimetypes
import posixpath
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile
from xml.etree import ElementTree

from pdf_to_cbz_lossless import PdfImageError


def validate_epub_structure(epub_path: Path) -> None:
    with ZipFile(epub_path) as archive:
        names = archive.namelist()
        duplicate_names = [name for name, count in Counter(names).items() if count > 1]
        if duplicate_names:
            raise PdfImageError(f"Duplicate EPUB zip entry: {duplicate_names[0]}")
        name_set = set(names)
        if not names or names[0] != "mimetype":
            raise PdfImageError("EPUB mimetype must be the first zip entry")
        if archive.getinfo("mimetype").compress_type != ZIP_STORED:
            raise PdfImageError("EPUB mimetype must be stored without compression")
        if archive.read("mimetype") != b"application/epub+zip":
            raise PdfImageError("EPUB mimetype has invalid content")
        for required in ("META-INF/container.xml", "EPUB/content.opf"):
            if required not in name_set:
                raise PdfImageError(f"Required EPUB file missing: {required}")

        opf = ElementTree.fromstring(archive.read("EPUB/content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        manifest: dict[str, tuple[str, str, str]] = {}
        nav_items = 0
        for item in opf.findall(".//opf:manifest/opf:item", ns):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type", "")
            properties = item.attrib.get("properties", "")
            if not item_id or not href:
                continue
            manifest[item_id] = (href, media_type, properties)
            archive_path = posixpath.normpath(posixpath.join("EPUB", href))
            if archive_path not in name_set:
                raise PdfImageError(f"Manifest href missing from EPUB: {archive_path}")
            if "nav" in properties.split():
                if archive_path != "EPUB/nav.xhtml" or media_type != "application/xhtml+xml":
                    raise PdfImageError("EPUB nav item must reference EPUB/nav.xhtml")
                nav_items += 1
            if media_type == "application/xhtml+xml":
                _validate_xhtml(archive, archive_path)
            if media_type.startswith("image/"):
                _validate_image_media_type(archive_path, media_type)

        if nav_items != 1:
            raise PdfImageError("EPUB nav item missing")

        for itemref in opf.findall(".//opf:spine/opf:itemref", ns):
            idref = itemref.attrib.get("idref")
            if idref and idref not in manifest:
                raise PdfImageError(f"Spine itemref {idref} has no manifest item")

        cover_items = [
            (item_id, media_type)
            for item_id, (_href, media_type, properties) in manifest.items()
            if "cover-image" in properties.split()
        ]
        for item_id, media_type in cover_items:
            if not media_type.startswith("image/"):
                raise PdfImageError(f"Cover item {item_id} is not an image")


def _validate_xhtml(archive: ZipFile, archive_path: str) -> None:
    try:
        ElementTree.fromstring(archive.read(archive_path))
    except ElementTree.ParseError as exc:
        raise PdfImageError(f"Malformed XHTML file: {archive_path}") from exc


def _validate_image_media_type(archive_path: str, media_type: str) -> None:
    ext = Path(archive_path).suffix.lower()
    expected = "image/jpeg" if ext in {".jpg", ".jpeg"} else mimetypes.types_map.get(ext)
    if expected and expected != media_type:
        raise PdfImageError(f"Image media type mismatch for {archive_path}: {media_type} != {expected}")
