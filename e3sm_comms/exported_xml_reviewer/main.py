from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit, urlunsplit

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
INPUT_WHITELIST: str = f"{IO_DIR}/input/exported_xml_reviewer/whitelisted_web_pages.txt"
INPUT_REQUESTED_LINKS: str = f"{IO_DIR}/input/exported_xml_reviewer/requested_links.csv"

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


@dataclass
class RequestedLinkRecord:
    e3sm_url: str
    included_later: bool
    current_status: str
    currently_whitelisted: bool
    requesting_urls: str


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")

    normalized = urlunsplit((scheme, netloc, path, "", ""))
    return normalized


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


def display_status(status: str) -> str:
    mapping = {
        "published": "Published",
        "archived": "Archived",
        "draft": "Draft",
        "future": "Future",
        "pending": "Pending",
        "private": "Private",
        "unknown": "Unknown",
    }
    return mapping.get(status, status.title())


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read_sensitive_terms(file_path: str) -> List[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        terms = [line.strip().lower() for line in f if line.strip()]
    return sorted(set(terms))


def read_whitelist_patterns(file_path: str) -> List[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def read_requested_links(file_path: str) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []

    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            print(f"Requested links CSV has no headers: {file_path}")
            return rows

        normalized_to_actual = {
            header.strip().lower(): header for header in reader.fieldnames if header
        }

        e3sm_header = normalized_to_actual.get("e3sm.org link")
        requesting_header = normalized_to_actual.get(
            "list of urls that wants to link to it"
        )

        if requesting_header is None:
            for candidate in [
                "list of urls that want to link to it",
                "requesting urls",
                "requesting url",
                "list of urls",
            ]:
                requesting_header = normalized_to_actual.get(candidate)
                if requesting_header:
                    break

        if e3sm_header is None:
            print(
                f"Requested links CSV is missing required column 'e3sm.org link'. "
                f"Found headers: {reader.fieldnames}"
            )
            return rows

        if requesting_header is None:
            print(
                "Requested links CSV could not find the requesting URLs column. "
                f"Found headers: {reader.fieldnames}"
            )

        for row in reader:
            e3sm_url = normalize_url(row.get(e3sm_header, ""))
            requesting_urls = (
                row.get(requesting_header, "").strip() if requesting_header else ""
            )

            if e3sm_url:
                rows.append((e3sm_url, requesting_urls))

    return rows


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


def matches_pattern(pattern: str, url: str) -> bool:
    if "*" not in pattern:
        return normalize_url(pattern) == normalize_url(url)

    normalized_url = normalize_url(url)
    normalized_pattern = normalize_url(pattern)

    if "*" not in normalized_pattern:
        return normalized_pattern == normalized_url

    if normalized_pattern.count("*") == 1 and normalized_pattern.endswith("*"):
        prefix = normalized_pattern[:-1]
        return normalized_url.startswith(prefix)

    parts = normalized_pattern.split("*")
    position = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        found_at = normalized_url.find(part, position)
        if found_at == -1:
            return False
        if i == 0 and not normalized_pattern.startswith("*") and found_at != 0:
            return False
        position = found_at + len(part)

    if (
        not normalized_pattern.endswith("*")
        and parts[-1]
        and not normalized_url.endswith(parts[-1])
    ):
        return False

    return True


def expand_patterns_to_urls(patterns: List[str], all_urls: List[str]) -> Set[str]:
    matched_urls: Set[str] = set()
    for pattern in patterns:
        for url in all_urls:
            if matches_pattern(pattern, url):
                matched_urls.add(url)
    return matched_urls


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
                mapping[normalize_url(e3sm_url)] = confluence_url
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
            normalize_url(link_elem.text)
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


def build_requested_link_records(
    requested_links_file: str,
    raw_items: List[WordpressItem],
    whitelisted_urls: Set[str],
    flagged_urls: Set[str],
) -> List[RequestedLinkRecord]:
    requested_rows = read_requested_links(requested_links_file)
    item_by_url = {item.url: item for item in raw_items if item.url}

    records: List[RequestedLinkRecord] = []
    for e3sm_url, requesting_urls in requested_rows:
        item = item_by_url.get(e3sm_url)

        if item is None:
            current_status = "Not found"
            currently_whitelisted = False
        else:
            current_status = display_status(normalize_status(item.status))
            currently_whitelisted = e3sm_url in whitelisted_urls

        records.append(
            RequestedLinkRecord(
                e3sm_url=e3sm_url,
                included_later=e3sm_url in flagged_urls,
                current_status=current_status,
                currently_whitelisted=currently_whitelisted,
                requesting_urls=requesting_urls,
            )
        )

    return records


def build_records(
    xml_pages: str,
    xml_posts: str,
    confluence_hierarchy: str,
    sensitive_terms_file: str,
    whitelist_file: str,
    requested_links_file: str,
) -> Tuple[List[ReportRecord], Dict[str, int], List[RequestedLinkRecord]]:
    sensitive_terms_list = read_sensitive_terms(sensitive_terms_file)
    confluence_map = get_confluence_mapping(confluence_hierarchy)

    raw_items: List[WordpressItem] = []
    raw_items.extend(parse_wordpress_xml(xml_pages, "page"))
    raw_items.extend(parse_wordpress_xml(xml_posts, "post"))

    whitelist_patterns = read_whitelist_patterns(whitelist_file)
    all_urls = [item.url for item in raw_items if item.url]
    whitelisted_urls = expand_patterns_to_urls(whitelist_patterns, all_urls)

    records: List[ReportRecord] = []
    status_totals: DefaultDict[str, int] = defaultdict(int)

    for item in raw_items:
        base_status = normalize_status(item.status)
        report_status = base_status

        if base_status == "published":
            if item.url in whitelisted_urls:
                report_status = "published & whitelisted"
            else:
                report_status = "published & not whitelisted"

        status_totals[report_status] += 1

        plain_text = strip_html(item.body)
        term_counts = count_sensitive_terms(plain_text, sensitive_terms_list)

        if not term_counts:
            continue

        records.append(
            ReportRecord(
                title=item.title,
                e3sm_url=item.url,
                status=report_status,
                sensitive_terms=term_counts,
                confluence_draft_url=confluence_map.get(item.url),
            )
        )

    flagged_urls = {record.e3sm_url for record in records}
    requested_link_records = build_requested_link_records(
        requested_links_file=requested_links_file,
        raw_items=raw_items,
        whitelisted_urls=whitelisted_urls,
        flagged_urls=flagged_urls,
    )

    return records, dict(status_totals), requested_link_records


def sort_requested_link_records(
    requested_link_records: List[RequestedLinkRecord],
) -> List[RequestedLinkRecord]:
    status_order = {
        "Published": 0,
        "Archived": 1,
        "Not found": 3,
    }

    return sorted(
        requested_link_records,
        key=lambda r: (
            0 if r.included_later else 1,
            status_order.get(r.current_status, 2),
            0 if r.currently_whitelisted else 1,
            r.e3sm_url.lower(),
        ),
    )


def write_markdown_report(
    output_path: str,
    records: List[ReportRecord],
    status_totals: Dict[str, int],
    requested_link_records: List[RequestedLinkRecord],
) -> None:
    grouped: DefaultDict[str, List[ReportRecord]] = defaultdict(list)
    for record in records:
        grouped[record.status].append(record)

    for status in grouped:
        grouped[status].sort(
            key=lambda r: (-sum(r.sensitive_terms.values()), r.title.lower())
        )

    ordered_statuses = [
        "published & whitelisted",
        "published & not whitelisted",
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
            "The detailed sections below include only e3sm.org pages/posts where one or more sensitive terms were found. "
            "The summary table includes counts for both flagged and unflagged items.\n\n"
        )

        f.write("| Status | With sensitive terms | Without sensitive terms | Total |\n")
        f.write("| --- | ---: | ---: | ---: |\n")

        total_with_terms = 0
        total_without_terms = 0

        all_summary_statuses = set(status_totals) | set(grouped)
        extra_statuses = sorted(
            s for s in all_summary_statuses if s not in ordered_statuses
        )

        for status in ordered_statuses + extra_statuses:
            total_in_status = status_totals.get(status, 0)
            with_terms = len(grouped.get(status, []))
            without_terms = total_in_status - with_terms

            if total_in_status == 0 and with_terms == 0:
                continue

            total_with_terms += with_terms
            total_without_terms += without_terms
            f.write(
                f"| {status} | {with_terms} | {without_terms} | {total_in_status} |\n"
            )

        grand_total = total_with_terms + total_without_terms
        f.write(
            f"| TOTAL | {total_with_terms} | {total_without_terms} | {grand_total} |\n"
        )
        f.write("\n")

        if requested_link_records:
            requested_link_records = sort_requested_link_records(requested_link_records)

            f.write("## Requested Links\n\n")
            f.write(
                "| e3sm.org link | Included later on this page? | Current status | Currently whitelisted? | Requesting URLs |\n"
            )
            f.write("| --- | --- | --- | --- | --- |\n")

            for requested_record in requested_link_records:
                included_later = (
                    "Yes"
                    if requested_record.included_later
                    else "No (i.e., contains no sensitive terms)"
                )
                currently_whitelisted = (
                    "Yes" if requested_record.currently_whitelisted else "No"
                )
                f.write(
                    f"| {requested_record.e3sm_url} | {included_later} | {requested_record.current_status} | "
                    f"{currently_whitelisted} | {requested_record.requesting_urls} |\n"
                )

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
                    f" [(confluence draft)]({record.confluence_draft_url})"
                    if record.confluence_draft_url
                    else ""
                )

                f.write(
                    f"{idx}. {record.title}: {e3sm_md}{confluence_md} -- {record.sensitive_terms}\n"
                )

            f.write("\n")


def main() -> None:
    records, status_totals, requested_link_records = build_records(
        xml_pages=INPUT_XML_PAGES,
        xml_posts=INPUT_XML_POSTS,
        confluence_hierarchy=INPUT_CONFLUENCE_HIERARCHY,
        sensitive_terms_file=INPUT_SEARCH_PHRASES,
        whitelist_file=INPUT_WHITELIST,
        requested_links_file=INPUT_REQUESTED_LINKS,
    )

    write_markdown_report(
        OUTPUT_MARKDOWN_REPORT,
        records,
        status_totals,
        requested_link_records,
    )
    print(f"Wrote report to {OUTPUT_MARKDOWN_REPORT}")


if __name__ == "__main__":
    main()
