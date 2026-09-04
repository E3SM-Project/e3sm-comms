from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Dict, List, Optional, Set, Tuple

from e3sm_comms.exported_xml_reviewer.confluence import get_confluence_mapping
from e3sm_comms.exported_xml_reviewer.link_analysis import (
    check_external_link,
    check_redirect_target,
    extract_external_links,
    extract_internal_e3sm_links,
)
from e3sm_comms.exported_xml_reviewer.readers import (
    read_expected_archived_patterns,
    read_keep_unchanged_links,
    read_known_ok_links,
    read_requested_links,
    read_sensitive_terms,
    read_whitelist_patterns,
)
from e3sm_comms.exported_xml_reviewer.utils import (
    display_status,
    normalize_status,
    strip_html,
)
from e3sm_comms.page_reviewer.utils_base import get_e3sm_url_status
from e3sm_comms.utils import (
    WordpressItem,
    count_sensitive_terms,
    expand_patterns_to_urls,
    normalize_url,
    parse_wordpress_xml_items,
)


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


@dataclass
class TopLevelPageIssue:
    title: str
    url: str
    status: str


@dataclass
class ArchivedParentPublishedChildIssue:
    parent_title: str
    parent_url: str
    parent_status: str
    child_title: str
    child_url: str
    child_status: str


@dataclass
class PublishedContentLinkSummary:
    title: str
    url: str
    archived_links: List[str]
    redirected_links: List[str]
    timed_out_links: List[str]
    broken_links: List[str]
    valid_links: List[str]


@dataclass
class ExternalContentLinkSummary:
    title: str
    url: str
    not_found_links: List[str]
    timed_out_links: List[str]
    security_error_links: List[str]
    inaccessible_links: List[str]
    valid_links: List[str]


@dataclass
class AccessibleNonPublishedIssue:
    title: str
    url: str
    status: str
    e3sm_url_status: str


def build_records(
    xml_pages: str,
    xml_posts: str,
    confluence_hierarchy: str,
    sensitive_terms_file: str,
    whitelist_file: str,
    requested_links_file: str,
    known_ok_links_file: str,
    expected_archived_file: str = "",
    keep_unchanged_links_file: str = "",
) -> Tuple[
    List[ReportRecord],
    Dict[str, int],
    List[RequestedLinkRecord],
    List[WordpressItem],
    List[Tuple[str, str]],
    List[Tuple[str, str]],
]:
    sensitive_terms_list = read_sensitive_terms(sensitive_terms_file)

    confluence_map = {}
    if confluence_hierarchy:
        confluence_map = get_confluence_mapping(confluence_hierarchy)

    known_ok_urls = read_known_ok_links(known_ok_links_file)
    keep_unchanged_urls = (
        read_keep_unchanged_links(keep_unchanged_links_file)
        if keep_unchanged_links_file
        else set()
    )

    raw_items: List[WordpressItem] = []
    raw_items.extend(parse_wordpress_xml_items(xml_pages, "page"))
    raw_items.extend(parse_wordpress_xml_items(xml_posts, "post"))

    all_urls = [item.url for item in raw_items if item.url]
    if whitelist_file:
        whitelist_patterns = read_whitelist_patterns(whitelist_file)
        whitelisted_urls = set(expand_patterns_to_urls(whitelist_patterns, all_urls))
    else:
        whitelisted_urls = set(all_urls)

    records: List[ReportRecord] = []
    status_totals: DefaultDict[str, int] = defaultdict(int)

    for item in raw_items:
        base_status = normalize_status(item.status)
        report_status = base_status

        if base_status == "published":
            if item.url in whitelisted_urls:
                if item.url in known_ok_urls:
                    report_status = "published & whitelisted, known ok"
                else:
                    report_status = "published & whitelisted"
            else:
                report_status = "published & not whitelisted"

        if item.url in keep_unchanged_urls:
            report_status = f"{report_status}, keep unchanged"

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

    should_be_archived = build_should_be_archived(
        raw_items=raw_items,
        all_urls=all_urls,
        expected_archived_file=expected_archived_file,
    )

    published_not_in_confluence = build_published_not_in_confluence(
        raw_items=raw_items,
        confluence_map=confluence_map,
        whitelisted_urls=whitelisted_urls,
    )

    return (
        records,
        dict(status_totals),
        requested_link_records,
        raw_items,
        should_be_archived,
        published_not_in_confluence,
    )


