import ast
from typing import Dict, List, Optional, Tuple

from e3sm_comms.page_reviewer.utils_base import map_confluence_to_e3sm
from e3sm_comms.utils import IO_DIR

INPUT_E3SM_ORG: str = f"{IO_DIR}/input/term_reviewer/wordpress_sensitive_terms.txt"
INPUT_CONFLUENCE: str = f"{IO_DIR}/input/term_reviewer/confluence_sensitive_terms.txt"
OUTPUT: str = f"{IO_DIR}/output/term_reviewer/sensitive_terms.md"

CONFLUENCE_SPACE = "EPWCD"
CONFLUENCE_BASE = "https://e3sm.atlassian.net/wiki"


def build_confluence_url(page_id: str, space_key: str = CONFLUENCE_SPACE) -> str:
    return f"{CONFLUENCE_BASE}/spaces/{space_key}/pages/{page_id}"


def parse_dict(dict_str: str) -> Optional[Dict[str, int]]:
    try:
        data = ast.literal_eval(dict_str)
    except (SyntaxError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    try:
        # Force numeric validation
        total = sum(data.values())
    except TypeError:
        return None

    if not isinstance(total, (int, float)):
        return None

    return data


def sort_by_match_sum(input_file: str) -> List[Tuple[int, str]]:
    entries: List[Tuple[int, str]] = []

    with open(input_file, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue

            dict_start = line.find("{")
            if dict_start == -1:
                print(f"Skipping malformed line: {line}")
                continue

            dict_str = line[dict_start:].strip()
            dict_data = parse_dict(dict_str)
            if dict_data is None:
                print(f"Skipping malformed dictionary: {line}")
                continue

            total = int(sum(dict_data.values()))
            entries.append((total, line))

    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def format_wordpress_line(line: str) -> Optional[str]:
    """
    Input example:
    https://e3sm.org/moab-based-coupler-achieves-bit-for-bit-parity-with-legacy-system/: {'str1': 1}

    Output example:
    [https://e3sm.org/moab-based-coupler-achieves-bit-for-bit-parity-with-legacy-system/](https://e3sm.org/moab-based-coupler-achieves-bit-for-bit-parity-with-legacy-system/) -- {'str1': 1}
    """
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    prefix = line[:dict_start].rstrip()
    counts = line[dict_start:].strip()

    if prefix.endswith(":"):
        prefix = prefix[:-1].rstrip()

    url = prefix
    return f"[{url}]({url}) -- {counts}"


def format_confluence_line(line: str) -> Optional[str]:
    """
    Input example:
    3841294373: E3SM Publicity -- {'str1': 85, 'str2': 20, 'str3': 2}

    Output example:
    E3SM Publicity: [confluence](https://e3sm.atlassian.net/wiki/spaces/EPWCD/pages/3841294373) [e3sm.org](https://e3sm.org/e3sm-publicity) -- {'str1': 85, 'str2': 20, 'str3': 2}
    """
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    counts = line[dict_start:].strip()
    prefix = line[:dict_start].rstrip()

    # Expected prefix format:
    # "<page_id>: <title> --"
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

    confluence_url = build_confluence_url(page_id)

    try:
        e3sm_url = map_confluence_to_e3sm(confluence_url, page_title=title)
    except Exception as exc:
        print(
            f"Could not map Confluence URL to e3sm.org URL for {confluence_url}: {exc}"
        )
        e3sm_url = None

    md = f"{title}: [confluence]({confluence_url})"
    if e3sm_url:
        md += f" [e3sm.org]({e3sm_url})"
    md += f" -- {counts}"

    return md


def main() -> None:
    entries_e3sm_org: List[Tuple[int, str]] = sort_by_match_sum(INPUT_E3SM_ORG)
    entries_confluence: List[Tuple[int, str]] = sort_by_match_sum(INPUT_CONFLUENCE)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("# Sensitive Terms Report\n\n")

        f.write("## e3sm.org\n\n")
        for _, line in entries_e3sm_org:
            formatted = format_wordpress_line(line)
            if formatted:
                f.write(f"- {formatted}\n")

        f.write("\n## Confluence\n\n")
        for _, line in entries_confluence:
            formatted = format_confluence_line(line)
            if formatted:
                f.write(f"- {formatted}\n")
