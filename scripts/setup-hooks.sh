#!/usr/bin/env bash
set -euo pipefail
repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"
python3 - <<'PY'
import json
import os
from pathlib import Path
from scripts.check_privacy import local_identities

root = Path.cwd()
identities = local_identities(root)
profile = root / '.privacy-identifiers.json'
fd = os.open(profile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as stream:
    json.dump(identities, stream)
os.chmod(profile, 0o600)
PY
git config --local core.hooksPath .githooks
git config --local user.name Contributor
git config --local user.email contributor@users.noreply.github.com
printf 'Hooks enabled. Future commits use an anonymous repository-local identity. Global Git settings are unchanged.\n'
