from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Tuple

from e3sm_comms.page_reviewer.utils_base import map_confluence_to_e3sm
from e3sm_comms.utils import IO_DIR

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

INPUT_XML_PAGES: str = f"{IO_DIR}/input/exported_xml_reviewer/wordpress_pages.xml"
INPUT_XML_POSTS: str = f"{IO_DIR}/input/exported_xml_reviewer/wordpress_posts.xml"
INPUT_CONFLUENCE_HIERARCHY: str = (
    f"{IO_DIR}/input/exported_xml_reviewer/hierarchical_outline.txt"
)
INPUT_SEARCH_PHRASES: str = f"{IO_DIR}/input/shared/sensitive_terms.txt"

OUTPUT_MARKDOWN_REPORT: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_sensitive_terms_report.md"
)

CONFLUENCE_SPACE = "EPWCD"
CONFLUENCE_BASE = "https://e3sm.atlassian.net/wiki"


@dataclass
class WordpressItem:
    title: str
    url: str
    status: str
    body: str


@dataclass
class ReportRecord:
    title: str
    e3sm_url: str
    status: str
    sensitive_terms: Dict[str, int]
    confluence_draft_url: Optional[str]


def build_confluence_url(page_id: str, space_key: str = CONFLUENCE_SPACE) -> str:
    return f"{CONFLUENCE_BASE}/spaces/{space_key}/pages/{page_id}"


