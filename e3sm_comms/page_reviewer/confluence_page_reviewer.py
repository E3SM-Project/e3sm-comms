import re
from typing import Dict, List

from e3sm_comms.page_reviewer.utils_base import (
    Config,
    ConfluenceCredentials,
    ConfluencePage,
    LinkedURLs,
    find_sensitive_terms,
    get_json,
    remove_output_files,
    split_html,
)
from e3sm_comms.page_reviewer.utils_newsletter_reviewer import (
    construct_markdown_table,
    extract_data_from_comments_url,
    filter_acronyms,
    find_double_spaces_after_periods,
    find_first_person_phrases,
    get_acronyms,
    get_image_mention_frequencies,
    get_image_resolutions,
    process_newsletter,
    read_page_list,
    set_wordpress_keys,
    skip_newsletter_metadata_in_header,
)
from e3sm_comms.page_reviewer.utils_resource_reviewer import process_resource
from e3sm_comms.page_reviewer.utils_website_reviewer import (
    extract_confluence_table_to_dict,
    write_results,
)


# Main functionality ##########################################################
def run(config: Config):
    remove_output_files(config)
    try:
        credentials = ConfluenceCredentials()
        if config.mode in ["resource", "website"]:
            for tab in config.list_input_confluence_paths:
                walk_page_and_child_pages(config, credentials, tab)
        if config.mode == "newsletter":
            newsletter_page_list: List[ConfluencePage] = read_page_list(config)
            for page in newsletter_page_list:
                extract_data_from_page(config, credentials, page)
            newsletter_dict: Dict[str, str]
            if config.newsletter_test_link:
                newsletter_dict = process_newsletter(
                    config.newsletter_test_link, config.list_sensitive_terms
                )
            else:
                newsletter_dict = {}
            construct_markdown_table(config, newsletter_page_list, newsletter_dict)
    finally:
        del credentials.api_token  # Clear the API token from memory, for added security


# Recurse through pages #######################################################
def walk_page_and_child_pages(
    config: Config,
    credentials: ConfluenceCredentials,
    page_url: str,
    current_depth: int = 0,
):
    current_page = ConfluencePage(page_url, current_depth)
    extract_data_from_page(config, credentials, current_page)
    if config.mode == "resource":
        process_resource(config, current_page)
    for child_page_id in current_page.child_page_ids:
        child_page_url = (
            f"https://e3sm.atlassian.net/wiki/spaces/EPWCD/pages/{child_page_id}/"
        )
        walk_page_and_child_pages(
            config, credentials, child_page_url, current_depth=current_depth + 1
        )


# Per page analysis ###############################################################
def extract_data_from_page(
    config: Config, credentials: ConfluenceCredentials, page: ConfluencePage
):
    extract_data_from_content_url(credentials, page)
    if config.mode in ["newsletter", "website"]:
        extract_data_from_content_url_body(config, credentials, page)
    if config.mode == "newsletter":
        extract_data_from_comments_url(credentials, page)
    if config.mode in ["resource", "website"]:
        extract_data_from_child_pages_url(credentials, page)
    if config.mode == "website":
        write_results(config, page)


# Functions used by all modes #################################################
def extract_data_from_content_url(
    credentials: ConfluenceCredentials, page: ConfluencePage
):
    data = get_json(credentials, page.page_id, page.content_url)
    if "title" not in data:
        raise RuntimeError(
            f"Response for page_id={page.page_id} does not contain 'title'. Full response: {data}"
        )
    page.title = re.sub(r"[\r\n]+", "", data["title"])
    print(f"Extracting data from page_id={page.page_id}, title={page.title}")
    if "version" not in data or "number" not in data["version"]:
        raise RuntimeError(
            f"Response for page_id={page.page_id} does not contain 'version' or 'version > number'. Full response: {data}"
        )
    current_version: str = data["version"]["number"]
    page.current_version = int(current_version)


# Functions used by newsletter, website modes ###################################
def extract_data_from_content_url_body(
    config: Config, credentials: ConfluenceCredentials, page: ConfluencePage
):
    data = get_json(
        credentials,
        page.page_id,
        page.content_url,
        params={"expand": "body.view.value"},
    )
    # print_json(data) # For debugging
    raw_html = data.get("body", {}).get("view", {}).get("value", "")
    if config.mode == "newsletter":
        raw_html = skip_newsletter_metadata_in_header(raw_html)
    page.main_html, page.metadata_html = split_html(raw_html)
    if config.check_links_work:
        page.main_html.linked_urls = LinkedURLs(
            page.main_html.links,
            config.scan_links_for_sensitive_terms,
            config.list_sensitive_terms,
        )
    if ("sensitive_terms" in config.requested_output) or (
        "newsletter_review_table" in config.requested_output
    ):
        page.main_html.sensitive_terms = find_sensitive_terms(
            config.list_sensitive_terms, page.main_html.text_lowercase
        )

    if "newsletter_review_table" in config.requested_output:
        if page.url not in config.list_first_person_urls:
            if any(page.page_id in url for url in config.list_first_person_urls):
                print(
                    "  Skipping first-person review. Page ID is in the approved list."
                )
            else:
                page.main_html.first_person_phrases = find_first_person_phrases(
                    page.main_html.paragraphs
                )
        else:
            print("  Skipping first-person review. Page URL is in the approved list.")
        page.main_html.double_spaces_after_periods = find_double_spaces_after_periods(
            page.main_html.paragraphs
        )
        lowercase_text: str = page.main_html.text.lower()
        page.main_html.img_mentions = get_image_mention_frequencies(
            lowercase_text, page.main_html.num_imgs
        )
        page.main_html.img_resolutions = get_image_resolutions(
            page.main_html.img_srcs, "https://e3sm.atlassian.net/wiki", credentials
        )
        acronyms = get_acronyms(
            page.main_html.text
        )  # Use original text, not lowercase_text!!
        page.main_html.acronyms = filter_acronyms(page.url, acronyms)
        set_wordpress_keys(page)
    if "need_to_sync_wordpress" in config.requested_output:
        if page.metadata_html:
            table = extract_confluence_table_to_dict(page.metadata_html)
            page.page_owner = table.get("Page Owner", "Unknown")
            if table.get("Sync to WordPress", "").lower() == "yes":
                page.need_to_sync_wordpress = True


# Functions used by resource, website modes ###################################
def extract_data_from_child_pages_url(
    credentials: ConfluenceCredentials, page: ConfluencePage
):
    data = get_json(credentials, page.page_id, page.child_pages_url)
    page.child_page_ids = [page["id"] for page in data.get("results", [])]
    count = len(page.child_page_ids)
    if count:
        print(f"  Found {count} child pages: {page.child_page_ids}")
