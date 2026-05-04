import ast
import re
from collections import defaultdict
from typing import Callable, DefaultDict, Dict, List, Optional, Tuple

from e3sm_comms.page_reviewer.utils_base import (
    get_e3sm_url_status,
    map_confluence_to_e3sm,
)
from e3sm_comms.utils import IO_DIR

INPUT_E3SM_ORG: str = f"{IO_DIR}/input/term_reviewer/wordpress_sensitive_terms.txt"
INPUT_CONFLUENCE: str = f"{IO_DIR}/input/term_reviewer/confluence_sensitive_terms.txt"
INPUT_ARCHIVED_E3SM_ORG_PATHS: str = f"{IO_DIR}/input/shared/archived_web_pages.txt"
INPUT_IGNORED_E3SM_ORG_PATHS: str = (
    f"{IO_DIR}/input/term_reviewer/ignored_e3sm_org_paths.txt"
)
OUTPUT: str = f"{IO_DIR}/output/term_reviewer/sensitive_terms.md"

CONFLUENCE_SPACE = "EPWCD"
CONFLUENCE_BASE = "https://e3sm.atlassian.net/wiki"
ARCHIVED_YEAR_LABEL = "Archived (or should be archived)"
IGNORED_YEAR_LABEL = "IGNORED (manually reviewed)"

FROM_PREFIX_RE = re.compile(r"^\[From\s+(\d{4})-\d{2}-\d{2}T[^\]]+\]\s*(.*)$")


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
        total = sum(data.values())
    except TypeError:
        return None

    if not isinstance(total, (int, float)):
        return None

    return data


def extract_year_and_remainder(line: str) -> Tuple[Optional[int], str]:
    """
    Supports lines like:
    [From 2023-04-12T21:05:24.198Z] 3746136122: Title -- {'str1': 3}
    """
    match = FROM_PREFIX_RE.match(line)
    if not match:
        return None, line

    year = int(match.group(1))
    remainder = match.group(2).strip()
    return year, remainder


def sort_and_group_by_year(input_file: str) -> Dict[str, List[Tuple[int, str]]]:
    grouped_entries: DefaultDict[str, List[Tuple[int, str]]] = defaultdict(list)

    with open(input_file, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue

            year, remainder = extract_year_and_remainder(line)
            year_key = str(year) if year is not None else "Unknown year"

            dict_start = remainder.find("{")
            if dict_start == -1:
                print(f"Skipping malformed line: {line}")
                continue

            dict_str = remainder[dict_start:].strip()
            dict_data = parse_dict(dict_str)
            if dict_data is None:
                print(f"Skipping malformed dictionary: {line}")
                continue

            total = int(sum(dict_data.values()))
            grouped_entries[year_key].append((total, remainder))

    for year_key in grouped_entries:
        grouped_entries[year_key].sort(key=lambda x: x[0], reverse=True)

    return dict(grouped_entries)


def extract_wordpress_url(line: str) -> Optional[str]:
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    prefix = line[:dict_start].rstrip()
    if prefix.endswith(":"):
        prefix = prefix[:-1].rstrip()

    return prefix


def extract_confluence_predicted_e3sm_url(line: str) -> Optional[str]:
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    prefix = line[:dict_start].rstrip()
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
        return map_confluence_to_e3sm(confluence_url, page_title=title)
    except Exception as exc:
        print(
            f"Could not map Confluence URL to e3sm.org URL for {confluence_url}: {exc}"
        )
        return None


def move_entries_to_label(
    grouped_entries: Dict[str, List[Tuple[int, str]]],
    matching_paths: List[str],
    e3sm_url_extractor: Callable[[str], Optional[str]],
    target_label: str,
) -> Dict[str, List[Tuple[int, str]]]:
    matching_set = {path.strip() for path in matching_paths if path.strip()}
    if not matching_set:
        return grouped_entries

    updated: DefaultDict[str, List[Tuple[int, str]]] = defaultdict(list)

    for year, entries in grouped_entries.items():
        for total, line in entries:
            e3sm_url = e3sm_url_extractor(line)

            if e3sm_url and e3sm_url in matching_set:
                updated[target_label].append((total, line))
            else:
                updated[year].append((total, line))

    for year_key in updated:
        updated[year_key].sort(key=lambda x: x[0], reverse=True)

    return dict(updated)


def format_wordpress_line(line: str) -> Optional[str]:
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
    dict_start = line.find("{")
    if dict_start == -1:
        return None

    counts = line[dict_start:].strip()
    prefix = line[:dict_start].rstrip()

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

    e3sm_url: Optional[str]
    try:
        e3sm_url = map_confluence_to_e3sm(confluence_url, page_title=title)
    except Exception as exc:
        print(
            f"Could not map Confluence URL to e3sm.org URL for {confluence_url}: {exc}"
        )
        e3sm_url = None

    e3sm_url_status: Optional[str] = None
    if e3sm_url:
        e3sm_url_status = get_e3sm_url_status(e3sm_url)

    md = f"{title}: [confluence]({confluence_url})"
    if e3sm_url:
        md += f" [e3sm.org]({e3sm_url})"
        if e3sm_url_status:
            md += f" (Note: {e3sm_url_status})"
    md += f" -- {counts}"

    return md


def year_sort_key(year_str: str) -> Tuple[int, int]:
    if year_str == ARCHIVED_YEAR_LABEL:
        return (1, 0)
    if year_str == IGNORED_YEAR_LABEL:
        return (2, 0)
    if year_str == "Unknown year":
        return (3, 0)
    return (0, -int(year_str))


def build_year_summary(
    grouped_entries: Dict[str, List[Tuple[int, str]]],
) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}

    for year, entries in grouped_entries.items():
        counts = {
            "total": len(entries),
            "1": 0,
            "2": 0,
            "3": 0,
            "4": 0,
            "5+": 0,
        }

        for total_terms, _ in entries:
            if total_terms == 1:
                counts["1"] += 1
            elif total_terms == 2:
                counts["2"] += 1
            elif total_terms == 3:
                counts["3"] += 1
            elif total_terms == 4:
                counts["4"] += 1
            elif total_terms >= 5:
                counts["5+"] += 1

        summary[year] = counts

    return summary