def build_should_be_archived(
    raw_items: List[WordpressItem],
    all_urls: List[str],
    expected_archived_file: str,
) -> List[Tuple[str, str]]:
    """
    Cross-reference a manually
    curated list of e3sm.org paths that are expected to be archived against
    each page/post's actual WordPress status, and flag any that have not
    actually been archived yet. Returns (title, url) pairs, sorted by title.
    """
    if not expected_archived_file:
        return []

    expected_archived_patterns = read_expected_archived_patterns(expected_archived_file)
    expected_archived_urls = set(
        expand_patterns_to_urls(expected_archived_patterns, all_urls)
    )

    if not expected_archived_urls:
        return []

    flagged: List[Tuple[str, str]] = []
    for item in raw_items:
        if not item.url or item.url not in expected_archived_urls:
            continue
        if normalize_status(item.status) != "archived":
            flagged.append((item.title, item.url))

    return sorted(flagged, key=lambda x: x[0].lower())


def build_published_not_in_confluence(
    raw_items: List[WordpressItem],
    confluence_map: Dict[str, str],
    whitelisted_urls: Set[str],
) -> List[Tuple[str, str]]:
    """
    Published pages/posts with no corresponding entry in the
    Confluence-predicted URL map, i.e. content that's live on
    e3sm.org but has no source-of-truth Confluence page.
    Restricted to whitelisted URLs. Returns (title, url) pairs,
    sorted by title. Empty if no Confluence hierarchy file was supplied.
    """
    if not confluence_map:
        return []

    flagged: List[Tuple[str, str]] = []
    for item in raw_items:
        if not item.url or normalize_status(item.status) != "published":
            continue
        if item.url not in whitelisted_urls:
            continue
        if normalize_url(item.url) not in confluence_map:
            flagged.append((item.title, item.url))

    return sorted(flagged, key=lambda x: x[0].lower())


def build_accessible_non_published_issues(
    raw_items: List[WordpressItem],
) -> List[AccessibleNonPublishedIssue]:
    """
    For every non-published page/post,
    make a live, logged-out HTTP request to its e3sm.org URL and flag it if
    the page is actually reachable. Draft/private/pending/future content
    should 404 or redirect to a login when fetched without credentials; if
    it returns 200, it's effectively public despite its WordPress status.

    This makes one live network request per non-published URL, so it's
    opt-in (see `--check-non-published-access` in main.py) and can be slow
    on a site with many drafts.
    """
    flagged: List[AccessibleNonPublishedIssue] = []

    for item in raw_items:
        if not item.url or normalize_status(item.status) == "published":
            continue

        e3sm_url_status = get_e3sm_url_status(item.url)
        if e3sm_url_status == "link works not logged-in":
            flagged.append(
                AccessibleNonPublishedIssue(
                    title=item.title,
                    url=item.url,
                    status=display_status(normalize_status(item.status)),
                    e3sm_url_status=e3sm_url_status,
                )
            )

    return sorted(flagged, key=lambda x: x.title.lower())


