# e3sm-comms

This package is for implementing the software needs of the E3SM Communications team.

## Available commands

### Simple commands

`e3sm-comms-e3sm-org-reviewer`
- input: txt file listing e3sm.org pages to review, txt file containing phrases to search for, txt file listing e3sm.org pages that should be marked as archived
- output: txt file listing e3sm.org pages containing those phrases, txt file listing e3sm.org pages that are accessible even though they should be archived

`e3sm-comms-html-reviewer`
- input: 1 txt file of html copied from WordPress that includes yellow highlights left over from Confluence.
- output: 1 txt file of html with those highlights removed.
- Known issues: more than just `<mark>` tags are changed (presumably no other semantic changes though)

`e3sm-comms-term-reviewer`
- input: 2 txt files of sensitive terms (use the output from `e3sm-comms-e3sm-org-reviewer` & `e3sm-comms-website-reviewer`), txt file listing e3sm.org pages that should be marked as archived, txt file listing e3sm.org pages that do not contain the search terms (and presumably only show up because their corresponding Confluence pages have the terms somewhere in metadata), txt file listing e3sm.org pages that are known not to exist (either the script couldn't determine the correct e3sm.org path, or it doesn't even exist), txt file listing e3sm.org pages that are to be kept unchanged.
- output: Markdown report of terms found

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
