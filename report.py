#!/usr/bin/env python3
"""Check and consolidate Sustainability Scanner runs for GitHub Actions.

entrypoint.sh runs susscanner once per resource and writes one directory per
run under RUNS_DIR:

  resource        the path given to susscanner (staged copy, or the stack name)
  original        the name shown to the user (raw bytes)
  scanner.exit    susscanner's exit code
  scanner.stdout  susscanner's report
  scanner.stderr  susscanner's error output
  guard.*         what CFN Guard really did, recorded by the cfn-guard wrapper:
                  calls (one line per call), argv (NUL-separated), exit,
                  stdout and stderr

sustainability-scanner 1.3.0 ignores CFN Guard's exit code and reports a
clean score when CFN Guard fails. Every run is therefore checked against CFN
Guard's own result (see check_run): CFN Guard ran once on the expected file,
exited 0 (pass) or 19 (FAIL), evaluated every bundled rule, its output is
consistent, and the scanner's report lists exactly the failed rules that are
enabled in the rules metadata. Any other result is a scan error and the run
fails closed. All runs are checked before failing, so every failed file is
listed.

In directory mode only, a file that CFN Guard cannot parse is skipped (and
listed) when it cannot be a CloudFormation template (see could_be_template).
A file that could be a template fails. In file mode a parse failure always
fails.

When every run is valid:

  1. Prints a single consolidated JSON report to stdout.
     - A single report is passed through unchanged (backward compatible).
     - Multiple reports are merged into an aggregate object with a total
       "sustainability_score" and a "reports" array.
     The "file" field of every report is rewritten from the staged name back
     to the original path (not in CDK mode).
  2. Appends a Markdown summary to $GITHUB_STEP_SUMMARY when it is set.
  3. Evaluates optional failure gates from the action inputs:
     - INPUT_FAIL_ON_FINDINGS: fail if any sustainability improvement is found.
     - INPUT_MAX_SCORE_THRESHOLD: fail if the total sustainability score
       exceeds this value (a higher score means more improvements to apply).

Usage: report.py MODE RUNS_DIR   (MODE is file, directory or cdk)

Exit codes: 0 = success, 1 = a failure gate was triggered, 2 = usage error,
scan error or unexpected scanner output (nothing is printed on stdout).
"""

import importlib.util
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import PurePosixPath

MODES = ("file", "directory", "cdk")


def parse_reports_text(text):
    """Parse concatenated JSON documents; return a list, or None if invalid."""
    reports = []
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        # Skip whitespace between concatenated JSON documents
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        try:
            report, index = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            return None
        reports.append(report)
    return reports


def original_label(raw):
    """Return the name shown for a template, from the raw original path.

    The scanner reports str(pathlib.Path(argument)), which drops a leading
    "./" and duplicate slashes. Normalize the same way so the "file" value is
    identical to what an unstaged scan reported.
    """
    return str(PurePosixPath(raw.decode("utf-8", errors="replace")))


_RUN_TEXT_FILES = {
    "resource": "resource",
    "scanner_exit": "scanner.exit",
    "scanner_stdout": "scanner.stdout",
    "scanner_stderr": "scanner.stderr",
    "guard_calls": "guard.calls",
    "guard_exit": "guard.exit",
    "guard_stdout": "guard.stdout",
    "guard_stderr": "guard.stderr",
    "probe_exit": "probe.exit",
}


def read_run(run_dir):
    """Read the files of one run directory. Missing files are None."""

    def read(name):
        try:
            with open(os.path.join(run_dir, name), "rb") as f:
                return f.read()
        except OSError:
            return None

    run = {"dir": run_dir}
    for key, name in _RUN_TEXT_FILES.items():
        data = read(name)
        run[key] = None if data is None else data.decode("utf-8", errors="replace")
    run["original"] = read("original") or b""
    argv = read("guard.argv")
    if argv is None:
        run["guard_argv"] = None
    else:
        parts = argv.split(b"\0")
        # Every argument ends with a NUL, so the last element is always empty
        if parts and parts[-1] == b"":
            parts.pop()
        run["guard_argv"] = [p.decode("utf-8", errors="replace") for p in parts]
    return run


def bundled_metadata_path():
    """Return the rules metadata bundled with the installed scanner."""
    # find_spec locates the package without importing (and running) it
    spec = importlib.util.find_spec("susscanner")
    if spec is None or not spec.origin:
        print("sustainability-scanner is not installed for this Python", file=sys.stderr)
        sys.exit(2)
    return os.path.join(os.path.dirname(spec.origin), "rules_metadata.json")


def _metadata_rules(path):
    with open(path, "r") as f:
        data = json.load(f)
    for group in data["all_rules"].values():
        for rule in group["rules"]:
            yield group, rule


