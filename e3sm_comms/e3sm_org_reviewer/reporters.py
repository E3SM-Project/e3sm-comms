from collections import defaultdict
from typing import Callable, DefaultDict, Dict, List, Set, TextIO

from e3sm_comms.e3sm_org_reviewer.classifiers import (
    classification_sort_key,
    year_sort_key,
)
from e3sm_comms.e3sm_org_reviewer.record import SensitiveTermRecord
from e3sm_comms.e3sm_org_reviewer.utils import get_all_urls, get_status_counts_for_urls
from e3sm_comms.page_reviewer.utils_base import get_e3sm_url_status
from e3sm_comms.utils import expand_patterns_to_urls


def write_markdown_report(
    output_path: str,
    all_urls_by_status: Dict[str, List[str]],
    valid_whitelisted_paths: List[str],
    valid_expected_archived_paths: List[str],
    valid_confluence_paths: List[str],
    whitelisted_but_not_published: List[str],
    published_but_not_whitelisted: List[str],
    should_be_archived: List[str],
    published_but_not_in_confluence: List[str],
    published_not_whitelisted_and_not_in_confluence: List[str],
    incorrectly_accessible_non_published_urls: List[str],
    invalid_whitelisted_paths: List[str],
    invalid_expected_archived_paths: List[str],
    invalid_confluence_paths: List[str],
    confluence_unmapped_entries: List[str],
) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        write_summary_table(
            f,
            all_urls_by_status=all_urls_by_status,
            valid_whitelisted_paths=valid_whitelisted_paths,
            valid_expected_archived_paths=valid_expected_archived_paths,
            valid_confluence_paths=valid_confluence_paths,
            invalid_confluence_paths=invalid_confluence_paths,
            confluence_unmapped_entries=confluence_unmapped_entries,
        )

        f.write("# Valid Paths\n\n")
        write_markdown_section(
            f,
            "Whitelisted but not published",
            whitelisted_but_not_published,
        )
        write_markdown_section(
            f,
            "Published but not whitelisted",
            published_but_not_whitelisted,
        )
        write_markdown_section(
            f,
            "Expecting to be archived, but not yet archived",
            should_be_archived,
        )
        write_markdown_section(
            f,
            "Published but no matching Confluence path found",
            published_but_not_in_confluence,
        )
        write_markdown_section(
            f,
            "Published but not whitelisted and no matching Confluence path found",
            published_not_whitelisted_and_not_in_confluence,
        )
        write_markdown_section(
            f,
            "Non-published e3sm.org pages that are still accessible without login",
            incorrectly_accessible_non_published_urls,
        )

        f.write("# Invalid Paths\n\n")
        write_markdown_section(
            f,
            "Identified in whitelist input",
            invalid_whitelisted_paths,
        )
        write_markdown_section(
            f,
            "Identified in archive input",
            invalid_expected_archived_paths,
        )
        write_markdown_section(
            f,
            "Identified in Confluence input",
            invalid_confluence_paths,
        )
        write_markdown_section(
            f,
            "Confluence pages with no mappable e3sm.org URL",
            confluence_unmapped_entries,
        )


