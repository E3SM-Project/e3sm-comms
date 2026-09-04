from __future__ import annotations

import argparse

from e3sm_comms.exported_xml_reviewer.builders import (
    build_accessible_non_published_issues,
    build_external_content_link_summaries,
    build_navigation_issue_records,
    build_published_content_link_summaries,
    build_records,
)
from e3sm_comms.exported_xml_reviewer.link_analysis import (
    build_invalid_internal_link_groups,
    build_non_published_internal_link_groups,
)
from e3sm_comms.exported_xml_reviewer.readers import read_inaccessible_prefixes
from e3sm_comms.exported_xml_reviewer.reporters import (
    write_external_links_report,
    write_hierarchical_outline,
    write_invalid_internal_links_report,
    write_navigation_issues_report,
    write_non_published_accessibility_report,
    write_published_pages_link_report,
    write_terms_report,
)
from e3sm_comms.utils import IO_DIR

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Required inputs:
INPUT_XML_PAGES: str = f"{IO_DIR}/input/exported_xml_reviewer/wordpress_pages.xml"
INPUT_XML_POSTS: str = f"{IO_DIR}/input/exported_xml_reviewer/wordpress_posts.xml"
# These 3 inputs are only used for wordpress_sensitive_terms_report.md:
INPUT_SEARCH_PHRASES: str = f"{IO_DIR}/input/shared/sensitive_terms.txt"
INPUT_REQUESTED_LINKS: str = f"{IO_DIR}/input/exported_xml_reviewer/requested_links.csv"
INPUT_KNOWN_OK_LINKS: str = f"{IO_DIR}/input/exported_xml_reviewer/known_ok_links.txt"
INPUT_INACCESSIBLE_PREFIXES: str = (
    f"{IO_DIR}/input/exported_xml_reviewer/inaccessible_prefixes.txt"
)

# Optional inputs:
DEFAULT_CONFLUENCE_HIERARCHY: str = (
    f"{IO_DIR}/input/exported_xml_reviewer/hierarchical_outline.txt"
)
DEFAULT_WHITELIST: str = (
    f"{IO_DIR}/input/exported_xml_reviewer/whitelisted_web_pages.txt"
)
DEFAULT_EXPECTED_ARCHIVED: str = (
    f"{IO_DIR}/input/exported_xml_reviewer/archived_web_pages.txt"
)
DEFAULT_KEEP_UNCHANGED: str = (
    f"{IO_DIR}/input/exported_xml_reviewer/keep_unchanged_web_pages.txt"
)

