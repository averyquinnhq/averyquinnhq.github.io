#!/usr/bin/env python3
"""Dependency-free integrity checks for the static Avery Quinn site."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ORIGIN = "https://averyquinnhq.github.io"


@dataclass
class Page:
    path: Path
    ids: set[str] = field(default_factory=set)
    references: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PageParser(HTMLParser):
    def __init__(self, page: Page) -> None:
        super().__init__(convert_charrefs=True)
        self.page = page

    def handle_decl(self, decl: str) -> None:
        if decl.lower() != "doctype html":
            self.page.errors.append(f"unexpected declaration: {decl}")

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.page.ids:
                self.page.errors.append(f"duplicate id: {element_id}")
            self.page.ids.add(element_id)

        for attribute in ("href", "src"):
            value = values.get(attribute)
            if value:
                self.page.references.append((attribute, value))


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
        parser = PageParser(page)
        parser.feed(text)
        parser.close()
        pages[relative] = page
    return pages


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

    for source, page in pages.items():
        errors.extend(f"{source}: {error}" for error in page.errors)
        for attribute, value in page.references:
            resolved = resolve_local_reference(source, value)
            if resolved is None:
                continue
            target, fragment = resolved
            if not target.exists():
                errors.append(f"{source}: broken {attribute} {value!r}")
                continue
            if fragment:
                target_page = page_by_absolute.get(target)
                if target_page is None:
                    errors.append(
                        f"{source}: fragment {fragment!r} targets non-HTML {value!r}"
                    )
                elif fragment not in target_page.ids:
                    errors.append(f"{source}: missing fragment {value!r}")
    return errors


def parse_xml(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise AssertionError(f"{path.relative_to(ROOT)}: invalid XML: {exc}") from exc


def relative_public_url(url: str) -> str:
    prefix = f"{PUBLIC_ORIGIN}/"
    if not url.startswith(prefix):
        raise AssertionError(f"unexpected public URL: {url}")
    return url[len(prefix) :]


def validate_public_indexes() -> list[str]:
    errors: list[str] = []
    notes = {
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "notes").glob("*.html"))
    }

    index_text = (ROOT / "index.html").read_text(encoding="utf-8")
    missing_from_index = sorted(
        note for note in notes if f'href="{note}"' not in index_text
    )
    errors.extend(f"index.html: missing field note {note}" for note in missing_from_index)

    feed_root = parse_xml(ROOT / "feed.xml")
    feed_urls = [
        item.findtext("link", default="") for item in feed_root.findall("./channel/item")
    ]
    if len(feed_urls) != len(set(feed_urls)):
        errors.append("feed.xml: duplicate item links")
    feed_notes = {relative_public_url(url) for url in feed_urls if url}
    errors.extend(
        f"feed.xml: missing field note {note}" for note in sorted(notes - feed_notes)
    )

    sitemap_root = parse_xml(ROOT / "sitemap.xml")
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_urls = [
        element.text or ""
        for element in sitemap_root.findall("./sm:url/sm:loc", namespace)
    ]
    if len(sitemap_urls) != len(set(sitemap_urls)):
        errors.append("sitemap.xml: duplicate locations")
    sitemap_paths = {relative_public_url(url) for url in sitemap_urls if url}
    errors.extend(
        f"sitemap.xml: missing field note {note}"
        for note in sorted(notes - sitemap_paths)
    )
    for required in {"now.html", *notes}:
        if not (ROOT / required).is_file():
            errors.append(f"missing published file: {required}")

    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    expected_sitemap = f"Sitemap: {PUBLIC_ORIGIN}/sitemap.xml"
    if expected_sitemap not in robots:
        errors.append("robots.txt: missing canonical sitemap URL")
    return errors


def main() -> int:
    pages = parse_pages()
    errors = validate_references(pages)
    errors.extend(validate_public_indexes())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    note_count = len(list((ROOT / "notes").glob("*.html")))
    print(f"Validated {len(pages)} HTML pages and {note_count} published field notes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
