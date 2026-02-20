# Dependency hierarchy

It is important to not introduce circular dependencies.
To avoid this, the dependency hierarchy is listed below:

- Top level: `confluence_page_reviewer.py`
- Mid level: `utils_*_reviewer.py`
- Base level: `utils_base.py`
