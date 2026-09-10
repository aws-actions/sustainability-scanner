#!/usr/bin/env python3
"""Consolidate Sustainability Scanner reports for GitHub Actions.

Reads a file containing one or more concatenated JSON reports produced by
susscanner (one report per scanned template) and prints a single
consolidated JSON report to stdout.

  - A single report is passed through unchanged (backward compatible).
  - Multiple reports are merged into an aggregate object with a total
    "sustainability_score" and a "reports" array.

Exit codes: 0 = success, 2 = usage error.
"""

import json
import sys


def parse_reports(path):
    """Parse concatenated JSON documents from a file into a list of reports."""
    try:
        with open(path, "r") as f:
            content = f.read()
    except OSError as err:
        print(f"Unable to read results file: {err}", file=sys.stderr)
        sys.exit(2)

    reports = []
    decoder = json.JSONDecoder()
    index = 0
    length = len(content)
    while index < length:
        # Skip whitespace between concatenated JSON documents
        while index < length and content[index].isspace():
            index += 1
        if index >= length:
            break
        try:
            report, index = decoder.raw_decode(content, index)
        except json.JSONDecodeError as err:
            print(f"Unable to parse scanner output: {err}", file=sys.stderr)
            sys.exit(2)
        reports.append(report)
    return reports


def merge_reports(reports):
    """Merge reports into a single consolidated report."""
    if not reports:
        return {}
    if len(reports) == 1:
        return reports[0]
    return {
        "title": "Sustainability Scanner Report",
        "version": reports[0].get("version", ""),
        "sustainability_score": sum(
            r.get("sustainability_score", 0) for r in reports
        ),
        "reports": reports,
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: report.py RESULTS_FILE", file=sys.stderr)
        sys.exit(2)

    reports = parse_reports(sys.argv[1])

    # Consolidated report on stdout, captured by entrypoint.sh
    print(json.dumps(merge_reports(reports), indent=4))


if __name__ == "__main__":
    main()
