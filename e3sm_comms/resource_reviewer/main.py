from e3sm_comms.page_reviewer.confluence_page_reviewer import run
from e3sm_comms.page_reviewer.utils_base import Config


def main():
    c = Config("resource")
    c.file_input_confluence_paths = "/home/ac.forsyth2/ez/e3sm-comms-io/input/resource_reviewer/resource_top_levels.txt"
    c.output_dir = "/home/ac.forsyth2/ez/e3sm-comms-io/output/resource_reviewer/"  # Must end with "/"
    c.requested_output = ["resource_spreadsheet"]
    c.check_links_work = False
    c.scan_links_for_sensitive_terms = False
    c.read_input()
    run(c)