def write_summary_table(f, grouped_entries: Dict[str, List[Tuple[int, str]]]) -> None:
    summary = build_year_summary(grouped_entries)

    f.write("### Summary Table\n")
    f.write(
        "How to interpret: each cell's value is the number of pages published in year `row` that contains `col` terms\n"
    )

    f.write("| Year | Total (i.e., any number of terms) | 1 | 2 | 3 | 4 | 5+ |\n")
    f.write("| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n")

    for year in sorted(summary.keys(), key=year_sort_key):
        counts = summary[year]
        f.write(
            f"| {year} | {counts['total']} | {counts['1']} | {counts['2']} | "
            f"{counts['3']} | {counts['4']} | {counts['5+']} |\n"
        )

    f.write("\n")


def write_section(
    f,
    section_title: str,
    section_description: str,
    grouped_entries: Dict[str, List[Tuple[int, str]]],
    formatter,
) -> None:
    f.write(f"## {section_title}\n\n")
    f.write(f"Description: {section_description}\n\n")

    write_summary_table(f, grouped_entries)

    for year in sorted(grouped_entries.keys(), key=year_sort_key):
        f.write(f"### {year}\n\n")
        for idx, (_, line) in enumerate(grouped_entries[year], start=1):
            formatted = formatter(line)
            if formatted:
                f.write(f"{idx}. {formatted}\n")
        f.write("\n")


def main() -> None:
    description_e3sm_org: str = (
        "These are the currently publicly-available (whitelisted) e3sm.org pages that include sensitive terms."
    )
    description_confluence: str = (
        "These are the Confluence pages (serving as drafts of e3sm.org pages) that include sensitive terms. The 'confluence' links are what the script _actually_ reviewed. The 'e3sm.org' links are _predicted_ based on common URL naming patterns and thus may in fact be broken links. If the Confluence drafts and actual e3sm.org pages have not been kept in sync, remember that the term count is for the Confluence draft, not the actual e3sm.org page."
    )

    with open(INPUT_ARCHIVED_E3SM_ORG_PATHS, "r", encoding="utf-8") as f:
        list_input_archived_e3sm_org_paths: List[str] = [line.strip() for line in f]

    with open(INPUT_IGNORED_E3SM_ORG_PATHS, "r", encoding="utf-8") as f:
        list_input_ignored_e3sm_org_paths: List[str] = [line.strip() for line in f]

    entries_e3sm_org = sort_and_group_by_year(INPUT_E3SM_ORG)
    entries_e3sm_org = move_entries_to_label(
        entries_e3sm_org,
        list_input_archived_e3sm_org_paths,
        extract_wordpress_url,
        ARCHIVED_YEAR_LABEL,
    )
    entries_e3sm_org = move_entries_to_label(
        entries_e3sm_org,
        list_input_ignored_e3sm_org_paths,
        extract_wordpress_url,
        IGNORED_YEAR_LABEL,
    )

    entries_confluence = sort_and_group_by_year(INPUT_CONFLUENCE)
    entries_confluence = move_entries_to_label(
        entries_confluence,
        list_input_archived_e3sm_org_paths,
        extract_confluence_predicted_e3sm_url,
        ARCHIVED_YEAR_LABEL,
    )
    entries_confluence = move_entries_to_label(
        entries_confluence,
        list_input_ignored_e3sm_org_paths,
        extract_confluence_predicted_e3sm_url,
        IGNORED_YEAR_LABEL,
    )

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("# Sensitive Terms Report\n\n")

        write_section(
            f, "e3sm.org", description_e3sm_org, entries_e3sm_org, format_wordpress_line
        )
        write_section(
            f,
            "Confluence",
            description_confluence,
            entries_confluence,
            format_confluence_line,
        )


if __name__ == "__main__":
    main()
