import csv
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Set

import pytz  # type: ignore
import requests  # type: ignore
from bs4 import BeautifulSoup
from PIL import Image
from requests.auth import HTTPBasicAuth  # type: ignore

from e3sm_comms.page_reviewer.utils_base import (
    Config,
    ConfluenceCredentials,
    ConfluencePage,
    find_sensitive_terms,
    get_json,
    map_confluence_to_e3sm,
)

# These functions are only called in newsletter_reviewer mode #################


# read_page_list ##############################################################
def read_page_list(config: Config) -> List[ConfluencePage]:
    with open(config.file_input_story_versions, newline="") as opened_file:
        reader = csv.reader(opened_file)
        header: List[str] = []
        page_list: List[ConfluencePage] = []
        for row in reader:
            # Get labels
            if header == []:
                for label in row:
                    header.append(label.strip())
            else:
                page: Optional[ConfluencePage] = None
                for i in range(len(header)):
                    label = header[i]
                    if len(row) != len(header):
                        raise RuntimeError(
                            f"header has {len(header)} labels, but row={row} has {len(row)} entries"
                        )
                    value = row[i].strip()
                    if label == "url":
                        page = ConfluencePage(value)
                        continue
                    if page:
                        if label == "reviewed_version":
                            page.reviewed_version = 0 if value == "" else int(value)
                        if label == "wordpress_version":
                            page.wordpress_version = 0 if value == "" else int(value)
                        if label == "review_status":
                            page.review_status = value
                if page:
                    page_list.append(page)
    return page_list


# extract_data_from_content_url_body ##########################################
def skip_newsletter_metadata_in_header(raw_html: str):
    # Attempt to only process text after the line break
    # Split at the first horizontal rule, if it exists
    # Usually, stuff before that is just discussion about what to include on the page.

    # Make sure to match the first <hr> with or without attributes:
    split_html = re.split(r"<hr\b[^>]*>", raw_html, maxsplit=1, flags=re.IGNORECASE)
    main_html = split_html[1] if len(split_html) > 1 else raw_html
    return main_html


def find_first_person_phrases(paragraphs: List[str]) -> List[str]:
    # Subject Pronoun, Object Pronoun, Posessive Adjective, Posessive Pronoun, Reflexive Pronoun
    first_person_terms: Set[str] = set(
        [
            "i",
            "me",
            "my",
            "mine",
            "myself",
            "we",
            "us",
            "our",
            "ours",
            "ourselves",
        ]
    )
    found_first_person_phrases: List[str] = []
    for paragraph in paragraphs:
        text = ignore_terms_based_on_context(paragraph)
        tokens: List[str] = tokenize(text)
        found_first_person_phrases += get_terms_in_context(tokens, first_person_terms)
    return found_first_person_phrases


def ignore_terms_based_on_context(text: str) -> str:
    # Ignore Heroic Bug Fixes header
    heroic_bug_fixes = "Bugs are an inevitable part of any complex software project, and E3SM is no exception. A lot of time goes into finding and fixing bugs, the resulting impacts can rival major parameterization changes, but these efforts and their impacts frequently go unreported. Starting with this issue, Floating Points is proud to introduce Heroic Bug Fixes, a recurring column that celebrates the critical yet often overlooked work of debugging. We hope that by shining a well-deserved spotlight on this critical work we can inspire further debugging efforts across the community and provide the broader E3SM community with timely information about changes which could aid their own development and investigations."
    text = re.sub(heroic_bug_fixes, "", text)
    # us
    text = re.sub("contiguous US", "contiguous U.S.", text)
    text = re.sub("US Department", "U.S. Department", text)
    # i
    text = re.sub("Part I", "Part One", text)
    text = re.sub("I/O", "input/output", text)
    return text


def tokenize(text: str) -> List[str]:
    text = " ".join(text.split())
    # Regex for tokens: words with optional apostrophes or periods, or standalone punctuation
    token_pattern = r"\w+(?:'\w+)?(?:\.\w+)*|[^\w\s]"
    tokens = re.findall(token_pattern, text)
    return tokens


def get_terms_in_context(tokens: List[str], term_set: Set[str]) -> List[str]:
    found_phrases: List[str] = []
    for idx, token in enumerate(tokens):
        if token.lower() in term_set:
            before = tokens[idx - 1] if idx > 0 else ""
            after = tokens[idx + 1] if idx < len(tokens) - 1 else ""
            phrase = f"{before} {token} {after}".strip()
            found_phrases.append(phrase)
    return found_phrases


