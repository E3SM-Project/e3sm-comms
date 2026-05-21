import ast
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, DefaultDict, Dict, List, Optional, Set, TextIO, Tuple

from e3sm_comms.page_reviewer.utils_base import (
    LinkedURLs,
    get_e3sm_url_status,
    map_confluence_to_e3sm,
)
from e3sm_comms.utils import IO_DIR

# From WordPress under Tools > Export:
INPUT_XML_PAGES: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_pages.xml"
INPUT_XML_POSTS: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_posts.xml"

# From output of `e3sm-comms-website-reviewer`:
INPUT_CONFLUENCE_HIERARCHY: str = (
    f"{IO_DIR}/input/e3sm_org_reviewer/hierarchical_outline.txt"
)
INPUT_CONFLUENCE_SENSITIVE_TERMS: str = (
    f"{IO_DIR}/input/e3sm_org_reviewer/confluence_sensitive_terms.txt"
)

# Other:
INPUT_WHITELIST: str = f"{IO_DIR}/input/e3sm_org_reviewer/whitelisted_web_pages.txt"
INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/input/shared/archived_web_pages.txt"
)
INPUT_SEARCH_PHRASES: str = f"{IO_DIR}/input/shared/sensitive_terms.txt"
INPUT_KNOWN_OK_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/input/e3sm_org_reviewer/known_ok_e3sm_org_paths.txt"
)
INPUT_KEEP_UNCHANGED_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/input/e3sm_org_reviewer/keep_unchanged_e3sm_org_paths.txt"
)

OUTPUT_MARKDOWN_REPORT: str = f"{IO_DIR}/output/e3sm_org_reviewer/path_report.md"
OUTPUT_SENSITIVE_TERMS_REPORT: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/sensitive_terms.md"
)
OUTPUT_ACTION_ITEMS_REPORT: str = f"{IO_DIR}/output/e3sm_org_reviewer/action_items.md"

RUN_CHECKS: bool = True  # Set to False for faster debugging

CONFLUENCE_SPACE = "EPWCD"
CONFLUENCE_BASE = "https://e3sm.atlassian.net/wiki"

FROM_PREFIX_RE = re.compile(r"^\[From\s+(\d{4})-\d{2}-\d{2}T[^\]]+\]\s*(.*)$")

CLASS_PUBLISHED = "Published"
CLASS_ARCHIVED = "Archived"
CLASS_SHOULD_BE_ARCHIVED = "Should be archived"
CLASS_NOT_PUBLISHED = "Not published"
CLASS_KNOWN_OK = "Known OK"
CLASS_KEEP_UNCHANGED = "Keep unchanged"
CLASS_NO_MAPPED_E3SM_URL = "No mapped e3sm.org URL"
CLASS_PREDICTED_URL_NOT_IN_EXPORT = "Predicted e3sm.org URL not in WordPress export"


@dataclass
class SensitiveTermRecord:
    source: str  # "e3sm.org" or "confluence"
    raw_line: str
    year_label: str
    year_int: Optional[int]
    total_terms: int
    term_counts: Dict[str, int]
    source_url: Optional[str]
    title: Optional[str]
    confluence_url: Optional[str]
    e3sm_url: Optional[str]
    classification: str
    wordpress_status: Optional[str]


def build_confluence_url(page_id: str, space_key: str = CONFLUENCE_SPACE) -> str:
    return f"{CONFLUENCE_BASE}/spaces/{space_key}/pages/{page_id}"


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


def get_confluence_predicted_e3sm_urls(
    input_file: str,
) -> Tuple[List[str], List[str]]:
    valid_predicted_urls: List[str] = []
    unmapped_confluence_pages: List[str] = []

    for page_id, title in parse_confluence_hierarchy_file(input_file):
        confluence_url = build_confluence_url(page_id)
        try:
            e3sm_url = map_confluence_to_e3sm(confluence_url, page_title=title)
            if e3sm_url:
                valid_predicted_urls.append(e3sm_url)
            else:
                unmapped_confluence_pages.append(f"{title}: {confluence_url}")
        except Exception as exc:
            print(
                f"Could not map Confluence URL to e3sm.org URL for {confluence_url}: {exc}"
            )
            unmapped_confluence_pages.append(f"{title}: {confluence_url}")

    return sorted(set(valid_predicted_urls)), sorted(unmapped_confluence_pages)


def print_status_counts(all_urls_by_status: Dict[str, List[str]]) -> None:
    for status in ["publish", "archive", "draft", "future", "pending", "private"]:
        if status in all_urls_by_status:
            print(f"Found {len(all_urls_by_status[status])} {status} URLs")