def enabled_rules(path):
    """Rule names the scanner reports, as in sustainability-scanner 1.3.0
    Scan.load_metadata: both the group and the rule must be enabled."""
    return {
        rule["rule_name"]
        for group, rule in _metadata_rules(path)
        if group["enabled"] and rule["enabled"]
    }


def all_rules(path):
    """Every rule name listed in a rules metadata file."""
    return {rule["rule_name"] for _, rule in _metadata_rules(path)}


def guard_blocks(stdout):
    """Return the JSON objects CFN Guard printed (one per rule file)."""
    blocks = []
    decoder = json.JSONDecoder()
    index = stdout.find("{")
    while index >= 0:
        try:
            value, end = decoder.raw_decode(stdout, index)
        except json.JSONDecodeError:
            index = stdout.find("{", index + 1)
            continue
        if isinstance(value, dict):
            blocks.append(value)
        index = stdout.find("{", end)
    return blocks


_FAIL_LINE = re.compile(r"^\S+\.guard/(\S+)[ \t]+FAIL[ \t]*$", re.M)


def fail_lines(stdout):
    """Rule names from CFN Guard's "<file>.guard/<rule>    FAIL" lines."""
    return _FAIL_LINE.findall(stdout)


def block_rules(blocks):
    """Return (failed rule names, every rule name seen), or None if malformed."""
    failed = []
    seen = set()
    try:
        for block in blocks:
            for entry in block.get("not_compliant") or []:
                name = entry["Rule"]["name"]
                if not isinstance(name, str):
                    return None
                failed.append(name)
            for key in ("compliant", "not_applicable"):
                names = block.get(key) or []
                if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                    return None
                seen.update(names)
    except (AttributeError, KeyError, TypeError):
        return None
    seen.update(failed)
    return failed, seen


def log_text(value, limit=2000):
    """Make untrusted text safe on one log line: quoted, escaped, no "##["."""
    text = str(value)
    # Truncate before escaping so an escape sequence is never cut in half
    if len(text) > limit:
        text = text[:limit] + "..."
    return json.dumps(text, ensure_ascii=True).replace("##[", "##\\[")


TEMPLATE_MARKERS = ("Resources", "AWSTemplateFormatVersion", "Transform")
_ESCAPE = re.compile(r"\\(?:x([0-9A-Fa-f]{2})|u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8}))")
_NON_LETTERS = re.compile(r"[^A-Za-z]+")


def _decode_escape(match):
    value = int(next(group for group in match.groups() if group), 16)
    return chr(value) if value <= 0x10FFFF else match.group(0)


def could_be_template(data):
    """Decide whether an unparseable file could be a CloudFormation template.

    Returns (verdict, reason). When in doubt the verdict is True (fail).

    Every deployable template has a top-level "Resources" key; "Transform"
    (macros, AWS::Include) is the only way to add content later, and
    "AWSTemplateFormatVersion" is checked for extra caution. In the syntax
    CloudFormation accepts (JSON, and YAML 1.1 without aliases, merge keys or
    the binary tag), a key's characters are either literal or written as a
    \\x, \\u or \\U escape. Every other escape, quoting, flow style, explicit
    keys, comments, line folding and escaped line breaks only add non-letters
    between the letters. So the key always appears in the letters-only text
    of the file, with escapes decoded. The checks, in order:

      1. A leading UTF-8 BOM is ignored.
      2. Not valid UTF-8 (UTF-16/32 with a BOM, other encodings, binary data):
         could be a template.
      3. Contains a NUL byte (UTF-16/32 without a BOM, which is ASCII
         interleaved with NUL and can hide escapes): could be a template.
      4. Empty or whitespace only: could be a template.
      5. Three views of the text are searched: as is, with every \\xHH,
         \\uHHHH and \\UHHHHHHHH escape decoded (greedily, even where a parser
         would not), and the decoded view after NFKC normalization (fullwidth
         letters). Every character other than A-Z and a-z is removed. A view
         containing a marker (case-sensitive) could be a template.
      6. Otherwise the file cannot be a template.
    """
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return True, "it is not valid UTF-8 text"
    if "\0" in text:
        return True, "it contains NUL bytes"
    if not text.strip():
        return True, "it is empty"
    decoded = _ESCAPE.sub(_decode_escape, text)
    for view in (text, decoded, unicodedata.normalize("NFKC", decoded)):
        letters = _NON_LETTERS.sub("", view)
        for marker in TEMPLATE_MARKERS:
            if marker in letters:
                return True, f"it mentions {marker}"
    return False, "it does not mention " + ", ".join(TEMPLATE_MARKERS[:-1]) + " or " + TEMPLATE_MARKERS[-1]


def _int(value):
    try:
        return int(value.strip())
    except (AttributeError, ValueError):
        return None


