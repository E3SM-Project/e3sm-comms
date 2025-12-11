from typing import Dict

from e3sm_comms.page_reviewer.utils_base import Config, ConfluencePage, ParsedHTML


# These functions are only called in website_reviewer mode ####################
def extract_confluence_table_to_dict(parsed_html: ParsedHTML) -> Dict[str, str]:
    table = parsed_html.soup.find("table", class_="confluenceTable")
    result: Dict[str, str] = {}
    if not table:
        return result
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            # Get text, strip whitespace, join if multiple elements
            key = " ".join(cells[0].stripped_strings)
            value = " ".join(cells[1].stripped_strings)
            result[key] = value
    return result


def write_results(config: Config, page: ConfluencePage):
    line_id: str = f"{page.page_id}: {page.title}"

    if "hierarchical_outline" in config.requested_output:
        with open(
            f"{config.output_dir}hierarchical_outline.txt", "a", encoding="utf-8"
        ) as f:
            f.write(f"{page.depth * "  "}{line_id}\n")

    if "sensitive_terms" in config.requested_output:
        # Append if sensitive terms were found.
        if page.main_html and page.main_html.sensitive_terms:
            with open(
                f"{config.output_dir}sensitive_terms.txt", "a", encoding="utf-8"
            ) as f:
                f.write(f"{line_id} -- {page.main_html.sensitive_terms}\n")

    if "missing_metadata" in config.requested_output:
        # Append if there is no metadata table.
        if not page.metadata_html:
            with open(
                f"{config.output_dir}missing_metadata.txt", "a", encoding="utf-8"
            ) as f:
                f.write(f"{line_id} -- No metadata table found\n")

    if "need_to_sync_wordpress" in config.requested_output:
        # Append if e3sm.org needs to be updated accordingly.
        if page.need_to_sync_wordpress:
            with open(
                f"{config.output_dir}need_to_sync_wordpress.txt", "a", encoding="utf-8"
            ) as f:
                f.write(line_id + "\n")
