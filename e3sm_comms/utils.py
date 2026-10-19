import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
from urllib.parse import urlsplit, urlunsplit

# Note: to use a more hardened XML library, instead use:
# import defusedxml.ElementTree as ET
# And add defusedxml to conda/dev.yml.
# However, we are only using XML files downloaded directly from WordPress.

# IO DIR ######################################################################
# Chrysalis
IO_DIR = "/home/ac.forsyth2/ez/e3sm-comms-io"

# Perlmutter
# IO_DIR = "/global/homes/f/forsyth/ez/e3sm-comms-io"

# Confluence ##################################################################


def parse_confluence_hierarchy_file(input_file: str) -> List[Tuple[str, str]]:
    parsed: List[Tuple[str, str]] = []

    with open(input_file, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue

            stripped = line.lstrip()
            if ":" not in stripped:
                print(f"Skipping malformed Confluence line {line_number}: {line}")
                continue

            page_id, title = stripped.split(":", 1)
            page_id = page_id.strip()
            title = title.strip()

            if not page_id.isdigit():
                print(
                    f"Skipping Confluence line {line_number} with non-numeric page id: {line}"
                )
                continue

            parsed.append((page_id, title))

    return parsed


# Pattern matching ############################################################


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def matches_pattern(pattern: str, url: str, normalize: bool = True) -> bool:
    if normalize:
        pattern = normalize_url(pattern)
        url = normalize_url(url)

    if "*" not in pattern:
        return pattern == url

    if pattern.count("*") == 1 and pattern.endswith("*"):
        return url.startswith(pattern[:-1])

    parts = pattern.split("*")
    position = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        found_at = url.find(part, position)
        if found_at == -1:
            return False
        if i == 0 and not pattern.startswith("*") and found_at != 0:
            return False
        position = found_at + len(part)

    if not pattern.endswith("*") and parts[-1] and not url.endswith(parts[-1]):
        return False

    return True


def expand_patterns_to_urls(
    patterns: List[str], all_urls: List[str], normalize: bool = True
) -> List[str]:
    matched: Set[str] = set()
    for pattern in patterns:
        for url in all_urls:
            if matches_pattern(pattern, url, normalize=normalize):
                matched.add(url)
    return sorted(matched)


def get_invalid_patterns(
    patterns: List[str], all_urls: List[str], normalize: bool = True
) -> List[str]:
    return sorted(
        pattern
        for pattern in patterns
        if not any(
            matches_pattern(pattern, url, normalize=normalize) for url in all_urls
        )
    )


# Sensitive term counting #####################################################


def count_sensitive_terms(
    text: str, terms: List[str], whole_words_only: bool = True
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for term in terms:
        escaped = re.escape(term)
        pattern = rf"\b{escaped}\b" if whole_words_only else escaped
        matches = re.findall(pattern, text)
        if matches:
            counts[term] = len(matches)
    return counts


# WordPress XML parsing #######################################################

WORDPRESS_NS = {"wp": "http://wordpress.org/export/1.2/"}


@dataclass
class WordpressItem:
    post_id: str
    post_parent: str
    post_type: str
    title: str
    url: str
    status: str
    body: str


def _get_item_text(item: ET.Element, tag: str, ns: bool = True) -> str:
    elem = item.find(tag, WORDPRESS_NS) if ns else item.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""


def parse_wordpress_xml_items(
    xml_file_path: str, post_type: str
) -> List[WordpressItem]:
    tree = ET.parse(xml_file_path)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return []

    items: List[WordpressItem] = []
    for item in channel.findall("item"):
        post_type_elem = item.find("wp:post_type", WORDPRESS_NS)
        if post_type_elem is None or (post_type_elem.text or "").strip() != post_type:
            continue

        items.append(
            WordpressItem(
                post_id=_get_item_text(item, "wp:post_id"),
                post_parent=_get_item_text(item, "wp:post_parent") or "0",
                post_type=post_type,
                title=_get_item_text(item, "title", ns=False) or "Untitled",
                url=normalize_url(_get_item_text(item, "link", ns=False)),
                status=_get_item_text(item, "wp:status") or "unknown",
                body=_extract_item_body(item),
            )
        )

    return items


def get_wordpress_urls_by_status(
    xml_file_path: str, post_type: str
) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    for item in parse_wordpress_xml_items(xml_file_path, post_type):
        if item.url:
            grouped[item.status].append(item.url)
    return {status: sorted(urls) for status, urls in sorted(grouped.items())}


def _extract_item_body(item: ET.Element) -> str:
    ns = {
        "wp": "http://wordpress.org/export/1.2/",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    }
    body_parts: List[str] = []

    content_elem = item.find("content:encoded", ns)
    if content_elem is not None and content_elem.text and content_elem.text.strip():
        body_parts.append(content_elem.text.strip())

    excerpt_elem = item.find("excerpt:encoded", ns)
    if excerpt_elem is not None and excerpt_elem.text and excerpt_elem.text.strip():
        body_parts.append(excerpt_elem.text.strip())

    for postmeta in item.findall("wp:postmeta", ns):
        meta_key_elem = postmeta.find("wp:meta_key", ns)
        meta_value_elem = postmeta.find("wp:meta_value", ns)
        meta_key = (
            meta_key_elem.text.strip()
            if meta_key_elem is not None and meta_key_elem.text
            else ""
        )
        meta_value = (
            meta_value_elem.text.strip()
            if meta_value_elem is not None and meta_value_elem.text
            else ""
        )
        if (
            meta_value
            and meta_key.endswith("_free_form_content")
            and not meta_key.startswith("_")
        ):
            body_parts.append(meta_value)

    return "\n".join(body_parts)


# File reading ################################################################


def read_lines(
    file_path: str,
    strip: bool = True,
    skip_empty: bool = True,
    lowercase: bool = False,
) -> List[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]
    if strip:
        lines = [line.strip() for line in lines]
    if skip_empty:
        lines = [line for line in lines if line]
    if lowercase:
        lines = [line.lower() for line in lines]
    return lines
