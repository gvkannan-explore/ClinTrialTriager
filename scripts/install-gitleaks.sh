#!/usr/bin/env bash
set -euo pipefail

version=8.30.1
repo_root=$(git rev-parse --show-toplevel)
install_dir="$repo_root/.tools/bin"
case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    *) echo 'Unsupported OS. Install Gitleaks manually.' >&2; exit 1 ;;
esac
case "$(uname -m)" in
    arm64|aarch64) arch=arm64 ;;
    x86_64|amd64) arch=x64 ;;
    *) echo 'Unsupported architecture. Install Gitleaks manually.' >&2; exit 1 ;;
esac

archive="gitleaks_${version}_${os}_${arch}.tar.gz"
release_url="https://github.com/gitleaks/gitleaks/releases/download/v${version}"
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
curl --fail --silent --show-error --location "$release_url/$archive" -o "$tmp_dir/$archive"
curl --fail --silent --show-error --location "$release_url/gitleaks_${version}_checksums.txt" -o "$tmp_dir/checksums.txt"
awk -v archive="$archive" '$2 == archive {print}' "$tmp_dir/checksums.txt" > "$tmp_dir/selected-checksum.txt"
if [[ ! -s "$tmp_dir/selected-checksum.txt" ]]; then
    echo 'Release checksum is missing; installation stopped.' >&2
    exit 1
fi
(
    cd "$tmp_dir"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum --check selected-checksum.txt
    else
        shasum -a 256 --check selected-checksum.txt
    fi
)
tar -xzf "$tmp_dir/$archive" -C "$tmp_dir" gitleaks
mkdir -p "$install_dir"
install -m 755 "$tmp_dir/gitleaks" "$install_dir/gitleaks"
"$install_dir/gitleaks" version
