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
# Text file listing, one per line, the Title (as it appears in the PAMS
# export) of any project whose PAMS abstract text is malformed. Matched
# projects are pulled out of the "Has E3SM staff" / "No E3SM staff"
# groups and reported instead under their own "Malformed Abstracts"
# h2 section, with project details rendered exactly as they otherwise
# would be.
INPUT_MALFORMED_ABSTRACTS = (
    f"{IO_DIR}/input/related_project_reviewer/malformed_abstracts.txt"
)


# CSV of E3SM-related awards tracked on Confluence, with keys:
#   PI Last Name,PI First Name,Title,Genesis Mission Focus Area,Known E3SM Staff
# Each row is a known-relevant award. "Title" and PI name are used to
# match against the PAMS export (title first, PI as a fallback when no
# title match is found). "Genesis Mission Focus Area" is the focus area
# code (e.g. "15-C") as recorded on Confluence, which is reported
# alongside any focus area code found in the PAMS abstract text.
# "Known E3SM Staff" is either "No" or a semi-colon-separated list of
# E3SM staff names known (via Confluence) to be involved with the
# project. This is reported alongside (and merged with) any staff names
# found by scanning the PAMS abstract/PI text, and is used to determine
# which report section a project lands in — it does not affect matching
# against PAMS.
INPUT_KNOWN_RELEVANT_AWARDS = (
    f"{IO_DIR}/input/related_project_reviewer/e3sm_related_awards.csv"
)
INPUT_KNOWN_E3SM_STAFF = f"{IO_DIR}/input/related_project_reviewer/e3sm_staff.txt"

OUTPUT_REPORT = f"{IO_DIR}/output/related_project_reviewer/related_project_report.md"


def _normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _load_lines(path):
    """Read a text file into a list of non-empty, whitespace-normalized lines."""
    with open(path, encoding="utf-8-sig") as f:
        lines = []
        for line in f:
            norm = _normalize(line)
            if norm:
                lines.append(norm)
        return lines


def load_known_staff(path):
    return _load_lines(path)


def load_malformed_titles(path):
    """
    Reads malformed_abstracts.txt (one PAMS Title per line) into a set of
    casefolded titles, used to route matched projects into the
    "Malformed Abstracts" report section instead of the staff-based ones.
    """
    return {title.casefold() for title in _load_lines(path)}


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


def find_focus_area_code(abstract, focus_areas):
    """
    Looks for "focus area" in the abstract, then a nearby code (e.g. "1-A").
    Falls back to scanning the whole abstract for any known code.
    Returns the bare code (e.g. "1-A") if found, else None.
    """
    if not abstract:
        return None
    for m in re.finditer(r"focus area[s]?", abstract, flags=re.IGNORECASE):
        window = abstract[m.end() : m.end() + 40]
        code_match = re.search(r"\d+-[A-Za-z]", window)
        if code_match:
            return code_match.group(0).upper()
    for code in focus_areas:
        if re.search(rf"\b{re.escape(code)}\b", abstract, flags=re.IGNORECASE):
            return code
    return None


def _format_focus_area(code, focus_areas):
    """Renders a bare code as "CODE: description" when the description is
    known, otherwise just the bare code."""
    return f"{code}: {focus_areas[code]}" if code in focus_areas else code


def combine_focus_area_display(abstract_code, confluence_code, focus_areas):
    """
    Builds the "Focus Area" line for a project from up to two sources:
    a code found in the PAMS abstract text, and a code noted on Confluence
    (from the known_relevant_awards CSV). Each source is labeled, e.g.:
        "15-A (found in abstract), 15-C (noted on Confluence)"
    If both sources agree on the same code, it's shown once with both
    labels attached. Returns None if neither source has a code.
    """
    if not abstract_code and not confluence_code:
        return None
    if (
        abstract_code
        and confluence_code
        and abstract_code.upper() == confluence_code.upper()
    ):
        return (
            f"{_format_focus_area(abstract_code, focus_areas)} "
            "(found in abstract, noted on Confluence)"
        )
    parts = []
    if abstract_code:
        parts.append(
            f"{_format_focus_area(abstract_code, focus_areas)} (found in abstract)"
        )
    if confluence_code:
        parts.append(
            f"{_format_focus_area(confluence_code, focus_areas)} (noted on Confluence)"
        )
    return ", ".join(parts)