def find_double_spaces_after_periods(paragraphs: List[str]) -> List[str]:
    matches: List[str] = []
    for paragraph in paragraphs:
        # Literally matching spaces
        # We don't care about other whitespace characters that `\s` catches
        match_list: List[str] = re.findall(r"(\w+\.  \w+)", paragraph)
        matches.extend(match_list)
    # Markdown collapses double spaces, so let's just do that here.
    # In the table, we'll say "change to: " and then show the match with a single space.
    return [re.sub("  ", " ", match) for match in matches]


def get_image_mention_frequencies(lowercase_text: str, num_images: int) -> List[int]:
    frequencies: List[int] = [0] * num_images
    # Account for the fact there is no Fig. 0
    for i in range(1, num_images + 1):
        # Match "fig 1", "fig. 1", "figure 1", "figure. 1"
        # \b = word boundary, \.? = optional period, \s* = optional whitespace
        pattern = rf"\b(fig|figure)\.?\s*{i}\b"
        matches = re.findall(pattern, lowercase_text)
        count = len(matches)
        frequencies[i - 1] = count
    return frequencies


def get_image_resolutions(
    img_srcs: List[str], confluence_url: str, credentials: ConfluenceCredentials
) -> List[str]:
    image_resolutions: List[str] = []
    for src in img_srcs:
        # Ensure full URL if src is relative
        if src.startswith("/"):
            src = confluence_url + src
        img_resp = requests.get(
            src, auth=HTTPBasicAuth(credentials.email, credentials.api_token)
        )
        if img_resp.status_code == 200:
            img = Image.open(BytesIO(img_resp.content))
            width, height = img.size
            pixel_count = width * height
            if pixel_count > Image.MAX_IMAGE_PIXELS:
                print(
                    f"Warning: Image at {src} has {pixel_count} pixels, which exceeds PIL's maximum pixel limit."
                )
            info_str: str = f"{width}x{height}= {pixel_count:.2e} px"
            # Check for low-res indicators
            high_res_lower_bound_width: int = 800  # 3840
            high_res_lower_bound_height: int = 800  # 2160
            high_res_lower_bound_dpi: int = 70
            low_res_indicators: List[str] = []
            if width < high_res_lower_bound_width:
                low_res_indicators.append(f"width={width}")
            if height < high_res_lower_bound_height:
                low_res_indicators.append(f"height={height}")
            if "dpi" in img.info:
                dpi_x, dpi_y = img.info["dpi"]
                if dpi_x < high_res_lower_bound_dpi:
                    low_res_indicators.append(f"dpi_x={int(dpi_x)}")
                if dpi_y < high_res_lower_bound_dpi:
                    low_res_indicators.append(f"dpi_y={int(dpi_y)}")
            if low_res_indicators:
                indicator_str = ", ".join(low_res_indicators)
                resolution_inference = f"{info_str} (Low-res? {indicator_str})"
            else:
                resolution_inference = ""  # Empty as to not clutter the table
            # Add the inference
            image_resolutions.append(resolution_inference)
    return image_resolutions


def get_acronyms(text: str) -> List[str]:
    # Regex matches 2+ uppercase letters/numbers
    pattern = r"\b[A-Z0-9]{2,}\b"
    matches = set(re.findall(pattern, text))
    # List of explicit exclusions
    exclusions = {
        "CAPTION",
        "E3SM",
        "TBD",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "V8",
        "V9",
    }
    # Set of Roman numerals to exclude (add more as needed)
    roman_numerals = {"I", "II", "III"}
    filtered = [
        m
        for m in matches
        if m not in exclusions and not m.isdigit() and m not in roman_numerals
    ]
    found_acronyms = sorted(filtered)
    # Now, we only care about acronyms that are not defined in the text.
    # We can infer that an acronym is defined if it appears at least once in parentheses, e.g., `(E3SM)`.
    undefined_acronyms: List[str] = []
    for acronym in found_acronyms:
        if not re.search(rf"\({acronym}\)", text):
            undefined_acronyms.append(acronym)
    return undefined_acronyms


