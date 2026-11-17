#!/usr/bin/env bash
set -u -o pipefail

repo_root=$(git rev-parse --show-toplevel) || exit 1
cd "$repo_root" || exit 1
staged_paths=$(mktemp) || exit 1
trap 'rm -f "$staged_paths"' EXIT

# Read only added/modified staged paths, including both sides of renames as
# independent additions/deletions. NUL separation preserves unusual filenames.
git diff --cached --name-only --no-renames --diff-filter=ACMT -z -- > "$staged_paths" || exit 1
failed=0
while IFS= read -r -d '' path; do
    case "$path" in
        *.lock|*.lockb|package-lock.json|*/package-lock.json|npm-shrinkwrap.json|*/npm-shrinkwrap.json|pnpm-lock.yaml|*/pnpm-lock.yaml)
            continue ;;
        generated/*|*/generated/*|__generated__/*|*/__generated__/*|vendor/*|*/vendor/*|node_modules/*|*/node_modules/*|dist/*|*/dist/*|build/*|*/build/*)
            continue ;;
        *.generated.*|*.gen.*|*.min.js|*.min.css|*.js.map|*.css.map|*.pb.go|*.pb.cc|*.pb.h|*_pb2.py|*_pb2_grpc.py)
            continue ;;
    esac
    excluded=0
    for attribute in linguist-generated linguist-vendored; do
        value=$(git check-attr --cached "$attribute" -- "$path") || exit 1
        case "${value##*: }" in true|set) excluded=1 ;; esac
    done
    if [[ "$excluded" -eq 1 ]]; then
        continue
    fi
    entry=$(git ls-files --stage -- ":(literal)$path") || exit 1
    # Submodule commit objects need not be present in the parent repository.
    if [[ "$entry" == 160000\ * ]]; then
        continue
    fi
    bytes=$(git cat-file -s ":$path") || exit 1
    if [[ "$bytes" -gt 20000 ]]; then
        printf 'File size blocked: %q has %s staged bytes (%d.%02d tokens); limit is 20000 bytes (5000 tokens).\n' \
            "$path" "$bytes" "$((bytes / 4))" "$(((bytes % 4) * 25))" >&2
        failed=1
    fi
done < "$staged_paths"

if [[ "$failed" -ne 0 ]]; then
    cat >&2 <<'HELP'

Split each oversized file before committing:
  1. Group code by responsibility and move cohesive functions/classes into
     smaller modules. Update imports and callers; keep each file <= 20000 bytes.
  2. Move independent test scenarios into focused test files and share fixtures.
     Split long documents by topic and link the new documents from the original.
  3. Run the relevant checks, then stage every changed/new file with git add
     and retry the commit. Editing an unstaged copy does not change this check.

For actual generated or vendored files, add a precise path to .gitattributes
with linguist-generated=true or linguist-vendored=true and stage that file too.
Do not mark maintained source or tests as generated to bypass the limit.
HELP
fi
exit "$failed"
