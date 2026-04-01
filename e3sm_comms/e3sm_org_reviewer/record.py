from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class SensitiveTermRecord:
    source: str  # "e3sm.org" or "confluence"
    raw_line: str
    year_label: str
    year_int: Optional[int]
    total_terms: int
    term_counts: Dict[str, int]
    source_url: Optional[str]
    title: Optional[str]
    confluence_url: Optional[str]
    e3sm_url: Optional[str]
    classification: str
    wordpress_status: Optional[str]