# Outputs:
OUTPUT_TERMS_REPORT: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_sensitive_terms_report.md"
)
OUTPUT_HIERARCHICAL_OUTLINE: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_hierarchical_outline.txt"
)
OUTPUT_NAVIGATION_ISSUES_REPORT: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_navigation_issues_report.md"
)
OUTPUT_INVALID_INTERNAL_LINKS_REPORT: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_invalid_internal_links_report.md"
)
OUTPUT_PUBLISHED_PAGES_LINK_REPORT: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_published_pages_link_report.md"
)
OUTPUT_EXTERNAL_LINKS_REPORT: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_invalid_external_links_report.md"
)
OUTPUT_NON_PUBLISHED_ACCESSIBILITY_REPORT: str = (
    f"{IO_DIR}/output/exported_xml_reviewer/wordpress_non_published_accessibility_report.md"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review exported WordPress XML files.")
    parser.add_argument(
        "--use-confluence",
        action="store_true",
        help="Use the Confluence hierarchy file for hierarchical outline generation.",
    )
    parser.add_argument(
        "--use-whitelist",
        action="store_true",
        help="Use the whitelisted web pages file to filter results.",
    )
    parser.add_argument(
        "--use-expected-archived",
        action="store_true",
        help=(
            "Flag pages/posts that are expected to be archived (per the shared "
            "archived_web_pages.txt list) but are not yet archived in WordPress."
        ),
    )
    parser.add_argument(
        "--use-keep-unchanged",
        action="store_true",
        help="Annotate pages/posts that are on the keep-unchanged exception list.",
    )
    parser.add_argument(
        "--check-non-published-access",
        action="store_true",
        help=(
            "Make a live, logged-out HTTP request to every non-published "
            "page/post and flag any that are actually reachable. Makes one "
            "network request per non-published URL, so this is slow and "
            "off by default."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_confluence_hierarchy = (
        DEFAULT_CONFLUENCE_HIERARCHY if args.use_confluence else ""
    )
    input_whitelist = DEFAULT_WHITELIST if args.use_whitelist else ""
    input_expected_archived = (
        DEFAULT_EXPECTED_ARCHIVED if args.use_expected_archived else ""
    )
    input_keep_unchanged = DEFAULT_KEEP_UNCHANGED if args.use_keep_unchanged else ""

    inaccessible_prefixes = read_inaccessible_prefixes(INPUT_INACCESSIBLE_PREFIXES)

    (
        records,
        status_totals,
        requested_link_records,
        raw_items,
        should_be_archived,
        published_not_in_confluence,
    ) = build_records(
        xml_pages=INPUT_XML_PAGES,
        xml_posts=INPUT_XML_POSTS,
        confluence_hierarchy=input_confluence_hierarchy,
        sensitive_terms_file=INPUT_SEARCH_PHRASES,
        whitelist_file=input_whitelist,
        requested_links_file=INPUT_REQUESTED_LINKS,
        known_ok_links_file=INPUT_KNOWN_OK_LINKS,
        expected_archived_file=input_expected_archived,
        keep_unchanged_links_file=input_keep_unchanged,
    )

    write_terms_report(
        OUTPUT_TERMS_REPORT,
        records,
        status_totals,
        requested_link_records,
    )

    write_hierarchical_outline(
        OUTPUT_HIERARCHICAL_OUTLINE,
        raw_items,
    )

    top_level_issues, archived_parent_published_child_issues = (
        build_navigation_issue_records(raw_items)
    )

    write_navigation_issues_report(
        OUTPUT_NAVIGATION_ISSUES_REPORT,
        top_level_issues,
        archived_parent_published_child_issues,
        should_be_archived=should_be_archived,
        published_not_in_confluence=published_not_in_confluence,
    )

    invalid_link_groups = build_invalid_internal_link_groups(raw_items)
    non_published_link_groups = build_non_published_internal_link_groups(raw_items)
    write_invalid_internal_links_report(
        OUTPUT_INVALID_INTERNAL_LINKS_REPORT,
        invalid_link_groups,
        non_published_link_groups,
    )

    published_page_link_summaries = build_published_content_link_summaries(
        raw_items,
        "page",
    )
    published_post_link_summaries = build_published_content_link_summaries(
        raw_items,
        "post",
    )
    write_published_pages_link_report(
        OUTPUT_PUBLISHED_PAGES_LINK_REPORT,
        published_page_link_summaries,
        published_post_link_summaries,
    )

    external_page_summaries = build_external_content_link_summaries(
        raw_items, "page", inaccessible_prefixes
    )
    external_post_summaries = build_external_content_link_summaries(
        raw_items, "post", inaccessible_prefixes
    )
    write_external_links_report(
        OUTPUT_EXTERNAL_LINKS_REPORT,
        external_page_summaries,
        external_post_summaries,
    )

    if args.check_non_published_access:
        accessibility_issues = build_accessible_non_published_issues(raw_items)
        write_non_published_accessibility_report(
            OUTPUT_NON_PUBLISHED_ACCESSIBILITY_REPORT,
            accessibility_issues,
        )
        print(
            "Wrote non-published accessibility report to "
            f"{OUTPUT_NON_PUBLISHED_ACCESSIBILITY_REPORT}"
        )

    print(f"Wrote report to {OUTPUT_TERMS_REPORT}")
    print(f"Wrote hierarchical outline to {OUTPUT_HIERARCHICAL_OUTLINE}")
    print(f"Wrote navigation issues report to {OUTPUT_NAVIGATION_ISSUES_REPORT}")
    print(
        f"Wrote invalid internal links report to {OUTPUT_INVALID_INTERNAL_LINKS_REPORT}"
    )
    print(f"Wrote published pages link report to {OUTPUT_PUBLISHED_PAGES_LINK_REPORT}")
    print(f"Wrote external links report to {OUTPUT_EXTERNAL_LINKS_REPORT}")


if __name__ == "__main__":
    main()
