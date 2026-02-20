# e3sm-comms

This package is for implementing the software needs of the E3SM Communications team.

## Available commands

### Simple commands

`e3sm-comms-e3sm-org-reviewer`
- input: txt file listing e3sm.org pages to review, txt file containing phrases to search for
- output: txt file listing e3sm.org pages containing those phrases

`e3sm-comms-tree-reviewer`
- input: 2 txt files showing the website structure in hierarchical form (via indents) -- i.e. in tree form
- output: txt file listing the steps of moving subtrees to get from one tree to the other

`e3sm-comms-video-reviewer`
- input: txt file of time intervals to cut from the video, txt file of initial timestamps
- output: txt file of new timestamps after cutting the specified intervals

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
