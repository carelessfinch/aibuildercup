#!/usr/bin/env bash
# Fails if any private/forbidden file is tracked in git.
set -euo pipefail

patterns=(
  "litrag/corpus/*"
  "litrag/index/*"
  "litrag/models/*"
  "training/data/*"
  "training/weights/*"
  "*.pdf"
  "*.task"
  "*.safetensors"
  "*.ckpt"
  "*.gguf"
)

bad=""
while IFS= read -r f; do
  for p in "${patterns[@]}"; do
    case "$f" in
      $p) bad="$bad$f\n"; break ;;
    esac
  done
done < <(git ls-files)

if [ -n "$bad" ]; then
  echo "PRIVATE/FORBIDDEN FILES TRACKED:"
  printf '%b' "$bad"
  echo "Remove them from the index and history."
  exit 1
fi

echo "private-file guard: OK"
