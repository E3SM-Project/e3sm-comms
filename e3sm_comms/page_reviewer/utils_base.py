import getpass
import html
import json
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import requests  # type: ignore
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth  # type: ignore


# Classes #####################################################################
# Set these values in newsletter_review/main.py, resource_reviewer/main.py, website_reviewer/main.py
class Config(object):
    def __init__(self, mode: str):
        self.mode = mode
        if mode not in ["newsletter", "resource", "website"]:
            raise RuntimeError(f"Invalid Config mode={mode}")

        # Input:
        self.file_input_confluence_paths: str = ""
        self.file_input_story_versions: str = ""
        self.sensitive_terms_file: str = ""
        self.first_person_file: str = ""
        self.newsletter_test_link = ""
        # These will be set by read_input():
        self.list_input_confluence_paths: List[str] = []
        self.list_sensitive_terms: List[str] = []
        self.list_first_person_urls: List[str] = []

        # Output:
        self.output_dir = ""  # Must end with "/"
        # Options by mode:
        # newsletter: "newsletter_review_table"
        # resource: "resource_spreadsheet"
        # website: "hierarchical_outline", "sensitive_terms", "missing_metadata", "need_to_sync_wordpress"
        self.requested_output: List[str] = []

        # Flags:
        # Set to True to check all links on each page for accessibility (may be slow)
        self.check_links_work: bool = False
        # Set to True to scan all links on each page for sensitive terms (may be slow)
        # NOTE: This requires CHECK_LINKS_WORK to be True
        self.scan_links_for_sensitive_terms: bool = False
        self.confluence_api_comment_tracking_bug_exists: bool = True

        # Counter:
        self.resource_counter: int = 0

    def read_input(self):
        if self.file_input_confluence_paths:
            with open(self.file_input_confluence_paths, "r", encoding="utf-8") as f:
                self.list_input_confluence_paths = [line.strip() for line in f]
        if self.sensitive_terms_file:
            with open(self.sensitive_terms_file, "r", encoding="utf-8") as f:
                terms: List[str] = [line.rstrip("\n").lower() for line in f]
                self.list_sensitive_terms = sorted(terms)
        if self.first_person_file:
            with open(self.first_person_file, "r", encoding="utf-8") as f:
                urls: List[str] = [line.rstrip("\n").lower() for line in f]
                self.list_first_person_urls = sorted(urls)


class ConfluenceCredentials(object):
    def __init__(self):
        print(
            "If you do not have a Confluence API token, create one at https://id.atlassian.com/manage-profile/security/api-tokens. That page states 'Your API tokens need to be treated as securely as any other password.' Note that scopes will not work!! Even selecting all the classic read scopes, the request will fail with 401 Unauthorized. For added security, you can revoke your token after running this script."
        )

        self.email: str = input("Confluence email: ")
        self.api_token = getpass.getpass("Confluence API token: ")


class ConfluencePage(object):
    def __init__(self, url: str, depth: int = 0):
        self.url: str = url
        self.depth: int = depth

        match_object = re.match(
            "https://e3sm.atlassian.net/wiki/spaces/EPWCD/pages/([0-9]+)/", url
        )
        if match_object:
            page_id: str = match_object.group(1)
            self.page_id: str = page_id
        else:
            raise RuntimeError(f"Could not extract `page_id` from url={url}")

        base_url: str = "https://e3sm.atlassian.net/wiki"
        self.content_url: str = f"{base_url}/rest/api/content/{page_id}"
        self.comments_url: str = f"{base_url}/rest/api/content/{page_id}/child/comment"
        self.child_pages_url = f"{base_url}/rest/api/content/{page_id}/child/page"

        # Set by read_page_list
        self.reviewed_version: int = 0
        self.wordpress_version: int = 0
        self.review_status: str = ""

        # Set by extract_data_from_content_url
        self.title: str = ""
        self.current_version: int = 0

        # Set by extract_data_from_content_url_body
        self.main_html: Optional[ParsedHTML] = None
        self.metadata_html: Optional[ParsedHTML] = None
        self.need_to_sync_wordpress: bool = False
        self.raw_wordpress_url: Optional[str] = None
        self.display_wordpress_url: str = ""
        self.page_owner: Optional[str] = None

        # Set by extract_data_from_comments_url
        self.inline_resolved_comments: int = 0
        self.inline_open_comments: int = 0
        self.footer_resolved_comments: int = 0
        self.footer_open_comments: int = 0

        # Set by extract_data_from_child_pages_url
        self.child_page_ids: List[str] = []


