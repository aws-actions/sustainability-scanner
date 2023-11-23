#!/bin/bash

# Leverage the default env variables as described in:
# https://docs.github.com/en/actions/reference/environment-variables#default-environment-variables
if [[ $GITHUB_ACTIONS != "true" ]]
then
  susscanner "$@"
  exit $?
fi

# If an external set of rules is defined then add it to RULES_FILE var
if [ -n "$INPUT_RULES_FILE" ] && [ -e "$INPUT_RULES_FILE" ]; then
  RULES_FILE="--rules-file $INPUT_RULES_FILE"
fi

# Create an empty array to store file names to scan
RESOURCES_TO_SCAN=()

# If INPUT_FILE variable exists then scan the specific resource
if [ -n "$INPUT_FILE" ]; then
  RESOURCES_TO_SCAN+=("$INPUT_FILE")
else
# Otherwise scan directory provided (root by default)
  if [ -d "$INPUT_DIRECTORY" ]; then
    # Use 'find' to search for YAML and JSON files inside the directory
    while IFS= read -r -d $'\0' file; do
      RESOURCES_TO_SCAN+=("$file")
    done < <(find "$INPUT_DIRECTORY" -type f \( -name "*.json" -o -name "*.yaml" -o -name "*.yml" \) -print0)

    # Check if any files were found
    if [ -n "$RESOURCES_TO_SCAN" ]; then
      echo "${#RESOURCES_TO_SCAN[@]} file(s) found in directory: $INPUT_DIRECTORY"
    else
      echo "No template files found in directory: $INPUT_DIRECTORY" 
    fi
  else
    echo "Directory not found: $INPUT_DIRECTORY"
  fi
fi

# Build command
for RESOURCE in "${RESOURCES_TO_SCAN[@]}"; do
  echo "Running susscanner on file: $RESOURCE"
  echo "susscanner $RESOURCE $RULES_FILE"
  SUSSCAN_RESULTS=$(susscanner $RESOURCE $RULES_FILE)

  SUSSCAN_EXIT_CODE=$?

  if [ $SUSSCAN_EXIT_CODE -eq 0 ]; then
    echo "${SUSSCAN_RESULTS}"
  else
    echo "Scan failed with exit code $SUSSCAN_EXIT_CODE."
    exit $SUSSCAN_EXIT_CODE
  fi
done

# Save output to GitHub
EOF=$(dd if=/dev/urandom bs=15 count=1 status=none | base64)
{ echo "SUSSCAN_RESULTS<<$EOF"; echo "${SUSSCAN_RESULTS:0:65536}"; echo "$EOF"; } >> $GITHUB_ENV
{ echo "results<<$EOF"; echo "$SUSSCAN_RESULTS"; echo "$EOF"; } >> $GITHUB_OUTPUT

exit $SUSSCAN_EXIT_CODE