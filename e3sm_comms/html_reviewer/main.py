import difflib
import re
from pathlib import Path

from bs4 import BeautifulSoup

INPUT_HTML = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/input/html_reviewer/highlighted_html.txt"
)
OUTPUT_HTML = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/output/html_reviewer/non_highlighted_html.txt"
)


def remove_inline_comment_marks(html: str) -> str:
    """
    Remove only <mark> tags with data-mark-annotation-type="inlineComment",
    preserving their inner content. Other <mark> tags are left as-is.
    """
    soup = BeautifulSoup(html, "html.parser")

    for mark in soup.find_all(
        "mark", attrs={"data-mark-annotation-type": "inlineComment"}
    ):
        mark.unwrap()

    return str(soup)


def _split_html_for_diff(html: str) -> list[str]:
    """
    Split HTML into a list of small chunks suitable for diffing.
    This version splits so that each tag and each text run is a separate item.
    """
    # This regex splits before "<" and after ">"
    # Example: "text<p>more</p>" -> ["text", "<p>", "more", "</p>"]
    parts = re.split(r"(<[^>]+>)", html)
    # Remove empty strings but keep whitespace-only chunks, since they matter in HTML
    return [p for p in parts if p != ""]


def main() -> None:
    input_path = Path(INPUT_HTML)
    output_path = Path(OUTPUT_HTML)

    # Read input HTML
    original_html = input_path.read_text(encoding="utf-8")

    # Transform
    cleaned_html = remove_inline_comment_marks(original_html)

    # Write output HTML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cleaned_html, encoding="utf-8")

    # Prepare sequences for diffing, using tag-aware splitting
    original_chunks = _split_html_for_diff(original_html)
    cleaned_chunks = _split_html_for_diff(cleaned_html)

    diff = difflib.unified_diff(
        original_chunks,
        cleaned_chunks,
        fromfile=str(input_path),
        tofile=str(output_path),
        lineterm="",  # avoid adding extra newlines
        n=3,  # context size
    )

    print("\n".join(diff))


if __name__ == "__main__":
    main()
