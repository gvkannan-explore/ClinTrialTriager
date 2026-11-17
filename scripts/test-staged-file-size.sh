#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
checker="$repo_root/scripts/check-staged-file-size.sh"
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
mkdir "$tmp_dir/repo"
cd "$tmp_dir/repo"
git init --quiet

large_file() {
    head -c "${2:-20001}" /dev/zero | tr '\0' x > "$1"
}
expect_pass() {
    if ! bash "$checker" > "$tmp_dir/result" 2>&1; then
        cat "$tmp_dir/result" >&2
        echo "FAIL: $1" >&2
        exit 1
    fi
}
expect_fail() {
    if bash "$checker" > "$tmp_dir/result" 2>&1; then
        echo "FAIL: $1" >&2
        exit 1
    fi
    if ! grep -q 'Split each oversized file' "$tmp_dir/result"; then
        echo 'FAIL: rejection must explain how to split files' >&2
        exit 1
    fi
}

large_file unstaged.py
printf 'small staged file\n' > small.py
git add small.py
expect_pass 'Unstaged oversized files must be ignored'

large_file boundary.py 20000
git add boundary.py
large_file boundary.py 25000
expect_pass 'Exactly 5000 staged tokens must pass despite larger working copy'

large_file 'too big.py'
git add 'too big.py'
printf 'small working copy\n' > 'too big.py'
expect_fail 'Must check oversized staged content despite smaller working copy'
grep -q '20001 staged bytes (5000.25 tokens)' "$tmp_dir/result"
git read-tree --empty

mkdir -p generated vendor
for path in uv.lock package-lock.json pnpm-lock.yaml generated/client.py vendor/library.py client.generated.ts service_pb2.py; do
    large_file "$path"
    git add "$path"
done
expect_pass 'Conventional lockfiles, generated files and vendored files are excluded'
git read-tree --empty

large_file custom-output.py
large_file external-library.py
printf 'custom-output.py linguist-generated=true\nexternal-library.py linguist-vendored\n' > .gitattributes
git add .gitattributes custom-output.py external-library.py
printf 'custom-output.py -linguist-generated\n' > .gitattributes
expect_pass 'Generated and vendored attributes must use the staged version'
git add .gitattributes
printf 'custom-output.py linguist-generated=true\n' > .gitattributes
expect_fail 'An unstaged exclusion must not bypass checks'
git read-tree --empty

large_file 'first oversized.md'
large_file $'second\nfile.py'
git add 'first oversized.md' $'second\nfile.py'
expect_fail 'All oversized paths must be reported, including unusual filenames'
[[ $(grep -c '^File size blocked:' "$tmp_dir/result") -eq 2 ]]
git read-tree --empty

# A gitlink can refer to an object unavailable in this repository.
git update-index --add --cacheinfo 160000,1111111111111111111111111111111111111111,submodule
expect_pass 'Submodule entries must be skipped without loading their objects'

printf 'PASS: staged byte limit, partial staging, exclusions, unusual paths and submodules\n'
