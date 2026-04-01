from e3sm_comms.page_reviewer.confluence_page_reviewer import run
from e3sm_comms.page_reviewer.utils_base import Config
from e3sm_comms.utils import IO_DIR


def main():
    c = Config("website")
    # c.file_input_confluence_paths = f"{IO_DIR}/input/website_reviewer/confluence_top_level_tabs_20260109.txt"
    c.file_input_confluence_paths = (
        f"{IO_DIR}/input/website_reviewer/confluence_top_levels_ALL.txt"
    )
    c.sensitive_terms_file = f"{IO_DIR}/input/shared/sensitive_terms.txt"
    c.output_dir = f"{IO_DIR}/output/website_reviewer/"  # Must end with "/"
    c.requested_output = [
        "hierarchical_outline",
        "sensitive_terms",
        "missing_metadata",
        "need_to_sync_wordpress",
    ]
    c.check_links_work = False
    c.scan_links_for_sensitive_terms = False
    c.read_input()
    run(c)
