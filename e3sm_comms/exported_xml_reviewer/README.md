# Dependency hierarchy

It is important to not introduce circular dependencies.
To avoid this, the dependency hierarchy is listed below:

- Level 1: `main.py`
- Level 2: `builders.py`
- Level 3: `confluence.py`, `link_analysis.py`, `readers.py`
- Level 4: `utils.py`
