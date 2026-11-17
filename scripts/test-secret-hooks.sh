#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
fixture="$tmp_dir/repo"
mkdir -p "$fixture/scripts" "$fixture/.githooks" "$fixture/.tools/bin" "$fixture/runs"
printf '#!/usr/bin/env bash\nexit "${FAKE_CI_STATUS:-0}"\n' > "$fixture/runs/perform_ci.sh"
cp "$repo_root/scripts/check-secrets.sh" "$fixture/scripts/"
cp "$repo_root/scripts/check-staged-file-size.sh" "$fixture/scripts/"
cp "$repo_root/scripts/check_privacy.py" "$fixture/scripts/"
cp "$repo_root/.githooks/pre-commit" "$repo_root/.githooks/pre-push" "$repo_root/.githooks/commit-msg" "$fixture/.githooks/"
ln -s "$repo_root/.tools/bin/gitleaks" "$fixture/.tools/bin/gitleaks"
cd "$fixture"
git init --quiet
git config user.name Contributor
git config user.email contributor@users.noreply.github.com
git config core.hooksPath .githooks
printf 'A clean file\n' > clean.txt
git add clean.txt
git commit --quiet -m 'Clean fixture'
clean_oid=$(git rev-parse HEAD)
zero_oid=$(printf '%040d' 0)
printf 'refs/heads/main %s refs/heads/main %s\n' "$clean_oid" "$zero_oid" | bash .githooks/pre-push

printf '%s%s%s\n' 'contact=' 'person' '@mail.test' > personal.txt
git add personal.txt
if bash .githooks/pre-commit > "$tmp_dir/privacy.log" 2>&1; then
    echo 'FAIL: pre-commit accepted a personal email' >&2
    exit 1
fi
if grep -q 'person''@mail.test' "$tmp_dir/privacy.log"; then
    echo 'FAIL: privacy diagnostics exposed a matched email' >&2
    exit 1
fi
git restore --staged personal.txt
printf 'placeholder\n' > .env
git add -f .env
if bash .githooks/pre-commit > "$tmp_dir/private-file.log" 2>&1; then
    echo 'FAIL: pre-commit accepted a private file' >&2
    exit 1
fi
git restore --staged .env
printf '%s%s%s\n' 'Contact ' 'person' '@mail.test' > "$tmp_dir/message"
if bash .githooks/commit-msg "$tmp_dir/message" > "$tmp_dir/message.log" 2>&1; then
    echo 'FAIL: commit-msg accepted personal information' >&2
    exit 1
fi
if GIT_AUTHOR_NAME='Another Person' bash .githooks/pre-commit > "$tmp_dir/identity.log" 2>&1; then
    echo 'FAIL: pre-commit accepted a personal identity override' >&2
    exit 1
fi

head -c 20001 /dev/zero | tr '\0' x > oversized.py
git add oversized.py
if bash .githooks/pre-commit > "$tmp_dir/size.log" 2>&1; then
    echo 'FAIL: pre-commit accepted an oversized staged file' >&2
    exit 1
fi
if ! grep -q 'Split each oversized file' "$tmp_dir/size.log"; then
    echo 'FAIL: pre-commit did not explain how to split the oversized file' >&2
    exit 1
fi
git restore --staged oversized.py

# This token is generated locally for the test and is not a real credential.
printf 'token = "%s%s"\n' 'ghp_' '81b7d90e5f3a6240c9d8b701fe4a3c65209de8ab' > secret.txt
git add secret.txt
if bash .githooks/pre-commit > "$tmp_dir/scan.log" 2>&1; then
    echo 'FAIL: pre-commit accepted a synthetic secret' >&2
    exit 1
fi
# Bypass only inside the disposable fixture to test the pre-push hook.
git -c core.hooksPath=/dev/null commit --quiet -m 'Synthetic secret fixture'
secret_oid=$(git rev-parse HEAD)
if printf 'refs/heads/main %s refs/heads/main %s\n' "$secret_oid" "$clean_oid" | bash .githooks/pre-push > "$tmp_dir/scan.log" 2>&1; then
    echo 'FAIL: pre-push accepted a synthetic secret' >&2
    exit 1
fi
if printf 'refs/heads/secret %s refs/heads/secret %s\nrefs/heads/clean %s refs/heads/clean %s\n' \
    "$secret_oid" "$zero_oid" "$clean_oid" "$zero_oid" | bash .githooks/pre-push > "$tmp_dir/multi.log" 2>&1; then
    echo 'FAIL: a later clean ref masked an earlier secret scan failure' >&2
    exit 1
fi
if printf 'refs/heads/clean %s refs/heads/clean %s\n' "$clean_oid" "$zero_oid" | \
    FAKE_CI_STATUS=7 bash .githooks/pre-push > "$tmp_dir/ci.log" 2>&1; then
    echo 'FAIL: pre-push ignored a failed local check suite' >&2
    exit 1
fi
if ! grep -q REDACTED "$tmp_dir/scan.log"; then
    echo 'FAIL: synthetic secret was not reported with redaction' >&2
    exit 1
fi
if grep -q '81b7d90e5f3a6240c9d8b701fe4a3c65209de8ab' "$tmp_dir/scan.log"; then
    echo 'FAIL: scanner exposed the synthetic secret in its output' >&2
    exit 1
fi
printf 'PASS: clean commits pass; privacy, identity, messages, file size, secrets, and failed CI block with redacted output\n'
