import ast
from typing import Dict, List, Optional, Set, Tuple

from e3sm_comms.e3sm_org_reviewer.classifiers import (
    classify_e3sm_url,
    extract_year_and_remainder,
)
from e3sm_comms.e3sm_org_reviewer.confluence import build_confluence_url
from e3sm_comms.e3sm_org_reviewer.record import SensitiveTermRecord
from e3sm_comms.page_reviewer.utils_base import map_confluence_to_e3sm


def parse_dict(dict_str: str) -> Optional[Dict[str, int]]:
    try:
        data = ast.literal_eval(dict_str)
    except (SyntaxError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    try:
        total = sum(data.values())
    except TypeError:
        return None

    if not isinstance(total, (int, float)):
        return None

    return data


def parse_wordpress_sensitive_terms_lines(lines: List[str]) -> List[Tuple[int, str]]:
    parsed: List[Tuple[int, str]] = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue

        dict_start = line.find("{")
        if dict_start == -1:
            print(f"Skipping malformed WordPress sensitive-terms line: {line}")
            continue

        dict_str = line[dict_start:].strip()
        dict_data = parse_dict(dict_str)
        if dict_data is None:
            print(f"Skipping malformed dictionary in WordPress line: {line}")
            continue

        total = int(sum(dict_data.values()))
        parsed.append((total, line))

    parsed.sort(key=lambda x: x[0], reverse=True)
    return parsed


def parse_wordpress_record(
    line: str,
    url_to_status: Dict[str, str],
    expected_archived_urls: Set[str],
    known_ok_urls: Set[str],
    keep_unchanged_urls: Set[str],
) -> Optional[SensitiveTermRecord]:
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    url = extract_wordpress_url(line)
    if not url:
        return None

    dict_str = line[dict_start:].strip()
    term_counts = parse_dict(dict_str)
    if term_counts is None:
        return None

    total_terms = int(sum(term_counts.values()))
    classification, wordpress_status = classify_e3sm_url(
        e3sm_url=url,
        url_to_status=url_to_status,
        expected_archived_urls=expected_archived_urls,
        known_ok_urls=known_ok_urls,
        keep_unchanged_urls=keep_unchanged_urls,
    )

    return SensitiveTermRecord(
        source="e3sm.org",
        raw_line=line,
        year_label="N/A",
        year_int=None,
        total_terms=total_terms,
        term_counts=term_counts,
        source_url=url,
        title=None,
        confluence_url=None,
        e3sm_url=url,
        classification=classification,
        wordpress_status=wordpress_status,
    )


def parse_confluence_record(
    line: str,
    url_to_status: Dict[str, str],
    expected_archived_urls: Set[str],
    known_ok_urls: Set[str],
    keep_unchanged_urls: Set[str],
) -> Optional[SensitiveTermRecord]:
    components = extract_confluence_components(line)
    if components is None:
        return None

    year, page_id, title, term_counts = components
    confluence_url = build_confluence_url(page_id)

    try:
        e3sm_url = map_confluence_to_e3sm(confluence_url, page_title=title)
    except Exception as exc:
        print(
            f"Could not map Confluence URL to e3sm.org URL for {confluence_url}: {exc}"
        )
        e3sm_url = None

    classification, wordpress_status = classify_e3sm_url(
        e3sm_url=e3sm_url,
        url_to_status=url_to_status,
        expected_archived_urls=expected_archived_urls,
        known_ok_urls=known_ok_urls,
        keep_unchanged_urls=keep_unchanged_urls,
    )

    total_terms = int(sum(term_counts.values()))
    year_label = str(year) if year is not None else "Unknown year"

    return SensitiveTermRecord(
        source="confluence",
        raw_line=line,
        year_label=year_label,
        year_int=year,
        total_terms=total_terms,
        term_counts=term_counts,
        source_url=confluence_url,
        title=title,
        confluence_url=confluence_url,
        e3sm_url=e3sm_url,
        classification=classification,
        wordpress_status=wordpress_status,
    )


def extract_wordpress_url(line: str) -> Optional[str]:
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    prefix = line[:dict_start].rstrip()
    if prefix.endswith(":"):
        prefix = prefix[:-1].rstrip()

    return prefix


def extract_confluence_components(
    line: str,
) -> Optional[Tuple[Optional[int], str, str, Dict[str, int]]]:
    year, remainder = extract_year_and_remainder(line)

    dict_start = remainder.find("{")
    if dict_start == -1:
        print(f"Skipping malformed Confluence line: {line}")
        return None

    dict_str = remainder[dict_start:].strip()
    term_counts = parse_dict(dict_str)
    if term_counts is None:
        print(f"Skipping malformed dictionary in Confluence line: {line}")
        return None

    prefix = remainder[:dict_start].rstrip()
    if prefix.endswith("--"):
        prefix = prefix[:-2].rstrip()

    first_colon = prefix.find(":")
    if first_colon == -1:
        print(f"Skipping malformed Confluence line: {line}")
        return None

    page_id = prefix[:first_colon].strip()
    title = prefix[first_colon + 1 :].strip()

    if not page_id.isdigit():
        print(f"Skipping Confluence line with non-numeric page id: {line}")
        return None

    return year, page_id, title, term_counts