def build_navigation_issue_records(
    items: List[WordpressItem],
) -> Tuple[List[TopLevelPageIssue], List[ArchivedParentPublishedChildIssue]]:
    allowed_top_level_titles = {
        "about",
        "news",
        "resources",
        "tools",
        "policies",
        "home page",
    }

    pages = [item for item in items if item.post_type == "page" and item.post_id]
    item_by_id: Dict[str, WordpressItem] = {item.post_id: item for item in pages}

    top_level_issues: List[TopLevelPageIssue] = []
    archived_parent_published_child_issues: List[ArchivedParentPublishedChildIssue] = []

    for page in pages:
        normalized_status = normalize_status(page.status)

        is_top_level = (
            not page.post_parent
            or page.post_parent == "0"
            or page.post_parent not in item_by_id
        )

        if is_top_level and page.title.strip().lower() not in allowed_top_level_titles:
            top_level_issues.append(
                TopLevelPageIssue(
                    title=page.title,
                    url=page.url,
                    status=display_status(normalized_status),
                )
            )

        if (
            page.post_parent
            and page.post_parent != "0"
            and page.post_parent in item_by_id
            and normalized_status == "published"
        ):
            parent = item_by_id[page.post_parent]
            parent_status = normalize_status(parent.status)

            if parent_status == "archived":
                archived_parent_published_child_issues.append(
                    ArchivedParentPublishedChildIssue(
                        parent_title=parent.title,
                        parent_url=parent.url,
                        parent_status=display_status(parent_status),
                        child_title=page.title,
                        child_url=page.url,
                        child_status=display_status(normalized_status),
                    )
                )

    status_order = {
        "Published": 0,
        "Draft": 1,
        "Pending": 2,
        "Future": 3,
        "Private": 4,
        "Archived": 5,
        "Unknown": 6,
    }

    top_level_issues.sort(
        key=lambda x: (
            status_order.get(x.status, 99),
            x.title.lower(),
            x.url.lower(),
        )
    )

    archived_parent_published_child_issues.sort(
        key=lambda x: (
            x.parent_title.lower(),
            x.child_title.lower(),
            x.child_url.lower(),
        )
    )

    return top_level_issues, archived_parent_published_child_issues


def build_published_content_link_summaries(
    items: List[WordpressItem],
    post_type: str,
) -> List[PublishedContentLinkSummary]:
    item_by_url = {normalize_url(item.url): item for item in items if item.url}
    actual_urls = set(item_by_url.keys())

    if post_type == "page":
        ordered_items = get_page_hierarchy_order(items)
    else:
        ordered_items = sorted(
            [item for item in items if item.post_type == post_type and item.post_id],
            key=lambda x: x.title.lower(),
        )

    summaries: List[PublishedContentLinkSummary] = []

    for item in ordered_items:
        if normalize_status(item.status) != "published":
            continue
        if not item.url or not item.body:
            continue

        archived_links: Set[str] = set()
        redirected_links: Set[str] = set()
        timed_out_links: Set[str] = set()
        broken_links: Set[str] = set()
        valid_links: Set[str] = set()

        for linked_url in extract_internal_e3sm_links(item.body):
            linked_norm = normalize_url(linked_url)
            target_item = item_by_url.get(linked_norm)

            if target_item is not None:
                target_status = normalize_status(target_item.status)
                if target_status == "archived":
                    archived_links.add(linked_norm)
                else:
                    valid_links.add(linked_norm)
                continue

            # check_redirect_target is memoized (see link_analysis.py), so
            # for any URL already looked up by build_invalid_internal_link_groups()
            # this reuses the cached result instead of firing another request.
            redirect_target, _redirect_status, timed_out = check_redirect_target(
                linked_norm
            )
            if redirect_target and normalize_url(redirect_target) in actual_urls:
                redirected_links.add(linked_norm)
                valid_links.add(linked_norm)
            elif timed_out:
                timed_out_links.add(linked_norm)
            else:
                broken_links.add(linked_norm)

        summaries.append(
            PublishedContentLinkSummary(
                title=item.title,
                url=item.url,
                archived_links=sorted(archived_links),
                redirected_links=sorted(redirected_links),
                timed_out_links=sorted(timed_out_links),
                broken_links=sorted(broken_links),
                valid_links=sorted(valid_links),
            )
        )

    return summaries


