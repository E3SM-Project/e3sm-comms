from e3sm_comms.page_reviewer.confluence_page_reviewer import run
from e3sm_comms.page_reviewer.utils_base import Config


def main():
    c = Config("website")
    c.file_input_confluence_paths = "/home/ac.forsyth2/ez/e3sm-comms-io/input/website_reviewer/confluence_top_level_tabs_20260109.txt"
    # c.file_input_confluence_paths = "/home/ac.forsyth2/ez/e3sm-comms-io/input/website_reviewer/confluence_top_levels_ALL.txt"
    c.sensitive_terms_file = (
        "/home/ac.forsyth2/ez/e3sm-comms-io/input/shared/sensitive_terms.txt"
    )
    c.output_dir = "/home/ac.forsyth2/ez/e3sm-comms-io/output/website_reviewer/"  # Must end with "/"
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
