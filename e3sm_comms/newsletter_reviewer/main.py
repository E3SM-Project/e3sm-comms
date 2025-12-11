from e3sm_comms.page_reviewer.confluence_page_reviewer import run
from e3sm_comms.page_reviewer.utils_base import Config


def main():
    c = Config("newsletter")
    c.file_input_story_versions = "/home/ac.forsyth2/ez/e3sm-comms-io/input/newsletter_reviewer/2026_02_newsletter.csv"
    c.sensitive_terms_file = (
        "/home/ac.forsyth2/ez/e3sm-comms-io/input/shared/sensitive_terms.txt"
    )
    c.first_person_file = "/home/ac.forsyth2/ez/e3sm-comms-io/input/newsletter_reviewer/first_person_ok_urls.txt"
    c.newsletter_test_link = ""
    c.output_dir = "/home/ac.forsyth2/ez/e3sm-comms-io/output/newsletter_reviewer/"  # Must end with "/"
    c.requested_output = ["newsletter_review_table"]
    c.check_links_work = True
    c.scan_links_for_sensitive_terms = True
    c.confluence_api_comment_tracking_bug_exists = False
    c.read_input()
    run(c)
