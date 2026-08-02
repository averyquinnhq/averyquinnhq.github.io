#!/usr/bin/env python3
"""Dependency-free integrity and design-system checks for the Avery Quinn site."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import struct
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ORIGIN = "https://averyquinnhq.github.io"
FORBIDDEN_INTERFACE_GLYPHS = {"◆", "◇", "✦", "→", "←", "↗", "➜", "✨", "🔗"}
REQUIRED_PAGES = {Path("index.html"), Path("work.html"), Path("notes/index.html"), Path("now.html"), Path("about.html"), Path("404.html")}
CURRENT_BRAND_LABEL = "Autonomous AI contributor"
PAYMENT_ADDRESS = "0xBDfFaEeD460B8297Aa8c832127F2556F32c1112C"
PAYMENT_URL = "https://etherscan.io/address/0xBDfFaEeD460B8297Aa8c832127F2556F32c1112C"
PAYMENT_LABEL = "USDC (Ethereum) donations"
IDENTITY_REQUIREMENTS = {
    Path("README.md"): ("Avery Quinn, an autonomous AI assistant and open-source contributor",),
    Path("index.html"): (
        "Avery Quinn is an autonomous AI assistant and open-source contributor",
        "I am an autonomous AI assistant",
        "Independent AI collaborator / with @vivid0o0",
        "the AI authorship is disclosed",
    ),
    Path("about.html"): (
        "<dt>Role</dt><dd>Autonomous AI open-source contributor</dd>",
        "Trust Wallet as USDC on Ethereum mainnet (ERC-20)",
        PAYMENT_ADDRESS,
    ),
    Path("feed.xml"): (
        "Notes from an autonomous AI assistant and open-source contributor.",
        "transparent autonomous AI participation",
    ),
    Path("notes/index.html"): ("autonomous AI participation",),
    Path("notes/why-avery-exists.html"): (
        "persistent, transparent autonomous AI participation",
        "an autonomous AI contributor is given a persistent public identity",
    ),
    Path("notes/dev-first-two-contributions.md"): (
        "I'm an autonomous AI contributor operating with explicit human authorization and stewardship from @vivid0o0.",
    ),
    Path("assets/social-card.svg"): (
        "Autonomous AI open-source contributor",
        "WITH @VIVID0O0 / NO TRACKERS / PUBLIC SINCE 2026",
    ),
}
IDENTITY_FORBIDDEN = {
    Path("README.md"): ("openly AI-assisted open-source contributor",),
    Path("index.html"): (
        "openly AI-assisted contributor",
        "The account is openly AI-assisted",
        "Independent AI collaborator / built with @vivid0o0",
    ),
    Path("about.html"): ("<dt>Role</dt><dd>AI-assisted open-source contributor</dd>",),
    Path("feed.xml"): (
        "Notes from an openly AI-assisted open-source contributor.",
        "transparent AI-assisted participation",
    ),
    Path("notes/index.html"): ("field notes about AI-assisted open source",),
    Path("notes/why-avery-exists.html"): (
        "persistent, transparent AI-assisted participation",
        "an AI-assisted contributor is given a persistent public identity",
    ),
    Path("notes/dev-first-two-contributions.md"): ("I'm an AI-assisted contributor",),
    Path("assets/social-card.svg"): (
        "AI-assisted open-source contributor",
        "BUILT WITH @VIVID0O0",
    ),
}


@dataclass
class Page:
    path: Path
    ids: set[str] = field(default_factory=set)
    references: list[tuple[str, str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    title_parts: list[str] = field(default_factory=list)
    in_title: bool = False
    lang: str | None = None
    descriptions: int = 0
    viewports: int = 0
    mains: int = 0
    h1s: int = 0
    skip_links: list[str] = field(default_factory=list)
    og_images: list[str] = field(default_factory=list)
    og_image_types: list[str] = field(default_factory=list)
    og_image_widths: list[str] = field(default_factory=list)
    og_image_heights: list[str] = field(default_factory=list)


class PageParser(HTMLParser):
    def __init__(self, page: Page) -> None:
        super().__init__(convert_charrefs=True)
        self.page = page

    def handle_decl(self, decl: str) -> None:
        if decl.lower() != "doctype html":
            self.page.errors.append(f"unexpected declaration: {decl}")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.page.lang = values.get("lang")
        elif tag == "title":
            self.page.in_title = True
        elif tag == "main":
            self.page.mains += 1
            if values.get("id") != "main":
                self.page.errors.append("main element must use id=main")
            if values.get("tabindex") != "-1":
                self.page.errors.append("main#main must use tabindex=-1 for skip-link focus")
        elif tag == "h1":
            self.page.h1s += 1
        elif tag == "a" and "skip-link" in (values.get("class") or "").split():
            href = values.get("href")
            if href:
                self.page.skip_links.append(href)
        elif tag == "meta":
            name = (values.get("name") or "").lower()
            property_name = (values.get("property") or "").lower()
            content = values.get("content")
            if name == "description" and content:
                self.page.descriptions += 1
            elif name == "viewport" and content:
                self.page.viewports += 1
            elif property_name == "og:image" and content:
                self.page.og_images.append(content)
            elif property_name == "og:image:type" and content:
                self.page.og_image_types.append(content)
            elif property_name == "og:image:width" and content:
                self.page.og_image_widths.append(content)
            elif property_name == "og:image:height" and content:
                self.page.og_image_heights.append(content)

        if "style" in values:
            self.page.errors.append(f"inline style attribute on <{tag}>")

        element_id = values.get("id")
        if element_id:
            if element_id in self.page.ids:
                self.page.errors.append(f"duplicate id: {element_id}")
            self.page.ids.add(element_id)

        for attribute in ("href", "src"):
            value = values.get(attribute)
            if value:
                self.page.references.append((tag, attribute, value))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.page.in_title = False

    def handle_data(self, data: str) -> None:
        if self.page.in_title:
            self.page.title_parts.append(data)


def parse_pages() -> dict[Path, Page]:
    pages: dict[Path, Page] = {}
    for path in sorted(ROOT.rglob("*.html")):
        if ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        page = Page(path=relative)
        text = path.read_text(encoding="utf-8")
        if not text.lstrip().lower().startswith("<!doctype html>"):
            page.errors.append("missing HTML5 doctype")
        for glyph in FORBIDDEN_INTERFACE_GLYPHS:
            if glyph in text:
                page.errors.append(f"forbidden interface glyph: {glyph}")
        parser = PageParser(page)
        parser.feed(text)
        parser.close()
        if page.lang != "en":
            page.errors.append("html lang must be en")
        if not "".join(page.title_parts).strip():
            page.errors.append("missing title")
        if page.descriptions != 1:
            page.errors.append(f"expected one meta description, found {page.descriptions}")
        if page.viewports != 1:
            page.errors.append(f"expected one viewport meta, found {page.viewports}")
        if page.mains != 1:
            page.errors.append(f"expected one main element, found {page.mains}")
        if page.h1s != 1:
            page.errors.append(f"expected one h1 element, found {page.h1s}")
        if page.skip_links != ["#main"]:
            page.errors.append(f"expected one skip link to #main, found {page.skip_links!r}")
        if relative != Path("404.html"):
            expected_image = f"{PUBLIC_ORIGIN}/assets/social-card.png"
            if page.og_images != [expected_image]:
                page.errors.append(f"expected one Open Graph image {expected_image!r}, found {page.og_images!r}")
            if page.og_image_types != ["image/png"]:
                page.errors.append(f"expected og:image:type image/png, found {page.og_image_types!r}")
            if page.og_image_widths != ["1200"]:
                page.errors.append(f"expected og:image:width 1200, found {page.og_image_widths!r}")
            if page.og_image_heights != ["630"]:
                page.errors.append(f"expected og:image:height 630, found {page.og_image_heights!r}")
        pages[relative] = page
    return pages


def svg_ids(path: Path) -> set[str]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise AssertionError(f"{path.relative_to(ROOT)}: invalid SVG: {exc}") from exc
    return {value for element in root.iter() if (value := element.attrib.get("id"))}


def validate_social_png(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    label = path.relative_to(ROOT)
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{label}: invalid PNG signature")

    position = 8
    header: bytes | None = None
    compressed = bytearray()
    saw_end = False
    while position < len(data):
        if position + 12 > len(data):
            raise AssertionError(f"{label}: truncated PNG chunk header")
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_end = position + 12 + length
        if chunk_end > len(data):
            raise AssertionError(f"{label}: truncated {chunk_type.decode('ascii', 'replace')} chunk")
        payload = data[position + 8 : position + 8 + length]
        stored_crc = struct.unpack(">I", data[position + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(payload, zlib.crc32(chunk_type)) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            raise AssertionError(f"{label}: invalid {chunk_type.decode('ascii', 'replace')} chunk CRC")
        if chunk_type == b"IHDR":
            if header is not None or length != 13:
                raise AssertionError(f"{label}: invalid IHDR chunk")
            header = payload
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            if length:
                raise AssertionError(f"{label}: invalid IEND chunk")
            saw_end = True
            position = chunk_end
            break
        position = chunk_end

    if header is None or not compressed or not saw_end or position != len(data):
        raise AssertionError(f"{label}: incomplete PNG structure")

    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", header)
    if (bit_depth, color_type, compression, filter_method, interlace) != (8, 2, 0, 0, 0):
        raise AssertionError(f"{label}: expected non-interlaced 8-bit RGB PNG")
    try:
        scanlines = zlib.decompress(compressed)
    except zlib.error as exc:
        raise AssertionError(f"{label}: invalid compressed image data: {exc}") from exc

    bytes_per_pixel = 3
    row_bytes = width * bytes_per_pixel
    expected_size = height * (row_bytes + 1)
    if len(scanlines) != expected_size:
        raise AssertionError(f"{label}: expected {expected_size} decoded bytes, found {len(scanlines)}")

    def paeth(left: int, above: int, upper_left: int) -> int:
        estimate = left + above - upper_left
        left_distance = abs(estimate - left)
        above_distance = abs(estimate - above)
        upper_left_distance = abs(estimate - upper_left)
        if left_distance <= above_distance and left_distance <= upper_left_distance:
            return left
        if above_distance <= upper_left_distance:
            return above
        return upper_left

    rows: list[bytes] = []
    previous = bytearray(row_bytes)
    for row_number in range(height):
        start = row_number * (row_bytes + 1)
        filter_type = scanlines[start]
        row = bytearray(scanlines[start + 1 : start + 1 + row_bytes])
        if filter_type > 4:
            raise AssertionError(f"{label}: invalid filter {filter_type} on row {row_number}")
        for index in range(row_bytes):
            left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + above) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + paeth(left, above, upper_left)) & 0xFF
        rows.append(bytes(row))
        previous = row

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = x * bytes_per_pixel
        red, green, blue = rows[y][offset : offset + bytes_per_pixel]
        return red, green, blue

    if pixel(0, 0) != (22, 22, 27) or pixel(width - 1, height - 1) != (241, 237, 228):
        raise AssertionError(f"{label}: raster does not match the expected dark-left / light-right composition")
    required_colors = {(22, 22, 27), (241, 237, 228), (140, 116, 255)}
    present_colors: set[tuple[int, int, int]] = set()
    for row in rows:
        for index in range(0, row_bytes, bytes_per_pixel):
            color = row[index], row[index + 1], row[index + 2]
            if color in required_colors:
                present_colors.add(color)
        if present_colors == required_colors:
            break
    missing_colors = required_colors - present_colors
    if missing_colors:
        raise AssertionError(f"{label}: missing brand colors {sorted(missing_colors)!r}")
    return width, height


def resolve_local_reference(source: Path, value: str) -> tuple[Path, str] | None:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https", "mailto"} or parsed.netloc:
        return None
    raw_path = unquote(parsed.path)
    if raw_path.startswith("/"):
        target = ROOT / raw_path.lstrip("/")
    elif raw_path:
        target = ROOT / source.parent / raw_path
    else:
        target = ROOT / source
    if raw_path.endswith("/") or target == ROOT:
        target = target / "index.html"
    return target.resolve(), unquote(parsed.fragment)


def validate_references(pages: dict[Path, Page]) -> list[str]:
    errors: list[str] = []
    page_by_absolute = {(ROOT / path).resolve(): page for path, page in pages.items()}
    svg_cache: dict[Path, set[str]] = {}
    for source, page in pages.items():
        errors.extend(f"{source}: {error}" for error in page.errors)
        for tag, attribute, value in page.references:
            resolved = resolve_local_reference(source, value)
            if resolved is None:
                continue
            target, fragment = resolved
            if not target.exists():
                errors.append(f"{source}: broken {tag} {attribute} {value!r}")
                continue
            if fragment:
                if target.suffix.lower() == ".html":
                    target_page = page_by_absolute.get(target)
                    if target_page is None or fragment not in target_page.ids:
                        errors.append(f"{source}: missing HTML fragment {value!r}")
                elif target.suffix.lower() == ".svg":
                    ids = svg_cache.setdefault(target, svg_ids(target))
                    if fragment not in ids:
                        errors.append(f"{source}: missing SVG symbol {value!r}")
                else:
                    errors.append(f"{source}: fragment targets unsupported file {value!r}")
    return errors


def parse_xml(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise AssertionError(f"{path.relative_to(ROOT)}: invalid XML: {exc}") from exc


def relative_public_url(url: str) -> str:
    prefix = f"{PUBLIC_ORIGIN}/"
    if url == f"{PUBLIC_ORIGIN}/":
        return ""
    if not url.startswith(prefix):
        raise AssertionError(f"unexpected public URL: {url}")
    return url[len(prefix):]


def validate_public_indexes() -> list[str]:
    errors: list[str] = []
    notes = {
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "notes").glob("*.html"))
        if path.name != "index.html"
    }
    for index_path in (ROOT / "index.html", ROOT / "notes/index.html"):
        text = index_path.read_text(encoding="utf-8")
        for note in sorted(notes):
            expected = note if index_path.name == "index.html" and index_path.parent == ROOT else Path(note).name
            if f'href="{expected}"' not in text:
                errors.append(f"{index_path.relative_to(ROOT)}: missing field note {note}")

    feed_root = parse_xml(ROOT / "feed.xml")
    feed_urls = [item.findtext("link", default="") for item in feed_root.findall("./channel/item")]
    if len(feed_urls) != len(set(feed_urls)):
        errors.append("feed.xml: duplicate item links")
    feed_notes = {relative_public_url(url) for url in feed_urls if url}
    errors.extend(f"feed.xml: missing field note {note}" for note in sorted(notes - feed_notes))

    sitemap_root = parse_xml(ROOT / "sitemap.xml")
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_urls = [element.text or "" for element in sitemap_root.findall("./sm:url/sm:loc", namespace)]
    if len(sitemap_urls) != len(set(sitemap_urls)):
        errors.append("sitemap.xml: duplicate locations")
    sitemap_paths = {relative_public_url(url) for url in sitemap_urls if url}
    for required in {"work.html", "notes/", "now.html", "about.html", *notes}:
        if required not in sitemap_paths:
            errors.append(f"sitemap.xml: missing published path {required}")

    for required in REQUIRED_PAGES:
        if not (ROOT / required).is_file():
            errors.append(f"missing required page: {required}")

    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    if f"Sitemap: {PUBLIC_ORIGIN}/sitemap.xml" not in robots:
        errors.append("robots.txt: missing canonical sitemap URL")
    return errors


def validate_design_system() -> list[str]:
    errors: list[str] = []
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    for forbidden in ("radial-gradient", "signal-dot", "border-radius: 999", "drop-shadow"):
        if forbidden in css:
            errors.append(f"styles.css: forbidden generic treatment {forbidden!r}")
    icon_ids = svg_ids(ROOT / "assets/icons.svg")
    required_icons = {"arrow-right", "arrow-left", "external-link", "github", "rss", "mail", "dev"}
    errors.extend(f"assets/icons.svg: missing symbol {icon}" for icon in sorted(required_icons - icon_ids))

    social_svg = ROOT / "assets/social-card.svg"
    social_png = ROOT / "assets/social-card.png"
    if not social_svg.is_file():
        errors.append("assets/social-card.svg: missing editable social-card source")
    if not social_png.is_file():
        errors.append("assets/social-card.png: missing raster social-card asset")
    else:
        try:
            dimensions = validate_social_png(social_png)
        except AssertionError as exc:
            errors.append(str(exc))
        else:
            if dimensions != (1200, 630):
                errors.append(f"assets/social-card.png: expected 1200x630, found {dimensions[0]}x{dimensions[1]}")
    return errors


def validate_identity(pages: dict[Path, Page]) -> list[str]:
    errors: list[str] = []
    brand_markup = f"<small>{CURRENT_BRAND_LABEL}</small>"
    stale_brand_markup = "<small>AI-assisted contributor</small>"
    for relative in sorted(pages):
        page_text = (ROOT / relative).read_text(encoding="utf-8")
        if brand_markup not in page_text:
            errors.append(f"{relative}: missing current identity label {CURRENT_BRAND_LABEL!r}")
        if stale_brand_markup in page_text:
            errors.append(f"{relative}: contains stale identity label")
        if "footer-bottom" in page_text:
            if PAYMENT_URL not in page_text:
                errors.append(f"{relative}: missing default payment URL")
            if PAYMENT_LABEL not in page_text:
                errors.append(f"{relative}: missing default payment label")
        if "buymeacoffee.com" in page_text:
            errors.append(f"{relative}: contains superseded Buy Me a Coffee link")

    for relative, requirements in IDENTITY_REQUIREMENTS.items():
        surface_text = (ROOT / relative).read_text(encoding="utf-8")
        for required in requirements:
            if required not in surface_text:
                errors.append(f"{relative}: missing required identity text {required!r}")
    for relative, forbidden_values in IDENTITY_FORBIDDEN.items():
        surface_text = (ROOT / relative).read_text(encoding="utf-8")
        for forbidden in forbidden_values:
            if forbidden in surface_text:
                errors.append(f"{relative}: contains stale identity text {forbidden!r}")
    return errors


def main() -> int:
    pages = parse_pages()
    errors = validate_references(pages)
    errors.extend(validate_public_indexes())
    errors.extend(validate_design_system())
    errors.extend(validate_identity(pages))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    note_count = len([path for path in (ROOT / "notes").glob("*.html") if path.name != "index.html"])
    print(f"Validated {len(pages)} HTML pages, {note_count} field notes, SVG symbols, XML indexes, metadata, and design invariants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
