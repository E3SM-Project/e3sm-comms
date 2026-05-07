import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List, Set, TextIO, Tuple

from e3sm_comms.page_reviewer.utils_base import (
    LinkedURLs,
    get_e3sm_url_status,
    map_confluence_to_e3sm,
)
from e3sm_comms.utils import IO_DIR

INPUT_XML_PAGES: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_pages.xml"
INPUT_XML_POSTS: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_posts.xml"
INPUT_WHITELIST: str = f"{IO_DIR}/input/e3sm_org_reviewer/whitelisted_web_pages.txt"
INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/input/shared/archived_web_pages.txt"
)
INPUT_SEARCH_PHRASES: str = f"{IO_DIR}/input/shared/sensitive_terms.txt"
INPUT_CONFLUENCE_HIERARCHY: str = (
    f"{IO_DIR}/input/e3sm_org_reviewer/hierarchical_outline.txt"
)

OUTPUT_MARKDOWN_REPORT: str = f"{IO_DIR}/output/e3sm_org_reviewer/path_report.md"
OUTPUT_FOUND_PHRASES: str = f"{IO_DIR}/output/e3sm_org_reviewer/found_phrases.txt"
OUTPUT_INCORRECTLY_ACCESSIBLE_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/incorrectly_accessible_web_pages.txt"
)

RUN_CHECKS: bool = False  # Set to False for faster debugging

CONFLUENCE_SPACE = "EPWCD"
CONFLUENCE_BASE = "https://e3sm.atlassian.net/wiki"


def build_confluence_url(page_id: str, space_key: str = CONFLUENCE_SPACE) -> str:
    return f"{CONFLUENCE_BASE}/spaces/{space_key}/pages/{page_id}"


def parse_confluence_hierarchy_file(input_file: str) -> List[Tuple[str, str]]:
    """
    Parses a hierarchy file whose indentation only indicates nesting.

    Expected line format:
        <optional spaces><page_id>: <title>

    Returns:
        List of (page_id, title)
    """
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
    """
    Reads a Confluence hierarchy file and returns:
    - valid_predicted_urls: predicted e3sm.org URLs successfully mapped from Confluence
    - unmapped_confluence_pages: human-readable Confluence entries that could not be mapped
    """
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


def main():
    # Review XML exports from WordPress
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

    # Compare with expectations
    with open(INPUT_WHITELIST, "r", encoding="utf-8") as f:
        list_whitelisted_paths: List[str] = [line.strip() for line in f if line.strip()]
    with open(INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS, "r", encoding="utf-8") as f:
        list_expected_archived_paths: List[str] = [
            line.strip() for line in f if line.strip()
        ]

    all_urls: List[str] = get_all_urls(all_urls_by_status)

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

    print(
        f"Of {len(list_whitelisted_paths)} whitelisted paths, {len(valid_whitelisted_paths)} are valid URLs/patterns"
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

    whitelisted_urls_expanded: List[str] = expand_patterns_to_urls(
        valid_whitelisted_paths, all_urls
    )
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

    print(f"Whitelisted, but not published: {len(whitelisted_but_not_published)}")
    print(f"Published, but not whitelisted: {len(published_but_not_whitelisted)}")
    print(f"Not archived, but should be archived: {len(should_be_archived)}")
    print(
        f"Published, but no matching Confluence path found: {len(published_but_not_in_confluence)}"
    )
    print(f"Invalid whitelist paths: {len(invalid_whitelisted_paths)}")
    print(f"Invalid archive-input paths: {len(invalid_expected_archived_paths)}")
    print(
        f"Invalid Confluence-predicted e3sm.org paths: {len(invalid_confluence_paths)}"
    )

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
        invalid_whitelisted_paths=invalid_whitelisted_paths,
        invalid_expected_archived_paths=invalid_expected_archived_paths,
        invalid_confluence_paths=invalid_confluence_paths,
        confluence_unmapped_entries=confluence_unmapped_entries,
    )

    # Run checks
    if RUN_CHECKS:
        print(
            f"Checking {len(list_whitelisted_paths)} whitelisted e3sm.org pages for search phrases"
        )
        expanded_whitelist_for_checks: List[str] = expand_patterns_to_urls(
            list_whitelisted_paths, all_urls
        )
        with open(INPUT_SEARCH_PHRASES, "r", encoding="utf-8") as f:
            terms: List[str] = [line.rstrip("\n").lower() for line in f]
            list_search_phrases: List[str] = sorted(terms)

        links = LinkedURLs(
            expanded_whitelist_for_checks,
            scan_links_for_sensitive_terms=True,
            list_sensitive_terms=list_search_phrases,
        )
        relevant_links: Dict[str, Dict[str, int]] = links.links_with_sensitive_terms
        with open(OUTPUT_FOUND_PHRASES, "w", encoding="utf-8") as f:
            for link in relevant_links:
                f.write(f"{link}: {relevant_links[link]}\n")

        print(
            f"Checking {len(non_published_urls)} non-published e3sm.org pages are inaccessible"
        )
        with open(
            OUTPUT_INCORRECTLY_ACCESSIBLE_E3SM_ORG_PATHS, "w", encoding="utf-8"
        ) as f:
            for e3sm_url in non_published_urls:
                e3sm_url_status = get_e3sm_url_status(e3sm_url)
                if e3sm_url_status == "link works not logged-in":
                    f.write(f"{e3sm_url}\n")


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
    file_obj.write("\n")


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
    return {status: sorted(urls) for status, urls in merged.items()}


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