def filter_acronyms(
    page_url: str,
    acronyms: List[str],
    known_defined_acronyms_dict: Dict[str, Set[str]] = {},
) -> List[str]:
    filtered_acronyms: List[str] = []
    if page_url in known_defined_acronyms_dict:
        known_defined_acronyms: Set[str] = known_defined_acronyms_dict[page_url]
        found_acronyms: Set[str] = set(acronyms)
        remaining_acronyms: Set[str] = found_acronyms - known_defined_acronyms
        filtered_acronyms = sorted(list(remaining_acronyms))
    return filtered_acronyms


def set_wordpress_keys(page: ConfluencePage):
    if page.wordpress_version != 0:
        wp_url = map_confluence_to_e3sm(page.url)
        wp_is_accessible = check_wp_is_accessible(wp_url)
        page.raw_wordpress_url = wp_url
        if wp_is_accessible:
            page.display_wordpress_url = wp_url
        else:
            page.display_wordpress_url = f"Inferred {wp_url} but could not access it."


def check_wp_is_accessible(wp_url):
    try:
        response = requests.get(wp_url)
        response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
        return True
    except Exception:
        return False


# extract_data_from_comments_url ##############################################
def extract_data_from_comments_url(
    credentials: ConfluenceCredentials, page: ConfluencePage
):
    data = get_json(
        credentials,
        page.page_id,
        page.comments_url,
        params={"expand": "extensions.resolution"},
    )
    comments = data.get("results", [])

    # Initialize counters
    inline_resolved: int = 0
    inline_open: int = 0
    footer_resolved: int = 0
    footer_open: int = 0
    unaccounted: int = 0
    for comment in comments:
        location = comment.get("extensions", {}).get("location", "")
        resolution = comment.get("extensions", {}).get("resolution", {})
        resolution_status = resolution.get("status", "")
        if location == "inline" and resolution_status == "resolved":
            inline_resolved += 1
        elif location == "inline" and (resolution_status in ["open", "reopened"]):
            inline_open += 1
        elif location == "footer" and resolution_status == "resolved":
            footer_resolved += 1
        elif location == "footer" and (resolution_status in ["open", "reopened"]):
            footer_open += 1
        else:
            unaccounted += 1
            print(
                f"Warning: Unaccounted comment with ID {comment.get('id')} on page_id={page.page_id}. Location: '{location}', Resolution status: '{resolution_status}'"
            )
    page.inline_resolved_comments = inline_resolved
    page.inline_open_comments = inline_open
    page.footer_resolved_comments = footer_resolved
    page.footer_open_comments = footer_open
    if unaccounted > 0:
        print(f"Total unaccounted comments on page_id={page.page_id}: {unaccounted}")


# process_newsletter ##########################################################
def process_newsletter(
    newsletter_test_link: str, list_sensitive_terms: List[str]
) -> Dict[str, str]:
    print("Processing newsletter itself")
    url: str = newsletter_test_link.replace("e=__test_email__&", "")
    newsletter_dict: Dict[str, str] = {}
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
        html_content = response.content
        soup = BeautifulSoup(html_content, "html.parser")
        text_content = soup.get_text(separator=" ", strip=True)
        lowercase_text: str = text_content.lower()
        sensitive_terms: Dict[str, int] = find_sensitive_terms(
            list_sensitive_terms, lowercase_text
        )
        draft_terms: List[str] = find_draft_terms(lowercase_text)

        # Put text into code blocks so Markdown doens't try to render it differently.
        newsletter_dict["test_link"] = f"`{newsletter_test_link}`"
        newsletter_dict["footer_link"] = f"`{url}`"
        newsletter_dict["sensitive_terms"] = f"`{str(sensitive_terms)}`"
        newsletter_dict["draft_terms"] = f"`{str(draft_terms)}`"
    except Exception as e:
        print(f"Could not access newsletter at {url}: {e}")
    return newsletter_dict


def find_draft_terms(lowercase_text: str) -> List[str]:
    draft_terms: List[str] = ["TODO:", "TBD", "NOTE:", "DRAFT IN PROGRESS"]
    found_terms: List[str] = [
        term for term in draft_terms if term.lower() in lowercase_text
    ]
    return found_terms


