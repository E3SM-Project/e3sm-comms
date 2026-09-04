from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Set

from e3sm_comms.exported_xml_reviewer.builders import (
    AccessibleNonPublishedIssue,
    ArchivedParentPublishedChildIssue,
    ExternalContentLinkSummary,
    PublishedContentLinkSummary,
    ReportRecord,
    RequestedLinkRecord,
    TopLevelPageIssue,
    sort_requested_link_records,
)
from e3sm_comms.exported_xml_reviewer.link_analysis import (
    InvalidInternalLinkGroup,
    NonPublishedInternalLinkGroup,
)
from e3sm_comms.exported_xml_reviewer.utils import display_status, normalize_status
from e3sm_comms.utils import WordpressItem


def write_terms_report(
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
        "published & whitelisted, known ok",
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

            f.write(f"## {status.capitalize()} ({len(grouped[status])})\n\n")

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


def write_invalid_internal_links_report(
    output_path: str,
    groups: List[InvalidInternalLinkGroup],
    non_published_groups: List[NonPublishedInternalLinkGroup],
) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    def render_table(f, table_groups: List[InvalidInternalLinkGroup]) -> None:
        f.write(
            "| Invalid linked URL | Does it redirect to a working link? | Inferred by inference rules | Found under different prefix | Status of inferred/found page/post | Referenced on these published pages | Referenced on these non-published pages |\n"
        )
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")

        for group in table_groups:
            redirect_md = (
                f"[{group.redirect_target}]({group.redirect_target})"
                if group.redirect_target
                else ""
            )
            if redirect_md and group.redirect_status:
                redirect_md = (
                    f"{redirect_md} (redirect status: {group.redirect_status})"
                )

            inferred_md = (
                f"[{group.inferred_link}]({group.inferred_link})"
                if group.inferred_link
                else ""
            )
            prefix_md = (
                f"[{group.found_under_different_prefix}]({group.found_under_different_prefix})"
                if group.found_under_different_prefix
                else ""
            )

            referenced_published = ", ".join(
                f"[{title}]({url})" for title, url in group.referenced_on_published
            )
            referenced_non_published = ", ".join(
                f"[{title}]({url})" for title, url in group.referenced_on_non_published
            )

            f.write(
                f"| {group.linked_url} | {redirect_md} | {inferred_md} | {prefix_md} | {group.linked_target_status} | {referenced_published} | {referenced_non_published} |\n"
            )

    def render_non_published_table(
        f, table_groups: List[NonPublishedInternalLinkGroup]
    ) -> None:
        f.write(
            "| Valid linked URL | Target status | Referenced on these published pages | Referenced on these non-published pages |\n"
        )
        f.write("| --- | --- | --- | --- |\n")

        for group in table_groups:
            referenced_published = ", ".join(
                f"[{title}]({url})" for title, url in group.referenced_on_published
            )
            referenced_non_published = ", ".join(
                f"[{title}]({url})" for title, url in group.referenced_on_non_published
            )
            f.write(
                f"| {group.linked_url} | {group.target_status} | {referenced_published} | {referenced_non_published} |\n"
            )

    working_redirects: List[InvalidInternalLinkGroup] = []
    published_targets: List[InvalidInternalLinkGroup] = []
    archived_targets: List[InvalidInternalLinkGroup] = []
    no_candidate: List[InvalidInternalLinkGroup] = []

    for group in groups:
        if group.redirect_target:
            working_redirects.append(group)
        elif group.linked_target_status == "Published":
            published_targets.append(group)
        elif group.linked_target_status == "Archived":
            archived_targets.append(group)
        else:
            no_candidate.append(group)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Invalid Internal e3sm.org Links\n\n")

        if not groups and not non_published_groups:
            f.write("No invalid internal links found.\n")
            return

        f.write(
            f"## 1. These have working redirections already ({len(working_redirects)})\n\n"
        )
        if working_redirects:
            render_table(f, working_redirects)
        else:
            f.write("None found.\n")
        f.write("\n")

        f.write(
            f"## 2. The target pages are published, we just need to set up the redirections ({len(published_targets)})\n\n"
        )
        if published_targets:
            render_table(f, published_targets)
        else:
            f.write("None found.\n")
        f.write("\n")

        f.write(f"## 3. The target pages are archived ({len(archived_targets)})\n\n")
        if archived_targets:
            render_table(f, archived_targets)
        else:
            f.write("None found.\n")
        f.write("\n")

        f.write(
            f"## 4. Couldn't find a redirection candidate ({len(no_candidate)})\n\n"
        )
        if no_candidate:
            render_table(f, no_candidate)
        else:
            f.write("None found.\n")
        f.write("\n")

        f.write(
            f"## 5. Technically valid links that point to non-published targets ({len(non_published_groups)})\n\n"
        )
        if non_published_groups:
            render_non_published_table(f, non_published_groups)
        else:
            f.write("None found.\n")


def write_published_pages_link_report(
    output_path: str,
    page_summaries: List[PublishedContentLinkSummary],
    post_summaries: List[PublishedContentLinkSummary],
) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    def render_link_list(urls: List[str]) -> str:
        return ", ".join(f"[{url}]({url})" for url in urls)

    def write_section(
        f,
        section_title: str,
        summaries: List[PublishedContentLinkSummary],
    ) -> None:
        invalid_summaries = [
            s
            for s in summaries
            if s.archived_links or s.redirected_links or s.broken_links
        ]
        valid_only_summaries = [
            s
            for s in summaries
            if not (s.archived_links or s.redirected_links or s.broken_links)
        ]

        f.write(f"## {section_title}\n\n")

        if not summaries:
            f.write("No published items with links found.\n\n")
            return

        f.write(f"### Items with invalid links ({len(invalid_summaries)})\n\n")
        if invalid_summaries:
            f.write(
                "| Published item | known archived links | published item, wrong URL, but redirection working | link does not work | valid e3sm.org links |\n"
            )
            f.write("| --- | --- | --- | --- | --- |\n")

            archived_total = 0
            redirected_total = 0
            broken_total = 0
            valid_total = 0

            archived_unique: Set[str] = set()
            redirected_unique: Set[str] = set()
            broken_unique: Set[str] = set()
            valid_unique: Set[str] = set()

            for summary in invalid_summaries:
                item_md = f"[{summary.title}]({summary.url})"
                archived_md = render_link_list(summary.archived_links)
                redirected_md = render_link_list(summary.redirected_links)
                broken_md = render_link_list(summary.broken_links)
                valid_md = render_link_list(summary.valid_links)

                archived_total += len(summary.archived_links)
                redirected_total += len(summary.redirected_links)
                broken_total += len(summary.broken_links)
                valid_total += len(summary.valid_links)

                archived_unique.update(summary.archived_links)
                redirected_unique.update(summary.redirected_links)
                broken_unique.update(summary.broken_links)
                valid_unique.update(summary.valid_links)

                f.write(
                    f"| {item_md} | {archived_md} | {redirected_md} | {broken_md} | {valid_md} |\n"
                )

            f.write(
                f"| Total link count | {archived_total} | {redirected_total} | {broken_total} | {valid_total} |\n"
            )
            f.write(
                f"| Unique link count | {len(archived_unique)} | {len(redirected_unique)} | {len(broken_unique)} | {len(valid_unique)} |\n"
            )
        else:
            f.write("No items with invalid links found.\n")

        f.write("\n")
        f.write(f"### Items with no invalid links ({len(valid_only_summaries)})\n\n")

        if valid_only_summaries:
            f.write("| Published item | valid e3sm.org link count |\n")
            f.write("| --- | ---: |\n")

            total_links = 0
            unique_links: Set[str] = set()

            for summary in valid_only_summaries:
                item_md = f"[{summary.title}]({summary.url})"
                f.write(f"| {item_md} | {len(summary.valid_links)} |\n")
                total_links += len(summary.valid_links)
                unique_links.update(summary.valid_links)

            f.write(f"| Total link count | {total_links} |\n")
            f.write(f"| Unique link count | {len(unique_links)} |\n")
        else:
            f.write("No items with only valid links found.\n")

        f.write("\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Published Content Invalid Link Report\n\n")
        write_section(f, "Published Pages", page_summaries)
        write_section(f, "Published Posts", post_summaries)


def write_external_links_report(
    output_path: str,
    page_summaries: List[ExternalContentLinkSummary],
    post_summaries: List[ExternalContentLinkSummary],
) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    def render_link_list(urls: List[str]) -> str:
        return ", ".join(f"[{url}]({url})" for url in urls)

    def write_section(
        f,
        section_title: str,
        summaries: List[ExternalContentLinkSummary],
    ) -> None:
        invalid_summaries = [
            s
            for s in summaries
            if s.not_found_links
            or s.timed_out_links
            or s.security_error_links
            or s.inaccessible_links
        ]
        valid_only_summaries = [
            s
            for s in summaries
            if not (
                s.not_found_links
                or s.timed_out_links
                or s.security_error_links
                or s.inaccessible_links
            )
        ]

        f.write(f"## {section_title}\n\n")

        if not summaries:
            f.write("No published items with external links found.\n\n")
            return

        f.write(f"### Items with invalid links ({len(invalid_summaries)})\n\n")

        if invalid_summaries:
            f.write(
                "Known inaccessible to script: these are likely accessible manually, or are fake Lorem Ipsum links\n"
            )
            f.write(
                "| Published item | Link not found | Link timed out | Security error | Known inaccessible to script | Valid link |\n"
            )
            f.write("| --- | --- | --- | --- | --- | --- |\n")

            not_found_total = 0
            timed_out_total = 0
            security_total = 0
            inaccessible_total = 0
            valid_total = 0

            not_found_unique: Set[str] = set()
            timed_out_unique: Set[str] = set()
            security_unique: Set[str] = set()
            inaccessible_unique: Set[str] = set()
            valid_unique: Set[str] = set()

            for s in invalid_summaries:
                item_md = f"[{s.title}]({s.url})"
                not_found_md = render_link_list(s.not_found_links)
                timed_out_md = render_link_list(s.timed_out_links)
                security_md = render_link_list(s.security_error_links)
                inaccessible_md = render_link_list(s.inaccessible_links)
                valid_md = render_link_list(s.valid_links)

                not_found_total += len(s.not_found_links)
                timed_out_total += len(s.timed_out_links)
                security_total += len(s.security_error_links)
                inaccessible_total += len(s.inaccessible_links)
                valid_total += len(s.valid_links)

                not_found_unique.update(s.not_found_links)
                timed_out_unique.update(s.timed_out_links)
                security_unique.update(s.security_error_links)
                inaccessible_unique.update(s.inaccessible_links)
                valid_unique.update(s.valid_links)

                f.write(
                    f"| {item_md} | {not_found_md} | {timed_out_md} | {security_md} | {inaccessible_md} | {valid_md} |\n"
                )

            f.write(
                f"| Total link count | {not_found_total} | {timed_out_total} | {security_total} | {inaccessible_total} | {valid_total} |\n"
            )
            f.write(
                f"| Unique link count | {len(not_found_unique)} | {len(timed_out_unique)} | {len(security_unique)} | {len(inaccessible_unique)} | {len(valid_unique)} |\n"
            )
        else:
            f.write("No items with invalid external links found.\n")

        f.write("\n")
        f.write(f"### Items with no invalid links ({len(valid_only_summaries)})\n\n")

        if valid_only_summaries:
            f.write("| Published item | Valid external link count |\n")
            f.write("| --- | ---: |\n")

            total_links = 0
            unique_links: Set[str] = set()

            for s in valid_only_summaries:
                item_md = f"[{s.title}]({s.url})"
                f.write(f"| {item_md} | {len(s.valid_links)} |\n")
                total_links += len(s.valid_links)
                unique_links.update(s.valid_links)

            f.write(f"| Total link count | {total_links} |\n")
            f.write(f"| Unique link count | {len(unique_links)} |\n")
        else:
            f.write("No items with only valid external links found.\n")

        f.write("\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Published Content External Links Report\n\n")
        write_section(f, "Published Pages", page_summaries)
        write_section(f, "Published Posts", post_summaries)


def write_hierarchical_outline(output_path: str, items: List[WordpressItem]) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    def write_section(f, section_items: List[WordpressItem], heading: str) -> None:
        from collections import defaultdict as _defaultdict

        section_items = [item for item in section_items if item.post_id]

        children_by_parent: DefaultDict[str, List[WordpressItem]] = _defaultdict(list)
        item_by_id: Dict[str, WordpressItem] = {}

        for item in section_items:
            item_by_id[item.post_id] = item

        for item in section_items:
            parent_id = (
                item.post_parent if item.post_parent and item.post_parent != "0" else ""
            )
            children_by_parent[parent_id].append(item)

        for child_list in children_by_parent.values():
            child_list.sort(key=lambda x: x.title.lower())

        roots = [
            item
            for item in section_items
            if not item.post_parent
            or item.post_parent == "0"
            or item.post_parent not in item_by_id
        ]
        roots.sort(key=lambda x: x.title.lower())

        f.write(f"{heading}\n")

        seen: Set[str] = set()

        def walk(node: WordpressItem, depth: int) -> None:
            indent = "  " * depth
            status_label = display_status(normalize_status(node.status))
            line = f"{indent}{node.title} [{status_label}]"
            if node.url:
                line += f" [{node.url}]"
            f.write(line + "\n")

            if node.post_id in seen:
                return

            seen.add(node.post_id)

            for child in children_by_parent.get(node.post_id, []):
                walk(child, depth + 1)

        for root in roots:
            walk(root, 0)

        f.write("\n")

    pages = [item for item in items if item.post_type == "page"]
    posts = [item for item in items if item.post_type == "post"]

    with open(output_path, "w", encoding="utf-8") as f:
        write_section(f, pages, "Pages")
        write_section(f, posts, "Posts")


def write_non_published_accessibility_report(
    output_path: str,
    issues: List[AccessibleNonPublishedIssue],
) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Non-Published Pages That Are Still Accessible\n\n")
        f.write(
            'For every page/post whose WordPress status is not "publish", this '
            "checks the live e3sm.org URL (logged out) and flags it here if it's "
            "actually reachable without logging in.\n\n"
        )

        if not issues:
            f.write("No incorrectly accessible non-published pages found.\n")
            return

        f.write(f"## Found {len(issues)} issue(s)\n\n")
        f.write("| Title | WordPress status | URL | Live check result |\n")
        f.write("| --- | --- | --- | --- |\n")
        for issue in issues:
            f.write(
                f"| {issue.title} | {issue.status} | {issue.url} | {issue.e3sm_url_status} |\n"
            )


def write_navigation_issues_report(
    output_path: str,
    top_level_issues: List[TopLevelPageIssue],
    archived_parent_published_child_issues: List[ArchivedParentPublishedChildIssue],
    should_be_archived: List[tuple],
    published_not_in_confluence: List[tuple],
) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# WordPress Navigation Issues Report\n\n")

        f.write("## 1. Top-level pages that are not expected top-level tabs\n\n")
        f.write(
            "Expected top-level tabs are: About, News, Resources, Tools, Policies, Home Page.\n\n"
        )

        if top_level_issues:
            f.write("| Title | Status | URL |\n")
            f.write("| --- | --- | --- |\n")
            for top_level_issue in top_level_issues:
                f.write(
                    f"| {top_level_issue.title} | {top_level_issue.status} | {top_level_issue.url} |\n"
                )
        else:
            f.write("No unexpected top-level pages found.\n")

        f.write("\n")

        f.write("## 2. Published child pages under archived parent pages\n\n")

        if archived_parent_published_child_issues:
            f.write(
                "| Parent title | Parent status | Parent URL | Child title | Child status | Child URL |\n"
            )
            f.write("| --- | --- | --- | --- | --- | --- |\n")
            for archived_child_issue in archived_parent_published_child_issues:
                f.write(
                    f"| {archived_child_issue.parent_title} | {archived_child_issue.parent_status} | {archived_child_issue.parent_url} | "
                    f"{archived_child_issue.child_title} | {archived_child_issue.child_status} | {archived_child_issue.child_url} |\n"
                )
        else:
            f.write(
                "No published child pages were found under archived parent pages.\n"
            )

        f.write("\n")

        f.write(
            "## 3. Expecting to be archived, but not yet archived "
            f"({len(should_be_archived)})\n\n"
        )
        if should_be_archived:
            f.write("| Title | URL |\n")
            f.write("| --- | --- |\n")
            for title, url in should_be_archived:
                f.write(f"| {title} | {url} |\n")
        else:
            f.write(
                "No pages/posts found (or `--use-expected-archived` was not passed).\n"
            )

        f.write("\n")

        f.write(
            "## 4. Published & whitelisted, but no matching Confluence page found "
            f"({len(published_not_in_confluence)})\n\n"
        )
        if published_not_in_confluence:
            f.write("| Title | URL |\n")
            f.write("| --- | --- |\n")
            for title, url in published_not_in_confluence:
                f.write(f"| {title} | {url} |\n")
        else:
            f.write("No pages/posts found (or `--use-confluence` was not passed).\n")
