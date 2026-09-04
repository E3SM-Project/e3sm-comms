# e3sm-comms

This package is for implementing the software needs of the E3SM Communications team.

## Available commands

### Simple commands

`e3sm-comms-html-reviewer`
- input: 1 txt file of html copied from WordPress that includes yellow highlights left over from Confluence.
- output: 1 txt file of html with those highlights removed.
- Known issues: more than just `<mark>` tags are changed (presumably no other semantic changes though)

`e3sm-comms-tree-reviewer`
- input: 2 txt files showing the website structure in hierarchical form (via indents) -- i.e. in tree form
- output: txt file listing the steps of moving subtrees to get from one tree to the other

`e3sm-comms-video-reviewer`
- input: txt file of time intervals to cut from the video, txt file of initial timestamps
- output: txt file of new timestamps after cutting the specified intervals

`e3sm-comms-exported-xml-reviewer`
- input:
  - From WordPress under Tools > Export: xml file of WordPress pages, xml file of WordPress posts. NOTE: Only ever use the XML files downloaded directly from WordPress; the source must be trusted.
  - From output of `e3sm-comms-website-reviewer`: txt file of hierarchical outline of Confluence pages
  - Other: txt file of sensitive terms, txt file of whitelisted e3sm.org pages, txt file of links known to be inaccessible for automated review
- output: 6 files under `output/exported_xml_reviewer/`: (1) `wordpress_sensitive_terms_report.md`, (2) `wordpress_hierarchical_outline.txt`, (3) `wordpress_navigation_issues_report.md`, (4) `wordpress_invalid_internal_links_report.md`, (5) `wordpress_published_pages_link_report.md`, (6) `wordpress_invalid_external_links_report.md`
- output (optional, with `--check-non-published-access`): also `wordpress_non_published_accessibility_report.md`

### Confluence API commands (require Confluence token)

`e3sm-comms-newsletter-reviewer`
- input: csv file of newsletter stories, txt file of first-person-ok URLs, txt file of sensitive terms
- output: summary markdown file that can be copied to Confluence

`e3sm-comms-resource-reviewer`
- input: txt file of Confluence top-level pages to review
- output: csv file that attempts to approximate the resource spreadsheet

`e3sm-comms-website-reviewer`
- input: txt file of Confluence top-level pages (website tabs) to review, txt file of sensitive terms
- output: txt file showing the website structure in hierarchical form (via indents), txt file of Confluence pages missing the metadata table, txt file of pages using sensitive terms (includes counts of terms)