# construct_markdown_table ####################################################
def construct_markdown_table(
    config: Config, page_list: List[ConfluencePage], newsletter_dict: Dict[str, str]
):
    output_file: str = f"{config.output_dir}version_check_results.md"
    timestamp = datetime.now(pytz.timezone("America/Los_Angeles")).strftime(
        "%Y_%m_%d %H:%M"
    )
    with open(output_file, "w") as f:
        f.write("# High-level summary\n\n")
        f.write(f"Status as of {timestamp} (Pacific Time)\n\n")
        if newsletter_dict:
            f.write("The newsletter itself:\n")
            f.write(f"- Test link: {newsletter_dict['test_link']}\n")
            f.write(f"- Footer link: {newsletter_dict['footer_link']}\n")
            f.write(f"- Sensitive terms found: {newsletter_dict['sensitive_terms']}\n")
            f.write(f"- Draft terms found: {newsletter_dict['draft_terms']}\n")
            f.write("\n")
        f.write("List of pages:\n\n")
        f.write(
            "Note: e3sm.org URLs below are inferred from Confluence titles; they may not be correct, especially if the Confluence draft has changed titles.\n\n"
        )
        groups = split_by_review_status(page_list)
        for status in [
            "Peter reviewed",
            "Ready for Peter",
            "Ready for Renata",
            "Draft",
        ]:
            if groups[status]:
                f.write(f"### Status: {status}\n")
                enumerate_stories(f, groups[status])
        f.write("\n")
        f.write("# Details\n\n")
        f.write(f"Status as of {timestamp} (Pacific Time)\n\n")
        if config.confluence_api_comment_tracking_bug_exists:
            f.write(
                "Note: There appears to be a new bug in the Confluence API affecting if comments show as resolved or not. Therefore, the Comments column below should be ignored -- manually check the pages for open comments.\n\n"
            )
        f.write(
            "Note: to see newly created Wordpress pages, check the version history of the [new page list](https://e3sm.atlassian.net/wiki/spaces/EPWCD/pages/5535302115/Pages+ready+to+be+created+2025-11+newsletter).\n\n"
        )
        f.write(
            "Note: to see how to add the footer to each Wordpress page, see [here](https://e3sm.atlassian.net/wiki/spaces/EPWCD/pages/5246976191/Reusable+Sections+on+WordPress#Shortcoder)\n\n"
        )
        f.write(
            "| Story | Section headers (visually check these match on the page) | Things to fix (A. Sensitive terms found, B. First person terms, with context (ignoring valid uses), C. Double spaces after periods, change to:) | Comments (A. Inline unresolved comments, B. Footer comments) | Image summary (A. Count, B. Mentions in text, C. Resolution notes) | Undefined acronyms | Links to check (A. Links with sensitive terms, B. Not-whitelisted e3sm.org pages, C. Script couldn't access)| Changes to review | Changes to port to Wordpress | Inferred e3sm.org URL |\n"
        )
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for page in page_list:
            if not page.main_html:
                print(
                    f"Warning: skipping page={page.title}, page_id={page.page_id} because html was not extracted."
                )
                continue
            story: str = f"[{page.title}]({page.url}) (v{page.current_version})"
            things_to_fix: str = combine_output_under_one_header(
                ["Sensitive", "First person", "Double spaces"],
                [
                    # Gets an ordered list of the form:
                    # 1. term1: 4
                    # 2. term2: 2
                    get_ordered_list_str_from_dict(page.main_html.sensitive_terms),
                    get_ordered_list_str(page.main_html.first_person_phrases),
                    get_ordered_list_str(page.main_html.double_spaces_after_periods),
                ],
            )
            comments: str
            if config.confluence_api_comment_tracking_bug_exists:
                comments = "N/A due to Confluence API bug"
            else:
                inline_open_comments: str = (
                    str(page.inline_open_comments)
                    if page.inline_open_comments != 0
                    else ""
                )
                num_footer_comments: int = int(page.footer_open_comments) + int(
                    page.footer_resolved_comments
                )
                footer_comments: str = (
                    str(num_footer_comments) if num_footer_comments != 0 else ""
                )
                comments = combine_output_under_one_header(
                    ["Inline unresolved", "Footer"],
                    [inline_open_comments, footer_comments],
                )
            link_list: List[str]
            if page.main_html.linked_urls:
                link_list = [
                    # Gets an ordered list of the form:
                    # 1. linked url: {'term1': 4, 'term2': 2}
                    get_ordered_list_str_from_nested_dict(
                        page.main_html.linked_urls.links_with_sensitive_terms
                    ),
                    get_ordered_list_str(
                        page.main_html.linked_urls.e3sm_org_links_not_whitelisted
                    ),
                    get_ordered_list_str(
                        page.main_html.linked_urls.other_inaccessible_links
                    ),
                ]
            else:
                link_list = ["", "", ""]
            links_to_check = combine_output_under_one_header(
                ["Sensitive", "Add to e3sm.org whitelist", "Script couldn't access"],
                link_list,
            )
            image_summary: str = combine_output_under_one_header(
                ["Count", "Mentions", "Resolution notes"],
                [
                    page.main_html.num_imgs,
                    get_ordered_list_str(page.main_html.img_mentions),
                    get_ordered_list_str(page.main_html.img_resolutions),
                ],
            )
            acronyms: str = get_ordered_list_str(page.main_html.acronyms)
            review_diff_str: str = get_diff_str(
                page.page_id, page.reviewed_version, page.current_version
            )
            wordpress_diff_str: str = get_diff_str(
                page.page_id, page.wordpress_version, page.current_version
            )

            f.write(
                f"| {story} | {get_ordered_list_str(page.main_html.headers)} | {things_to_fix} | {comments} | {image_summary} | {acronyms} | {links_to_check} | {review_diff_str} | {wordpress_diff_str} | {page.display_wordpress_url} |\n"
            )


