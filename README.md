# AWS Sustainability Scanner GitHub action

This GitHub Action runs [AWS Sustainability Scanner](https://github.com/awslabs/sustainability-scanner) against infrastructure-as-code to identify sustainability best practices, generates a report with a score and suggested improvements to apply to your template.

## Usage

In your Github worflows, under steps, add the following:

```yml
name: AWS Sustainability Scanner
uses: aws-actions/sustainability-scanner@v1
with:
  <INPUTS>
```

## Inputs

### `file`

Path to the specific file you want to scan. This file is never skipped: the action fails if CFN Guard cannot parse it.

### `directory`

Path to the directory you want to scan. Every `.json`, `.yml` and `.yaml` files that this directory contain will be scan. Files that CFN Guard cannot parse are skipped only when they cannot be CloudFormation templates, see [Errored scans and skipped files](#errored-scans-and-skipped-files).

### `stack_name`

Name of the stack or stacks to be scanned. See how to [specify stacks](https://docs.aws.amazon.com/cdk/v2/guide/cli.html#cli-stacks) from AWS documentation. The value may contain letters, digits and `_ . / : * ? -`, and must not start with `-`. Use a wildcard pattern such as `*Stack` instead of listing several stacks separated by spaces.

### `rules_file`

Path to your `.json` file to extend the Susscan rules set.

### `fail_on_findings`

Optional, defaults to `false`. When set to `true`, the action fails if the scan identifies any sustainability improvement. Useful to enforce a quality gate in CI/CD pipelines.

### `max_score_threshold`

Optional. When set to an integer, the action fails if the total sustainability score exceeds this value. A higher score means more suggested improvements, so a lower threshold is stricter.

## Outputs

### `results`

The results from the scanner. See how to use it in this [example](#use-output-for-commenting-pull-requests).

When a single file or CDK stack is scanned, `results` contains the scanner report for that resource. When a directory with multiple templates is scanned, `results` contains a consolidated report with the total `sustainability_score` and a `reports` array holding the individual report of each scanned template:

```json
{
    "title": "Sustainability Scanner Report",
    "version": "1.3.0",
    "sustainability_score": 12,
    "reports": [
        { "file": "template-a.yaml", "sustainability_score": 8, "failed_rules": ["..."] },
        { "file": "template-b.yaml", "sustainability_score": 4, "failed_rules": ["..."] }
    ]
}
```

When every file in the directory is skipped, `results` is `{}`. When a scan error makes the action fail, `results` is empty.

## Job summary

The action writes a Markdown summary of the scan to the workflow run's job summary, listing each scanned template with its sustainability score and the identified improvements, with links to the related AWS Well-Architected Sustainability Pillar best practices. The summary also lists the files that could not be scanned (scan errors) and the skipped files, with the reason.

## Example usage

### Simple usage with one specific file

```yml
name: susscan

# Controls when the workflow will run
on:
  # Triggers the workflow on push events but only for the "main" branch
  push:
    branches: "main"
  # Allows you to run this workflow manually from the Actions tab
  workflow_dispatch:

# A workflow run is made up of one or more jobs that can run sequentially or in parallel
jobs:
  # This workflow contains a single job called "scan"
  scan:
    # The type of runner that the job will run on
    runs-on: ubuntu-latest

    # Steps represent a sequence of tasks that will be executed as part of the job
    steps:
      # Checks-out your repository under $GITHUB_WORKSPACE, so follow-up steps can access it
      - uses: actions/checkout@v4

      # Run AWS Sustainability Scanner against template.yaml
      - name: AWS Sustainability Scanner
        uses: aws-actions/sustainability-scanner@v1
        with:
          file: 'template.yaml'
```

### Usage with a directory and custom rules set

```yml
name: susscan

on:
  push:
    branches: "main"
  workflow_dispatch:

jobs:
  scan:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      # Run AWS Sustainability Scanner against "my-cf-stacks" folder with an additional rules set
      - name: AWS Sustainability Scanner
        uses: aws-actions/sustainability-scanner@v1
        with:
          directory: 'my-cf-code'
          rules-file: 'tests/additional-rules.json'
```

### Usage for CDK stacks

```yml
name: susscan

on:
  pull_request:

jobs:
  scan:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: AWS Sustainability Scanner
        uses: aws-actions/sustainability-scanner@v1
        with:
          stack_name: '*Stack' # All stacks finishing by Stack, eg. DatabaseStack, ApplicationStack
```

### Use as a quality gate in CI/CD

```yml
name: susscan

on:
  pull_request:

jobs:
  scan:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      # Fail the job if the total sustainability score exceeds 10
      - name: AWS Sustainability Scanner
        uses: aws-actions/sustainability-scanner@v1
        with:
          directory: 'my-cf-code'
          max_score_threshold: 10

      # Or fail the job on any finding by using:
      #   fail_on_findings: true
```

### Use output for commenting pull requests

```yml
name: susscan

on:
  pull_request:

jobs:
  scan:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: AWS Sustainability Scanner
        uses: aws-actions/sustainability-scanner@v1
        id: scanner
        with:
          file: 'template.yaml'

      # Use scanner output to create a comment on pull request
      - name: Comment on pull request
        uses: actions/github-script@v7
        with:
          script: |
            result=${{ (steps.scanner.outputs.results) }}
            const score = result.sustainability_score
            const number_failed_rules = result.failed_rules.length

            if (score === 0) {
              body = `✅ Your current sustainability score is **${score}**. Sustainability scanner did not find any improvements to apply to your template.`
            } else {
              body = `❌ Your current sustainability score is **${score}**. Sustainability scanner suggests **${number_failed_rules}** improvements to apply to your template.\nCheck out the details of the sustainability scanner here: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`
            }
            
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            })
```

## Security

### Security considerations

Template files are copied to a temporary directory with neutral names before they are scanned, so unusual file names (quotes, spaces, line breaks) cannot alter how the scanner invokes CFN Guard. The original names are kept in the results and the job summary.

The action stops the runner from processing workflow commands while it runs, so template content in the scan output cannot be interpreted as a workflow command, and CFN Guard error output is printed escaped.

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

### Errored scans and skipped files

The action checks CFN Guard's own exit code and output for every file, and fails when CFN Guard did not evaluate the file completely. This covers invalid YAML or JSON, empty or non-UTF-8 files, rule-file and evaluation errors, output without any rule result, and a scanner report that lacks a failed rule. Rules disabled with `rules_file` are not reported and do not fail the scan. The action scans every file first, then lists all the files that failed in the log and the job summary.

In `file` and `stack_name` mode, nothing is skipped: any CFN Guard error fails the action.

In `directory` mode, a file that CFN Guard cannot parse is skipped and listed, with the reason, in the log and the job summary, unless it could be a CloudFormation template. A file that could be a template fails the action. Any other CFN Guard error always fails. A file could be a CloudFormation template when:

1. after removing a leading UTF-8 byte order mark, it is not valid UTF-8 text (for example UTF-16 with a byte order mark, or binary data), or
2. it contains a NUL byte (for example UTF-16 or UTF-32 without a byte order mark), or
3. it is empty or contains only whitespace, or
4. it contains `Resources`, `AWSTemplateFormatVersion` or `Transform` (case-sensitive) in any of these views of its text, after removing every character other than the ASCII letters `A`-`Z` and `a`-`z`:
   - the text as is;
   - the text with every `\xHH`, `\uHHHH` and `\UHHHHHHHH` escape decoded;
   - the decoded text after Unicode NFKC normalization (for example fullwidth letters).

Every deployable template has a `Resources` section, and JSON or YAML can only spell that key with literal letters or these escapes, so quoting, flow style, comments, line continuations or another encoding cannot hide it. The detection is conservative: a file that is not a template but mentions one of these words fails the action.

To avoid skipped files or such failures, point `directory` at the folder that holds your templates, or use `file`. Under the default `directory: '.'`, files such as `.github/workflows/*.yml`, `tsconfig.json` with comments, Helm templates or docker-compose files with merge keys are typically skipped.

CFN Guard itself evaluates only the first document of a multi-document YAML file, and reads a YAML template that starts with a UTF-8 byte order mark without its top-level keys; the action does not change this.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
