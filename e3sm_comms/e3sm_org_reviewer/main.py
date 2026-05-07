import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List

from e3sm_comms.page_reviewer.utils_base import LinkedURLs, get_e3sm_url_status
from e3sm_comms.utils import IO_DIR

INPUT_XML_PAGES: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_pages.xml"
INPUT_XML_POSTS: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_posts.xml"
INPUT_WHITELIST: str = f"{IO_DIR}/input/e3sm_org_reviewer/whitelisted_web_pages.txt"
INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/input/shared/archived_web_pages.txt"
)
INPUT_SEARCH_PHRASES: str = f"{IO_DIR}/input/shared/sensitive_terms.txt"

OUTPUT_WHITELISTED_NOT_PUBLISHED: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/whitelisted_not_published.txt"
)
OUTPUT_PUBLISHED_NOT_WHITELISTED: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/published_not_whitelisted.txt"
)
OUTPUT_SHOULD_BE_ARCHIVED: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/should_be_archived.txt"
)
OUTPUT_EXTRA_ARCHIVED: str = f"{IO_DIR}/output/e3sm_org_reviewer/extra_archived.txt"
OUTPUT_FOUND_PHRASES: str = f"{IO_DIR}/output/e3sm_org_reviewer/found_phrases.txt"
OUTPUT_INCORRECTLY_ACCESSIBLE_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/incorrectly_accessible_web_pages.txt"
)

RUN_CHECKS: bool = False  # Set to False for faster debugging


