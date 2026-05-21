# Before running:

# WordPress: Tools > Export > export pages
# WordPress: Tools > Export > export posts
# scp wordpress_pages.xml forsyth@perlmutter.nersc.gov:/global/homes/f/forsyth/ez/e3sm-comms-io/input/exported_xml_reviewer/wordpress_pages.xml
# scp wordpress_posts.xml forsyth@perlmutter.nersc.gov:/global/homes/f/forsyth/ez/e3sm-comms-io/input/exported_xml_reviewer/wordpress_posts.xml

# WordPress: CMP Settings > CMP Advanced Setup: copy the list of pages to /global/homes/f/forsyth/ez/e3sm-comms-io//input/exported_xml_reviewer/whitelisted_web_pages.txt

IO_DIR=/global/homes/f/forsyth/ez/e3sm-comms-io

echo "Count of top-level Confluence pages:"
wc -l ${IO_DIR}/input/website_reviewer/confluence_top_levels_ALL.txt

echo "Count of requested links:"
wc -l ${IO_DIR}/input/exported_xml_reviewer/requested_links.csv
echo "Count of whitelisted pages:"
wc -l ${IO_DIR}/input/exported_xml_reviewer/whitelisted_web_pages.txt

echo "Step 1. Review Confluence pages"
echo "Note: this will require a Confluence login"
e3sm-comms-website-reviewer

echo "Step 2. Review xml exported from e3sm.org"
cp ${IO_DIR}/output/website_reviewer/hierarchical_outline.txt ${IO_DIR}/input/exported_xml_reviewer/hierarchical_outline.txt
e3sm-comms-exported-xml-reviewer
echo "Output report: ${IO_DIR}/output/exported_xml_reviewer/wordpress_sensitive_terms_report.md"