def write_summary_table(
    file_obj: TextIO,
    all_urls_by_status: Dict[str, List[str]],
    valid_whitelisted_paths: List[str],
    valid_expected_archived_paths: List[str],
    valid_confluence_paths: List[str],
    invalid_confluence_paths: List[str],
    confluence_unmapped_entries: List[str],
) -> None:
    statuses: List[str] = sorted(all_urls_by_status.keys())
    all_urls: List[str] = get_all_urls(all_urls_by_status)

    whitelist_set: Set[str] = set(
        expand_patterns_to_urls(valid_whitelisted_paths, all_urls)
    )
    expected_archived_set: Set[str] = set(
        expand_patterns_to_urls(valid_expected_archived_paths, all_urls)
    )
    both_set: Set[str] = whitelist_set.intersection(expected_archived_set)
    neither_set: Set[str] = set(all_urls) - whitelist_set.union(expected_archived_set)

    rows = [
        ("Whitelisted URLs", whitelist_set),
        ("Expected archived", expected_archived_set),
        ("Both whitelisted and expected archived", both_set),
        ("Neither whitelisted nor expected archived", neither_set),
        ("TOTAL", set(all_urls)),
    ]

    file_obj.write("# Summary\n\n")
    file_obj.write("| Type | " + " | ".join(statuses) + " | Total |\n")
    file_obj.write("| --- | " + " | ".join("---" for _ in statuses) + " | --- |\n")

    for row_name, row_urls in rows:
        counts = get_status_counts_for_urls(
            urls=list(row_urls),
            all_urls_by_status=all_urls_by_status,
            statuses=statuses,
        )
        total_count = sum(counts.values())
        file_obj.write(
            f"| {row_name} | "
            + " | ".join(str(counts[status]) for status in statuses)
            + f" | {total_count} |\n"
        )

    confluence_valid_set: Set[str] = set(valid_confluence_paths)
    all_urls_set: Set[str] = set(all_urls)

    e3sm_with_confluence: Set[str] = all_urls_set.intersection(confluence_valid_set)
    e3sm_without_confluence: Set[str] = all_urls_set - confluence_valid_set

    confluence_not_valid_count: int = len(invalid_confluence_paths) + len(
        confluence_unmapped_entries
    )
    total_confluence_urls: int = len(confluence_valid_set) + confluence_not_valid_count
    total_e3sm_urls: int = len(all_urls_set)

    confluence_counts_match: bool = (
        confluence_not_valid_count + len(e3sm_with_confluence) == total_confluence_urls
    )
    e3sm_counts_match: bool = (
        len(e3sm_without_confluence) + len(e3sm_with_confluence) == total_e3sm_urls
    )

    file_obj.write("\n## Confluence Mapping Summary\n\n")
    file_obj.write("| Type | Count |\n")
    file_obj.write("| --- | --- |\n")
    file_obj.write(
        f"| Confluence paths that do not map to a valid e3sm.org path | {confluence_not_valid_count} |\n"
    )
    file_obj.write(
        f"| e3sm.org paths that do not have a Confluence path associated with them | {len(e3sm_without_confluence)} |\n"
    )
    file_obj.write(
        f"| e3sm.org paths that do have a Confluence counterpart | {len(e3sm_with_confluence)} |\n"
    )
    file_obj.write(f"| Total Confluence-derived paths | {total_confluence_urls} |\n")
    file_obj.write(f"| Total e3sm.org paths | {total_e3sm_urls} |\n")
    file_obj.write("\n")

    file_obj.write("Validation:\n\n")
    file_obj.write(
        f"- Confluence counts match: "
        f"{confluence_not_valid_count} + {len(e3sm_with_confluence)} = {total_confluence_urls} "
        f"({'yes' if confluence_counts_match else 'no'})\n"
    )
    file_obj.write(
        f"- e3sm.org counts match: "
        f"{len(e3sm_without_confluence)} + {len(e3sm_with_confluence)} = {total_e3sm_urls} "
        f"({'yes' if e3sm_counts_match else 'no'})\n\n"
    )


def write_markdown_section(file_obj: TextIO, title: str, items: List[str]) -> None:
    file_obj.write(f"## {title}\n\n")
    if not items:
        file_obj.write("_None._\n\n")
        return

    for i, item in enumerate(items, start=1):
        file_obj.write(f"{i}. {item}\n")
    file_obj.write("\n")


def write_action_items_report(
    output_path: str,
    should_be_archived: List[str],
    published_not_whitelisted_and_not_in_confluence: List[str],
    confluence_published_sensitive_records: List[SensitiveTermRecord],
) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Action Items Report\n\n")

        f.write("## Summary\n\n")
        f.write("| Action Area | Count |\n")
        f.write("| --- | ---: |\n")
        f.write(
            f"| Expecting to be archived, but not yet archived | {len(should_be_archived)} |\n"
        )
        f.write(
            f"| Published but not whitelisted and no matching Confluence path found | {len(published_not_whitelisted_and_not_in_confluence)} |\n"
        )
        f.write(
            f"| Confluence pages with sensitive terms mapped to published e3sm.org pages | {len(confluence_published_sensitive_records)} |\n"
        )
        f.write("\n")

        write_markdown_section(
            f,
            "Expecting to be archived, but not yet archived",
            should_be_archived,
        )

        write_markdown_section(
            f,
            "Published but not whitelisted and no matching Confluence path found",
            published_not_whitelisted_and_not_in_confluence,
        )

        write_action_items_confluence_section(f, confluence_published_sensitive_records)


def write_action_items_confluence_section(
    f: TextIO, records: List[SensitiveTermRecord]
) -> None:
    f.write(
        "## Confluence pages with sensitive terms mapped to published e3sm.org pages\n\n"
    )

    if not records:
        f.write("_None._\n\n")
        return

    grouped = group_records_by_classification_and_year(records)

    for classification in sorted(grouped.keys(), key=classification_sort_key):
        f.write(f"### {classification}\n\n")

        for year_label in sorted(grouped[classification].keys(), key=year_sort_key):
            f.write(f"#### {year_label}\n\n")
            for idx, record in enumerate(grouped[classification][year_label], start=1):
                f.write(f"{idx}. {format_confluence_record(record)}\n")
            f.write("\n")


