#!/bin/bash

# Leverage the default env variables as described in:
# https://docs.github.com/en/actions/reference/environment-variables#default-environment-variables
if [[ $GITHUB_ACTIONS != "true" ]]
then
  susscanner "$@"
  exit $?
fi

# Verify that only one input has been provided
if [[ -n "$INPUT_FILE" && -n "$INPUT_STACK_NAME" ]]; then
  echo "file and stack_name inputs cannot be provided at the same time"
  exit 1
fi

# Temporary state, removed on every exit path. Variables are initialised empty
# so the trap is safe when the script exits early.
STAGING_DIR=""
RESULTS_FILE=""
LABELS_FILE=""
cleanup() {
  if [ -n "$STAGING_DIR" ]; then rm -rf -- "$STAGING_DIR"; fi
  if [ -n "$RESULTS_FILE" ]; then rm -f -- "$RESULTS_FILE"; fi
  if [ -n "$LABELS_FILE" ]; then rm -f -- "$LABELS_FILE"; fi
  return 0
}
trap cleanup EXIT

# Template names come from the repository being scanned and are untrusted.
# Print them escaped on a single line, always after a fixed prefix, so a name
# containing line breaks cannot forge GitHub workflow commands in the log.
display_name() {
  printf '%q' "$1"
}

# Optional scanner arguments are kept in arrays so every element is passed to
# susscanner as exactly one argument, regardless of whitespace or glob characters.
SCAN_ARGS=()

# If an external set of rules is defined then add it to the scanner arguments
if [ -n "$INPUT_RULES_FILE" ]; then
  if [ ! -e "$INPUT_RULES_FILE" ]; then
    echo "Rules file not found: $(display_name "$INPUT_RULES_FILE")"
    exit 1
  fi
  # Defense in depth: sustainability-scanner builds a shell-style command
  # string internally, so a quote or line break in this path must never reach it.
  case "$INPUT_RULES_FILE" in
    *\'*|*\"*|*$'\n'*|*$'\r'*)
      echo "rules_file must not contain quotes or line breaks in its path"
      exit 1
      ;;
  esac
  SCAN_ARGS+=(--rules "$INPUT_RULES_FILE")
fi

# ORIGINALS holds the names shown to the user, RESOURCES_TO_SCAN holds what is
# passed to susscanner (staged copies for templates, the stack name for CDK).
ORIGINALS=()
RESOURCES_TO_SCAN=()
STAGE_TEMPLATES=false

# If INPUT_FILE variable exists then scan the specific resource
if [ -n "$INPUT_FILE" ]; then
  if [ ! -f "$INPUT_FILE" ]; then
    echo "Template file not found: $(display_name "$INPUT_FILE")"
    exit 1
  fi
  ORIGINALS+=("$INPUT_FILE")
  STAGE_TEMPLATES=true
elif [ -n "$INPUT_STACK_NAME" ]; then
  SCAN_ARGS+=(--format cdk)
  ORIGINALS+=("$INPUT_STACK_NAME")
  RESOURCES_TO_SCAN+=("$INPUT_STACK_NAME")
else
  # Otherwise scan directory provided (root by default)
  if [ ! -d "$INPUT_DIRECTORY" ]; then
    echo "Directory not found: $(display_name "$INPUT_DIRECTORY")"
    exit 1
  fi

  # Use 'find' to search for YAML and JSON files inside the directory
  while IFS= read -r -d $'\0' file; do
    ORIGINALS+=("$file")
  done < <(find "$INPUT_DIRECTORY" -type f \( -name "*.json" -o -name "*.yaml" -o -name "*.yml" \) -print0)

  # Refuse to report success when nothing was scanned
  if [ "${#ORIGINALS[@]}" -eq 0 ]; then
    echo "No template files found in directory: $(display_name "$INPUT_DIRECTORY")"
    exit 1
  fi
  echo "${#ORIGINALS[@]} file(s) found in directory: $(display_name "$INPUT_DIRECTORY")"
  STAGE_TEMPLATES=true
