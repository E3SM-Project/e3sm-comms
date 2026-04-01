# Dependency hierarchy

It is important to not introduce circular dependencies.
To avoid this, the dependency hierarchy is listed below:

- Level 1: `main.py`
- Level 2: `parsers.py`, `reporters.py`
- Level 3: `classifiers.py`, `confluence.py`, `readers.py`, `record.py`, `utils.py`
