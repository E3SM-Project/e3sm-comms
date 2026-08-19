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
    """Returns (original lines, case-insensitive set) of known-relevant titles."""
    lines = _load_lines(path)
    return lines, {t.casefold() for t in lines}


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


def _reorder_pi_name(pi):
    """
    PAMS PI names are formatted "Last Name, First Name". Reorders to
    "First Name Last Name" so it can be matched against staff names the
    same way abstract text is (staff names are expected in natural order).
    Returns the input unchanged if it doesn't contain a comma.
    """
    if not pi or "," not in pi:
        return pi
    last, _, first = pi.partition(",")
    last, first = last.strip(), first.strip()
    if not last or not first:
        return pi
    return f"{first} {last}"


def find_staff_in_text(text, staff_list):
    if not text:
        return []
    return [
        name
        for name in staff_list
        if re.search(rf"\b{re.escape(name)}\b", text, flags=re.IGNORECASE)
    ]


def find_staff(abstract, pi, staff_list):
    """
    Checks both the abstract and the PI field (reordered to "First Last",
    and also checked in its raw "Last, First" form) for known E3SM staff
    names, returning a deduplicated list that preserves the order in
    which names first appear.
    """
    found = []
    for name in (
        find_staff_in_text(abstract, staff_list)
        + find_staff_in_text(_reorder_pi_name(pi), staff_list)
        + find_staff_in_text(pi, staff_list)
    ):
        if name not in found:
            found.append(name)
    return found


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


def _build_section(title, fa, pi, staff, abstract):
    """
    Builds a single project section. Metadata lines are joined with a
    trailing double-space + newline so Markdown renders them as separate
    lines within the same paragraph (a plain "\n" gets collapsed by
    Markdown renderers), rather than running together as one line.
    """
    meta_lines = [
        f"### {title}",
        f"**Focus Area:** {fa if fa else '_none found in abstract_'}",
        f"**PI:** {pi if pi else '_unknown_'}",
        f"**E3SM Staff:** {', '.join(staff) if staff else '_none found_'}",
    ]
    meta_block = "  \n".join(meta_lines)
    abstract_block = abstract if abstract else "_no abstract available_"
    return f"{meta_block}\n\n**Abstract:**\n\n{abstract_block}"


def _build_missing_section(missing_titles):
    if not missing_titles:
        return None
    bullets = "\n".join(f"- {t}" for t in missing_titles)
    return f"## Not found in PAMS export\n\n{bullets}"


def build_report(rows, known_titles_list, known_titles, staff_list, focus_areas):
    with_staff_sections = []
    without_staff_sections = []
    matched_titles = set()

    for row in rows:
        title = row["Title"]
        if not title or title.casefold() not in known_titles:
            continue
        matched_titles.add(title.casefold())
        abstract = row["Abstract"]
        pi = row["PI"]
        fa = find_focus_area(abstract, focus_areas)
        staff = find_staff(abstract, pi, staff_list)
        section = _build_section(title, fa, pi, staff, abstract)
        if staff:
            with_staff_sections.append(section)
        else:
            without_staff_sections.append(section)

    missing_titles = [
        t for t in known_titles_list if t.casefold() not in matched_titles
    ]

    if not with_staff_sections and not without_staff_sections and not missing_titles:
        return "_No related projects found._\n"

    groups = []
    if with_staff_sections:
        groups.append("## Has E3SM staff\n\n" + "\n\n".join(with_staff_sections))
    if without_staff_sections:
        groups.append("## No E3SM staff\n\n" + "\n\n".join(without_staff_sections))
    missing_section = _build_missing_section(missing_titles)
    if missing_section:
        groups.append(missing_section)

    return "\n\n".join(groups)


def _build_counts_section(rows, known_titles_list, known_titles):
    pams_titles = {row["Title"].casefold() for row in rows if row["Title"]}
    found_not_known = pams_titles - known_titles
    known_not_found = known_titles - pams_titles

    lines = [
        "## Counts",
        "",
        f"- Awards in PAMS export: {len(rows)}",
        f"- Titles in known_relevant_titles: {len(known_titles_list)}",
        f"- On PAMS but not in known_relevant_titles: {len(found_not_known)}",
        f"- In known_relevant_titles but not on PAMS: {len(known_not_found)}",
    ]
    return "\n".join(lines)


def main():
    rows = load_pams_rows(INPUT_PAMS)
    known_titles_list, known_titles = load_known_titles(INPUT_KNOWN_RELEVANT_TITLES)
    staff_list = load_known_staff(INPUT_KNOWN_E3SM_STAFF)
    focus_areas = load_focus_areas(INPUT_FOCUS_AREAS)

    counts_section = _build_counts_section(rows, known_titles_list, known_titles)
    body = build_report(rows, known_titles_list, known_titles, staff_list, focus_areas)
    report = f"{counts_section}\n\n{body}"

    out_path = Path(OUTPUT_REPORT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote report for {report.count('### ')} project(s) to {out_path}")


if __name__ == "__main__":
    main()
