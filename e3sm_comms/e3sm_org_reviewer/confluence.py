from typing import List, Tuple

from e3sm_comms.page_reviewer.utils_base import map_confluence_to_e3sm
from e3sm_comms.utils import parse_confluence_hierarchy_file

CONFLUENCE_SPACE = "EPWCD"
CONFLUENCE_BASE = "https://e3sm.atlassian.net/wiki"


def build_confluence_url(page_id: str, space_key: str = CONFLUENCE_SPACE) -> str:
    return f"{CONFLUENCE_BASE}/spaces/{space_key}/pages/{page_id}"


def get_confluence_predicted_e3sm_urls(
    input_file: str,
) -> Tuple[List[str], List[str]]:
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