def build_external_content_link_summaries(
    items: List[WordpressItem],
    post_type: str,
    inaccessible_prefixes: Tuple[str, ...] = (),
) -> List[ExternalContentLinkSummary]:
    """
    Mirror of build_published_content_link_summaries, but for external links.

    Deduplicates URLs across all items before fetching so each external URL
    is checked exactly once.

    URLs whose prefix matches any entry in `inaccessible_prefixes` are skipped
    entirely (no network request) and reported in the "inaccessible" column.
    """
    if post_type == "page":
        ordered_items = get_page_hierarchy_order(items)
    else:
        ordered_items = sorted(
            [item for item in items if item.post_type == post_type and item.post_id],
            key=lambda x: x.title.lower(),
        )

    # Collect all unique external URLs first to avoid redundant fetches.
    all_external_urls: Set[str] = set()
    item_to_external_urls: Dict[str, Set[str]] = {}

    for item in ordered_items:
        if normalize_status(item.status) != "published":
            continue
        if not item.url or not item.body:
            continue
        found = extract_external_links(item.body)
        item_to_external_urls[item.url] = found
        all_external_urls.update(found)

    # Check each unique URL once, skipping known-inaccessible prefixes.
    url_results: Dict[str, str] = {}
    for ext_url in sorted(all_external_urls):
        if inaccessible_prefixes and any(
            ext_url.startswith(prefix) for prefix in inaccessible_prefixes
        ):
            url_results[ext_url] = "inaccessible"
        else:
            url_results[ext_url] = check_external_link(ext_url).status

    summaries: List[ExternalContentLinkSummary] = []

    for item in ordered_items:
        if normalize_status(item.status) != "published":
            continue
        if not item.url or not item.body:
            continue

        ext_urls = item_to_external_urls.get(item.url, set())
        if not ext_urls:
            continue

        not_found: Set[str] = set()
        timed_out: Set[str] = set()
        security_error: Set[str] = set()
        inaccessible: Set[str] = set()
        valid: Set[str] = set()

        for ext_url in ext_urls:
            status = url_results.get(ext_url, "not_found")
            if status == "valid":
                valid.add(ext_url)
            elif status == "timed_out":
                timed_out.add(ext_url)
            elif status == "security_error":
                security_error.add(ext_url)
            elif status == "inaccessible":
                inaccessible.add(ext_url)
            else:
                not_found.add(ext_url)

        summaries.append(
            ExternalContentLinkSummary(
                title=item.title,
                url=item.url,
                not_found_links=sorted(not_found),
                timed_out_links=sorted(timed_out),
                security_error_links=sorted(security_error),
                inaccessible_links=sorted(inaccessible),
                valid_links=sorted(valid),
            )
        )

    return summaries


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


def get_page_hierarchy_order(items: List[WordpressItem]) -> List[WordpressItem]:
    pages = [item for item in items if item.post_type == "page" and item.post_id]
    item_by_id: Dict[str, WordpressItem] = {item.post_id: item for item in pages}

    children_by_parent: DefaultDict[str, List[WordpressItem]] = defaultdict(list)
    for item in pages:
        parent_id = (
            item.post_parent if item.post_parent and item.post_parent != "0" else ""
        )
        children_by_parent[parent_id].append(item)

    for child_list in children_by_parent.values():
        child_list.sort(key=lambda x: x.title.lower())

    roots = [
        item
        for item in pages
        if not item.post_parent
        or item.post_parent == "0"
        or item.post_parent not in item_by_id
    ]
    roots.sort(key=lambda x: x.title.lower())

    ordered: List[WordpressItem] = []
    seen: Set[str] = set()

    def walk(node: WordpressItem) -> None:
        if node.post_id in seen:
            return
        seen.add(node.post_id)
        ordered.append(node)
        for child in children_by_parent.get(node.post_id, []):
            walk(child)

    for root in roots:
        walk(root)

    return ordered


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
