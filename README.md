# AWS Sustainability Scanner GitHub action

This GitHub Action runs [AWS Sustainability Scanner](https://github.com/awslabs/sustainability-scanner) against infrastructure-as-code to identify sustainability best practices, generates a report with a score and suggested improvements to apply to your template.

## Usage

In your Github worflows, under steps, add the following:

```yml
name: AWS Sustainability Scanner
uses: aws-actions/sustainability-scanner@latest
with:
  <INPUTS>
```

## Inputs

### `file`

Path to the specific file you want to scan.

### `directory`

Path to the directory you want to scan. Every `.yml` and `.yaml` files that this directory contain will be scan.

### `rules_file`

Path to your `.json` file to extend the Susscan rules set.


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
      - uses: actions/checkout@v3

      # Run AWS Sustainability Scanner against template.yaml
      - name: AWS Sustainability Scanner
        uses: aws-actions/sustainability-scanner@latest
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
      - uses: actions/checkout@v3

      # Run AWS Sustainability Scanner against "my-cf-stacks" folder with an additional rules set
      - name: AWS Sustainability Scanner
        uses: aws-actions/sustainability-scanner@latest
        with:
          directory: 'my-cf-stacks/'
          rules-file: 'tests/additional-rules.json'
```

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

