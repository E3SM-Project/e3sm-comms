import ast

from e3sm_comms.utils import IO_DIR

INPUT: str = f"{IO_DIR}/input/term_reviewer/wordpress_sensitive_terms.txt"
# INPUT: str = f"{IO_DIR}/input/term_reviewer/confluence_sensitive_terms.txt"
OUTPUT: str = f"{IO_DIR}/output/term_reviewer/sensitive_terms.txt"


def sort_by_match_sum(input_file, output_file):
    entries = []

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue

            dict_start = line.find("{")
            if dict_start == -1:
                print(f"Skipping malformed line: {line}")
                continue

            dict_str = line[dict_start:].strip()

            try:
                dict_data = ast.literal_eval(dict_str)
            except (SyntaxError, ValueError):
                print(f"Skipping malformed dictionary: {line}")
                continue

            if not isinstance(dict_data, dict):
                print(f"Skipping non-dictionary line: {line}")
                continue

            try:
                total = sum(dict_data.values())
            except TypeError:
                print(f"Skipping line with non-numeric values: {line}")
                continue

            entries.append((total, line))

    entries.sort(key=lambda x: x[0], reverse=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for _, line in entries:
            f.write(line + "\n")


def main():
    sort_by_match_sum(INPUT, OUTPUT)
