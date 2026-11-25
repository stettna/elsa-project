#!/usr/bin/env bash

set -euo pipefail

CONFIG_FILE="$1"
CSV_FILE="$2"
SUBSET_NAME="$3"
OUTPUT_DIR="${4:-runs}"
REDO_FLAG="${5:-}"

# Extract instance IDs (skip header), join into comma-separated string
INSTANCE_FILTER=$(tail -n +2 "$CSV_FILE" | cut -d, -f1 | paste -sd "|" -)

# Build optional args
EXTRA_ARGS=()
if [[ "$REDO_FLAG" == "redo" ]]; then
    EXTRA_ARGS+=(--redo-existing)
fi

# Run three iterations, appending the iteration number to the output directory.
for iteration in 1 2 3; do
    ITERATION_OUTPUT_DIR="${OUTPUT_DIR}${iteration}"
    mkdir -p "$ITERATION_OUTPUT_DIR"

    echo "Starting iteration $iteration; output directory: $ITERATION_OUTPUT_DIR"
    mini-extra swebench --subset "$SUBSET_NAME" --workers 2 --split test --config "$CONFIG_FILE" --output "$ITERATION_OUTPUT_DIR" --filter "$INSTANCE_FILTER" "${EXTRA_ARGS[@]}"
done

echo "All three runs complete."
