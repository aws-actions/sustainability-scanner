# Changelog

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

## [1.4.0](https://github.com/aws-actions/sustainability-scanner/compare/v1.3.1...v1.4.0) (unreleased)

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