def combine_staff_display(abstract_staff, confluence_staff):
    """
    Merges E3SM staff found by scanning the PAMS abstract/PI text with
    E3SM staff noted on Confluence (the known_relevant_awards CSV's
    "Known E3SM Staff" column) into a single ordered list of
    "Name (source)" display strings, e.g.:
        ["NameA (found in abstract and noted on Confluence)",
         "nameB (found in abstract)",
         "NameC (noted on Confluence)"]

    Names are matched between the two lists case-insensitively (so minor
    casing differences between the abstract text and the Confluence CSV
    don't produce duplicate entries). Abstract-found names are listed
    first (in the order they were found), followed by any
    Confluence-only names. When a name appears in both lists, the
    abstract's casing/spelling is used for display.
    """
    confluence_casefold = {n.casefold() for n in confluence_staff}

    entries = []
    seen = set()
    for name in abstract_staff:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        if key in confluence_casefold:
            entries.append(f"{name} (found in abstract and noted on Confluence)")
        else:
            entries.append(f"{name} (found in abstract)")
    for name in confluence_staff:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        entries.append(f"{name} (noted on Confluence)")
    return entries


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


def _pi_variants(pi):
    """
    Returns a set of casefolded variants of a PI name, covering both
    "Last, First" and "First Last" orderings, so names can be matched
    regardless of which format a given source (PAMS export vs. the
    known_relevant_awards CSV) happens to use.
    """
    if not pi:
        return set()
    variants = {pi.casefold()}
    reordered = _reorder_pi_name(pi)
    if reordered:
        variants.add(reordered.casefold())
    return variants


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


def _get_known_award_pi(row):
    """
    Builds the PI field for a known_relevant_awards row as "Last, First",
    matching the format PAMS uses (so the existing _pi_variants /
    _reorder_pi_name matching logic works unchanged). Prefers separate
    "PI Last Name" / "PI First Name" columns, since a single free-text
    "Last, First" column is prone to inconsistent spacing/punctuation.
    Falls back to a single combined-name column if the split columns
    aren't present.
    """
    last = _normalize(_get_field(row, "PI Last Name", "Last Name"))
    first = _normalize(_get_field(row, "PI First Name", "First Name"))
    if last or first:
        return f"{last}, {first}" if last and first else (last or first)
    return _normalize(_get_field(row, "Principal Investigator", "PI", "PI Name"))


def _parse_confluence_staff(value):
    """
    Parses the "Known E3SM Staff" column: either "No" (or blank), meaning
    no staff are known via Confluence, or a semi-colon-separated list of
    staff names. Returns a list of normalized names (empty if none).
    """
    value = _normalize(value)
    if not value or value.casefold() == "no":
        return []
    return [_normalize(name) for name in value.split(";") if _normalize(name)]


