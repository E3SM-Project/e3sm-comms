import xml.etree.ElementTree as ET
from typing import Dict, List

from e3sm_comms.page_reviewer.utils_base import LinkedURLs, get_e3sm_url_status
from e3sm_comms.utils import IO_DIR

INPUT_ACCESSIBLE_E3SM_ORG_PATHS: str = f"{IO_DIR}/input/e3sm_org_reviewer/web_pages.txt"
INPUT_SEARCH_PHRASES: str = f"{IO_DIR}/input/shared/sensitive_terms.txt"
OUTPUT_FOUND_PHRASES: str = f"{IO_DIR}/output/e3sm_org_reviewer/found_phrases.txt"

INPUT_ARCHIVED_E3SM_ORG_PATHS: str = f"{IO_DIR}/input/shared/archived_web_pages.txt"
OUTPUT_INCORRECTLY_ACCESSIBLE_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/incorrectly_accessible_web_pages.txt"
)

INPUT_XML_PAGES: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_pages.xml"
INPUT_XML_POSTS: str = f"{IO_DIR}/input/e3sm_org_reviewer/wordpress_posts.xml"
OUTPUT_PAGE_URLS_FROM_XML: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/page_urls_from_xml.txt"
)
OUTPUT_POST_URLS_FROM_XML: str = (
    f"{IO_DIR}/output/e3sm_org_reviewer/post_urls_from_xml.txt"
)


def main():
    # Check the accesible pages for search phrases ############################
    with open(INPUT_ACCESSIBLE_E3SM_ORG_PATHS, "r", encoding="utf-8") as f:
        list_input_e3sm_org_paths: List[str] = [line.strip() for line in f]
    with open(INPUT_SEARCH_PHRASES, "r", encoding="utf-8") as f:
        terms: List[str] = [line.rstrip("\n").lower() for line in f]
        list_search_phrases: List[str] = sorted(terms)
    print(f"Checking {len(list_input_e3sm_org_paths)} accessible e3sm.org pages")
    links = LinkedURLs(
        list_input_e3sm_org_paths,
        scan_links_for_sensitive_terms=True,
        list_sensitive_terms=list_search_phrases,
    )
    relevant_links: Dict[str, Dict[str, int]] = links.links_with_sensitive_terms
    with open(OUTPUT_FOUND_PHRASES, "w", encoding="utf-8") as f:
        for link in relevant_links:
            f.write(f"{link}: {relevant_links[link]}\n")

    # Check that the inaccessible pages are in fact inaccessible ###############
    with open(INPUT_ARCHIVED_E3SM_ORG_PATHS, "r", encoding="utf-8") as f:
        list_input_archived_e3sm_org_paths: List[str] = [line.strip() for line in f]
    print(f"Checking {len(list_input_archived_e3sm_org_paths)} archived e3sm.org pages")
    with open(OUTPUT_INCORRECTLY_ACCESSIBLE_E3SM_ORG_PATHS, "w", encoding="utf-8") as f:
        for e3sm_url in list_input_archived_e3sm_org_paths:
            e3sm_url_status = get_e3sm_url_status(e3sm_url)
            if e3sm_url_status == "link works not logged-in":
                # This URL works, when it should not.
                f.write(f"{link}\n")
            pass

    # Review XML exports from WordPress #######################################
    # urls = get_wordpress_page_urls("wordpress-export.xml", status_filter="publish")
    page_urls = get_wordpress_urls(INPUT_XML_PAGES, "page")
    post_urls = get_wordpress_urls(INPUT_XML_POSTS, "post")
    print(f"Checking {len(page_urls)} page URLs, {len(post_urls)} post URLs")
    with open(OUTPUT_PAGE_URLS_FROM_XML, "w", encoding="utf-8") as f:
        for url in page_urls:
            f.write(f"{url}\n")
    with open(OUTPUT_POST_URLS_FROM_XML, "w", encoding="utf-8") as f:
        for url in post_urls:
            f.write(f"{url}\n")


def get_wordpress_urls(xml_file_path: str, wordpress_type: str, status_filter=None):
    """
    Read a WordPress export XML file and return a list of hosted page URLs.

    Args:
        xml_file_path (str): Path to the WordPress export XML file.
        status_filter (str | None): Optional, like 'publish'. If set, only
            pages with this wp:status are included. publish, archive

    Returns:
        list[str]: List of page URLs.
    """
    ns = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "excerpt": "http://wordpress.org/export/1.2/excerpt/",
        "wfw": "http://wellformedweb.org/CommentAPI/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "wp": "http://wordpress.org/export/1.2/",
    }

    tree = ET.parse(xml_file_path)
    root = tree.getroot()

    urls: List[str] = []

    channel = root.find("channel")
    if channel is None:
        return urls

    for item in channel.findall("item"):
        post_type = item.find("wp:post_type", ns)
        status = item.find("wp:status", ns)
        link = item.find("link")

        if post_type is None or post_type.text != wordpress_type:
            continue

        if status_filter and (status is None or status.text != status_filter):
            continue

        if link is not None and link.text:
            urls.append(link.text.strip())

    return urls