def split_by_review_status(
    page_list: List[ConfluencePage],
) -> Dict[str, List[ConfluencePage]]:
    groups: Dict[str, List[ConfluencePage]] = {
        "Draft": [],
        "Ready for Renata": [],
        "Ready for Peter": [],
        "Peter reviewed": [],
    }
    for page in page_list:
        status = page.review_status
        if status in groups:
            groups[status].append(page)
        else:
            raise RuntimeError(f"Invalid review_status {status} in story {page.title}")
    return groups


def enumerate_stories(f, page_list: List[ConfluencePage]):
    count = 0
    for page in page_list:
        count += 1
        story: str = (
            f"{count}. [{page.title}]({page.url}) (current: v{page.current_version})"
        )
        if page.raw_wordpress_url:
            num_behind: int = page.current_version - page.wordpress_version
            story = (
                f"{story} => {page.raw_wordpress_url} ({num_behind} versions behind)"
            )
        f.write(f"{story}\n")


def combine_output_under_one_header(subheaders: List[str], values: List[Any]) -> str:
    if len(subheaders) != len(values):
        raise RuntimeError(
            f"subheaders={subheaders} and values={values} must have the same length."
        )
    output_list: List[str] = []
    for subheader, value in zip(subheaders, values):
        if value:
            output_list.append(f"{subheader}:<br/>{value}")
    return "<br/>".join(output_list)


def get_ordered_list_str(values: List[Any]) -> str:
    if values:
        return "<br/>".join(f"{i + 1}. {term}" for i, term in enumerate(values))
    else:
        return ""


def get_ordered_list_str_from_dict(mapping: Dict[str, int]) -> str:
    if not mapping:
        return ""
    items = sorted(mapping.items(), key=lambda kv: str(kv[1]))  # Sort by value

    return "<br/>".join(
        f"{i + 1}. {key}: {value}" for i, (key, value) in enumerate(items)
    )


def get_ordered_list_str_from_nested_dict(mapping: Dict[str, Dict[str, int]]) -> str:
    if not mapping:
        return ""
    compressed_dict: Dict[str, str] = {}
    meta_key: str
    for meta_key in mapping:
        # Sort nested dict by value
        nested_dict = sorted(mapping[meta_key].items(), key=lambda kv: str(kv[1]))
        compressed_dict[meta_key] = str(nested_dict)

    return "<br/>".join(
        f"{i + 1}. {meta_key}: {nested_dict_str}"
        for i, (meta_key, nested_dict_str) in enumerate(compressed_dict.items())
    )


def get_diff_str(page_id: str, compared_version: int, current_version: int) -> str:
    diff = current_version - compared_version
    if diff != 0:
        diff_str = f"[{diff} versions behind](https://e3sm.atlassian.net/wiki/pages/diffpagesbyversion.action?pageId={page_id}&selectedPageVersions={compared_version}&selectedPageVersions={current_version})"
    else:
        diff_str = ""
    return diff_str
