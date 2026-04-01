from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, List, Set, Tuple
from urllib.parse import urlsplit

import requests  # type: ignore

from e3sm_comms.exported_xml_reviewer.utils import (
    display_status,
    is_legacy_content_url,
    normalize_status,
)
from e3sm_comms.utils import WordpressItem, normalize_url

_EXTERNAL_TIMEOUT = 15  # seconds


@dataclass
class InvalidInternalLinkGroup:
    linked_url: str
    redirect_target: str
    redirect_status: str
    inferred_link: str
    found_under_different_prefix: str
    linked_target_status: str
    referenced_on_published: List[Tuple[str, str]]
    referenced_on_non_published: List[Tuple[str, str]]


@dataclass
class NonPublishedInternalLinkGroup:
    linked_url: str
    target_status: str
    referenced_on_published: List[Tuple[str, str]]
    referenced_on_non_published: List[Tuple[str, str]]


@dataclass
class ExternalLinkResult:
    """Outcome of checking a single external URL."""

    url: str
    status: str  # "valid" | "not_found" | "timed_out" | "security_error"


def extract_internal_e3sm_links(html_text: str) -> Set[str]:
    links: Set[str] = set()

    for match in re.finditer(
        r'href=["\']([^"\']+)["\']', html_text, flags=re.IGNORECASE
    ):
        href = match.group(1).strip()
        if not href:
            continue

        try:
            parts = urlsplit(href)
        except ValueError:
            continue

        host = parts.netloc.lower()
        path = parts.path.lower()

        if host == "docs.e3sm.org":
            continue

        if host.endswith("e3sm.org"):
            if path.startswith("/wp-content"):
                continue

            normalized = normalize_url(href)
            if is_legacy_content_url(normalized):
                continue

            links.add(normalized)
        elif not parts.scheme and not parts.netloc and href.startswith("/"):
            normalized_relative = normalize_url(f"https://e3sm.org{href}")
            if "/wp-content" in normalized_relative.lower():
                continue
            if is_legacy_content_url(normalized_relative):
                continue

            links.add(normalized_relative)

    return links


def check_redirect_target(link_url: str) -> Tuple[str, str]:
    try:
        response = requests.get(link_url, timeout=10, allow_redirects=True)
        redirect_status = ""

        if response.history:
            first_response = response.history[0]
            if first_response.status_code in {301, 302, 303, 307, 308} and response.ok:
                final_url = normalize_url(response.url)
                redirect_status = str(first_response.status_code)
                return final_url, redirect_status

        return "", ""

    except (requests.exceptions.Timeout, requests.exceptions.RequestException):
        return "", ""


def extract_external_links(html_text: str) -> Set[str]:
    links: Set[str] = set()
    for match in re.finditer(
        r'href=["\']([^"\']+)["\']', html_text, flags=re.IGNORECASE
    ):
        href = match.group(1).strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        try:
            parts = urlsplit(href)
        except ValueError:
            continue
        if parts.scheme not in ("http", "https"):  # changed from `if not parts.scheme`
            continue
        if not parts.netloc:
            continue
        if " " in parts.netloc:
            continue
        if parts.netloc.lower().endswith("e3sm.org"):
            continue
        links.add(href)
    return links


