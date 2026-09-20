"""Validate integration metadata, build a HACS ZIP, and publish a tagged release."""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/spc_edp"
ARCHIVE = ROOT / "dist/spc_edp.zip"


def metadata() -> str:
    """Keep the development environment and HACS installation in agreement."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    if project["version"] != manifest["version"]:
        raise ValueError("pyproject and manifest versions differ")
    if project["dependencies"] != manifest["requirements"]:
        raise ValueError("Development and Home Assistant library pins differ")
    if (COMPONENT / "strings.json").read_bytes() != (
        COMPONENT / "translations/en.json"
    ).read_bytes():
        raise ValueError("English translations differ from strings.json")
    return str(manifest["version"])


def build() -> None:
    """Include only tracked integration files, rooted where HACS expects them."""
    metadata()
    paths = (
        subprocess.check_output(["git", "ls-files", "-z", "custom_components/spc_edp"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    ARCHIVE.parent.mkdir(exist_ok=True)
    with ZipFile(ARCHIVE, "w", ZIP_DEFLATED) as archive:
        for name in sorted(filter(None, paths)):
            path = ROOT / name
            archive.write(path, path.relative_to(COMPONENT))
    print(ARCHIVE)


def check() -> str:
    """Refuse mismatched tags or malformed HACS artifacts before publication."""
    version = metadata()
    tag = os.environ.get("RELEASE_TAG", f"v{version}")
    if tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match version {version}")
    with ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt HACS ZIP")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest != json.loads((COMPONENT / "manifest.json").read_text()):
            raise ValueError("ZIP manifest differs from the checked-out source")
        if any(
            n.startswith("custom_components/") or "__pycache__" in n for n in archive.namelist()
        ):
            raise ValueError("Incorrect ZIP layout")
    return tag


def main() -> None:
    action = sys.argv[1]
    if action == "metadata":
        metadata()
    elif action == "build":
        build()
        check()
    elif action == "check":
        print(check())
    elif action == "publish":
        tag = check()
        if "RELEASE_TAG" not in os.environ:
            raise ValueError("Set RELEASE_TAG explicitly to publish")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        tagged = subprocess.check_output(["git", "rev-parse", f"{tag}^{{commit}}"], cwd=ROOT)
        if head != tagged:
            raise ValueError("Release tag does not point to this checkout")
        subprocess.run(
            ["gh", "release", "create", tag, str(ARCHIVE), "--verify-tag", "--generate-notes"],
            cwd=ROOT,
            check=True,
        )
    else:
        raise ValueError(f"Unknown release action: {action}")


if __name__ == "__main__":
    main()
