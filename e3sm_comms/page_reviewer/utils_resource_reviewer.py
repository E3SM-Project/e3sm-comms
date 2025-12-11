import csv
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests  # type: ignore
from bs4 import BeautifulSoup

from e3sm_comms.page_reviewer.utils_base import (
    Config,
    ConfluencePage,
    map_confluence_to_e3sm,
)


# Class #######################################################################
class Resource(object):
    def __init__(self, resource_id: str):
        self.resource_id: str = resource_id  # Required
        self.resource_type: str = ""  # Recommended
        self.title: str = ""  # Required
        self.summary: str = ""
        self.citation: str = ""
        self.year: str = ""
        self.date: str = ""
        self.end_date: str = ""
        self.doi: str = ""
        self.link: str = ""  # Required
        self.related_assets: str = ""
        self.funding_source: str = ""
        self.project: str = ""
        self.e3sm_data_set: str = ""
        self.e3sm_simulation: str = ""
        self.tags: List[str] = []
        self.author1_first_name: str = ""
        self.author1_last_name: str = ""
        self.author_names: List[str] = []
        self.journal_short_name: str = ""
        self.llnl_flag_notes: str = ""
        self.date_added_to_spreadsheet: str = ""
        self.has_hyperarts_uploaded_this: bool = False
        self.person_adding_resource: str = ""
        self.newsletter_edition: str = ""

    def import_will_work(self):
        # From the spreadsheet:
        # In order for import to work, the "Resource ID", "Title", and "Link" columns must be filled in.
        # Additionally, Resource Type and Title should also always be provided.
        if self.resource_id and self.title and self.link and self.resource_type:
            return True
        else:
            return False

    def get_csv_row(self) -> List[str]:
        self.date_added_to_spreadsheet = datetime.now().strftime("%Y%m%d")
        return [
            self.resource_id,
            self.resource_type,
            self.title,
            self.summary,
            self.citation,
            self.year,
            self.date,
            self.end_date,
            self.doi,
            self.link,
            self.related_assets,
            self.funding_source,
            self.project,
            self.e3sm_data_set,
            self.e3sm_simulation,
            ",".join(self.tags) if self.tags else "",
            self.author1_first_name,
            self.author1_last_name,
            "; ".join(self.author_names) if self.author_names else "",
            self.journal_short_name,
            self.llnl_flag_notes,
            self.date_added_to_spreadsheet,
            "TRUE" if self.has_hyperarts_uploaded_this else "FALSE",
            self.person_adding_resource,
            self.newsletter_edition,
        ]

    # These methods correspond to the search options in the advanced-search feature.
    def can_find_by_date_range(self) -> bool:
        return bool(self.date)

    def can_find_by_year_range(self) -> bool:
        return bool(self.year)

    def can_find_by_resource_type_and_tags(self) -> bool:
        # resource_type is the full hierarchical sorting on the left hand side
        # tags are the blue boxes that appear on search results and match the resource_type hierarchy
        # That is, resource_type is the hierarchial organization of the tags
        return bool(self.resource_type) and bool(self.tags)

    def can_find_by_e3sm_dataset(self) -> bool:
        return bool(self.e3sm_data_set)

    def can_find_by_e3sm_simulation(self) -> bool:
        return bool(self.e3sm_simulation)

    def can_find_by_funding_source(self) -> bool:
        return bool(self.funding_source)

    # These methods correspond to the toggle options in the advanced-search feature.
    # These control what shows up for each search result.
    def has_toggle_for_summary(self) -> bool:
        return bool(self.summary)

    def has_toggle_for_citation(self) -> bool:
        return bool(self.citation)


# Functions: overarching process ##############################################
def process_resource(config: Config, page: ConfluencePage):
    config.resource_counter += 1
    r = Resource(str(config.resource_counter))
    r.link = map_confluence_to_e3sm(page.url, page.title)
    successful_read: bool = read_page(r)
    if successful_read:
        write_results(config, r)
    else:
        gap = "\n    "  # 4 spaces
        print(
            f"  Failed to process resource:{gap}page.url={page.url}{gap}page.title={page.title}{gap}r.link={r.link}"
        )


