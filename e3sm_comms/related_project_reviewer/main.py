import csv
import re
from pathlib import Path

from e3sm_comms.utils import IO_DIR

# 1. Go to PAMS Public Abstract Search:
# https://pamspublic.science.energy.gov/WebPAMSExternal/interface/awards/AwardSearchExternal.aspx
# 2. "Advanced Search Parameters" > "Solicitation Number like" > Enter the Solicitation Number.
# For Genesis Mission: DE-FOA-0003612 (the "Funding opportunity number" on the grants.gov link below)
# 3. At the bottom right, click "Export to Excel"
# 4. Convert to csv, and scp it to the IO DIR.
INPUT_PAMS = f"{IO_DIR}/input/related_project_reviewer/genesis_mission_awards.csv"

# grants.gov link for Genesis Mission: https://simpler.grants.gov/opportunity/0228b895-9cb3-4160-8acc-58709e75c3c7
# Download "Genesis_Mission_Phase_I_Application_Template_v2.xlsx"
# Go to "Focus Areas" sheet, which defines each focus area, in the form "1-A Topic 1 | Sub-topic A"
INPUT_FOCUS_AREAS = (
    f"{IO_DIR}/input/related_project_reviewer/genesis_mission_focus_areas.txt"
)

INPUT_KNOWN_RELEVANT_TITLES = (
    f"{IO_DIR}/input/related_project_reviewer/e3sm_related_titles.txt"
)
INPUT_KNOWN_E3SM_STAFF = f"{IO_DIR}/input/related_project_reviewer/e3sm_staff.txt"

OUTPUT_REPORT = f"{IO_DIR}/output/related_project_reviewer/related_project_report.md"


def _normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _load_lines(path):
    """Read a text file into a list of non-empty, whitespace-normalized lines."""
    with open(path, encoding="utf-8-sig") as f:
        return [_normalize(line) for line in f if _normalize(line)]


def load_known_titles(path):
    """Case-insensitive set of known-relevant titles."""
    return {t.casefold() for t in _load_lines(path)}


def load_known_staff(path):
    return _load_lines(path)


def load_focus_areas(path):
    """
    Parses lines of the form:
        1-A Topic 1 | Sub-topic A
    into {"1-A": "Topic 1 | Sub-topic A"}.
    """
    focus_areas = {}
    code_re = re.compile(r"^(\d+-[A-Za-z])\s+(.*)$")
    for line in _load_lines(path):
        m = code_re.match(line)
        if m:
            code, desc = m.group(1).upper(), m.group(2).strip()
            focus_areas[code] = desc
    return focus_areas


def find_focus_area(abstract, focus_areas):
    """
    Looks for "focus area" in the abstract, then a nearby code (e.g. "1-A").
    Falls back to scanning the whole abstract for any known code.
    Returns "CODE: description", a bare code if unmatched, or None.
    """
    if not abstract:
        return None
    for m in re.finditer(r"focus area[s]?", abstract, flags=re.IGNORECASE):
        window = abstract[m.end() : m.end() + 40]
        code_match = re.search(r"\d+-[A-Za-z]", window)
        if code_match:
            code = code_match.group(0).upper()
            return f"{code}: {focus_areas[code]}" if code in focus_areas else code
    for code, desc in focus_areas.items():
        if re.search(rf"\b{re.escape(code)}\b", abstract, flags=re.IGNORECASE):
            return f"{code}: {desc}"
    return None


def find_staff(abstract, staff_list):
    if not abstract:
        return []
    return [
        name
        for name in staff_list
        if re.search(rf"\b{re.escape(name)}\b", abstract, flags=re.IGNORECASE)
    ]


def _get_field(row, *candidates):
    """Case/whitespace-insensitive column lookup, to tolerate PAMS export naming."""
    normalized = {re.sub(r"\s+", "", k or "").casefold(): v for k, v in row.items()}
    for c in candidates:
        key = re.sub(r"\s+", "", c).casefold()
        if key in normalized:
            return normalized[key]
    return ""


def load_pams_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append(
                {
                    "Title": _normalize(
                        _get_field(row, "Title", "Award Title", "Project Title")
                    ),
                    "PI": _normalize(
                        _get_field(row, "PI", "Principal Investigator", "PI Name")
                    ),
                    "Abstract": _get_field(
                        row, "Abstract", "Abstract Text", "Public Abstract"
                    ).strip(),
                }
            )
        return rows


def build_report(rows, known_titles, staff_list, focus_areas):
    sections = []
    for row in rows:
        title = row["Title"]
        if not title or title.casefold() not in known_titles:
            continue
        abstract = row["Abstract"]
        pi = row["PI"]
        fa = find_focus_area(abstract, focus_areas)
        staff = find_staff(abstract, staff_list)
        sections.append(
            "\n".join(
                [
                    f"### {title}",
                    f"**Focus Area:** {fa if fa else '_none found_'}",
                    f"**PI:** {pi if pi else '_unknown_'}",
                    f"**E3SM Staff:** {', '.join(staff) if staff else '_none found_'}",
                    "**Abstract:**",
                    "",
                    abstract if abstract else "_no abstract available_",
                ]
            )
        )
    return "\n\n".join(sections) if sections else "_No related projects found._\n"


def main():
    rows = load_pams_rows(INPUT_PAMS)
    known_titles = load_known_titles(INPUT_KNOWN_RELEVANT_TITLES)
    staff_list = load_known_staff(INPUT_KNOWN_E3SM_STAFF)
    focus_areas = load_focus_areas(INPUT_FOCUS_AREAS)

    report = build_report(rows, known_titles, staff_list, focus_areas)

    out_path = Path(OUTPUT_REPORT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote report for {report.count('### ')} project(s) to {out_path}")


if __name__ == "__main__":
    main()
