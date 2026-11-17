# Changelog

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

## [Unreleased]

### Security

- fail closed when CFN Guard errors or its result does not match the scanner report: sustainability-scanner 1.3.0 hides CFN Guard errors (for example invalid YAML) and reports a clean score, so a malformed template could pass the gate. The action now checks CFN Guard's own exit code and output for every file, independently of the scanner version
- workflow commands (`::cmd::` and `##[cmd]`) in the scan output are no longer processed by the runner while the action runs
- CFN Guard and scanner error output, which can contain template content, is now printed escaped

### Behaviour changes

- in directory mode, files that CFN Guard cannot parse are skipped and listed in the log and the job summary when they cannot be CloudFormation templates; unparseable files that could be templates, including empty `.json`/`.yml`/`.yaml` files, now fail the action. Users of the default `directory: '.'` should check the skip list, or set `directory` or `file` to scan only their templates
- a file given with the `file` input is never skipped: any CFN Guard error fails the action
- every file is scanned before the action fails, and all failed files are listed
- scan errors exit with code 2

### Bug Fixes

- pin `click<8.2` in the Dockerfile: with click 8.2+, `rules_file` was read as an extra template and the action failed with "Expected 1 scanner report(s) but received 2"

## [1.4.1](https://github.com/aws-actions/sustainability-scanner/compare/v1.4.0...v1.4.1) (2026-10-12)

### Security

- template files are now copied to a temporary directory under neutral names before being passed to the scanner
- the action now fails when the scanner returns no report, or a report that does not match the staged template
- validate `stack_name` (letters, digits and `_ . / : * ? -`, not starting with `-`) before running `cdk synth`, to prevent argument injection; multiple space-separated stacks in one value are no longer accepted, use a wildcard pattern instead
- escape template names, resource names and control characters in the job summary and in log output
- pin `sustainability-scanner` to 1.3.0 and CFN Guard to 3.2.1 in the Dockerfile

## [1.4.0](https://github.com/aws-actions/sustainability-scanner/compare/v1.3.1...v1.4.0) (2026-09-23)

### Features

- add `fail_on_findings` and `max_score_threshold` inputs to use the action as a CI/CD quality gate [#11](https://github.com/aws-actions/sustainability-scanner/issues/11)
- render scan results as a Markdown table in the GitHub job summary [#11](https://github.com/aws-actions/sustainability-scanner/issues/11)

### Bug Fixes

- directory scans no longer overwrite the `results` output with the last scanned file; results are now consolidated into a single report with a `reports` array [#11](https://github.com/aws-actions/sustainability-scanner/issues/11)

### Security

- quote every argument passed to `susscanner` so a template file name containing whitespace or glob characters can no longer be split into extra arguments and make the scanner read a different file than the one found; a `rules_file` that does not exist is now an error instead of silently falling back to the default rules
- the action now fails when `directory` does not exist or contains no `.json`/`.yaml`/`.yml` templates, instead of reporting success without scanning anything

### Maintenance

- update base image from EOL `python:3.9-alpine` to `python:3.12-alpine` [#11](https://github.com/aws-actions/sustainability-scanner/issues/11)

## [1.3.1](https://github.com/aws-actions/sustainability-scanner/compare/v1.2.0...v1.3.1) (2025-06-12)

### Bug Fixes

- fix pip install package from hardcoded v1.0.1 to the latest version of sustainability-scanner [#9](https://github.com/aws-actions/sustainability-scanner/issues/9)
- update legacy key value format to add ~/.guard/bin/ to $PATH

## [1.3.0](https://github.com/aws-actions/sustainability-scanner/compare/v1.2.0...v1.3.0) (2024-09-11)

### Features

- add CDK support

### Bug Fixes

- change `--rules-file` into `--rules` argument in the scanner command

## [1.2.0](https://github.com/aws-actions/sustainability-scanner/compare/v1.1.0...v1.2.0) (2023-11-24)

### Features

- add scanner result as output [#3](https://github.com/aws-actions/sustainability-scanner/issues/3)

### Bug Fixes

- file input is no longer required

## [1.1.0](https://github.com/aws-actions/sustainability-scanner/compare/v1.0.0...v1.1.0) (2023-10-12)

### Features

- support of `.json` cloudformation template files
- better log output for directory scanning

### Bug Fixes

- fix array declaration in 'for' loop
- fix directory scanning

## [1.0.0](https://github.com/aws-actions/sustainability-scanner/tree/v1.0.0) (2023-08-18)

Initial release of AWS Sustainability scanner Github Action