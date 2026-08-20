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
#   PI Last Name,PI First Name,Title,Genesis Mission Focus Area,Has E3SM connection
# Each row is a known-relevant award. "Title" and PI name are used to
# match against the PAMS export (title first, PI as a fallback when no
# title match is found). "Genesis Mission Focus Area" is the focus area
# code (e.g. "15-C") as recorded on Confluence, which is reported
# alongside any focus area code found in the PAMS abstract text.
# "Has E3SM connection" ("Yes"/"No") is used ONLY to build the
# connection-based staff split reported in the Counts section — it does
# not affect matching against PAMS or which report section a project
# lands in.
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
        return [_normalize(line) for line in f if _normalize(line)]


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


def load_known_awards(path):
    """
    Loads e3sm_related_awards.csv (keys: PI Last Name, PI First Name,
    Title, Genesis Mission Focus Area, Has E3SM connection) into a list
    of records, each a dict with keys "pi", "title", "focus_area",
    "connection". Rows with neither a title nor a PI are skipped.

    "connection" is the raw casefolded value of "Has E3SM connection"
    (e.g. "yes", "no", or "" if blank/absent). It is used ONLY to build
    the connection-based staff split in the Counts section — it plays no
    role in matching against PAMS or in which report section a matched
    project is rendered under.
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
            connection = _normalize(
                _get_field(row, "Has E3SM connection", "E3SM Connection")
            ).casefold()
            if not title and not pi:
                continue
            records.append(
                {
                    "pi": pi,
                    "title": title,
                    "focus_area": focus_area or None,
                    "connection": connection,
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


def _build_section(title, fa_display, pi, staff, abstract):
    """
    Builds a single project section. Metadata lines are joined with a
    trailing double-space + newline so Markdown renders them as separate
    lines within the same paragraph (a plain "\n" gets collapsed by
    Markdown renderers), rather than running together as one line.
    """
    meta_lines = [
        f"### {title}",
        f"**Focus Area:** {fa_display if fa_display else '_none found_'}",
        f"**PI:** {pi if pi else '_unknown_'}",
        f"**E3SM Staff:** {', '.join(staff) if staff else '_none found_'}",
    ]
    meta_block = "  \n".join(meta_lines)
    abstract_block = abstract if abstract else "_no abstract available_"
    return f"{meta_block}\n\n**Abstract:**\n\n{abstract_block}"


def _build_missing_section(missing_records):
    if not missing_records:
        return None
    bullets = []
    for r in missing_records:
        if r["title"]:
            label = r["title"]
        elif r["pi"]:
            label = f"(no title; PI: {r['pi']})"
        else:
            label = "(no title or PI)"
        bullets.append(f"- {label}")
    return f"## Not found in PAMS export ({len(missing_records)})\n\n" + "\n".join(
        bullets
    )


def build_report(rows, known_awards, staff_list, focus_areas, malformed_titles=None):
    """
    Matches PAMS rows against known_relevant_awards and buckets each
    match into one of three mutually-exclusive groups: malformed (title
    is in malformed_titles), has-staff, or no-staff. Returns the
    rendered report body along with a `stats` dict:
        {
            "matched": <int, total PAMS rows matched to a known award>,
            "with_staff": <int>,
            "without_staff": <int>,
            "malformed": <int>,
            "not_in_pams": <int, known awards with no matching PAMS row>,
            "connection_yes_with_staff_titles": <list[str]>,
            "connection_yes_without_staff_titles": <list[str]>,
        }
    `stats` is the single source of truth for counts elsewhere in the
    report (e.g. the Counts section), so it never has to be recomputed
    independently and risk disagreeing with the body of the report.

    The two "connection_yes_*_titles" lists are derived solely for the
    Counts section's connection-based split (see load_known_awards) and
    do NOT affect which section (with_staff/without_staff/malformed) a
    project is rendered under in the report body.
    """
    malformed_titles = malformed_titles or set()
    title_to_record, pi_variant_to_records = index_known_awards(known_awards)

    with_staff_sections = []
    without_staff_sections = []
    malformed_sections = []
    matched_ids = set()
    connection_yes_with_staff_titles = []
    connection_yes_without_staff_titles = []

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
        staff = find_staff(abstract, pi, staff_list)
        section = _build_section(title, fa_display, pi, staff, abstract)

        if record.get("connection") == "yes":
            label = title or "(untitled project)"
            if staff:
                connection_yes_with_staff_titles.append(label)
            else:
                connection_yes_without_staff_titles.append(label)

        if title and title.casefold() in malformed_titles:
            malformed_sections.append(section)
        elif staff:
            with_staff_sections.append(section)
        else:
            without_staff_sections.append(section)

    missing_records = [r for r in known_awards if id(r) not in matched_ids]

    stats = {
        "matched": len(matched_ids),
        "with_staff": len(with_staff_sections),
        "without_staff": len(without_staff_sections),
        "malformed": len(malformed_sections),
        "not_in_pams": len(missing_records),
        "connection_yes_with_staff_titles": connection_yes_with_staff_titles,
        "connection_yes_without_staff_titles": connection_yes_without_staff_titles,
    }

    if (
        not with_staff_sections
        and not without_staff_sections
        and not malformed_sections
        and not missing_records
    ):
        return "_No related projects found._\n", stats

    groups = []
    if with_staff_sections:
        groups.append(
            f"## Has E3SM staff ({len(with_staff_sections)})\n\n"
            + "\n\n".join(with_staff_sections)
        )
    if without_staff_sections:
        groups.append(
            f"## No E3SM staff ({len(without_staff_sections)})\n\n"
            + "\n\n".join(without_staff_sections)
        )
    if malformed_sections:
        groups.append(
            f"## Malformed Abstracts ({len(malformed_sections)})\n\n"
            + "\n\n".join(malformed_sections)
        )
    missing_section = _build_missing_section(missing_records)
    if missing_section:
        groups.append(missing_section)

    return "\n\n".join(groups), stats


def _build_counts_section(rows, known_awards, stats):
    """
    Renders the top-level Counts section. The "both / staff / no staff /
    malformed" figures all come from `stats`, which build_report derives
    from the exact same matching pass used to render the report body —
    so these numbers are guaranteed to sum correctly and agree with the
    sections below (unlike computing them separately via title-set
    arithmetic, which can diverge whenever a match happens via the PI
    fallback rather than an exact title match).

    The trailing "Has E3SM connection (Yes)" block is a separate split,
    based purely on the "Has E3SM connection" column from
    known_relevant_awards, restricted to matched/PAMS-confirmed projects
    (since staff presence is only knowable for those). Each sub-bullet
    lists the actual project titles rather than just a count. It does
    not affect, and is not affected by, the sections above it.
    """
    on_pams_not_known = len(rows) - stats["matched"]
    connection_yes_with_staff_titles = stats["connection_yes_with_staff_titles"]
    connection_yes_without_staff_titles = stats["connection_yes_without_staff_titles"]
    connection_yes_total = len(connection_yes_with_staff_titles) + len(
        connection_yes_without_staff_titles
    )

    def _title_bullets(titles, indent="    "):
        return [f"{indent}- {t}" for t in titles] if titles else [f"{indent}- _none_"]

    lines = [
        "## Counts",
        "",
        f"- Awards in PAMS export: {len(rows)}",
        f"- Awards in known_relevant_awards: {len(known_awards)}",
        f"- On PAMS but not in known_relevant_awards: {on_pams_not_known}",
        f"- In known_relevant_awards but not on PAMS: {stats['not_in_pams']}",
        f"- In both PAMS export and known_relevant_awards: {stats['matched']}",
        f"  - Have E3SM staff: {stats['with_staff']}",
        f"  - No E3SM staff: {stats['without_staff']}",
        f"  - Malformed abstracts: {stats['malformed']}",
        f"- Has E3SM connection noted on Confluence: {connection_yes_total}",
        f"  - Have E3SM staff ({len(connection_yes_with_staff_titles)}):",
        *_title_bullets(connection_yes_with_staff_titles),
        f"  - No E3SM staff ({len(connection_yes_without_staff_titles)}):",
        *_title_bullets(connection_yes_without_staff_titles),
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
