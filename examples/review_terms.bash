# Before running:
# e3sm.org > CMP Settings > CMP Advanced Setup: copy the list of pages to /global/homes/f/forsyth/ez/e3sm-comms-io/input/e3sm_org_reviewer/web_pages.txt
# Also confirm confluence_top_levels_partial.txt is the list of top levels you want to use, otherwise switch it out.

IO_DIR=/global/homes/f/forsyth/ez/e3sm-comms-io

echo "Count of top-level Confluence pages:"
wc -l ${IO_DIR}/input/website_reviewer/confluence_top_levels_partial.txt # Excludes MODEL, RESEARCH, DATA
echo "Count of whitelisted e3sm.org pages":
wc -l ${IO_DIR}/input/e3sm_org_reviewer/web_pages.txt

echo "Step 1. Review Confluence"
echo "Note: this will require a Confluence login"
e3sm-comms-website-reviewer

echo "Step 2. Review e3sm.org"
e3sm-comms-e3sm-org-reviewer

echo "Step 3. Synthesize into report"
cp ${IO_DIR}/output/website_reviewer/sensitive_terms.txt ${IO_DIR}/input/term_reviewer/confluence_sensitive_terms.txt
cp ${IO_DIR}/output/e3sm_org_reviewer/found_phrases.txt ${IO_DIR}/input/term_reviewer/wordpress_sensitive_terms.txt
e3sm-comms-term-reviewer
echo "Output: ${IO_DIR}/output/term_reviewer/sensitive_terms.md"