def load_known_awards(path):
    """
    Loads e3sm_related_awards.csv (keys: PI Last Name, PI First Name,
    Title, Genesis Mission Focus Area, Known E3SM Staff) into a list of
    records, each a dict with keys "pi", "title", "focus_area",
    "confluence_staff". Rows with neither a title nor a PI are skipped.

    "confluence_staff" is a list of E3SM staff names noted on Confluence
    for this project (empty if the column says "No" or is blank). It is
    merged with staff found by scanning the PAMS abstract/PI text (see
    combine_staff_display) and used to decide which report section a
    matched project lands in — it plays no role in matching against PAMS.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        records = []
        for row in reader:
            pi = _get_known_award_pi(row)
            title = _normalize(_get_field(row, "Title", "Award Title"))
            focus_area = _normalize(
                _get_field(row, "Genesis Mission Focus Area", "Focus Area")
            )
            confluence_staff = _parse_confluence_staff(
                _get_field(row, "Known E3SM Staff", "E3SM Staff")
            )
            if not title and not pi:
                continue
            records.append(
                {
                    "pi": pi,
                    "title": title,
                    "focus_area": focus_area or None,
                    "confluence_staff": confluence_staff,
                }
            )
        return records


def index_known_awards(records):
    """
    Builds lookup indexes over known_relevant_awards records for matching
    against PAMS rows:
      - title_to_record: title (casefold) -> record. Titles are expected
        to be unique; if duplicated, the first occurrence wins.
      - pi_variant_to_records: casefolded PI name variant -> list of
        records sharing that variant. Used only as a fallback when a PAMS
        row's title doesn't match any known title.
    """
    title_to_record: dict[str, dict] = {}
    pi_variant_to_records: dict[str, list[dict]] = {}
    for record in records:
        if record["title"]:
            title_to_record.setdefault(record["title"].casefold(), record)
        for variant in _pi_variants(record["pi"]):
            pi_variant_to_records.setdefault(variant, []).append(record)
    return title_to_record, pi_variant_to_records


def _match_known_award(row, title_to_record, pi_variant_to_records):
    """
    Matches a PAMS row against known_relevant_awards records: first by
    title, and if that fails, by PI. Returns the matching record, or None.
    """
    title = row["Title"]
    if title:
        record = title_to_record.get(title.casefold())
        if record is not None:
            return record
    pi = row["PI"]
    if pi:
        for variant in _pi_variants(pi):
            candidates = pi_variant_to_records.get(variant)
            if candidates:
                return candidates[0]
    return None


def _build_section(title, fa_display, pi, staff_display, abstract):
    """
    Builds a single project section. Metadata lines are joined with a
    trailing double-space + newline so Markdown renders them as separate
    lines within the same paragraph (a plain "\n" gets collapsed by
    Markdown renderers), rather than running together as one line.

    `staff_display` is a list of already-formatted "Name (source)"
    strings (see combine_staff_display), not raw names.
    """
    meta_lines = [
        f"### {title}",
        f"**Focus Area:** {fa_display if fa_display else '_none found_'}",
        f"**PI:** {pi if pi else '_unknown_'}",
        f"**E3SM Staff:** {', '.join(staff_display) if staff_display else '_none found_'}",
    ]
    meta_block = "  \n".join(meta_lines)
    abstract_block = abstract if abstract else "_no abstract available_"
    return f"{meta_block}\n\n**Abstract:**\n\n{abstract_block}"


def _wrap_h2(heading, sections):
    """Renders an h2 sub-section with a count-bearing header, or None if empty."""
    if not sections:
        return None
    return f"## {heading} ({len(sections)})\n\n" + "\n\n".join(sections)


def build_report(rows, known_awards, staff_list, focus_areas, malformed_titles=None):
    """
    Matches PAMS rows against known_relevant_awards. For each matched
    ("Found in PAMS") project, buckets it into one of four mutually
    exclusive h2 groups, checked in this order:
      1. "Malformed Abstracts" — title is in malformed_titles
      2. "Has E3SM staff according to the abstract" — staff found by
         scanning the abstract/PI text (regardless of whether any of
         those staff are also noted on Confluence)
      3. "Has E3SM staff but only noted on Confluence" — no staff found
         in the abstract/PI text, but the known_relevant_awards CSV
         lists staff for this project
      4. "No E3SM staff" — neither of the above

    known_relevant_awards records with no matching PAMS row ("Not found
    in PAMS") are similarly bucketed, using only the Confluence-noted
    staff (there's no abstract to scan, so "found in abstract" and
    "Malformed Abstracts" can't apply):
      - "Has E3SM staff but only noted on Confluence"
      - "No E3SM staff"

    Returns the rendered report body along with a `stats` dict that is
    the single source of truth for counts elsewhere in the report (e.g.
    the Counts section), so it never has to be recomputed independently
    and risk disagreeing with the body of the report.
    """
    malformed_titles = malformed_titles or set()
    title_to_record, pi_variant_to_records = index_known_awards(known_awards)

    found_abstract_staff_sections = []
    found_confluence_only_sections = []
    found_no_staff_sections = []
    found_malformed_sections = []
    matched_ids = set()

    for row in rows:
        record = _match_known_award(row, title_to_record, pi_variant_to_records)
        if record is None:
            continue
        matched_ids.add(id(record))

        title = row["Title"] or record["title"]
        pi = row["PI"]
        abstract = row["Abstract"]

        abstract_code = find_focus_area_code(abstract, focus_areas)
        fa_display = combine_focus_area_display(
            abstract_code, record["focus_area"], focus_areas
        )

        abstract_staff = find_staff(abstract, pi, staff_list)
        confluence_staff = record["confluence_staff"]
        staff_display = combine_staff_display(abstract_staff, confluence_staff)

        section = _build_section(title, fa_display, pi, staff_display, abstract)

        if title and title.casefold() in malformed_titles:
            found_malformed_sections.append(section)
        elif abstract_staff:
            found_abstract_staff_sections.append(section)
        elif confluence_staff:
            found_confluence_only_sections.append(section)
        else:
            found_no_staff_sections.append(section)

    missing_records = [r for r in known_awards if id(r) not in matched_ids]

    notfound_confluence_sections = []
    notfound_no_staff_sections = []
    for record in missing_records:
        title = record["title"] or "(untitled project)"
        pi = record["pi"]
        fa_display = combine_focus_area_display(None, record["focus_area"], focus_areas)
        confluence_staff = record["confluence_staff"]
        staff_display = combine_staff_display([], confluence_staff)
        section = _build_section(
            title, fa_display, pi, staff_display, "_project not found in PAMS export_"
        )
        if confluence_staff:
            notfound_confluence_sections.append(section)
        else:
            notfound_no_staff_sections.append(section)

    found_in_pams = (
        len(found_abstract_staff_sections)
        + len(found_confluence_only_sections)
        + len(found_no_staff_sections)
        + len(found_malformed_sections)
    )

    stats = {
        "found_in_pams": found_in_pams,
        "not_found_in_pams": len(missing_records),
        "found_abstract_staff": len(found_abstract_staff_sections),
        "found_confluence_only_staff": len(found_confluence_only_sections),
        "found_no_staff": len(found_no_staff_sections),
        "found_malformed": len(found_malformed_sections),
        "notfound_confluence_staff": len(notfound_confluence_sections),
        "notfound_no_staff": len(notfound_no_staff_sections),
    }

    top_groups = []

    found_h2s = [
        _wrap_h2(
            "Has E3SM staff according to the abstract", found_abstract_staff_sections
        ),
        _wrap_h2(
            "Has E3SM staff but only noted on Confluence",
            found_confluence_only_sections,
        ),
        _wrap_h2("No E3SM staff", found_no_staff_sections),
        _wrap_h2("Malformed Abstracts", found_malformed_sections),
    ]
    found_h2s = [h2 for h2 in found_h2s if h2]
    if found_h2s:
        top_groups.append(
            f"# Found in PAMS ({stats['found_in_pams']})\n\n" + "\n\n".join(found_h2s)
        )

    notfound_h2s = [
        _wrap_h2(
            "Has E3SM staff but only noted on Confluence", notfound_confluence_sections
        ),
        _wrap_h2("No E3SM staff", notfound_no_staff_sections),
    ]
    notfound_h2s = [h2 for h2 in notfound_h2s if h2]
    if notfound_h2s:
        top_groups.append(
            f"# Not found in PAMS ({stats['not_found_in_pams']})\n\n"
            + "\n\n".join(notfound_h2s)
        )

    if not top_groups:
        return "_No related projects found._\n", stats

    return "\n\n".join(top_groups), stats


def _build_counts_section(rows, known_awards, stats):
    """
    Renders the top-level "# Counts" section. All figures come from
    `stats`, which build_report derives from the exact same matching
    pass used to render the report body — so these numbers are
    guaranteed to sum correctly and agree with the sections below
    (unlike computing them separately via title-set arithmetic, which
    can diverge whenever a match happens via the PI fallback rather than
    an exact title match).
    """
    on_pams_not_known = len(rows) - stats["found_in_pams"]

    lines = [
        "# Counts",
        "",
        f"- Awards in PAMS export: {len(rows)}",
        f"- Awards in known_relevant_awards: {len(known_awards)}",
        f"- On PAMS but not in known_relevant_awards: {on_pams_not_known}",
        f"- Found in PAMS ({stats['found_in_pams']}):",
        f"  - Has E3SM staff according to the abstract: {stats['found_abstract_staff']}",
        f"  - Has E3SM staff but only noted on Confluence: {stats['found_confluence_only_staff']}",
        f"  - No E3SM staff: {stats['found_no_staff']}",
        f"  - Malformed abstracts: {stats['found_malformed']}",
        f"- Not found in PAMS ({stats['not_found_in_pams']}):",
        f"  - Has E3SM staff but only noted on Confluence: {stats['notfound_confluence_staff']}",
        f"  - No E3SM staff: {stats['notfound_no_staff']}",
    ]
    return "\n".join(lines)


def main():
    rows = load_pams_rows(INPUT_PAMS)
    known_awards = load_known_awards(INPUT_KNOWN_RELEVANT_AWARDS)
    staff_list = load_known_staff(INPUT_KNOWN_E3SM_STAFF)
    focus_areas = load_focus_areas(INPUT_FOCUS_AREAS)
    malformed_titles = load_malformed_titles(INPUT_MALFORMED_ABSTRACTS)

    body, stats = build_report(
        rows, known_awards, staff_list, focus_areas, malformed_titles
    )
    counts_section = _build_counts_section(rows, known_awards, stats)
    report = f"{counts_section}\n\n{body}"

    out_path = Path(OUTPUT_REPORT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote report for {report.count('### ')} project(s) to {out_path}")


if __name__ == "__main__":
    main()