class ParsedHTML(object):
    def __init__(self, raw_html: str):
        self.raw_html: str = raw_html
        soup = BeautifulSoup(raw_html, "html.parser")
        self.soup = soup

        text = soup.get_text(separator="")
        self.text = html.unescape(text)
        self.text_lowercase: str = self.text.lower()

        p_tags = soup.find_all("p")
        self.paragraphs: List[str] = [p.get_text(separator="") for p in p_tags]

        h3_tags = soup.find_all("h3")
        self.headers: List[str] = [h3.get_text(separator="") for h3 in h3_tags]

        a_tags = soup.find_all("a")
        self.links: List[str] = [a.get("href") for a in a_tags if a.get("href")]

        img_tags = soup.find_all("img")
        img_srcs: List[str] = [img.get("src") for img in img_tags if img.get("src")]
        self.img_srcs: List[str] = img_srcs
        self.num_imgs = len(img_srcs)

        # To be set later:
        self.sensitive_terms: Dict[str, int] = {}
        self.first_person_phrases: List[str] = []
        self.double_spaces_after_periods: List[str] = []
        self.img_mentions: List[int] = []
        self.img_resolutions: List[str] = []
        self.acronyms: List[str] = []
        self.linked_urls: Optional[LinkedURLs] = None


class LinkedURLs(object):
    def __init__(
        self,
        links: List[str],
        scan_links_for_sensitive_terms: bool,
        list_sensitive_terms: List[str] = [],
    ):
        links_with_sensitive_terms: Dict[str, Dict[str, int]] = {}
        e3sm_org_links_not_whitelisted: List[str] = []
        other_inaccessible_links: List[str] = []
        for link_url in links:
            known_inaccessible: bool = False
            # No point trying to read these pages:
            known_inaccessible_link_prefixes: List[str] = [
                "https://glossary.ametsoc.org/",
                "https://www.amd.com/",
                "https://agupubs.onlinelibrary.wiley.com/",
                "https://doi.org/",
                "/wiki/spaces/",
                "mailto:",
            ]
            for prefix in known_inaccessible_link_prefixes:
                if link_url.startswith(prefix):
                    print(f"  Known inaccessible link: {link_url}")
                    other_inaccessible_links.append(link_url)
                    known_inaccessible = True
                    break
            if not known_inaccessible:
                try:
                    response = requests.get(link_url, timeout=10)
                    response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
                    if scan_links_for_sensitive_terms:
                        html_content = response.content
                        soup = BeautifulSoup(html_content, "html.parser")
                        text_content = soup.get_text(separator=" ", strip=True)
                        sensitive_terms: Dict[str, int] = find_sensitive_terms(
                            list_sensitive_terms, text_content.lower()
                        )
                        if sensitive_terms:
                            links_with_sensitive_terms[link_url] = sensitive_terms
                except requests.exceptions.Timeout:
                    print(f"  Timeout when requesting {link_url}")
                    other_inaccessible_links.append(link_url)
                except requests.exceptions.RequestException as e:
                    error_message: str = f"{e}"
                    if error_message.startswith(
                        "503 Server Error: Service Temporarily Unavailable for url: https://e3sm.org"
                    ):
                        e3sm_org_links_not_whitelisted.append(link_url)
                    else:
                        other_inaccessible_links.append(link_url)
                except Exception:
                    other_inaccessible_links.append(link_url)

        self.all_links: List[str] = links
        self.links_with_sensitive_terms: Dict[str, Dict[str, int]] = (
            links_with_sensitive_terms
        )
        self.e3sm_org_links_not_whitelisted: List[str] = e3sm_org_links_not_whitelisted
        self.other_inaccessible_links: List[str] = other_inaccessible_links


# Functions used by all modes #################################################
def get_json(
    credentials: ConfluenceCredentials,
    page_id: str,
    url: str,
    params: Dict[str, str] = {},
) -> Dict:
    if params:
        resp = requests.get(
            url,
            auth=HTTPBasicAuth(credentials.email, credentials.api_token),
            params=params,
        )
    else:
        resp = requests.get(
            url, auth=HTTPBasicAuth(credentials.email, credentials.api_token)
        )
    try:
        data = resp.json()
    except RuntimeError as e:
        print(f"Response from url={url} for page_id={page_id} is not valid JSON!")
        print("Status code:", resp.status_code)
        print("Response text:", resp.text)
        raise e
    return data


