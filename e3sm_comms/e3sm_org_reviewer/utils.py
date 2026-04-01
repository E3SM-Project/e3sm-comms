from collections import defaultdict
from typing import Dict, List


def get_list_difference(list1: List[str], list2: List[str]) -> List[str]:
    return sorted(set(list1) - set(list2))


def get_all_urls(urls_by_status: Dict[str, List[str]]) -> List[str]:
    all_urls: List[str] = []
    for urls in urls_by_status.values():
        all_urls.extend(urls)
    return sorted(all_urls)


def get_all_non_published_urls(urls_by_status: Dict[str, List[str]]) -> List[str]:
    non_published_urls: List[str] = []
    for status, urls in urls_by_status.items():
        if status != "publish":
            non_published_urls.extend(urls)
    return sorted(non_published_urls)


def get_total_count(urls_by_status: Dict[str, List[str]]) -> int:
    return sum(len(urls) for urls in urls_by_status.values())


def get_combined_urls_by_status(
    pages_by_status: Dict[str, List[str]], posts_by_status: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = defaultdict(list)
    for source in (pages_by_status, posts_by_status):
        for status, urls in source.items():
            merged[status].extend(urls)
    return {status: sorted(urls) for status, urls in sorted(merged.items())}


def get_status_counts_for_urls(
    urls: List[str], all_urls_by_status: Dict[str, List[str]], statuses: List[str]
) -> Dict[str, int]:
    url_set = set(urls)
    counts: Dict[str, int] = {}
    for status in statuses:
        counts[status] = len(url_set.intersection(all_urls_by_status.get(status, [])))
    return counts


def build_url_to_status(all_urls_by_status: Dict[str, List[str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for status, urls in all_urls_by_status.items():
        for url in urls:
            result[url] = status
    return result