def main():
    # Review XML exports from WordPress #######################################
    pages_by_status: Dict[str, List[str]] = get_wordpress_urls_by_status(
        INPUT_XML_PAGES, "page"
    )
    posts_by_status: Dict[str, List[str]] = get_wordpress_urls_by_status(
        INPUT_XML_POSTS, "post"
    )
    num_pages: int = get_total_count(pages_by_status)
    num_posts: int = get_total_count(posts_by_status)
    print(f"Found {num_pages} pages, {num_posts} posts")
    #    ['archive', 'draft', 'future', 'pending', 'private', 'publish']
    print(
        f"Pages have status in {pages_by_status.keys()}; posts have status in {posts_by_status.keys()}"
    )

    all_urls_by_status: Dict[str, List[str]] = get_combined_urls_by_status(
        pages_by_status, posts_by_status
    )
    if "publish" in all_urls_by_status:
        print(f"Found {len(all_urls_by_status['publish'])} published URLs")
    if "archive" in all_urls_by_status:
        print(f"Found {len(all_urls_by_status['archive'])} archived URLs")
    if "draft" in all_urls_by_status:
        print(f"Found {len(all_urls_by_status['draft'])} draft URLs")
    if "future" in all_urls_by_status:
        print(f"Found {len(all_urls_by_status['future'])} future URLs")
    if "pending" in all_urls_by_status:
        print(f"Found {len(all_urls_by_status['pending'])} pending URLs")
    if "private" in all_urls_by_status:
        print(f"Found {len(all_urls_by_status['private'])} private URLs")
    non_published_urls: List[str] = get_all_non_published_urls(all_urls_by_status)
    print(f"Total non-published URLs: {len(non_published_urls)}")

    # Compare with expectations ###############################################
    with open(INPUT_WHITELIST, "r", encoding="utf-8") as f:
        list_whitelisted_paths: List[str] = [line.strip() for line in f]
    with open(INPUT_EXPECTED_ARCHIVED_E3SM_ORG_PATHS, "r", encoding="utf-8") as f:
        list_expected_archived_paths: List[str] = [line.strip() for line in f]

    all_urls: List[str] = get_all_urls(all_urls_by_status)
    invalid_whitelisted_paths: List[str] = get_list_difference(
        list_whitelisted_paths, all_urls
    )
    valid_whitelisted_paths: List[str] = get_list_difference(
        list_whitelisted_paths, invalid_whitelisted_paths
    )
    invalid_expected_archived_paths: List[str] = get_list_difference(
        list_expected_archived_paths, all_urls
    )
    valid_expected_archived_paths: List[str] = get_list_difference(
        list_expected_archived_paths, invalid_expected_archived_paths
    )
    print(
        f"Of {len(list_whitelisted_paths)} whitelisted paths, {len(valid_whitelisted_paths)} are valid URLs"
    )
    print(
        f"Of {len(list_expected_archived_paths)} expected archived paths, {len(valid_expected_archived_paths)} are valid URLs"
    )

    whitelisted_but_not_published: List[str] = get_list_difference(
        valid_whitelisted_paths, all_urls_by_status["publish"]
    )
    published_but_not_whitelisted: List[str] = get_list_difference(
        all_urls_by_status["publish"], valid_whitelisted_paths
    )
    print(f"Whitelisted, but not published: {len(whitelisted_but_not_published)}")
    print(f"Published, but not whitelisted: {len(published_but_not_whitelisted)}")
    with open(OUTPUT_WHITELISTED_NOT_PUBLISHED, "w", encoding="utf-8") as f:
        for url in whitelisted_but_not_published:
            f.write(f"{url}\n")
    with open(OUTPUT_PUBLISHED_NOT_WHITELISTED, "w", encoding="utf-8") as f:
        for url in published_but_not_whitelisted:
            f.write(f"{url}\n")

    should_be_archived: List[str] = get_list_difference(
        valid_expected_archived_paths, all_urls_by_status["archive"]
    )
    extra_archived: List[str] = get_list_difference(
        all_urls_by_status["archive"], valid_expected_archived_paths
    )
    print(f"Not archived, but should be archived: {len(should_be_archived)}")
    print(f"Archived, but weren't on our expected list: {len(extra_archived)}")
    with open(OUTPUT_SHOULD_BE_ARCHIVED, "w", encoding="utf-8") as f:
        for url in should_be_archived:
            f.write(f"{url}\n")
    with open(OUTPUT_EXTRA_ARCHIVED, "w", encoding="utf-8") as f:
        for url in extra_archived:
            f.write(f"{url}\n")

    # Run checks ##############################################################
    if RUN_CHECKS:
        print(
            f"Checking {len(list_whitelisted_paths)} whitelisted e3sm.org pages for search phrases"
        )
        with open(INPUT_SEARCH_PHRASES, "r", encoding="utf-8") as f:
            terms: List[str] = [line.rstrip("\n").lower() for line in f]
            list_search_phrases: List[str] = sorted(terms)
        links = LinkedURLs(
            list_whitelisted_paths,
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
            for e3sm_url in list_expected_archived_paths:
                e3sm_url_status = get_e3sm_url_status(e3sm_url)
                if e3sm_url_status == "link works not logged-in":
                    # This URL works, when it should not.
                    f.write(f"{e3sm_url}\n")
                pass


def get_wordpress_urls_by_status(xml_file_path: str, post_type: str):
    ns = {
        "wp": "http://wordpress.org/export/1.2/",
    }

    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    grouped = defaultdict(list)
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
    count: int = 0
    for status in urls_by_status:
        count += len(urls_by_status[status])
    return count


def get_combined_urls_by_status(
    pages_by_status: Dict[str, List[str]], posts_by_status: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    merged = defaultdict(list)
    for source in (pages_by_status, posts_by_status):
        for status, urls in source.items():
            merged[status].extend(urls)
    return dict(merged)


def get_list_difference(list1: List[str], list2: List[str]) -> List[str]:
    diff: List[str] = list(set(list1) - set(list2))
    return sorted(diff)


def get_all_urls(urls_by_status: Dict[str, List[str]]) -> List[str]:
    non_published_urls: List[str] = []
    for status in urls_by_status:
        non_published_urls += urls_by_status[status]
    return non_published_urls


def get_all_non_published_urls(urls_by_status: Dict[str, List[str]]) -> List[str]:
    non_published_urls: List[str] = []
    for status in urls_by_status:
        if status != "publish":
            non_published_urls += urls_by_status[status]
    return non_published_urls
