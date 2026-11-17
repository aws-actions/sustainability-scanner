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
STOP_TOKEN=""
STAGING_DIR=""
STATE_DIR=""
cleanup() {
  if [ -n "$STOP_TOKEN" ]; then echo "::$STOP_TOKEN::"; fi
  if [ -n "$STAGING_DIR" ]; then rm -rf -- "$STAGING_DIR"; fi
  if [ -n "$STATE_DIR" ]; then rm -rf -- "$STATE_DIR"; fi
  return 0
}
trap cleanup EXIT

# Template content and the scanner output (for example resource paths in the
# JSON report) can contain "::cmd::" lines, or "##[cmd]" anywhere in a line.
# Stop the runner from processing workflow commands until the action exits;
# cleanup prints the token that resumes them.
STOP_TOKEN=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
if [[ ! "$STOP_TOKEN" =~ ^[0-9a-f]{32}$ ]]; then
  STOP_TOKEN=""
  echo "Unable to generate a stop-commands token"
  exit 1
fi
echo "::stop-commands::$STOP_TOKEN"

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
  MODE="file"
elif [ -n "$INPUT_STACK_NAME" ]; then
  # The scanner runs `cdk synth <stack_name>` through shlex, so whitespace,
  # quotes, a backslash or a leading dash could inject extra cdk arguments
  # (for example --app). Wildcards are safe: no shell and no glob expansion.
  if [[ ! "$INPUT_STACK_NAME" =~ ^[A-Za-z0-9_./:*?-]+$ ]] || [[ "$INPUT_STACK_NAME" == -* ]]; then
    echo "stack_name contains unsupported characters. Allowed: letters, digits and _ . / : * ? - (must not start with -)"
    exit 1
  fi
  SCAN_ARGS+=(--format cdk)
  ORIGINALS+=("$INPUT_STACK_NAME")
  RESOURCES_TO_SCAN+=("$INPUT_STACK_NAME")
  MODE="cdk"
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
  MODE="directory"
fi

# sustainability-scanner 1.3.0 ignores cfn-guard's exit code and error output
# and reports a clean score when cfn-guard fails. It finds cfn-guard through
# PATH, so put a wrapper first on PATH for each scan: the wrapper runs the real
# binary unchanged and records its argv, exit code, stdout and stderr in the
# run directory. report.py checks that record against the scanner's report and
# fails closed when cfn-guard did not evaluate the file completely. stderr is
# kept out of the log (it echoes template content); report.py prints it escaped.
REAL_GUARD=$(command -v cfn-guard)
if [[ "$REAL_GUARD" != /* ]]; then
  echo "cfn-guard not found"
  exit 1
fi
STATE_DIR=$(mktemp -d /tmp/susscan-state.XXXXXXXX) || { echo "Unable to create state directory"; exit 1; }
mkdir "$STATE_DIR/bin" "$STATE_DIR/runs" || { echo "Unable to create state directory"; exit 1; }
cat > "$STATE_DIR/bin/cfn-guard" <<'EOF'
#!/bin/bash
# Records what CFN Guard really did, so report.py can check the scanner's report.
state=${SUSSCAN_GUARD_STATE:?}
real=${SUSSCAN_REAL_GUARD:?}
echo call >> "$state/guard.calls"
printf '%s\0' "$@" > "$state/guard.argv"
"$real" "$@" > "$state/guard.stdout" 2> "$state/guard.stderr"
rc=$?
echo "$rc" > "$state/guard.exit"
cat "$state/guard.stdout"
exit "$rc"
EOF
chmod 700 "$STATE_DIR/bin/cfn-guard" || { echo "Unable to create the cfn-guard wrapper"; exit 1; }

# sustainability-scanner rebuilds a shell-style command string from the template
# path, so quotes, spaces or line breaks in a file name can change the arguments
# given to cfn-guard and make a template silently go unscanned. Copy every
# template to a staging directory under a neutral name (counter + fixed
# extension) so no attacker-controlled characters ever reach the scanner. The
# original path is restored in the report by report.py.
if [ "$STAGE_TEMPLATES" = true ]; then
  # Explicit template: a TMPDIR containing whitespace or quotes must not leak in
  STAGING_DIR=$(mktemp -d /tmp/susscan.XXXXXXXX) || { echo "Unable to create staging directory"; exit 1; }

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
    RESOURCES_TO_SCAN+=("$STAGED")
  done
fi

# Run the scanner once per resource. Every argument is quoted so a path can
# never be split into several arguments or expanded as a glob. Every resource
# is scanned, even after an error; report.py decides the outcome. Each run
# directory holds the staged path, the original name, the scanner's output and
# exit code, and the cfn-guard record written by the wrapper.
for i in "${!RESOURCES_TO_SCAN[@]}"; do
  RESOURCE="${RESOURCES_TO_SCAN[$i]}"
  printf -v RUN_DIR '%s/runs/%04d' "$STATE_DIR" $((i + 1))
  mkdir "$RUN_DIR" || { echo "Unable to create run directory"; exit 1; }
  printf '%s' "$RESOURCE" > "$RUN_DIR/resource"
  printf '%s' "${ORIGINALS[$i]}" > "$RUN_DIR/original"

  echo "Running susscanner on file: $(display_name "${ORIGINALS[$i]}")"
  printf 'susscanner'; printf ' %q' "${SCAN_ARGS[@]}" "$RESOURCE"; printf '\n'
  SUSSCAN_GUARD_STATE="$RUN_DIR" SUSSCAN_REAL_GUARD="$REAL_GUARD" PATH="$STATE_DIR/bin:$PATH" \
    susscanner "${SCAN_ARGS[@]}" "$RESOURCE" > "$RUN_DIR/scanner.stdout" 2> "$RUN_DIR/scanner.stderr"
  SUSSCAN_EXIT_CODE=$?
  echo "$SUSSCAN_EXIT_CODE" > "$RUN_DIR/scanner.exit"

  GUARD_EXIT="not run"
  if [ -s "$RUN_DIR/guard.exit" ]; then GUARD_EXIT=$(tr -cd '0-9' < "$RUN_DIR/guard.exit"); fi
  echo "cfn-guard exit code: $GUARD_EXIT"
  if [ $SUSSCAN_EXIT_CODE -eq 0 ]; then
    # A report built from a failed cfn-guard run is meaningless (score 0)
    if [ "$GUARD_EXIT" = 0 ] || [ "$GUARD_EXIT" = 19 ]; then
      cat "$RUN_DIR/scanner.stdout"
    else
      echo "Scanner report discarded: cfn-guard did not return a result"
    fi
  fi
done

# Check every run against cfn-guard's own result, restore the original
# template names, write the step summary and evaluate failure gates.
MERGED_RESULTS=$(python3 "${REPORT_SCRIPT:-/report.py}" "$MODE" "$STATE_DIR/runs")
GATE_EXIT_CODE=$?

# Save output to GitHub
EOF=$(dd if=/dev/urandom bs=15 count=1 status=none | base64)
{ echo "SUSSCAN_RESULTS<<$EOF"; echo "${MERGED_RESULTS:0:65536}"; echo "$EOF"; } >> "$GITHUB_ENV"
{ echo "results<<$EOF"; echo "$MERGED_RESULTS"; echo "$EOF"; } >> "$GITHUB_OUTPUT"

exit $GATE_EXIT_CODE