fi

# sustainability-scanner rebuilds a shell-style command string from the template
# path, so quotes, spaces or line breaks in a file name can change the arguments
# given to cfn-guard and make a template silently go unscanned. Copy every
# template to a staging directory under a neutral name (counter + fixed
# extension) so no attacker-controlled characters ever reach the scanner. The
# original path is restored in the report by report.py.
if [ "$STAGE_TEMPLATES" = true ]; then
  # Explicit template: a TMPDIR containing whitespace or quotes must not leak in
  STAGING_DIR=$(mktemp -d /tmp/susscan.XXXXXXXX) || { echo "Unable to create staging directory"; exit 1; }
  LABELS_FILE=$(mktemp /tmp/susscan-labels.XXXXXXXX) || { echo "Unable to create labels file"; exit 1; }

  COUNTER=0
  for ORIGINAL in "${ORIGINALS[@]}"; do
    # Keep the extension: the scanner and cfn-guard may rely on it
    case "$ORIGINAL" in
      *.json) EXT=json ;;
      *.yaml) EXT=yaml ;;
      *.yml) EXT=yml ;;
      *)
        # Only reachable in file mode with a custom extension
        FIRST=$(tr -d ' \t\r\n' < "$ORIGINAL" | head -c 1)
        if [ "$FIRST" = "{" ]; then EXT=json; else EXT=yaml; fi
        ;;
    esac
    COUNTER=$((COUNTER + 1))
    printf -v STAGED '%s/t%04d.%s' "$STAGING_DIR" "$COUNTER" "$EXT"
    if ! cp -- "$ORIGINAL" "$STAGED"; then
      echo "Unable to read template: $(display_name "$ORIGINAL")"
      exit 1
    fi
    # NUL-separated pairs: NUL is the only byte that cannot appear in a path
    printf '%s\0%s\0' "$STAGED" "$ORIGINAL" >> "$LABELS_FILE"
    RESOURCES_TO_SCAN+=("$STAGED")
  done
fi

# Run the scanner once per resource. Every argument is quoted so a path can
# never be split into several arguments or expanded as a glob.
RESULTS_FILE=$(mktemp)
for i in "${!RESOURCES_TO_SCAN[@]}"; do
  RESOURCE="${RESOURCES_TO_SCAN[$i]}"
  echo "Running susscanner on file: $(display_name "${ORIGINALS[$i]}")"
  printf 'susscanner'; printf ' %q' "${SCAN_ARGS[@]}" "$RESOURCE"; printf '\n'
  SUSSCAN_RESULTS=$(susscanner "${SCAN_ARGS[@]}" "$RESOURCE")

  SUSSCAN_EXIT_CODE=$?

  if [ $SUSSCAN_EXIT_CODE -eq 0 ]; then
    echo "${SUSSCAN_RESULTS}"
    # Accumulate each report so results are not overwritten between scans
    echo "${SUSSCAN_RESULTS}" >> "$RESULTS_FILE"
  else
    echo "Scan failed with exit code $SUSSCAN_EXIT_CODE."
    exit $SUSSCAN_EXIT_CODE
  fi
done

# Consolidate reports, restore the original template names, write the step
# summary and evaluate failure gates. LABELS_FILE is empty in CDK mode.
MERGED_RESULTS=$(python3 "${REPORT_SCRIPT:-/report.py}" "$RESULTS_FILE" ${LABELS_FILE:+"$LABELS_FILE"})
GATE_EXIT_CODE=$?

# Save output to GitHub
EOF=$(dd if=/dev/urandom bs=15 count=1 status=none | base64)
{ echo "SUSSCAN_RESULTS<<$EOF"; echo "${MERGED_RESULTS:0:65536}"; echo "$EOF"; } >> "$GITHUB_ENV"
{ echo "results<<$EOF"; echo "$MERGED_RESULTS"; echo "$EOF"; } >> "$GITHUB_OUTPUT"

exit $GATE_EXIT_CODE
