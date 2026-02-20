from typing import Dict, List

from e3sm_comms.page_reviewer.utils_base import LinkedURLs

INPUT_E3SM_ORG_PATHS: str = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/input/e3sm_org_reviewer/web_pages.txt"
)
INPUT_SEARCH_PHRASES: str = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/input/shared/sensitive_terms.txt"
)
OUTPUT: str = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/output/e3sm_org_reviewer/found_phrases.txt"
)


def main():
    with open(INPUT_E3SM_ORG_PATHS, "r", encoding="utf-8") as f:
        list_input_e3sm_org_paths: List[str] = [line.strip() for line in f]
    with open(INPUT_SEARCH_PHRASES, "r", encoding="utf-8") as f:
        terms: List[str] = [line.rstrip("\n").lower() for line in f]
        list_search_phrases: List[str] = sorted(terms)

    print(f"Checking {len(list_input_e3sm_org_paths)} e3sm.org pages")
    links = LinkedURLs(
        list_input_e3sm_org_paths,
        scan_links_for_sensitive_terms=True,
        list_sensitive_terms=list_search_phrases,
    )
    relevant_links: Dict[str, Dict[str, int]] = links.links_with_sensitive_terms
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for link in relevant_links:
            f.write(f"{link}: {relevant_links[link]}\n")
