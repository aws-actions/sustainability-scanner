#!/usr/bin/env python3
"""Consolidate Sustainability Scanner reports for GitHub Actions.

Reads a file containing one or more concatenated JSON reports produced by
susscanner (one report per scanned template), then:

  1. Prints a single consolidated JSON report to stdout.
     - A single report is passed through unchanged (backward compatible).
     - Multiple reports are merged into an aggregate object with a total
       "sustainability_score" and a "reports" array.
  2. Appends a Markdown summary to $GITHUB_STEP_SUMMARY when it is set.
  3. Evaluates optional failure gates from the action inputs:
     - INPUT_FAIL_ON_FINDINGS: fail if any sustainability improvement is found.
     - INPUT_MAX_SCORE_THRESHOLD: fail if the total sustainability score
       exceeds this value (a higher score means more improvements to apply).

Exit codes: 0 = success, 1 = a failure gate was triggered, 2 = usage error.
"""

import json
import os
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


def render_rule_row(rule):
    """Render a single failed rule as a Markdown table row."""
    name = rule.get("rule_name", "")
    links = rule.get("links", [])
    if links:
        name = f"[{name}]({links[0]})"
    severity = rule.get("severity", "")
    message = rule.get("message", "").replace("|", "\\|").replace("\n", " ")
    resources = "<br>".join(
        "`{}`{}".format(
            res.get("name", ""),
            f" (line {res['line']})" if res.get("line") else "",
        )
        for res in rule.get("resources", [])
    )
    return f"| {name} | {severity} | {message} | {resources} |"


def render_summary(reports):
    """Render the Markdown step summary for the scanned templates."""
    lines = ["# AWS Sustainability Scanner Report", ""]

    if not reports:
        lines.append("No template files were scanned.")
        return "\n".join(lines) + "\n"

    lines += [
        "| Template | Sustainability score | Findings |",
        "| --- | ---: | ---: |",
    ]
    for report in reports:
        file_name = report.get("file", "")
        score = report.get("sustainability_score", 0)
        findings = len(report.get("failed_rules", []))
        status = "✅" if findings == 0 else "❌"
        lines.append(f"| {status} `{file_name}` | {score} | {findings} |")
    lines.append("")

    for report in reports:
        failed_rules = report.get("failed_rules", [])
        if not failed_rules:
            continue
        lines += [
            f"## `{report.get('file', '')}`",
            "",
            "| Rule | Severity | Recommendation | Resources |",
            "| --- | --- | --- | --- |",
        ]
        lines += [render_rule_row(rule) for rule in failed_rules]
        lines.append("")

    lines += [
        "Learn more in the [AWS Well-Architected Sustainability Pillar]"
        "(https://docs.aws.amazon.com/wellarchitected/latest/sustainability-pillar/sustainability-pillar.html).",
        "",
    ]
    return "\n".join(lines)


def evaluate_gates(reports):
    """Evaluate failure gates; return a failure message or None."""
    total_findings = sum(len(r.get("failed_rules", [])) for r in reports)
    total_score = sum(r.get("sustainability_score", 0) for r in reports)

    fail_on_findings = os.environ.get("INPUT_FAIL_ON_FINDINGS", "").lower()
    if fail_on_findings == "true" and total_findings > 0:
        return (
            f"fail_on_findings is enabled and the scan identified "
            f"{total_findings} sustainability improvement(s)."
        )

    threshold = os.environ.get("INPUT_MAX_SCORE_THRESHOLD", "").strip()
    if threshold:
        try:
            threshold_value = int(threshold)
        except ValueError:
            print(
                f"max_score_threshold must be an integer, got: {threshold}",
                file=sys.stderr,
            )
            sys.exit(2)
        if total_score > threshold_value:
            return (
                f"Total sustainability score {total_score} exceeds "
                f"max_score_threshold {threshold_value}."
            )
    return None


def main():
    if len(sys.argv) != 2:
        print("Usage: report.py RESULTS_FILE", file=sys.stderr)
        sys.exit(2)

    reports = parse_reports(sys.argv[1])

    # Consolidated report on stdout, captured by entrypoint.sh
    print(json.dumps(merge_reports(reports), indent=4))

    # Markdown step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(render_summary(reports))

    # Failure gates
    failure = evaluate_gates(reports)
    if failure:
        print(failure, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
