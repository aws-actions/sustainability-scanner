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

# If File Variable exists then scan the specific resource
if [ -n "$INPUT_FILE" ]; then
  RESOURCES_TO_SCAN+=("$INPUT_FILE")
else
# Otherwise scan directory provided (root by default) to populate the array with all .yml or .yaml files
  echo "running susscanner on directory: $INPUT_DIRECTORY"
  for FILE in "$INPUT_DIRECTORY"/*.yaml "$INPUT_DIRECTORY"/*.yml; do
    RESOURCES_TO_SCAN+=("$FILE")
  done
fi

# Build command
for RESOURCE in $RESOURCES_TO_SCAN; do
  echo "running susscanner on file: $RESOURCE"
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

exit $SUSSCAN_EXIT_CODE