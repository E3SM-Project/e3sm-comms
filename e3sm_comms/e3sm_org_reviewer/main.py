from typing import Dict, List, Set

from e3sm_comms.e3sm_org_reviewer.classifiers import CLASS_PUBLISHED
from e3sm_comms.e3sm_org_reviewer.confluence import get_confluence_predicted_e3sm_urls
from e3sm_comms.e3sm_org_reviewer.parsers import (
    parse_confluence_record,
    parse_wordpress_record,
    parse_wordpress_sensitive_terms_lines,
)
from e3sm_comms.e3sm_org_reviewer.readers import print_status_counts
from e3sm_comms.e3sm_org_reviewer.record import SensitiveTermRecord
from e3sm_comms.e3sm_org_reviewer.reporters import (
    write_action_items_report,
    write_markdown_report,
    write_sensitive_terms_report,
)
from e3sm_comms.e3sm_org_reviewer.utils import (
    build_url_to_status,
    get_all_non_published_urls,
    get_all_urls,
    get_combined_urls_by_status,
    get_list_difference,
    get_total_count,
)
from e3sm_comms.page_reviewer.utils_base import LinkedURLs, get_e3sm_url_status
from e3sm_comms.utils import (
    IO_DIR,
    expand_patterns_to_urls,
    get_invalid_patterns,
    get_wordpress_urls_by_status,
    read_lines,
)

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

    list_whitelisted_paths: List[str] = read_lines(INPUT_WHITELIST)
    list_expected_archived_paths: List[str] = read_lines(
        INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS
    )
    list_known_ok_paths: List[str] = read_lines(INPUT_KNOWN_OK_E3SM_ORG_PATHS)
    list_keep_unchanged_paths: List[str] = read_lines(
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
