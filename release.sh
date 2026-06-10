#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./release.sh <version> [--dry-run]

Examples:
  ./release.sh 3.0.1
  ./release.sh v3.0.1
  ./release.sh 3.0.1 --dry-run

The script stages all changes, commits, tags, pushes main and the tag, and
creates a GitHub release from CHANGELOG.md. It also updates the integration
version in the repo before committing.
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 64
fi

VERSION="${1#v}"
TAG="v${VERSION}"
DRY_RUN=false

if [[ $# -eq 2 ]]; then
  if [[ "$2" != "--dry-run" ]]; then
    usage
    exit 64
  fi
  DRY_RUN=true
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid version: $1. Use semantic version format, for example 3.0.1." >&2
  exit 64
fi

if [[ ! -f "CHANGELOG.md" || ! -f "custom_components/djconnect/manifest.json" ]]; then
  echo "Run this script from the djconnect repository root." >&2
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag already exists locally: $TAG" >&2
  exit 1
fi

if [[ "$DRY_RUN" == false ]] && git ls-remote --exit-code --tags origin "refs/tags/${TAG}" >/dev/null 2>&1; then
  echo "Tag already exists on origin: $TAG" >&2
  exit 1
fi

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" == false ]]; then
    "$@"
  fi
}

bump_versions() {
  echo "+ update repo version to ${VERSION}"
  VERSION="$VERSION" DRY_RUN="$DRY_RUN" python3 - <<'PY'
import json
import os
import re
from pathlib import Path

version = os.environ["VERSION"]
tag = f"v{version}"
dry_run = os.environ["DRY_RUN"] == "true"


def replace_text(path: str, replacements: list[tuple[str, str]]) -> None:
    file_path = Path(path)
    text = file_path.read_text()
    updated = text
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, updated, flags=re.MULTILINE)
    if updated == text:
        print(f"  unchanged {path}")
        return
    print(f"  update {path}")
    if not dry_run:
        file_path.write_text(updated)


manifest_path = Path("custom_components/djconnect/manifest.json")
manifest = json.loads(manifest_path.read_text())
if manifest.get("version") != version:
    print("  update custom_components/djconnect/manifest.json")
    if not dry_run:
        manifest["version"] = version
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
else:
    print("  unchanged custom_components/djconnect/manifest.json")

replace_text(
    "custom_components/djconnect/const.py",
    [(r'^VERSION = "[^"]+"$', f'VERSION = "{version}"')],
)
replace_text(
    "CHANGELOG.md",
    [(r"^## .+$", f"## {version}")],
)
replace_text(
    "README.md",
    [
        (r"^- Home Assistant integration: `[^`]+`$", f"- Home Assistant integration: `{version}`"),
        (r'  "version": "[^"]+",', f'  "version": "{version}",'),
        (r'  "version_tag": "v[^"]+",', f'  "version_tag": "{tag}",'),
        (
            r"releases/download/v[0-9]+\.[0-9]+\.[0-9]+/",
            f"releases/download/{tag}/",
        ),
        (
            r"releases/download/v[0-9]+\.[0-9]+\.[0-9]+/",
            f"releases/download/{tag}/",
        ),
        (
            r"djconnect-lilygo-t-embed-s3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-lilygo-t-embed-s3-{tag}.bin",
        ),
        (
            r"djconnect-lilygo-t-embed-s3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-lilygo-t-embed-s3-{tag}.bin",
        ),
        (
            r"djconnect-esp32-s3-box-3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-esp32-s3-box-3-{tag}.bin",
        ),
        (
            r"djconnect-esp32-s3-box-3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-esp32-s3-box-3-{tag}.bin",
        ),
        (r'  "min_ha_integration": "[^"]+"', f'  "min_ha_integration": "{version}"'),
        (r"\./release\.sh [0-9]+\.[0-9]+\.[0-9]+", f"./release.sh {version}"),
        (r"\./release\.sh [0-9]+\.[0-9]+\.[0-9]+ --dry-run", f"./release.sh {version} --dry-run"),
        (r'git commit -m "Release DJConnect v[^"]+"', f'git commit -m "Release DJConnect {tag}"'),
        (r"git tag v[0-9]+\.[0-9]+\.[0-9]+", f"git tag {tag}"),
        (r"git push origin v[0-9]+\.[0-9]+\.[0-9]+", f"git push origin {tag}"),
        (
            r'gh release create v[0-9]+\.[0-9]+\.[0-9]+ --title "DJConnect v[^"]+" --notes-file CHANGELOG\.md',
            f'gh release create {tag} --title "DJConnect {tag}" --notes-file CHANGELOG.md',
        ),
    ],
)
replace_text(
    "examples/firmware_manifest.json",
    [
        (r'  "version": "[^"]+",', f'  "version": "{version}",'),
        (r'  "version_tag": "v[^"]+",', f'  "version_tag": "{tag}",'),
        (r'  "min_ha_integration": "[^"]+",', f'  "min_ha_integration": "{version}",'),
        (
            r"releases/download/v[0-9]+\.[0-9]+\.[0-9]+/",
            f"releases/download/{tag}/",
        ),
        (
            r"releases/download/v[0-9]+\.[0-9]+\.[0-9]+/",
            f"releases/download/{tag}/",
        ),
        (
            r"djconnect-lilygo-t-embed-s3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-lilygo-t-embed-s3-{tag}.bin",
        ),
        (
            r"djconnect-lilygo-t-embed-s3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-lilygo-t-embed-s3-{tag}.bin",
        ),
        (
            r"djconnect-esp32-s3-box-3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-esp32-s3-box-3-{tag}.bin",
        ),
        (
            r"djconnect-esp32-s3-box-3-v[0-9]+\.[0-9]+\.[0-9]+\.bin",
            f"djconnect-esp32-s3-box-3-{tag}.bin",
        ),
    ],
)
replace_text(
    "AGENTS.md",
    [(r"^- Actuele integratieversie: `[^`]+`\.$", f"- Actuele integratieversie: `{version}`.")],
)
PY
}

bump_versions
run git add .
run git commit -m "Release DJConnect ${TAG}"
run git tag "$TAG"
run git push origin main
run git push origin "$TAG"
run gh release create "$TAG" --title "DJConnect ${TAG}" --notes-file CHANGELOG.md

echo "Release ${TAG} complete."