def get_wordpress_urls_by_status(
    xml_file_path: str, post_type: str
) -> Dict[str, List[str]]:
    ns = {
        "wp": "http://wordpress.org/export/1.2/",
    }

    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    grouped: Dict[str, List[str]] = defaultdict(list)
    channel = root.find("channel")
    if channel is None:
        return {}

    for item in channel.findall("item"):
        item_post_type = item.find("wp:post_type", ns)
        item_status = item.find("wp:status", ns)
        link = item.find("link")

        if item_post_type is None or item_post_type.text != post_type:
            continue

        status = (
            item_status.text.strip()
            if item_status is not None and item_status.text
            else "unknown"
        )

        if link is not None and link.text:
            grouped[status].append(link.text.strip())

    return {status: sorted(urls) for status, urls in sorted(grouped.items())}


def get_total_count(urls_by_status: Dict[str, List[str]]) -> int:
    return sum(len(urls) for urls in urls_by_status.values())


def get_combined_urls_by_status(
    pages_by_status: Dict[str, List[str]], posts_by_status: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = defaultdict(list)
    for source in (pages_by_status, posts_by_status):
        for status, urls in source.items():
            merged[status].extend(urls)
    return {status: sorted(urls) for status, urls in sorted(merged.items())}


def get_list_difference(list1: List[str], list2: List[str]) -> List[str]:
    return sorted(set(list1) - set(list2))


def get_all_urls(urls_by_status: Dict[str, List[str]]) -> List[str]:
    all_urls: List[str] = []
    for urls in urls_by_status.values():
        all_urls.extend(urls)
    return sorted(all_urls)


def get_all_non_published_urls(urls_by_status: Dict[str, List[str]]) -> List[str]:
    non_published_urls: List[str] = []
    for status, urls in urls_by_status.items():
        if status != "publish":
            non_published_urls.extend(urls)
    return sorted(non_published_urls)


def matches_pattern(pattern: str, url: str) -> bool:
    if "*" not in pattern:
        return pattern == url

    if pattern.count("*") == 1 and pattern.endswith("*"):
        prefix = pattern[:-1]
        return url.startswith(prefix)

    parts = pattern.split("*")
    position = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        found_at = url.find(part, position)
        if found_at == -1:
            return False
        if i == 0 and not pattern.startswith("*") and found_at != 0:
            return False
        position = found_at + len(part)

    if not pattern.endswith("*") and parts[-1] and not url.endswith(parts[-1]):
        return False

    return True


def expand_patterns_to_urls(patterns: List[str], all_urls: List[str]) -> List[str]:
    matched_urls: Set[str] = set()
    for pattern in patterns:
        for url in all_urls:
            if matches_pattern(pattern, url):
                matched_urls.add(url)
    return sorted(matched_urls)


def get_invalid_patterns(patterns: List[str], all_urls: List[str]) -> List[str]:
    invalid_patterns: List[str] = []
    for pattern in patterns:
        if not any(matches_pattern(pattern, url) for url in all_urls):
            invalid_patterns.append(pattern)
    return sorted(invalid_patterns)


def get_status_counts_for_urls(
    urls: List[str], all_urls_by_status: Dict[str, List[str]], statuses: List[str]
) -> Dict[str, int]:
    url_set = set(urls)
    counts: Dict[str, int] = {}
    for status in statuses:
        counts[status] = len(url_set.intersection(all_urls_by_status.get(status, [])))
    return counts


def write_markdown_section(file_obj: TextIO, title: str, items: List[str]) -> None:
    file_obj.write(f"## {title}\n\n")
    if not items:
        file_obj.write("_None._\n\n")
        return

    for i, item in enumerate(items, start=1):
        file_obj.write(f"{i}. {item}\n")
    file_obj.write("\n")


def write_summary_table(
    file_obj: TextIO,
    all_urls_by_status: Dict[str, List[str]],
    valid_whitelisted_paths: List[str],
    valid_expected_archived_paths: List[str],
    valid_confluence_paths: List[str],
    invalid_confluence_paths: List[str],
    confluence_unmapped_entries: List[str],
) -> None:
    statuses: List[str] = sorted(all_urls_by_status.keys())
    all_urls: List[str] = get_all_urls(all_urls_by_status)

    whitelist_set: Set[str] = set(
        expand_patterns_to_urls(valid_whitelisted_paths, all_urls)
    )
    expected_archived_set: Set[str] = set(
        expand_patterns_to_urls(valid_expected_archived_paths, all_urls)
    )
    both_set: Set[str] = whitelist_set.intersection(expected_archived_set)
    neither_set: Set[str] = set(all_urls) - whitelist_set.union(expected_archived_set)

    rows = [
        ("Whitelisted URLs", whitelist_set),
        ("Expected archived", expected_archived_set),
        ("Both whitelisted and expected archived", both_set),
        ("Neither whitelisted nor expected archived", neither_set),
        ("TOTAL", set(all_urls)),
    ]

    file_obj.write("# Summary\n\n")
    file_obj.write("| Type | " + " | ".join(statuses) + " | Total |\n")
    file_obj.write("| --- | " + " | ".join("---" for _ in statuses) + " | --- |\n")

    for row_name, row_urls in rows:
        counts = get_status_counts_for_urls(
            urls=list(row_urls),
            all_urls_by_status=all_urls_by_status,
            statuses=statuses,
        )
        total_count = sum(counts.values())
        file_obj.write(
            f"| {row_name} | "
            + " | ".join(str(counts[status]) for status in statuses)
            + f" | {total_count} |\n"
        )

    confluence_valid_set: Set[str] = set(valid_confluence_paths)
    all_urls_set: Set[str] = set(all_urls)

    e3sm_with_confluence: Set[str] = all_urls_set.intersection(confluence_valid_set)
    e3sm_without_confluence: Set[str] = all_urls_set - confluence_valid_set

    confluence_not_valid_count: int = len(invalid_confluence_paths) + len(
        confluence_unmapped_entries
    )
    total_confluence_urls: int = len(confluence_valid_set) + confluence_not_valid_count
    total_e3sm_urls: int = len(all_urls_set)

    confluence_counts_match: bool = (
        confluence_not_valid_count + len(e3sm_with_confluence) == total_confluence_urls
    )
    e3sm_counts_match: bool = (
        len(e3sm_without_confluence) + len(e3sm_with_confluence) == total_e3sm_urls
    )

    file_obj.write("\n## Confluence Mapping Summary\n\n")
    file_obj.write("| Type | Count |\n")
    file_obj.write("| --- | --- |\n")
    file_obj.write(
        f"| Confluence paths that do not map to a valid e3sm.org path | {confluence_not_valid_count} |\n"
    )
    file_obj.write(
        f"| e3sm.org paths that do not have a Confluence path associated with them | {len(e3sm_without_confluence)} |\n"
    )
    file_obj.write(
        f"| e3sm.org paths that do have a Confluence counterpart | {len(e3sm_with_confluence)} |\n"
    )
    file_obj.write(f"| Total Confluence-derived paths | {total_confluence_urls} |\n")
    file_obj.write(f"| Total e3sm.org paths | {total_e3sm_urls} |\n")
    file_obj.write("\n")

    file_obj.write("Validation:\n\n")
    file_obj.write(
        f"- Confluence counts match: "
        f"{confluence_not_valid_count} + {len(e3sm_with_confluence)} = {total_confluence_urls} "
        f"({'yes' if confluence_counts_match else 'no'})\n"
    )
    file_obj.write(
        f"- e3sm.org counts match: "
        f"{len(e3sm_without_confluence)} + {len(e3sm_with_confluence)} = {total_e3sm_urls} "
        f"({'yes' if e3sm_counts_match else 'no'})\n\n"
    )


def write_markdown_report(
    output_path: str,
    all_urls_by_status: Dict[str, List[str]],
    valid_whitelisted_paths: List[str],
    valid_expected_archived_paths: List[str],
    valid_confluence_paths: List[str],
    whitelisted_but_not_published: List[str],
    published_but_not_whitelisted: List[str],
    should_be_archived: List[str],
    published_but_not_in_confluence: List[str],
    published_not_whitelisted_and_not_in_confluence: List[str],
    incorrectly_accessible_non_published_urls: List[str],
    invalid_whitelisted_paths: List[str],
    invalid_expected_archived_paths: List[str],
    invalid_confluence_paths: List[str],
    confluence_unmapped_entries: List[str],
) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        write_summary_table(
            f,
            all_urls_by_status=all_urls_by_status,
            valid_whitelisted_paths=valid_whitelisted_paths,
            valid_expected_archived_paths=valid_expected_archived_paths,
            valid_confluence_paths=valid_confluence_paths,
            invalid_confluence_paths=invalid_confluence_paths,
            confluence_unmapped_entries=confluence_unmapped_entries,
        )

        f.write("# Valid Paths\n\n")
        write_markdown_section(
            f,
            "Whitelisted but not published",
            whitelisted_but_not_published,
        )
        write_markdown_section(
            f,
            "Published but not whitelisted",
            published_but_not_whitelisted,
        )
        write_markdown_section(
            f,
            "Expecting to be archived, but not yet archived",
            should_be_archived,
        )
        write_markdown_section(
            f,
            "Published but no matching Confluence path found",
            published_but_not_in_confluence,
        )
        write_markdown_section(
            f,
            "Published but not whitelisted and no matching Confluence path found",
            published_not_whitelisted_and_not_in_confluence,
        )
        write_markdown_section(
            f,
            "Non-published e3sm.org pages that are still accessible without login",
            incorrectly_accessible_non_published_urls,
        )

        f.write("# Invalid Paths\n\n")
        write_markdown_section(
            f,
            "Identified in whitelist input",
            invalid_whitelisted_paths,
        )
        write_markdown_section(
            f,
            "Identified in archive input",
            invalid_expected_archived_paths,
        )
        write_markdown_section(
            f,
            "Identified in Confluence input",
            invalid_confluence_paths,
        )
        write_markdown_section(
            f,
            "Confluence pages with no mappable e3sm.org URL",
            confluence_unmapped_entries,
        )


def write_action_items_confluence_section(
    f: TextIO, records: List[SensitiveTermRecord]
) -> None:
    f.write(
        "## Confluence pages with sensitive terms mapped to published e3sm.org pages\n\n"
    )

    if not records:
        f.write("_None._\n\n")
        return

    grouped = group_records_by_classification_and_year(records)

    for classification in sorted(grouped.keys(), key=classification_sort_key):
        f.write(f"### {classification}\n\n")

        for year_label in sorted(grouped[classification].keys(), key=year_sort_key):
            f.write(f"#### {year_label}\n\n")
            for idx, record in enumerate(grouped[classification][year_label], start=1):
                f.write(f"{idx}. {format_confluence_record(record)}\n")
            f.write("\n")


def write_action_items_report(
    output_path: str,
    should_be_archived: List[str],
    published_not_whitelisted_and_not_in_confluence: List[str],
    confluence_published_sensitive_records: List[SensitiveTermRecord],
) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Action Items Report\n\n")

        f.write("## Summary\n\n")
        f.write("| Action Area | Count |\n")
        f.write("| --- | ---: |\n")
        f.write(
            f"| Expecting to be archived, but not yet archived | {len(should_be_archived)} |\n"
        )
        f.write(
            f"| Published but not whitelisted and no matching Confluence path found | {len(published_not_whitelisted_and_not_in_confluence)} |\n"
        )
        f.write(
            f"| Confluence pages with sensitive terms mapped to published e3sm.org pages | {len(confluence_published_sensitive_records)} |\n"
        )
        f.write("\n")

        write_markdown_section(
            f,
            "Expecting to be archived, but not yet archived",
            should_be_archived,
        )

        write_markdown_section(
            f,
            "Published but not whitelisted and no matching Confluence path found",
            published_not_whitelisted_and_not_in_confluence,
        )

        write_action_items_confluence_section(f, confluence_published_sensitive_records)


def parse_dict(dict_str: str) -> Optional[Dict[str, int]]:
    try:
        data = ast.literal_eval(dict_str)
    except (SyntaxError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    try:
        total = sum(data.values())
    except TypeError:
        return None

    if not isinstance(total, (int, float)):
        return None

    return data


def extract_year_and_remainder(line: str) -> Tuple[Optional[int], str]:
    match = FROM_PREFIX_RE.match(line)
    if not match:
        return None, line

    year = int(match.group(1))
    remainder = match.group(2).strip()
    return year, remainder


def build_url_to_status(all_urls_by_status: Dict[str, List[str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for status, urls in all_urls_by_status.items():
        for url in urls:
            result[url] = status
    return result


def read_nonempty_lines(file_path: str) -> List[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def classify_e3sm_url(
    e3sm_url: Optional[str],
    url_to_status: Dict[str, str],
    expected_archived_urls: Set[str],
    known_ok_urls: Set[str],
    keep_unchanged_urls: Set[str],
) -> Tuple[str, Optional[str]]:
    if not e3sm_url:
        return CLASS_NO_MAPPED_E3SM_URL, None

    if e3sm_url in known_ok_urls:
        return CLASS_KNOWN_OK, url_to_status.get(e3sm_url)

    if e3sm_url in keep_unchanged_urls:
        return CLASS_KEEP_UNCHANGED, url_to_status.get(e3sm_url)

    wordpress_status = url_to_status.get(e3sm_url)

    if wordpress_status is None:
        return CLASS_PREDICTED_URL_NOT_IN_EXPORT, None

    if wordpress_status == "archive":
        return CLASS_ARCHIVED, wordpress_status

    if e3sm_url in expected_archived_urls:
        return CLASS_SHOULD_BE_ARCHIVED, wordpress_status

    if wordpress_status != "publish":
        return CLASS_NOT_PUBLISHED, wordpress_status

    return CLASS_PUBLISHED, wordpress_status


def parse_wordpress_sensitive_terms_lines(lines: List[str]) -> List[Tuple[int, str]]:
    parsed: List[Tuple[int, str]] = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue

        dict_start = line.find("{")
        if dict_start == -1:
            print(f"Skipping malformed WordPress sensitive-terms line: {line}")
            continue

        dict_str = line[dict_start:].strip()
        dict_data = parse_dict(dict_str)
        if dict_data is None:
            print(f"Skipping malformed dictionary in WordPress line: {line}")
            continue

        total = int(sum(dict_data.values()))
        parsed.append((total, line))

    parsed.sort(key=lambda x: x[0], reverse=True)
    return parsed


def extract_wordpress_url(line: str) -> Optional[str]:
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    prefix = line[:dict_start].rstrip()
    if prefix.endswith(":"):
        prefix = prefix[:-1].rstrip()

    return prefix


def parse_wordpress_record(
    line: str,
    url_to_status: Dict[str, str],
    expected_archived_urls: Set[str],
    known_ok_urls: Set[str],
    keep_unchanged_urls: Set[str],
) -> Optional[SensitiveTermRecord]:
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    url = extract_wordpress_url(line)
    if not url:
        return None

    dict_str = line[dict_start:].strip()
    term_counts = parse_dict(dict_str)
    if term_counts is None:
        return None

    total_terms = int(sum(term_counts.values()))
    classification, wordpress_status = classify_e3sm_url(
        e3sm_url=url,
        url_to_status=url_to_status,
        expected_archived_urls=expected_archived_urls,
        known_ok_urls=known_ok_urls,
        keep_unchanged_urls=keep_unchanged_urls,
    )

    return SensitiveTermRecord(
        source="e3sm.org",
        raw_line=line,
        year_label="N/A",
        year_int=None,
        total_terms=total_terms,
        term_counts=term_counts,
        source_url=url,
        title=None,
        confluence_url=None,
        e3sm_url=url,
        classification=classification,
        wordpress_status=wordpress_status,
    )


def extract_confluence_components(
    line: str,
) -> Optional[Tuple[Optional[int], str, str, Dict[str, int]]]:
    year, remainder = extract_year_and_remainder(line)

    dict_start = remainder.find("{")
    if dict_start == -1:
        print(f"Skipping malformed Confluence line: {line}")
        return None

    dict_str = remainder[dict_start:].strip()
    term_counts = parse_dict(dict_str)
    if term_counts is None:
        print(f"Skipping malformed dictionary in Confluence line: {line}")
        return None

    prefix = remainder[:dict_start].rstrip()
    if prefix.endswith("--"):
        prefix = prefix[:-2].rstrip()

    first_colon = prefix.find(":")
    if first_colon == -1:
        print(f"Skipping malformed Confluence line: {line}")
        return None

    page_id = prefix[:first_colon].strip()
    title = prefix[first_colon + 1 :].strip()

    if not page_id.isdigit():
        print(f"Skipping Confluence line with non-numeric page id: {line}")
        return None

    return year, page_id, title, term_counts


def parse_confluence_record(
    line: str,
    url_to_status: Dict[str, str],
    expected_archived_urls: Set[str],
    known_ok_urls: Set[str],
    keep_unchanged_urls: Set[str],
) -> Optional[SensitiveTermRecord]:
    components = extract_confluence_components(line)
    if components is None:
        return None

    year, page_id, title, term_counts = components
    confluence_url = build_confluence_url(page_id)

    try:
        e3sm_url = map_confluence_to_e3sm(confluence_url, page_title=title)
    except Exception as exc:
        print(
            f"Could not map Confluence URL to e3sm.org URL for {confluence_url}: {exc}"
        )
        e3sm_url = None

    classification, wordpress_status = classify_e3sm_url(
        e3sm_url=e3sm_url,
        url_to_status=url_to_status,
        expected_archived_urls=expected_archived_urls,
        known_ok_urls=known_ok_urls,
        keep_unchanged_urls=keep_unchanged_urls,
    )

    total_terms = int(sum(term_counts.values()))
    year_label = str(year) if year is not None else "Unknown year"

    return SensitiveTermRecord(
        source="confluence",
        raw_line=line,
        year_label=year_label,
        year_int=year,
        total_terms=total_terms,
        term_counts=term_counts,
        source_url=confluence_url,
        title=title,
        confluence_url=confluence_url,
        e3sm_url=e3sm_url,
        classification=classification,
        wordpress_status=wordpress_status,
    )


def classification_sort_key(classification: str) -> Tuple[int, str]:
    order = {
        CLASS_PUBLISHED: 0,
        CLASS_SHOULD_BE_ARCHIVED: 1,
        CLASS_ARCHIVED: 2,
        CLASS_NOT_PUBLISHED: 3,
        CLASS_KNOWN_OK: 4,
        CLASS_KEEP_UNCHANGED: 5,
        CLASS_NO_MAPPED_E3SM_URL: 6,
        CLASS_PREDICTED_URL_NOT_IN_EXPORT: 7,
    }
    return (order.get(classification, 999), classification)


def year_sort_key(year_str: str) -> Tuple[int, int]:
    if year_str == "Unknown year":
        return (1, 0)
    if year_str == "N/A":
        return (2, 0)
    try:
        return (0, -int(year_str))
    except ValueError:
        return (3, 0)


def build_classification_summary(
    records: List[SensitiveTermRecord],
) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}

    for record in records:
        classification = record.classification
        if classification not in summary:
            summary[classification] = {
                "total": 0,
                "1": 0,
                "2": 0,
                "3": 0,
                "4": 0,
                "5+": 0,
            }

        summary[classification]["total"] += 1
        if record.total_terms == 1:
            summary[classification]["1"] += 1
        elif record.total_terms == 2:
            summary[classification]["2"] += 1
        elif record.total_terms == 3:
            summary[classification]["3"] += 1
        elif record.total_terms == 4:
            summary[classification]["4"] += 1
        elif record.total_terms >= 5:
            summary[classification]["5+"] += 1

    return summary


def group_records_by_classification_and_year(
    records: List[SensitiveTermRecord],
) -> Dict[str, Dict[str, List[SensitiveTermRecord]]]:
    grouped: DefaultDict[str, DefaultDict[str, List[SensitiveTermRecord]]] = (
        defaultdict(lambda: defaultdict(list))
    )

    for record in records:
        grouped[record.classification][record.year_label].append(record)

    for classification in grouped:
        for year_label in grouped[classification]:
            grouped[classification][year_label].sort(
                key=lambda r: (r.total_terms, r.e3sm_url or "", r.title or ""),
                reverse=True,
            )

    return {k: dict(v) for k, v in grouped.items()}


def write_sensitive_terms_summary_table(
    f: TextIO, records: List[SensitiveTermRecord]
) -> None:
    summary = build_classification_summary(records)

    f.write("### Summary Table\n\n")
    f.write("| Classification | Total | 1 | 2 | 3 | 4 | 5+ |\n")
    f.write("| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n")

    for classification in sorted(summary.keys(), key=classification_sort_key):
        counts = summary[classification]
        f.write(
            f"| {classification} | {counts['total']} | {counts['1']} | {counts['2']} | "
            f"{counts['3']} | {counts['4']} | {counts['5+']} |\n"
        )

    f.write("\n")


def format_term_counts(term_counts: Dict[str, int]) -> str:
    return str(term_counts)


def format_e3sm_record(record: SensitiveTermRecord) -> str:
    url = record.e3sm_url or record.source_url or "UNKNOWN"
    md = f"[{url}]({url})"
    if record.wordpress_status:
        md += f" (status: {record.wordpress_status})"
    md += f" -- {format_term_counts(record.term_counts)}"
    return md


def format_confluence_record(record: SensitiveTermRecord) -> str:
    title = record.title or "Untitled"
    confluence_url = record.confluence_url or record.source_url or ""
    md = f"{title}: [confluence]({confluence_url})"

    if record.e3sm_url:
        md += f" [e3sm.org]({record.e3sm_url})"

        try:
            e3sm_url_status = get_e3sm_url_status(record.e3sm_url)
        except Exception as exc:
            print(f"Could not get e3sm.org URL status for {record.e3sm_url}: {exc}")
            e3sm_url_status = None

        if e3sm_url_status:
            md += f" (Note: {e3sm_url_status})"

        if record.wordpress_status:
            md += f" (WordPress status: {record.wordpress_status})"

    md += f" -- {format_term_counts(record.term_counts)}"
    return md


def write_sensitive_terms_section(
    f: TextIO,
    section_title: str,
    description: str,
    records: List[SensitiveTermRecord],
    formatter: Callable[[SensitiveTermRecord], str],
) -> None:
    f.write(f"## {section_title}\n\n")
    f.write(f"{description}\n\n")

    write_sensitive_terms_summary_table(f, records)

    grouped = group_records_by_classification_and_year(records)

    for classification in sorted(grouped.keys(), key=classification_sort_key):
        f.write(f"### {classification}\n\n")

        for year_label in sorted(grouped[classification].keys(), key=year_sort_key):
            f.write(f"#### {year_label}\n\n")
            for idx, record in enumerate(grouped[classification][year_label], start=1):
                f.write(f"{idx}. {formatter(record)}\n")
            f.write("\n")


def write_sensitive_terms_report(
    output_path: str,
    e3sm_records: List[SensitiveTermRecord],
    confluence_records: List[SensitiveTermRecord],
) -> None:
    description_e3sm_org = (
        "These are the currently reviewed e3sm.org pages that include sensitive terms. "
        "Classification is derived from WordPress status, expected archived inputs, and the manual exception lists for known-ok and keep-unchanged paths."
    )
    description_confluence = (
        "These are the Confluence pages that include sensitive terms. The confluence links are what the website reviewer scanned. "
        "The e3sm.org links are predicted from Confluence mapping and then classified against the WordPress export."
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Sensitive Terms Report\n\n")

        write_sensitive_terms_section(
            f,
            "e3sm.org",
            description_e3sm_org,
            e3sm_records,
            format_e3sm_record,
        )
        write_sensitive_terms_section(
            f,
            "Confluence",
            description_confluence,
            confluence_records,
            format_confluence_record,
        )


def main():
    pages_by_status: Dict[str, List[str]] = get_wordpress_urls_by_status(
        INPUT_XML_PAGES, "page"
    )
    posts_by_status: Dict[str, List[str]] = get_wordpress_urls_by_status(
        INPUT_XML_POSTS, "post"
    )
    num_pages: int = get_total_count(pages_by_status)
    num_posts: int = get_total_count(posts_by_status)
    print(f"Found {num_pages} pages, {num_posts} posts")
    print(
        f"Pages have status in {pages_by_status.keys()}; posts have status in {posts_by_status.keys()}"
    )

    all_urls_by_status: Dict[str, List[str]] = get_combined_urls_by_status(
        pages_by_status, posts_by_status
    )
    print_status_counts(all_urls_by_status)

    non_published_urls: List[str] = get_all_non_published_urls(all_urls_by_status)
    print(f"Total non-published URLs: {len(non_published_urls)}")

    list_whitelisted_paths: List[str] = read_nonempty_lines(INPUT_WHITELIST)
    list_expected_archived_paths: List[str] = read_nonempty_lines(
        INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS
    )
    list_known_ok_paths: List[str] = read_nonempty_lines(INPUT_KNOWN_OK_E3SM_ORG_PATHS)
    list_keep_unchanged_paths: List[str] = read_nonempty_lines(
        INPUT_KEEP_UNCHANGED_E3SM_ORG_PATHS
    )

    all_urls: List[str] = get_all_urls(all_urls_by_status)
    url_to_status: Dict[str, str] = build_url_to_status(all_urls_by_status)

    invalid_whitelisted_paths: List[str] = get_invalid_patterns(
        list_whitelisted_paths, all_urls
    )
    valid_whitelisted_paths: List[str] = [
        path for path in list_whitelisted_paths if path not in invalid_whitelisted_paths
    ]

    invalid_expected_archived_paths: List[str] = get_invalid_patterns(
        list_expected_archived_paths, all_urls
    )
    valid_expected_archived_paths: List[str] = [
        path
        for path in list_expected_archived_paths
        if path not in invalid_expected_archived_paths
    ]

    confluence_predicted_urls, confluence_unmapped_entries = (
        get_confluence_predicted_e3sm_urls(INPUT_CONFLUENCE_HIERARCHY)
    )
    invalid_confluence_paths: List[str] = get_invalid_patterns(
        confluence_predicted_urls, all_urls
    )
    valid_confluence_paths: List[str] = [
        path
        for path in confluence_predicted_urls
        if path not in invalid_confluence_paths
    ]

    whitelisted_urls_expanded: List[str] = expand_patterns_to_urls(
        valid_whitelisted_paths, all_urls
    )
    print(
        f"Of {len(list_whitelisted_paths)} whitelisted paths, {len(valid_whitelisted_paths)} are valid URLs/patterns. Expanding patterns, it's {len(whitelisted_urls_expanded)} valid URLs."
    )
    print(
        f"Of {len(list_expected_archived_paths)} expected archived paths, {len(valid_expected_archived_paths)} are valid URLs/patterns"
    )
    print(
        f"Of {len(confluence_predicted_urls)} predicted Confluence e3sm.org paths, "
        f"{len(valid_confluence_paths)} are valid URLs"
    )
    print(
        f"Confluence pages with no predicted e3sm.org URL: {len(confluence_unmapped_entries)}"
    )

    published_urls: List[str] = all_urls_by_status.get("publish", [])
    archived_urls: List[str] = all_urls_by_status.get("archive", [])

    expected_archived_urls_expanded: List[str] = expand_patterns_to_urls(
        valid_expected_archived_paths, all_urls
    )

    whitelisted_but_not_published: List[str] = get_list_difference(
        whitelisted_urls_expanded, published_urls
    )
    published_but_not_whitelisted: List[str] = get_list_difference(
        published_urls, whitelisted_urls_expanded
    )
    should_be_archived: List[str] = get_list_difference(
        expected_archived_urls_expanded, archived_urls
    )
    published_but_not_in_confluence: List[str] = get_list_difference(
        published_urls, valid_confluence_paths
    )
    published_not_whitelisted_and_not_in_confluence: List[str] = get_list_difference(
        published_but_not_in_confluence, whitelisted_urls_expanded
    )

    print(f"Whitelisted, but not published: {len(whitelisted_but_not_published)}")
    print(f"Published, but not whitelisted: {len(published_but_not_whitelisted)}")
    print(f"Not archived, but should be archived: {len(should_be_archived)}")
    print(
        f"Published, but no matching Confluence path found: {len(published_but_not_in_confluence)}"
    )
    print(
        "Published, but not whitelisted and no matching Confluence path found: "
        f"{len(published_not_whitelisted_and_not_in_confluence)}"
    )
    print(f"Invalid whitelist paths: {len(invalid_whitelisted_paths)}")
    print(f"Invalid archive-input paths: {len(invalid_expected_archived_paths)}")
    print(
        f"Invalid Confluence-predicted e3sm.org paths: {len(invalid_confluence_paths)}"
    )

    incorrectly_accessible_non_published_urls: List[str] = []

    e3sm_records: List[SensitiveTermRecord] = []
    confluence_records: List[SensitiveTermRecord] = []

    if RUN_CHECKS:
        print(
            f"Checking {len(whitelisted_urls_expanded)} whitelisted e3sm.org pages for search phrases"
        )
        with open(INPUT_SEARCH_PHRASES, "r", encoding="utf-8") as f:
            terms: List[str] = [line.rstrip("\n").lower() for line in f]
            list_search_phrases: List[str] = sorted(terms)

        links = LinkedURLs(
            whitelisted_urls_expanded,
            scan_links_for_sensitive_terms=True,
            list_sensitive_terms=list_search_phrases,
        )
        relevant_links: Dict[str, Dict[str, int]] = links.links_with_sensitive_terms

        expected_archived_urls_set: Set[str] = set(expected_archived_urls_expanded)
        known_ok_urls_set: Set[str] = set(list_known_ok_paths)
        keep_unchanged_urls_set: Set[str] = set(list_keep_unchanged_paths)

        wordpress_lines_input: List[str] = [
            f"{link}: {relevant_links[link]}" for link in relevant_links
        ]
        wordpress_lines = parse_wordpress_sensitive_terms_lines(wordpress_lines_input)
        for _, line in wordpress_lines:
            record = parse_wordpress_record(
                line=line,
                url_to_status=url_to_status,
                expected_archived_urls=expected_archived_urls_set,
                known_ok_urls=known_ok_urls_set,
                keep_unchanged_urls=keep_unchanged_urls_set,
            )
            if record:
                e3sm_records.append(record)

        if INPUT_CONFLUENCE_SENSITIVE_TERMS:
            try:
                with open(INPUT_CONFLUENCE_SENSITIVE_TERMS, "r", encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.rstrip("\n")
                        if not line.strip():
                            continue

                        record = parse_confluence_record(
                            line=line,
                            url_to_status=url_to_status,
                            expected_archived_urls=expected_archived_urls_set,
                            known_ok_urls=known_ok_urls_set,
                            keep_unchanged_urls=keep_unchanged_urls_set,
                        )
                        if record:
                            confluence_records.append(record)
            except FileNotFoundError:
                print(
                    f"Confluence sensitive terms input not found: {INPUT_CONFLUENCE_SENSITIVE_TERMS}"
                )

        print(
            f"Checking {len(non_published_urls)} non-published e3sm.org pages are inaccessible"
        )
        for e3sm_url in non_published_urls:
            e3sm_url_status = get_e3sm_url_status(e3sm_url)
            if e3sm_url_status == "link works not logged-in":
                incorrectly_accessible_non_published_urls.append(e3sm_url)

    write_markdown_report(
        output_path=OUTPUT_MARKDOWN_REPORT,
        all_urls_by_status=all_urls_by_status,
        valid_whitelisted_paths=valid_whitelisted_paths,
        valid_expected_archived_paths=valid_expected_archived_paths,
        valid_confluence_paths=valid_confluence_paths,
        whitelisted_but_not_published=whitelisted_but_not_published,
        published_but_not_whitelisted=published_but_not_whitelisted,
        should_be_archived=should_be_archived,
        published_but_not_in_confluence=published_but_not_in_confluence,
        published_not_whitelisted_and_not_in_confluence=published_not_whitelisted_and_not_in_confluence,
        incorrectly_accessible_non_published_urls=incorrectly_accessible_non_published_urls,
        invalid_whitelisted_paths=invalid_whitelisted_paths,
        invalid_expected_archived_paths=invalid_expected_archived_paths,
        invalid_confluence_paths=invalid_confluence_paths,
        confluence_unmapped_entries=confluence_unmapped_entries,
    )

    write_sensitive_terms_report(
        output_path=OUTPUT_SENSITIVE_TERMS_REPORT,
        e3sm_records=e3sm_records,
        confluence_records=confluence_records,
    )

    confluence_published_sensitive_records: List[SensitiveTermRecord] = [
        record
        for record in confluence_records
        if record.classification == CLASS_PUBLISHED
    ]

    write_action_items_report(
        output_path=OUTPUT_ACTION_ITEMS_REPORT,
        should_be_archived=should_be_archived,
        published_not_whitelisted_and_not_in_confluence=published_not_whitelisted_and_not_in_confluence,
        confluence_published_sensitive_records=confluence_published_sensitive_records,
    )


if __name__ == "__main__":
    main()
