import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List, Set, TextIO

from e3sm_comms.page_reviewer.utils_base import LinkedURLs, get_e3sm_url_status
from e3sm_comms.utils import IO_DIR

INPUT_XML_PAGES: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_pages.xml"
INPUT_XML_POSTS: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_posts.xml"
INPUT_WHITELIST: str = f"{IO_DIR}/input/e3sm_org_reviewer/whitelisted_web_pages.txt"
INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/input/shared/archived_web_pages.txt"
)
INPUT_SEARCH_PHRASES: str = f"{IO_DIR}/input/shared/sensitive_terms.txt"

OUTPUT_MARKDOWN_REPORT: str = f"{IO_DIR}/output/e3sm_org_reviewer/path_report.md"
OUTPUT_FOUND_PHRASES: str = f"{IO_DIR}/output/e3sm_org_reviewer/found_phrases.txt"
OUTPUT_INCORRECTLY_ACCESSIBLE_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/incorrectly_accessible_web_pages.txt"
)

RUN_CHECKS: bool = False  # Set to False for faster debugging


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

    print(
        f"Of {len(list_whitelisted_paths)} whitelisted paths, {len(valid_whitelisted_paths)} are valid URLs/patterns"
    )
    print(
        f"Of {len(list_expected_archived_paths)} expected archived paths, {len(valid_expected_archived_paths)} are valid URLs/patterns"
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

    print(f"Whitelisted, but not published: {len(whitelisted_but_not_published)}")
    print(f"Published, but not whitelisted: {len(published_but_not_whitelisted)}")
    print(f"Not archived, but should be archived: {len(should_be_archived)}")
    print(f"Invalid whitelist paths: {len(invalid_whitelisted_paths)}")
    print(f"Invalid archive-input paths: {len(invalid_expected_archived_paths)}")

    write_markdown_report(
        output_path=OUTPUT_MARKDOWN_REPORT,
        all_urls_by_status=all_urls_by_status,
        valid_whitelisted_paths=valid_whitelisted_paths,
        valid_expected_archived_paths=valid_expected_archived_paths,
        whitelisted_but_not_published=whitelisted_but_not_published,
        published_but_not_whitelisted=published_but_not_whitelisted,
        should_be_archived=should_be_archived,
        invalid_whitelisted_paths=invalid_whitelisted_paths,
        invalid_expected_archived_paths=invalid_expected_archived_paths,
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
    whitelisted_but_not_published: List[str],
    published_but_not_whitelisted: List[str],
    should_be_archived: List[str],
    invalid_whitelisted_paths: List[str],
    invalid_expected_archived_paths: List[str],
) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        write_summary_table(
            f,
            all_urls_by_status=all_urls_by_status,
            valid_whitelisted_paths=valid_whitelisted_paths,
            valid_expected_archived_paths=valid_expected_archived_paths,
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


def write_summary_table(
    file_obj: TextIO,
    all_urls_by_status: Dict[str, List[str]],
    valid_whitelisted_paths: List[str],
    valid_expected_archived_paths: List[str],
) -> None:
    statuses: List[str] = sorted(all_urls_by_status.keys())
    all_urls: List[str] = get_all_urls(all_urls_by_status)

    whitelist_set: Set[str] = set(
        expand_patterns_to_urls(valid_whitelisted_paths, all_urls)
    )
    expected_archived_set: Set[str] = set(
        expand_patterns_to_urls(valid_expected_archived_paths, all_urls)
    )
    accounted_for_set = whitelist_set.union(expected_archived_set)

    all_urls_set = set(all_urls)
    remaining_set = all_urls_set - accounted_for_set

    rows = [
        ("Whitelisted URLs", whitelist_set),
        ("Expected archived", expected_archived_set),
        ("All remaining", remaining_set),
        ("TOTAL", all_urls_set),
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