# Functions: reading an e3sm.org page #########################################
def read_page(resource: Resource) -> bool:
    # Return True if page was read successfully (i.e., the spreadsheet row will be usable).
    # Otherwise, return False.
    e3sm_org_link: str = ""
    if resource.link and resource.link.startswith("https://e3sm.org"):
        e3sm_org_link = resource.link
    if not e3sm_org_link:
        return False
    try:
        response = requests.get(e3sm_org_link, timeout=10)
        response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
        html_content = response.content
        soup = BeautifulSoup(html_content, "html.parser")
        info: Dict[str, Any] = extract_page_info(soup)

        hierarchy_parts: List[str] = info["hierarchy_parts"]
        if hierarchy_parts and hierarchy_parts[-1] == "News":
            if "blog" in info["categories"]:
                resource.resource_type = "News > Blog"
            if "feature story" in info["categories"]:
                resource.resource_type = "News > Feature Story"
        if not resource.resource_type:
            resource.resource_type = " > ".join(hierarchy_parts)
        resource.tags = info["categories"]  # Just set this like this for now

        resource.title = info["title"]
        resource.date, resource.year = parse_date(info["publication_date"])
        if newsletter_date_matches(info["newsletter_edition"], resource.date):
            resource.newsletter_edition = resource.date
    except requests.exceptions.Timeout:
        print(f"Timeout when requesting {e3sm_org_link}")
        return False
    except requests.exceptions.RequestException as e:
        error_message: str = f"{e}"
        if error_message.startswith(
            "503 Server Error: Service Temporarily Unavailable for url: https://e3sm.org"
        ):
            print(f"  e3sm.org page {e3sm_org_link} is not currently whitelisted.")
        return False
    except Exception:
        print(f"  e3sm.org page {e3sm_org_link} could not be accessed.")
        return False
    if resource.import_will_work():
        return True
    else:
        print("  Resource is missing vital information for the spreadsheet import.")
        return False


def extract_page_info(soup) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "hierarchy_parts": None,
        "title": None,
        "publication_date": None,
        "categories": [],
        "newsletter_edition": None,
    }

    # Extract page hierarchy from breadcrumb
    breadcrumb = soup.find("div", class_="breadcrumb")
    if breadcrumb:
        # Get all span texts from breadcrumb links
        spans = breadcrumb.find_all("span")
        hierarchy_parts = [span.get_text(strip=True) for span in spans]
        info["hierarchy_parts"] = hierarchy_parts

    # Extract title
    title_tag = soup.find("h1", class_="entry-title")
    if title_tag:
        info["title"] = title_tag.get_text(strip=True)

    # Extract publication date
    date_li = soup.find("li", class_="id")
    if date_li:
        info["publication_date"] = date_li.get_text(strip=True)

    # Extract categories
    categories_li = soup.find("li", class_="categories")
    if categories_li:
        category_links = categories_li.find_all("a")
        info["categories"] = [
            link.get_text(strip=True).lower() for link in category_links
        ]

    # Extract newsletter edition
    # Look for links containing "E3SM Floating Points" or similar newsletter text
    newsletter_link = soup.find("a", href=lambda x: x and "mailchi.mp" in x)
    if newsletter_link:
        info["newsletter_edition"] = newsletter_link.get_text(strip=True)

    return info


def parse_date(date_str: str) -> Tuple[str, str]:
    """
    Convenience function that returns (yyyymmdd, year).

    Example: "November 18, 2025" -> ("20251118", "2025")
    """
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.strftime("%Y%m%d"), dt.strftime("%Y")
    except ValueError:
        return "", ""


# Map newsletter 3-letter month abbreviations to month numbers
MONTH_ABBREV_TO_NUM = {
    "Feb": 2,
    "May": 5,
    "Aug": 8,
    "Nov": 11,
}


def newsletter_date_matches(newsletter_title: str, yyyymmdd: str) -> bool:
    """
    Check whether the yyyymmdd date matches the month and year that appear in a
    newsletter title like:
      'E3SM Floating Points, Nov ’25: Success Amidst Change'

    Returns True if month and year match, False otherwise.
    """
    # 1. Parse the yyyymmdd date
    try:
        date_obj = datetime.strptime(yyyymmdd, "%Y%m%d")
    except ValueError:
        # Invalid date
        return False

    date_year = date_obj.year
    date_month = date_obj.month

    # 2. Extract the "Mon ’YY" or "Mon 'YY" part from the title
    #    Handles both ASCII apostrophe ' and curly apostrophe ’
    pattern = r"\b([A-Z][a-z]{2})\s+[’'](\d{2})\b"
    match = re.search(pattern, newsletter_title)

    if not match:
        return False

    month_abbrev = match.group(1)
    year_two_digit = match.group(2)

    # 3. Convert month abbrev and 2-digit year to numeric values
    if month_abbrev not in MONTH_ABBREV_TO_NUM:
        return False

    title_month = MONTH_ABBREV_TO_NUM[month_abbrev]

    # Assume years are 2000–2099
    title_year = 2000 + int(year_two_digit)

    # 4. Compare
    return (date_year == title_year) and (date_month == title_month)


# Functions: output ###########################################################
def write_results(config: Config, r: Resource):
    if "resource_spreadsheet" in config.requested_output:
        with open(
            f"{config.output_dir}resource_spreadsheet.csv", "a", encoding="utf-8"
        ) as f:
            writer = csv.writer(f)
            writer.writerow(r.get_csv_row())
