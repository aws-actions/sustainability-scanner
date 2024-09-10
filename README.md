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

Path to the specific file you want to scan.

### `directory`

Path to the directory you want to scan. Every `.json`, `.yml` and `.yaml` files that this directory contain will be scan.

### `stack_name`

Name of the stack or stacks to be scanned. See how to [specify stacks](https://docs.aws.amazon.com/cdk/v2/guide/cli.html#cli-stacks) from AWS documentation.

### `rules_file`

Path to your `.json` file to extend the Susscan rules set.

## Outputs

### `results`

The results from the scanner. See how to use it in this [example](#use-output-for-commenting-pull-requests).

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

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
