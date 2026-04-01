from e3sm_comms.page_reviewer.confluence_page_reviewer import run
from e3sm_comms.page_reviewer.utils_base import Config
from e3sm_comms.utils import IO_DIR


def main():
    c = Config("newsletter")
    c.file_input_story_versions = (
        f"{IO_DIR}/input/newsletter_reviewer/2026_02_newsletter.csv"
    )
    c.sensitive_terms_file = f"{IO_DIR}/input/shared/sensitive_terms.txt"
    c.first_person_file = f"{IO_DIR}/input/newsletter_reviewer/first_person_ok_urls.txt"
    c.newsletter_test_link = "https://us18.campaign-archive.com/?e=__test_email__&u=11f9e1f9713b9366390852682&id=f5a2221a36"
    c.output_dir = f"{IO_DIR}/output/newsletter_reviewer/"  # Must end with "/"
    c.requested_output = ["newsletter_review_table"]
    c.check_links_work = True
    c.scan_links_for_sensitive_terms = False
    c.confluence_api_comment_tracking_bug_exists = False
    c.read_input()
    run(c)
