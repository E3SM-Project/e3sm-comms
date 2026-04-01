from __future__ import annotations

from typing import Dict

from e3sm_comms.page_reviewer.utils_base import map_confluence_to_e3sm
from e3sm_comms.utils import normalize_url, parse_confluence_hierarchy_file

CONFLUENCE_SPACE = "EPWCD"
CONFLUENCE_BASE = "https://e3sm.atlassian.net/wiki"


def get_confluence_mapping(input_file: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    for page_id, title in parse_confluence_hierarchy_file(input_file):
        confluence_url = build_confluence_url(page_id)
        try:
            e3sm_url = map_confluence_to_e3sm(confluence_url, page_title=title)
            if e3sm_url:
                mapping[normalize_url(e3sm_url)] = confluence_url
        except Exception as exc:
            print(f"Could not map {confluence_url}: {exc}")

    return mapping


def build_confluence_url(page_id: str, space_key: str = CONFLUENCE_SPACE) -> str:
    return f"{CONFLUENCE_BASE}/spaces/{space_key}/pages/{page_id}"