def check_run(run, mode, effective, bundled):
    """Check one run against CFN Guard's own result.

    Returns ("ok", report), ("skipped", reason) or ("error", reason). The
    first failed check wins.
    """
    # 1. The wrapper recorded exactly one CFN Guard call
    calls = len((run["guard_calls"] or "").splitlines())
    if calls == 0:
        return "error", "cfn-guard was not run"
    if calls != 1:
        return "error", f"cfn-guard ran {calls} times"

    # 2. CFN Guard scanned the staged file (CDK mode synthesizes its own file)
    if mode != "cdk":
        argv = run["guard_argv"] or []
        data = [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "--data"]
        if argv.count("--data") != 1 or data != [run["resource"]]:
            return "error", "cfn-guard scanned an unexpected file"

    # 3. Only 0 (every rule passed or was skipped) and 19 (FAIL) are results
    code = _int(run["guard_exit"])
    if code is None:
        return "error", "cfn-guard did not report an exit code"
    stdout = run["guard_stdout"] or ""
    if code not in (0, 19):
        # A parse failure: exit 255, no rule result, and the parse-only probe
        # also exits 255. Directory mode only: it is skipped when the file
        # cannot be a template. Every other error fails.
        parse_failure = (
            code == 255
            and not stdout
            and (run["probe_exit"] or "").strip() == "255"
        )
        if parse_failure and mode != "directory":
            return "error", "CFN Guard could not parse this file (exit 255)"
        if parse_failure:
            try:
                with open(run["resource"], "rb") as f:
                    data = f.read()
            except (OSError, TypeError):
                return "error", "unable to read the staged file"
            template, reason = could_be_template(data)
            if template:
                return "error", (
                    "CFN Guard could not parse this file and it could be a "
                    "CloudFormation template: " + reason
                )
            return "skipped", "CFN Guard could not parse this file and " + reason
        return "error", f"cfn-guard exited with code {code}"

    # 4. At least one rule file was evaluated
    blocks = guard_blocks(stdout)
    if not blocks:
        return "error", f"cfn-guard exited with code {code} without evaluating any rule"

    # 5. The JSON results agree with the FAIL lines
    rules = block_rules(blocks)
    if rules is None:
        return "error", "cfn-guard output is inconsistent"
    failed, seen = rules
    if set(failed) != set(fail_lines(stdout)):
        return "error", "cfn-guard output is inconsistent"

    # 6. The exit code agrees with the results
    if (code == 19) != bool(failed):
        return "error", f"cfn-guard exit code {code} does not match its output"

    # 7. Every bundled rule has a result (a broken rule file can drop rules
    # and still exit 0). The names come from the image, not the template.
    missing = sorted(bundled - seen)
    if missing:
        return "error", (
            "cfn-guard did not evaluate every bundled rule (missing: "
            + ", ".join(missing) + ")"
        )

    # 8. The scanner itself succeeded
    scanner_exit = _int(run["scanner_exit"])
    if scanner_exit != 0:
        return "error", f"susscanner exited with code {scanner_exit}"

    # 9. The scanner returned one report for the scanned file
    reports = parse_reports_text(run["scanner_stdout"] or "")
    if not reports or len(reports) != 1 or not isinstance(reports[0], dict):
        return "error", "susscanner did not return one report"
    report = reports[0]
    if mode != "cdk" and report.get("file") != run["resource"]:
        return "error", "susscanner report does not match the scanned file"

    # 10. The report lists exactly the failed rules that are enabled in the
    # rules metadata given to the scanner (rules_file can disable rules)
    try:
        reported = Counter(r["rule_name"] for r in report.get("failed_rules", []))
    except (KeyError, TypeError):
        return "error", "susscanner did not return one report"
    if reported != Counter(name for name in failed if name in effective):
        return "error", "susscanner report does not list the rules cfn-guard reported as failed"

    # 11. Restore the original template name
    if mode != "cdk":
        report["file"] = original_label(run["original"])
    return "ok", report


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


_CONTROL = {c: " " for c in [*range(0x20), 0x7F, 0x85, 0x2028, 0x2029]}


def plain_text(value):
    """Replace control and line-separator characters with spaces."""
    return str(value).translate(_CONTROL)


def inline_text(value, limit=200):
    """Make untrusted text safe inside a Markdown code span in a table cell."""
    text = plain_text(value)
    # Truncate before escaping so an escape sequence is never cut in half
    if len(text) > limit:
        text = text[:limit] + "…"
    return text.replace("`", "'").replace("|", "\\|")


def render_rule_row(rule):
    """Render a single failed rule as a Markdown table row."""
    name = rule.get("rule_name", "")
    links = rule.get("links", [])
    if links:
        name = f"[{name}]({links[0]})"
    severity = rule.get("severity", "")
    message = plain_text(rule.get("message", "")).replace("|", "\\|")
    resources = "<br>".join(
        "`{}`{}".format(
            inline_text(res.get("name", "")),
            f" (line {res['line']})" if res.get("line") else "",
        )
        for res in rule.get("resources", [])
    )
    return f"| {name} | {severity} | {message} | {resources} |"


