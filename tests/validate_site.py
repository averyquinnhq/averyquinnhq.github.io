#!/usr/bin/env python3
"""Dependency-free integrity and design-system checks for the Avery Quinn site."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ORIGIN = "https://averyquinnhq.github.io"
FORBIDDEN_INTERFACE_GLYPHS = {"◆", "◇", "✦", "→", "←", "↗", "➜", "✨", "🔗"}
REQUIRED_PAGES = {Path("index.html"), Path("work.html"), Path("notes/index.html"), Path("now.html"), Path("about.html"), Path("404.html")}


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
        elif tag == "meta":
            name = (values.get("name") or "").lower()
            if name == "description" and values.get("content"):
                self.page.descriptions += 1
            elif name == "viewport" and values.get("content"):
                self.page.viewports += 1

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
        pages[relative] = page
    return pages


def svg_ids(path: Path) -> set[str]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise AssertionError(f"{path.relative_to(ROOT)}: invalid SVG: {exc}") from exc
    return {value for element in root.iter() if (value := element.attrib.get("id"))}


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
    return errors


def main() -> int:
    pages = parse_pages()
    errors = validate_references(pages)
    errors.extend(validate_public_indexes())
    errors.extend(validate_design_system())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    note_count = len([path for path in (ROOT / "notes").glob("*.html") if path.name != "index.html"])
    print(f"Validated {len(pages)} HTML pages, {note_count} field notes, SVG symbols, XML indexes, metadata, and design invariants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
