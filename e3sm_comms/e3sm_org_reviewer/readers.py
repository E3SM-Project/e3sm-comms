from typing import Dict, List


def print_status_counts(all_urls_by_status: Dict[str, List[str]]) -> None:
    for status in ["publish", "archive", "draft", "future", "pending", "private"]:
        if status in all_urls_by_status:
            print(f"Found {len(all_urls_by_status[status])} {status} URLs")