def check_external_link(url: str) -> ExternalLinkResult:
    """
    HEAD-then-GET a URL and return an ExternalLinkResult.

    Outcomes
    --------
    "valid"          – 2xx response (or safe redirect to one)
    "not_found"      – 4xx / 5xx response, or connection error
    "timed_out"      – requests.Timeout
    "security_error" – SSL error (mirrors Firefox "potential security risk ahead")
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; e3sm-link-checker/1.0)"}
    try:
        try:
            resp = requests.head(
                url,
                timeout=_EXTERNAL_TIMEOUT,
                allow_redirects=True,
                headers=headers,
            )
            if resp.status_code == 405:
                raise requests.exceptions.HTTPError("HEAD not allowed")
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
            resp = requests.get(
                url,
                timeout=_EXTERNAL_TIMEOUT,
                allow_redirects=True,
                headers=headers,
                stream=True,
            )
            resp.close()

        if resp.ok:
            return ExternalLinkResult(url=url, status="valid")
        return ExternalLinkResult(url=url, status="not_found")

    except requests.exceptions.Timeout:
        return ExternalLinkResult(url=url, status="timed_out")
    except requests.exceptions.SSLError:
        return ExternalLinkResult(url=url, status="security_error")
    except requests.exceptions.RequestException:
        return ExternalLinkResult(url=url, status="not_found")


def infer_likely_new_link(linked_url: str) -> str:
    parts = urlsplit(linked_url)
    path = parts.path.rstrip("/").lower()

    if path.startswith("/model"):
        suffix = parts.path[len("/model") :].lstrip("/")
        return f"https://e3sm.org/resources/model/{suffix}".rstrip("/")

    if path.startswith("/data"):
        suffix = parts.path[len("/data") :].lstrip("/")
        return f"https://e3sm.org/resources/data/{suffix}".rstrip("/")

    if path.startswith("/about/news"):
        suffix = parts.path[len("/about/news") :].lstrip("/")
        return f"https://e3sm.org/news/{suffix}".rstrip("/")

    if path.startswith("/resources/policies"):
        suffix = parts.path[len("/resources/policies") :].lstrip("/")
        return f"https://e3sm.org/policies/{suffix}".rstrip("/")

    if path.startswith("/resources/tools"):
        suffix = parts.path[len("/resources/tools") :].lstrip("/")
        return f"https://e3sm.org/tools/{suffix}".rstrip("/")

    return ""


def guess_redirect_target(linked_url: str, actual_urls: Set[str]) -> str:
    parts = urlsplit(linked_url)
    path = parts.path.strip("/").lower()

    if not path:
        return ""

    slug = path.split("/")[-1]
    candidates = []

    for actual_url in actual_urls:
        actual_parts = urlsplit(actual_url)
        actual_path = actual_parts.path.strip("/").lower()

        if actual_path.endswith("/" + slug) or actual_path == slug:
            candidates.append(normalize_url(actual_url))

    if len(candidates) == 1:
        return candidates[0]

    return ""


def build_invalid_internal_link_groups(
    items: List[WordpressItem],
) -> List[InvalidInternalLinkGroup]:
    actual_urls = {normalize_url(item.url) for item in items if item.url}
    item_by_url = {normalize_url(item.url): item for item in items if item.url}

    linked_to_sources_published: DefaultDict[str, Set[Tuple[str, str]]] = defaultdict(
        set
    )
    linked_to_sources_non_published: DefaultDict[str, Set[Tuple[str, str]]] = (
        defaultdict(set)
    )

    for item in items:
        if not item.url or not item.body:
            continue

        source_pair = (item.title, item.url)
        is_published_source = normalize_status(item.status) == "published"

        for linked_url in extract_internal_e3sm_links(item.body):
            if linked_url not in actual_urls:
                if is_published_source:
                    linked_to_sources_published[linked_url].add(source_pair)
                else:
                    linked_to_sources_non_published[linked_url].add(source_pair)

    groups: List[InvalidInternalLinkGroup] = []
    all_linked_urls = set(linked_to_sources_published) | set(
        linked_to_sources_non_published
    )

    for linked_url in all_linked_urls:
        redirect_target, redirect_status = check_redirect_target(linked_url)

        inferred_candidate = infer_likely_new_link(linked_url)
        inferred_link = (
            inferred_candidate
            if inferred_candidate and normalize_url(inferred_candidate) in actual_urls
            else ""
        )

        found_under_different_prefix = ""
        if not inferred_link:
            guessed_candidate = guess_redirect_target(linked_url, actual_urls)
            if guessed_candidate and normalize_url(guessed_candidate) in actual_urls:
                found_under_different_prefix = guessed_candidate

        status_target = inferred_link or found_under_different_prefix
        linked_target_status = ""
        if status_target:
            matched_item = item_by_url.get(normalize_url(status_target))
            if matched_item is not None:
                linked_target_status = display_status(
                    normalize_status(matched_item.status)
                )

        groups.append(
            InvalidInternalLinkGroup(
                linked_url=linked_url,
                redirect_target=redirect_target,
                redirect_status=redirect_status,
                inferred_link=inferred_link,
                found_under_different_prefix=found_under_different_prefix,
                linked_target_status=linked_target_status,
                referenced_on_published=sorted(
                    linked_to_sources_published.get(linked_url, set()),
                    key=lambda x: x[0].lower(),
                ),
                referenced_on_non_published=sorted(
                    linked_to_sources_non_published.get(linked_url, set()),
                    key=lambda x: x[0].lower(),
                ),
            )
        )

    def status_rank(status: str) -> int:
        status = status.lower()
        if status == "published":
            return 0
        if status == "archived":
            return 1
        return 2

    def inference_rank(group: InvalidInternalLinkGroup) -> int:
        if group.inferred_link:
            return 0
        if group.found_under_different_prefix:
            return 1
        return 2

    def sort_key(group: InvalidInternalLinkGroup) -> Tuple[int, int, int, str]:
        return (
            0 if group.redirect_target else 1,
            inference_rank(group),
            status_rank(group.linked_target_status),
            group.linked_url.lower(),
        )

    groups.sort(key=sort_key)
    return groups


def build_non_published_internal_link_groups(
    items: List[WordpressItem],
) -> List[NonPublishedInternalLinkGroup]:
    item_by_url = {normalize_url(item.url): item for item in items if item.url}

    linked_to_sources_published: DefaultDict[str, Set[Tuple[str, str]]] = defaultdict(
        set
    )
    linked_to_sources_non_published: DefaultDict[str, Set[Tuple[str, str]]] = (
        defaultdict(set)
    )

    for item in items:
        if not item.url or not item.body:
            continue

        source_pair = (item.title, item.url)
        is_published_source = normalize_status(item.status) == "published"

        for linked_url in extract_internal_e3sm_links(item.body):
            matched_item = item_by_url.get(normalize_url(linked_url))
            if matched_item is None:
                continue

            normalized_target_status = normalize_status(matched_item.status)
            if normalized_target_status == "published":
                continue

            if is_published_source:
                linked_to_sources_published[linked_url].add(source_pair)
            else:
                linked_to_sources_non_published[linked_url].add(source_pair)

    groups: List[NonPublishedInternalLinkGroup] = []
    all_linked_urls = set(linked_to_sources_published) | set(
        linked_to_sources_non_published
    )

    for linked_url in all_linked_urls:
        matched_item = item_by_url.get(normalize_url(linked_url))
        if matched_item is None:
            continue

        groups.append(
            NonPublishedInternalLinkGroup(
                linked_url=linked_url,
                target_status=display_status(normalize_status(matched_item.status)),
                referenced_on_published=sorted(
                    linked_to_sources_published.get(linked_url, set()),
                    key=lambda x: x[0].lower(),
                ),
                referenced_on_non_published=sorted(
                    linked_to_sources_non_published.get(linked_url, set()),
                    key=lambda x: x[0].lower(),
                ),
            )
        )

    groups.sort(
        key=lambda group: (group.target_status.lower(), group.linked_url.lower())
    )
    return groups