def write_sensitive_terms_report(
    output_path: str,
    e3sm_records: List[SensitiveTermRecord],
    confluence_records: List[SensitiveTermRecord],
) -> None:
    description_e3sm_org = (
        "These are the currently reviewed e3sm.org pages that include sensitive terms. "
        "Classification is derived from WordPress status, expected archived inputs, and the manual exception lists for known-ok and keep-unchanged paths."
    )
    description_confluence = (
        "These are the Confluence pages that include sensitive terms. The confluence links are what the website reviewer scanned. "
        "The e3sm.org links are predicted from Confluence mapping and then classified against the WordPress export."
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Sensitive Terms Report\n\n")

        write_sensitive_terms_section(
            f,
            "e3sm.org",
            description_e3sm_org,
            e3sm_records,
            format_e3sm_record,
        )
        write_sensitive_terms_section(
            f,
            "Confluence",
            description_confluence,
            confluence_records,
            format_confluence_record,
        )


def write_sensitive_terms_section(
    f: TextIO,
    section_title: str,
    description: str,
    records: List[SensitiveTermRecord],
    formatter: Callable[[SensitiveTermRecord], str],
) -> None:
    f.write(f"## {section_title}\n\n")
    f.write(f"{description}\n\n")

    write_sensitive_terms_summary_table(f, records)

    grouped = group_records_by_classification_and_year(records)

    for classification in sorted(grouped.keys(), key=classification_sort_key):
        f.write(f"### {classification}\n\n")

        for year_label in sorted(grouped[classification].keys(), key=year_sort_key):
            f.write(f"#### {year_label}\n\n")
            for idx, record in enumerate(grouped[classification][year_label], start=1):
                f.write(f"{idx}. {formatter(record)}\n")
            f.write("\n")


def write_sensitive_terms_summary_table(
    f: TextIO, records: List[SensitiveTermRecord]
) -> None:
    summary = build_classification_summary(records)

    f.write("### Summary Table\n\n")
    f.write("| Classification | Total | 1 | 2 | 3 | 4 | 5+ |\n")
    f.write("| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n")

    for classification in sorted(summary.keys(), key=classification_sort_key):
        counts = summary[classification]
        f.write(
            f"| {classification} | {counts['total']} | {counts['1']} | {counts['2']} | "
            f"{counts['3']} | {counts['4']} | {counts['5+']} |\n"
        )

    f.write("\n")


def format_e3sm_record(record: SensitiveTermRecord) -> str:
    url = record.e3sm_url or record.source_url or "UNKNOWN"
    md = f"[{url}]({url})"
    if record.wordpress_status:
        md += f" (status: {record.wordpress_status})"
    md += f" -- {format_term_counts(record.term_counts)}"
    return md


def format_confluence_record(record: SensitiveTermRecord) -> str:
    title = record.title or "Untitled"
    confluence_url = record.confluence_url or record.source_url or ""
    md = f"{title}: [confluence]({confluence_url})"

    if record.e3sm_url:
        md += f" [e3sm.org]({record.e3sm_url})"

        try:
            e3sm_url_status = get_e3sm_url_status(record.e3sm_url)
        except Exception as exc:
            print(f"Could not get e3sm.org URL status for {record.e3sm_url}: {exc}")
            e3sm_url_status = None

        if e3sm_url_status:
            md += f" (Note: {e3sm_url_status})"

        if record.wordpress_status:
            md += f" (WordPress status: {record.wordpress_status})"

    md += f" -- {format_term_counts(record.term_counts)}"
    return md


def format_term_counts(term_counts: Dict[str, int]) -> str:
    return str(term_counts)


def build_classification_summary(
    records: List[SensitiveTermRecord],
) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}

    for record in records:
        classification = record.classification
        if classification not in summary:
            summary[classification] = {
                "total": 0,
                "1": 0,
                "2": 0,
                "3": 0,
                "4": 0,
                "5+": 0,
            }

        summary[classification]["total"] += 1
        if record.total_terms == 1:
            summary[classification]["1"] += 1
        elif record.total_terms == 2:
            summary[classification]["2"] += 1
        elif record.total_terms == 3:
            summary[classification]["3"] += 1
        elif record.total_terms == 4:
            summary[classification]["4"] += 1
        elif record.total_terms >= 5:
            summary[classification]["5+"] += 1

    return summary


def group_records_by_classification_and_year(
    records: List[SensitiveTermRecord],
) -> Dict[str, Dict[str, List[SensitiveTermRecord]]]:
    grouped: DefaultDict[str, DefaultDict[str, List[SensitiveTermRecord]]] = (
        defaultdict(lambda: defaultdict(list))
    )

    for record in records:
        grouped[record.classification][record.year_label].append(record)

    for classification in grouped:
        for year_label in grouped[classification]:
            grouped[classification][year_label].sort(
                key=lambda r: (r.total_terms, r.e3sm_url or "", r.title or ""),
                reverse=True,
            )

    return {k: dict(v) for k, v in grouped.items()}
