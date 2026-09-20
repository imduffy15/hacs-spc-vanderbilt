"""Run pinned Home Assistant validators locally or in any CI system (requires Docker)."""

import os
import subprocess
import sys
from pathlib import Path

IMAGES = {
    "hassfest": "ghcr.io/home-assistant/hassfest@sha256:"
    "66b55a8ce14cdcf0c200dd4dab1f3228ac8d3f6e0404ec710a0d8a79b296eba4",
    "hacs": "ghcr.io/hacs/action@sha256:"
    "dc92fdad2f6ffbe74bffb7269d781ea8e064f52d9bb486cdf3925d74e7ab6ebf",
}
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    validator = sys.argv[1]
    image = IMAGES[validator]
    # Content-addressed archives avoid repeatedly pulling the large validator images.
    cache = ROOT / ".cache/docker" / f"{image.rsplit(':', 1)[1]}.tar"
    if subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True, check=False
    ).returncode:
        if cache.exists():
            subprocess.run(["docker", "load", "-i", str(cache)], check=True)
        # Archives preserve layers; pulling restores and verifies the digest reference.
        subprocess.run(["docker", "pull", "--platform=linux/amd64", image], check=True)
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["docker", "save", "-o", str(cache), image], check=True)
    args = ["docker", "run", "--rm", "--platform=linux/amd64", "-v", f"{ROOT}:/github/workspace:ro"]
    env = os.environ.copy()
    if validator == "hacs":
        # Forward a token through the environment, never through command-line arguments.
        env["INPUT_GITHUB_TOKEN"] = (
            env.get("GH_TOKEN")
            or subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        )
        env["REPOSITORY"] = env.get(
            "HACS_REPOSITORY", env.get("GITHUB_REPOSITORY", "imduffy15/hacs-spc-vanderbilt")
        )
        env["REPOSITORY_REF"] = (
            env.get("HACS_REF")
            or env.get("GITHUB_SHA")
            or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        )
        args += [
            "-e",
            "INPUT_GITHUB_TOKEN",
            "-e",
            "REPOSITORY",
            "-e",
            "REPOSITORY_REF",
            "-e",
            "CATEGORY=integration",
            "-e",
            "INPUT_COMMENT=false",
        ]
    subprocess.run([*args, image], env=env, check=True)


if __name__ == "__main__":
    main()