def normalize_status(raw_status: Optional[str]) -> str:
    if not raw_status:
        return "unknown"

    mapping = {
        "publish": "published",
        "archive": "archived",
        "draft": "draft",
        "future": "future",
        "pending": "pending",
        "private": "private",
    }
    return mapping.get(raw_status.strip().lower(), raw_status.strip().lower())


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read_sensitive_terms(file_path: str) -> List[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        terms = [line.strip().lower() for line in f if line.strip()]
    return sorted(set(terms))


def count_sensitive_terms(text: str, terms: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    lowered = text.lower()

    for term in terms:
        escaped = re.escape(term)
        pattern = rf"\b{escaped}\b"
        matches = re.findall(pattern, lowered)
        if matches:
            counts[term] = len(matches)

    return counts


def parse_confluence_hierarchy_file(input_file: str) -> List[Tuple[str, str]]:
    parsed: List[Tuple[str, str]] = []

    with open(input_file, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue

            stripped = line.lstrip()
            if ":" not in stripped:
                print(f"Skipping malformed Confluence line {line_number}: {line}")
                continue

            page_id, title = stripped.split(":", 1)
            page_id = page_id.strip()
            title = title.strip()

            if not page_id.isdigit():
                print(
                    f"Skipping Confluence line {line_number} with non-numeric page id: {line}"
                )
                continue

            parsed.append((page_id, title))

    return parsed


def get_confluence_mapping(input_file: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    if map_confluence_to_e3sm is None:
        print(
            "Warning: map_confluence_to_e3sm is not available, Confluence mapping will be skipped."
        )
        return mapping

    for page_id, title in parse_confluence_hierarchy_file(input_file):
        confluence_url = build_confluence_url(page_id)
        try:
            e3sm_url = map_confluence_to_e3sm(confluence_url, page_title=title)
            if e3sm_url:
                mapping[e3sm_url] = confluence_url
        except Exception as exc:
            print(f"Could not map {confluence_url}: {exc}")

    return mapping


def extract_item_body(item: ET.Element) -> str:
    ns = {
        "wp": "http://wordpress.org/export/1.2/",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    }

    body_parts: List[str] = []

    content_elem = item.find("content:encoded", ns)
    if content_elem is not None and content_elem.text and content_elem.text.strip():
        body_parts.append(content_elem.text.strip())

    excerpt_elem = item.find("excerpt:encoded", ns)
    if excerpt_elem is not None and excerpt_elem.text and excerpt_elem.text.strip():
        body_parts.append(excerpt_elem.text.strip())

    for postmeta in item.findall("wp:postmeta", ns):
        meta_key_elem = postmeta.find("wp:meta_key", ns)
        meta_value_elem = postmeta.find("wp:meta_value", ns)

        meta_key = (
            meta_key_elem.text.strip()
            if meta_key_elem is not None and meta_key_elem.text
            else ""
        )
        meta_value = (
            meta_value_elem.text.strip()
            if meta_value_elem is not None and meta_value_elem.text
            else ""
        )

        if not meta_value:
            continue

        if meta_key.endswith("_free_form_content") and not meta_key.startswith("_"):
            body_parts.append(meta_value)

    return "\n".join(body_parts)


def parse_wordpress_xml(
    xml_file_path: str, expected_post_type: str
) -> List[WordpressItem]:
    ns = {
        "wp": "http://wordpress.org/export/1.2/",
    }

    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    channel = root.find("channel")
    if channel is None:
        return []

    items: List[WordpressItem] = []

    for item in channel.findall("item"):
        post_type_elem = item.find("wp:post_type", ns)
        if post_type_elem is None:
            continue

        post_type_text = (post_type_elem.text or "").strip()
        if post_type_text != expected_post_type:
            continue

        title_elem = item.find("title")
        link_elem = item.find("link")
        status_elem = item.find("wp:status", ns)

        title = (
            title_elem.text.strip()
            if title_elem is not None and title_elem.text is not None
            else "Untitled"
        )
        link = (
            link_elem.text.strip()
            if link_elem is not None and link_elem.text is not None
            else ""
        )
        status = (
            status_elem.text.strip()
            if status_elem is not None and status_elem.text is not None
            else "unknown"
        )
        body = extract_item_body(item)

        items.append(
            WordpressItem(
                title=title,
                url=link,
                status=status,
                body=body,
            )
        )

    return items


def build_records(
    xml_pages: str,
    xml_posts: str,
    confluence_hierarchy: str,
    sensitive_terms_file: str,
) -> List[ReportRecord]:
    sensitive_terms_list = read_sensitive_terms(sensitive_terms_file)
    confluence_map = get_confluence_mapping(confluence_hierarchy)

    raw_items: List[WordpressItem] = []
    raw_items.extend(parse_wordpress_xml(xml_pages, "page"))
    raw_items.extend(parse_wordpress_xml(xml_posts, "post"))

    records: List[ReportRecord] = []

    for item in raw_items:
        plain_text = strip_html(item.body)
        term_counts = count_sensitive_terms(plain_text, sensitive_terms_list)

        if not term_counts:
            continue

        records.append(
            ReportRecord(
                title=item.title,
                e3sm_url=item.url,
                status=normalize_status(item.status),
                sensitive_terms=term_counts,
                confluence_draft_url=confluence_map.get(item.url),
            )
        )

    return records


def write_markdown_report(output_path: str, records: List[ReportRecord]) -> None:
    grouped: DefaultDict[str, List[ReportRecord]] = defaultdict(list)
    for record in records:
        grouped[record.status].append(record)

    for status in grouped:
        grouped[status].sort(
            key=lambda r: (-sum(r.sensitive_terms.values()), r.title.lower())
        )

    ordered_statuses = [
        "published",
        "archived",
        "draft",
        "future",
        "pending",
        "private",
        "unknown",
    ]

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# WordPress Sensitive Terms Report\n\n")
        f.write(
            "This report includes only e3sm.org pages/posts where one or more sensitive terms were found.\n\n"
        )

        f.write("| Status | Count |\n")
        f.write("| --- | ---: |\n")

        for status in ordered_statuses:
            if status in grouped:
                f.write(f"| {status} | {len(grouped[status])} |\n")

        extra_statuses = sorted(s for s in grouped if s not in ordered_statuses)
        for status in extra_statuses:
            f.write(f"| {status} | {len(grouped[status])} |\n")

        f.write("\n")

        all_statuses = ordered_statuses + extra_statuses
        seen = set()

        for status in all_statuses:
            if status not in grouped or status in seen:
                continue
            seen.add(status)

            f.write(f"## {status.capitalize()}\n\n")

            for idx, record in enumerate(grouped[status], start=1):
                e3sm_md = f"[e3sm.org]({record.e3sm_url})"
                confluence_md = (
                    f" [confluence draft]({record.confluence_draft_url})"
                    if record.confluence_draft_url
                    else ""
                )

                f.write(
                    f"{idx}. {record.title}: {e3sm_md}{confluence_md} -- {record.sensitive_terms}\n"
                )

            f.write("\n")


def main() -> None:
    records = build_records(
        xml_pages=INPUT_XML_PAGES,
        xml_posts=INPUT_XML_POSTS,
        confluence_hierarchy=INPUT_CONFLUENCE_HIERARCHY,
        sensitive_terms_file=INPUT_SEARCH_PHRASES,
    )

    write_markdown_report(OUTPUT_MARKDOWN_REPORT, records)
    print(f"Wrote report to {OUTPUT_MARKDOWN_REPORT}")


if __name__ == "__main__":
    main()
