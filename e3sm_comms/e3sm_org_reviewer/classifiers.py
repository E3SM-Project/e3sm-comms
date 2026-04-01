import re
from typing import Dict, Optional, Set, Tuple

CLASS_PUBLISHED = "Published"
CLASS_ARCHIVED = "Archived"
CLASS_SHOULD_BE_ARCHIVED = "Should be archived"
CLASS_NOT_PUBLISHED = "Not published"
CLASS_KNOWN_OK = "Known OK"
CLASS_KEEP_UNCHANGED = "Keep unchanged"
CLASS_NO_MAPPED_E3SM_URL = "No mapped e3sm.org URL"
CLASS_PREDICTED_URL_NOT_IN_EXPORT = "Predicted e3sm.org URL not in WordPress export"

FROM_PREFIX_RE = re.compile(r"^\[From\s+(\d{4})-\d{2}-\d{2}T[^\]]+\]\s*(.*)$")


def classify_e3sm_url(
    e3sm_url: Optional[str],
    url_to_status: Dict[str, str],
    expected_archived_urls: Set[str],
    known_ok_urls: Set[str],
    keep_unchanged_urls: Set[str],
) -> Tuple[str, Optional[str]]:
    if not e3sm_url:
        return CLASS_NO_MAPPED_E3SM_URL, None

    if e3sm_url in known_ok_urls:
        return CLASS_KNOWN_OK, url_to_status.get(e3sm_url)

    if e3sm_url in keep_unchanged_urls:
        return CLASS_KEEP_UNCHANGED, url_to_status.get(e3sm_url)

    wordpress_status = url_to_status.get(e3sm_url)

    if wordpress_status is None:
        return CLASS_PREDICTED_URL_NOT_IN_EXPORT, None

    if wordpress_status == "archive":
        return CLASS_ARCHIVED, wordpress_status

    if e3sm_url in expected_archived_urls:
        return CLASS_SHOULD_BE_ARCHIVED, wordpress_status

    if wordpress_status != "publish":
        return CLASS_NOT_PUBLISHED, wordpress_status

    return CLASS_PUBLISHED, wordpress_status


def classification_sort_key(classification: str) -> Tuple[int, str]:
    order = {
        CLASS_PUBLISHED: 0,
        CLASS_SHOULD_BE_ARCHIVED: 1,
        CLASS_ARCHIVED: 2,
        CLASS_NOT_PUBLISHED: 3,
        CLASS_KNOWN_OK: 4,
        CLASS_KEEP_UNCHANGED: 5,
        CLASS_NO_MAPPED_E3SM_URL: 6,
        CLASS_PREDICTED_URL_NOT_IN_EXPORT: 7,
    }
    return (order.get(classification, 999), classification)


def year_sort_key(year_str: str) -> Tuple[int, int]:
    if year_str == "Unknown year":
        return (1, 0)
    if year_str == "N/A":
        return (2, 0)
    try:
        return (0, -int(year_str))
    except ValueError:
        return (3, 0)


def extract_year_and_remainder(line: str) -> Tuple[Optional[int], str]:
    match = FROM_PREFIX_RE.match(line)
    if not match:
        return None, line

    year = int(match.group(1))
    remainder = match.group(2).strip()
    return year, remainder
