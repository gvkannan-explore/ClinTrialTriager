"""Check Git file contents without printing sensitive matches."""

import argparse
import getpass
import json
import os
import re
import subprocess
from pathlib import Path

EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PERSONAL_PATH = re.compile(
    rb"/(?:Users|home)/[^/\s\"'\\]+|[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+", re.I
)
SAFE_EMAIL_DOMAINS = {
    b"example.com",
    b"example.org",
    b"example.net",
    b"example.test",
    b"example.invalid",
}
SAFE_EMAILS = {b"contributor" + b"@users.noreply.github.com"}
PRIVATE_DIRS = {
    "datasets",
    "runs",
    "runs_modal",
    ".audit",
    "agent-transcripts",
    "envs",
    ".tools",
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)


def local_identities(root: Path) -> list[str]:
    values = [getpass.getuser(), Path.home().name]
    for key in ("user.name", "user.email"):
        result = subprocess.run(
            ["git", "config", "--get", key], capture_output=True, text=True
        )
        if result.returncode == 0:
            values.append(result.stdout.strip())
    profile = root / ".privacy-identifiers.json"
    if profile.exists():
        values.extend(json.loads(profile.read_text()))
    return sorted(
        {
            v.casefold()
            for v in values
            if len(v) >= 4
            and v.casefold()
            not in {"root", "runner", "runneradmin", "ubuntu", "nobody"}
            and v not in {"Contributor", "contributor@users.noreply.github.com"}
        }
    )


def findings(data: bytes, identities: list[str]) -> set[str]:
    found = set()
    if PERSONAL_PATH.search(data):
        found.add("personal directory")
    if any(
        m.group().lower() not in SAFE_EMAILS
        and m.group().lower().rsplit(b"@", 1)[1] not in SAFE_EMAIL_DOMAINS
        for m in EMAIL.finditer(data)
    ):
        found.add("email")
    text = data.decode("utf-8", errors="replace").casefold()
    if any(identity in text for identity in identities):
        found.add("local identity")
    return found


def private_path(path: str) -> bool:
    if path == "runs/perform_ci.sh":
        return False
    parts = Path(path).parts
    return (
        bool(set(parts) & PRIVATE_DIRS)
        or path in {"decisions.tsv", ".privacy-identifiers.json"}
        or any(
            p == ".env" or p.startswith(".env.") or p.endswith((".pem", ".key"))
            for p in parts
        )
    )


def scan(root: Path, mode: str, ref: str = "HEAD") -> int:
    identities = local_identities(root)
    problems = 0
    versions = (
        git("rev-list", ref).decode().splitlines() if mode == "history" else [mode]
    )
    for version in versions:
        if mode == "history":
            metadata = git(
                "show", "-s", "--format=%an%n%ae%n%cn%n%ce", version
            ).splitlines()
            expected_email = next(iter(SAFE_EMAILS))
            if metadata != [
                b"Contributor",
                expected_email,
                b"Contributor",
                expected_email,
            ]:
                print(
                    f"Privacy blocked: ref={version[:12]} rules=nonanonymous author metadata"
                )
                problems += 1
            if findings(git("show", "-s", "--format=%B", version), identities):
                print(f"Privacy blocked: ref={version[:12]} rules=commit message")
                problems += 1
            paths = git("ls-tree", "-rz", "--name-only", version).split(b"\0")
        elif mode == "staged":
            paths = git(
                "diff",
                "--cached",
                "--name-only",
                "--no-renames",
                "--diff-filter=ACMT",
                "-z",
            ).split(b"\0")
        else:
            paths = git(
                "ls-files", "--cached", "--others", "--exclude-standard", "-z"
            ).split(b"\0")
        for raw_path in sorted(set(paths) - {b""}):
            path = os.fsdecode(raw_path)
            tags = findings(raw_path, identities)
            if private_path(path):
                tags.add("private file")
            if mode == "worktree":
                file = root / path
                if file.is_symlink():
                    data = os.fsencode(os.readlink(file))
                elif file.is_file():
                    data = file.read_bytes()
                else:
                    continue
            else:
                data = git("show", f"{version if mode == 'history' else ''}:{path}")
            tags |= findings(data, identities)
            if tags:
                # Report a path hash rather than echoing a potentially personal filename.
                import hashlib

                file_id = hashlib.sha256(raw_path).hexdigest()[:12]
                print(
                    f"Privacy blocked: file-id={file_id} ref={version[:12]} rules={','.join(sorted(tags))}"
                )
                problems += 1
    print(f"Privacy scan: {problems} finding(s) ({mode}).")
    return int(problems > 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=["worktree", "staged", "history", "identity", "message"],
        default="worktree",
        nargs="?",
    )
    parser.add_argument(
        "--ref",
        default="HEAD",
        help="History tip to check, including all its ancestors",
    )
    parser.add_argument("--message-file", type=Path)
    args = parser.parse_args()
    root = Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip())
    os.chdir(root)
    if args.mode == "identity":
        expected = b"Contributor <" + next(iter(SAFE_EMAILS)) + b"> "
        for variable in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
            if not git("var", variable).startswith(expected):
                print(
                    "Privacy blocked: use the anonymous repository identity from bash scripts/setup-hooks.sh."
                )
                return 1
        return 0
    if args.mode == "message":
        if args.message_file is None:
            parser.error("message mode requires --message-file")
        if findings(args.message_file.read_bytes(), local_identities(root)):
            print(
                "Privacy blocked: commit message contains personal information (matches redacted)."
            )
            return 1
        return 0
    return scan(root, args.mode, args.ref)


if __name__ == "__main__":
    raise SystemExit(main())
