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
                f.write(link)
            pass
