#!/usr/bin/env bash
set -uo pipefail
repo_root=$(git rev-parse --show-toplevel) || exit 1
cd "$repo_root" || exit 1
env_dir=${CI_ENV_DIR:-$repo_root/.venv}
for tool in python ruff pyright; do
    if [[ ! -x "$env_dir/bin/$tool" ]]; then
        echo "Missing $tool. Run: uv sync --locked --group lint" >&2
        exit 1
    fi
done
failed=0
run_check() {
    local name="$1"
    shift
    printf '\n%s\n' "$name"
    "$@" || failed=1
}
run_check 'Working-file privacy scan' "$env_dir/bin/python" scripts/check_privacy.py worktree
run_check 'Staged privacy scan' "$env_dir/bin/python" scripts/check_privacy.py staged
run_check 'History privacy scan' "$env_dir/bin/python" scripts/check_privacy.py history
run_check 'Staged secret scan' bash scripts/check-secrets.sh --staged
run_check 'History secret scan' bash scripts/check-secrets.sh
run_check 'Privacy, secret, and size hook regressions' bash scripts/test-secret-hooks.sh
run_check 'File size boundary regressions' bash scripts/test-staged-file-size.sh
run_check 'Ruff lint' "$env_dir/bin/ruff" check .
run_check 'Ruff format' "$env_dir/bin/ruff" format --check .
run_check 'Pyright' "$env_dir/bin/pyright" --pythonpath "$env_dir/bin/python"
run_check 'Unit tests' "$env_dir/bin/python" -m unittest discover -s tests -v
while IFS= read -r -d '' script; do
    run_check "Shell syntax: $script" bash -n "$script"
done < <(find scripts runs .githooks -type f \( -name '*.sh' -o -name 'pre-commit' -o -name 'pre-push' -o -name 'commit-msg' \) -print0)
exit "$failed"
