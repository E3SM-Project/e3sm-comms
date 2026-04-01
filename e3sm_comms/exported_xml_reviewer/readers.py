from __future__ import annotations

import csv
from typing import List, Set, Tuple

from e3sm_comms.utils import normalize_url, read_lines


def read_sensitive_terms(file_path: str) -> List[str]:
    return sorted(set(read_lines(file_path, lowercase=True)))


def read_known_ok_links(file_path: str) -> Set[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        return {normalize_url(line.strip()) for line in f if line.strip()}


def read_inaccessible_prefixes(file_path: str) -> Tuple[str, ...]:
    """
    Read a plain-text file of URL prefixes (one per line) that are known to
    block automated access.  Blank lines and lines starting with '#' are
    ignored.  Returns a tuple suitable for use with str.startswith().
    """
    with open(file_path, "r", encoding="utf-8") as f:
        prefixes = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]
    return tuple(prefixes)


def read_requested_links(file_path: str) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []

    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            print(f"Requested links CSV has no headers: {file_path}")
            return rows

        normalized_to_actual = {
            header.strip().lower(): header for header in reader.fieldnames if header
        }

        e3sm_header = normalized_to_actual.get("e3sm.org link")
        requesting_header = normalized_to_actual.get(
            "list of urls that wants to link to it"
        )

        if requesting_header is None:
            for candidate in [
                "list of urls that want to link to it",
                "requesting urls",
                "requesting url",
                "list of urls",
            ]:
                requesting_header = normalized_to_actual.get(candidate)
                if requesting_header:
                    break

        if e3sm_header is None:
            print(
                f"Requested links CSV is missing required column 'e3sm.org link'. "
                f"Found headers: {reader.fieldnames}"
            )
            return rows

        if requesting_header is None:
            print(
                "Requested links CSV could not find the requesting URLs column. "
                f"Found headers: {reader.fieldnames}"
            )

        for row in reader:
            e3sm_url = normalize_url(row.get(e3sm_header, ""))
            requesting_urls = (
                row.get(requesting_header, "").strip() if requesting_header else ""
            )

            if e3sm_url:
                rows.append((e3sm_url, requesting_urls))

    return rows


def read_whitelist_patterns(file_path: str) -> List[str]:
    return read_lines(file_path)


def read_expected_archived_patterns(file_path: str) -> List[str]:
    return read_lines(file_path)


def read_keep_unchanged_links(file_path: str) -> Set[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        return {normalize_url(line.strip()) for line in f if line.strip()}