def split_html(raw_html: str) -> Tuple[ParsedHTML, Optional[ParsedHTML]]:
    soup = BeautifulSoup(raw_html, "html.parser")
    # Find the span with the unique marker text
    marker_span = soup.find("span", string=lambda s: s and "END OF e3sm.or page" in s)

    if marker_span:
        marker_str = str(marker_span)
        split_index = raw_html.find(marker_str)
        main_part = raw_html[:split_index]
        metadata = raw_html[split_index:]
        return ParsedHTML(main_part), ParsedHTML(metadata)
    else:
        main_part = raw_html
        return ParsedHTML(main_part), None


def find_sensitive_terms(
    list_sensitive_terms: List[str], lowercase_text: str
) -> Dict[str, int]:
    result = {}
    for term in list_sensitive_terms:
        pattern = re.escape(term)
        matches = re.findall(pattern, lowercase_text)
        count = len(matches)
        if count > 0:
            result[term] = count
    return result


def remove_output_files(config: Config):
    files_to_remove: List[str] = []
    if config.mode == "newsletter":
        files_to_remove.append(f"{config.output_dir}version_check_results.md")
    if config.mode == "resource":
        files_to_remove.append(f"{config.output_dir}resource_spreadsheet.csv")
    if config.mode == "website":
        if "hierarchical_outline" in config.requested_output:
            files_to_remove.append(f"{config.output_dir}hierarchical_outline.txt")
        if "sensitive_terms" in config.requested_output:
            files_to_remove.append(f"{config.output_dir}sensitive_terms.txt")
        if "missing_metadata" in config.requested_output:
            files_to_remove.append(f"{config.output_dir}missing_metadata.txt")
        if "need_to_sync_wordpress" in config.requested_output:
            files_to_remove.append(f"{config.output_dir}need_to_sync_wordpress.txt")
    for filename in files_to_remove:
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            print(f"Could not remove {filename}: {e}")


# Functions used by newsletter, resource modes ################################
def map_confluence_to_e3sm(url: str, page_title: str = "") -> str:
    if page_title:
        # Map:
        trans_table = str.maketrans(
            {
                # Single characters only:
                " ": "+",
                "/": "+",
                "(": None,
                ")": None,
                ":": None,
            }
        )
        clean = page_title.strip().translate(trans_table)
        clean = clean.replace(" - ", "+")
        clean = clean.replace("+–+", "+")
        # print(f"  clean={clean}")
        confluence_slug = quote(clean, safe="+")  # percent encode other chars
        # print(f"  confluence_slug={confluence_slug}")
        if confluence_slug not in url:
            # We're going off a confluence URL with only the page ID.
            # Add the slug back in.
            url = f"{url}/{confluence_slug}"
    url = url.replace("+-+", "+")  # Otherwise, we'll get "---" in the new URL.
    url = url.replace(
        "+s+", "s+"
    )  # The Confluence URL makes "'s" "+s", so we need to join the "s" to the previous word.
    url = url.replace(
        ".+", "-"
    )  # e3sm.org URLs will have hyphens instead of ending periods.
    url = url.replace(
        ".", "-"
    )  # e3sm.org URLs will have hyphens instead of inline periods.
    # Parse the URL and extract the last path segment
    path_segments = urlparse(url).path.split("/")
    if not path_segments[-1]:
        # If URL ends with '/', get the previous segment
        title_segment = path_segments[-2]
    else:
        title_segment = path_segments[-1]
    # Decode URL-encoded characters and replace '+' with space
    title = unquote(title_segment.replace("+", " "))
    # Convert to lowercase and replace spaces with hyphens
    # From LivChat: A slug is a URL-friendly, human-readable string that identifies a particular resource (like a blog post or page) on a website.
    slug = title.lower().replace(" ", "-")
    if slug.startswith("__"):
        # Accounts for pages in "__e3sm.org Content - reorganized, updated"
        slug = slug[2:]
    # Assemble the new URL
    new_url: str = f"https://e3sm.org/{slug}/"
    return new_url


# Debugging ###################################################################
def print_json(data: Dict):
    print(json.dumps(data, indent=4))


def print_html(html: ParsedHTML):
    pretty_html: str = html.soup.prettify()
    print(pretty_html)