def render_summary(reports, errors=(), skipped=()):
    """Render the Markdown step summary for the scanned templates.

    errors and skipped are lists of (name, reason) pairs for files that could
    not be scanned. Reasons are fixed strings from check_run, never tool output.
    """
    lines = ["# AWS Sustainability Scanner Report", ""]

    if reports:
        lines += [
            "| Template | Sustainability score | Findings |",
            "| --- | ---: | ---: |",
        ]
        for report in reports:
            file_name = report.get("file", "")
            score = report.get("sustainability_score", 0)
            findings = len(report.get("failed_rules", []))
            status = "✅" if findings == 0 else "❌"
            lines.append(
                f"| {status} `{inline_text(file_name)}` | {score} | {findings} |"
            )
        lines.append("")

        for report in reports:
            failed_rules = report.get("failed_rules", [])
            if not failed_rules:
                continue
            lines += [
                f"## `{inline_text(report.get('file', ''))}`",
                "",
                "| Rule | Severity | Recommendation | Resources |",
                "| --- | --- | --- | --- |",
            ]
            lines += [render_rule_row(rule) for rule in failed_rules]
            lines.append("")
    elif not errors:
        lines += ["No template files were scanned.", ""]

    if errors:
        lines += [
            "## Scan errors",
            "",
            "CFN Guard could not evaluate these files, so the action failed.",
            "",
            "| File | Reason |",
            "| --- | --- |",
        ]
        lines += [
            f"| ❌ `{inline_text(name)}` | {inline_text(reason)} |"
            for name, reason in errors
        ]
        lines.append("")

    if skipped:
        lines += [
            "## Skipped files",
            "",
            "CFN Guard could not parse these files and they cannot be "
            "CloudFormation templates, so they were not scanned. Set "
            "`directory` or `file` to scan only your templates.",
            "",
            "| File | Reason |",
            "| --- | --- |",
        ]
        lines += [
            f"| ⏭️ `{inline_text(name)}` | {inline_text(reason)} |"
            for name, reason in skipped
        ]
        lines.append("")

    if reports:
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


def load_rule_sets():
    """Return (enabled rules given to the scanner, every bundled rule)."""
    bundled_path = bundled_metadata_path()
    effective_path = os.environ.get("INPUT_RULES_FILE") or bundled_path
    try:
        return enabled_rules(effective_path), all_rules(bundled_path)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print("Unable to read the rules metadata", file=sys.stderr)
        sys.exit(2)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in MODES or not os.path.isdir(sys.argv[2]):
        print("Usage: report.py MODE RUNS_DIR", file=sys.stderr)
        sys.exit(2)
    mode, runs_dir = sys.argv[1], sys.argv[2]
    run_dirs = sorted(
        os.path.join(runs_dir, name)
        for name in os.listdir(runs_dir)
        if os.path.isdir(os.path.join(runs_dir, name))
    )
    if not run_dirs:
        print("No scan was run", file=sys.stderr)
        sys.exit(2)
    effective, bundled = load_rule_sets()

    reports = []
    errors = []
    skipped = []
    for run_dir in run_dirs:
        run = read_run(run_dir)
        status, value = check_run(run, mode, effective, bundled)
        if mode == "cdk":
            name = run["original"].decode("utf-8", errors="replace")
        else:
            name = original_label(run["original"])
        if status == "ok":
            reports.append(value)
            continue
        if status == "skipped":
            skipped.append((name, value))
            print(f"Skipped: {log_text(name)}: {value}", file=sys.stderr)
            continue
        errors.append((name, value))
        print(f"Scan error: {log_text(name)}: {value}", file=sys.stderr)
        if run["guard_stderr"]:
            print(f"  cfn-guard error output: {log_text(run['guard_stderr'])}", file=sys.stderr)
        if run["scanner_stderr"]:
            print(f"  susscanner error output: {log_text(run['scanner_stderr'])}", file=sys.stderr)

    # Markdown step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(render_summary(reports, errors, skipped))

    if skipped:
        print(
            f"{len(skipped)} file(s) skipped: CFN Guard could not parse them "
            "and they cannot be CloudFormation templates.",
            file=sys.stderr,
        )

    if errors:
        print(
            f"{len(errors)} file(s) could not be scanned. The action fails "
            "closed when CFN Guard cannot evaluate a file.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Consolidated report on stdout, captured by entrypoint.sh
    print(json.dumps(merge_reports(reports), indent=4))

    # Failure gates
    failure = evaluate_gates(reports)
    if failure:
        print(failure, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
