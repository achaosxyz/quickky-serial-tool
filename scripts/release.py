"""Prepare, publish, and finish a GitHub-only release from one tested commit."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_PATTERN = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-rc\.([1-9]\d*))?")
BOT_CONFIG = ("-c", "user.name=github-actions[bot]",
              "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com")


def git(*arguments, check=True):
    return subprocess.run(
        ["git", *arguments], cwd=ROOT_DIR, text=True, encoding="utf-8",
        capture_output=True, check=check,
    )


def revision(ref):
    return git("rev-parse", f"{ref}^{{commit}}").stdout.strip()


def is_ancestor(ancestor, descendant):
    result = git("merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if result.returncode not in (0, 1):
        result.check_returncode()
    return result.returncode == 0


def fetch_heads():
    git("fetch", "--tags", "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        "+refs/heads/develop:refs/remotes/origin/develop")


def validate_version(current, requested):
    """Require a confirmed release of the version currently under development."""
    target = VERSION_PATTERN.fullmatch(requested)
    source = VERSION_PATTERN.fullmatch(current.removesuffix("-snapshot"))
    if target is None or source is None:
        raise ValueError("Use MAJOR.MINOR.PATCH, -snapshot, or -rc.N versions")
    if source.group(1, 2, 3) != target.group(1, 2, 3):
        raise ValueError("Requested version must match develop VERSION without -snapshot")
    if source[4] and target[4] and int(target[4]) < int(source[4]):
        raise ValueError("Cannot release an earlier release candidate")


def next_snapshot(version):
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError("Invalid release version")
    if match[4]:
        return None
    return f"{match[1]}.{match[2]}.{int(match[3]) + 1}-snapshot"


def write_version(version):
    (ROOT_DIR / "VERSION").write_bytes(f"{version}\n".encode("ascii"))


def load_candidate(directory):
    return json.loads((directory / "release.json").read_text(encoding="utf-8"))


def validate_checkout(version, notes):
    """Resolve the clean development source that a user is being asked to approve."""
    if not notes.strip():
        raise ValueError("User-visible release notes are required")
    if git("status", "--porcelain").stdout:
        raise RuntimeError("Release preparation requires a clean checkout")
    validate_version((ROOT_DIR / "VERSION").read_text(encoding="utf-8").strip(), version)
    fetch_heads()
    source = revision("HEAD")
    main = revision("origin/main")
    if source != revision("origin/develop") or not is_ancestor(main, source):
        raise RuntimeError("Prepare from current develop containing main; do not force a merge")
    orchestration = git("diff", "--quiet", main, source, "--",
                        ".github/workflows", "scripts/release.py", check=False)
    if orchestration.returncode == 1:
        raise RuntimeError("Synchronize release orchestration to main before release preparation")
    orchestration.check_returncode()
    if git("show-ref", "--verify", "--quiet", f"refs/tags/v{version}", check=False).returncode == 0:
        raise RuntimeError("Version tag already exists; resume the failed publish job instead")
    return source, main


def request_release(version, notes, directory):
    """Save the exact version, source, and notes for user confirmation; never commit."""
    source, _ = validate_checkout(version, notes)
    if git("branch", "--show-current").stdout.strip() != "develop":
        raise RuntimeError("Prepare release information on develop")
    directory.mkdir(parents=True, exist_ok=True)
    request = {"version": version, "source": source, "notes": notes.strip()}
    (directory / "release_request.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps(request, ensure_ascii=False, indent=2))


def prepare_release(version, notes, directory, *, confirmed_source):
    """Create the confirmed local candidate; no remote state changes yet."""
    source, main = validate_checkout(version, notes)
    if confirmed_source != source:
        raise RuntimeError("Checkout does not match the confirmed source")
    git("switch", "-c", "release-candidate")
    write_version(version)
    git("add", "VERSION")
    if git("diff", "--cached", "--quiet", check=False).returncode:
        git(*BOT_CONFIG, "commit", "-m", f"chore: release v{version}")
    candidate = {"version": version, "source": source, "main": main, "commit": revision("HEAD")}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "release.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    (directory / "release_notes.md").write_text(notes.strip() + "\n", encoding="utf-8")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"version={version}\ncommit={candidate['commit']}\n")
    print(f"Prepared v{version} at {candidate['commit']}")


def export_release(directory):
    """Transfer the tested candidate and ZIP unchanged to the publishing job."""
    candidate = load_candidate(directory)
    if revision("HEAD") != candidate["commit"] or git(
        "status", "--porcelain",
    ).stdout:
        raise RuntimeError("The tested candidate changed during verification")
    archive_name = f"QSerial_v{candidate['version']}.zip"
    shutil.copyfile(ROOT_DIR / "dist" / archive_name, directory / archive_name)
    git("bundle", "create", str(directory / "candidate.bundle"), "release-candidate")


def gh(*arguments):
    return subprocess.run(
        ["gh", *arguments], cwd=ROOT_DIR, text=True, encoding="utf-8",
        capture_output=True, check=True,
    ).stdout


def github_release(version):
    """Resolve drafts and published releases by tag, then read REST metadata by ID."""
    repository = os.environ["GITHUB_REPOSITORY"]
    owner, name = repository.split("/", 1)
    query = """query($owner: String!, $name: String!, $tag: String!) {
      repository(owner: $owner, name: $name) {
        release(tagName: $tag) { databaseId }
      }
    }"""
    payload = json.loads(gh("api", "graphql", "-f", f"query={query}",
                            "-f", f"owner={owner}", "-f", f"name={name}",
                            "-f", f"tag=v{version}"))
    release = payload["data"]["repository"]["release"]
    if release is None:
        return None
    return json.loads(gh("api", f"repos/{repository}/releases/{release['databaseId']}"))


def verify_release(release, version, archive, notes):
    if release is None or release["draft"]:
        raise RuntimeError("Release was not published")
    if release["prerelease"] != ("-rc." in version):
        raise RuntimeError("Release type does not match the version")
    published_notes = (release["body"] or "").replace("\r\n", "\n").strip()
    if release["name"] != f"QSerial v{version}" or published_notes != notes.strip():
        raise RuntimeError("Published release information does not match the confirmed notes")
    if not any(asset["name"] == archive.name and asset["size"] == archive.stat().st_size
               for asset in release["assets"]):
        raise RuntimeError("Published release does not contain the expected ZIP")


def publish_release(directory):
    """Advance main/tag, upload a draft, then publish only the verified package."""
    candidate = load_candidate(directory)
    version, commit = candidate["version"], candidate["commit"]
    tag = f"v{version}"
    archive = directory / f"QSerial_v{version}.zip"
    if not archive.is_file():
        raise FileNotFoundError(archive)
    notes_path = directory / "release_notes.md"
    notes = notes_path.read_text(encoding="utf-8")
    fetch_heads()
    git("fetch", str(directory / "candidate.bundle"),
        "refs/heads/release-candidate:refs/heads/release-candidate")
    if revision("release-candidate") != commit:
        raise RuntimeError("Bundle does not contain the tested release commit")
    if git("show", f"{commit}:VERSION").stdout.strip() != version:
        raise RuntimeError("Release commit VERSION does not match the package")

    current_main = revision("origin/main")
    if current_main not in (candidate["main"], commit):
        raise RuntimeError("main advanced during release; do not overwrite it")
    tag_exists = git("show-ref", "--verify", "--quiet", f"refs/tags/{tag}", check=False).returncode == 0
    if tag_exists and revision(tag) != commit:
        raise RuntimeError("Existing tag points to a different commit")
    if current_main != commit:
        if revision("origin/develop") != candidate["source"]:
            raise RuntimeError("develop advanced during verification; start a new release run")
        if not tag_exists:
            git(*BOT_CONFIG, "tag", "-a", tag, commit, "-m", f"Release {tag}")
        git("push", "--atomic", "origin", f"{commit}:refs/heads/main", f"refs/tags/{tag}")
    elif not tag_exists:
        raise RuntimeError("main is at the release commit but its tag is missing")

    release = github_release(version)
    if release is None:
        flags = ["--prerelease"] if "-rc." in version else []
        gh("release", "create", tag, "--verify-tag", "--draft", "--title", f"QSerial {tag}",
           "--notes-file", str(notes_path), *flags)
        release = github_release(version)
    if release["draft"]:
        gh("release", "upload", tag, str(archive), "--clobber")
        gh("release", "edit", tag, "--draft=false", "--title", f"QSerial {tag}",
           "--notes-file", str(notes_path),
           "--prerelease=true" if "-rc." in version else "--prerelease=false",
           "--latest=false" if "-rc." in version else "--latest=true")
    verify_release(github_release(version), version, archive, notes)
    print(f"Published {tag}; ZIP and tag refer to {commit}")


def finish_release(directory):
    """Advance develop only after publication; never reset concurrent development."""
    candidate = load_candidate(directory)
    version, commit = candidate["version"], candidate["commit"]
    notes = (directory / "release_notes.md").read_text(encoding="utf-8")
    verify_release(github_release(version), version, directory / f"QSerial_v{version}.zip", notes)
    fetch_heads()
    current = revision("origin/develop")
    next_version = next_snapshot(version)
    current_version = git("show", f"{current}:VERSION").stdout.strip()
    if is_ancestor(commit, current) and current_version == (next_version or version):
        print("develop already includes this release and its expected version")
        return
    if current not in (candidate["source"], commit):
        raise RuntimeError("Release is published, but develop advanced; finish via the recovery SOP")
    git("switch", "--detach", commit)
    if next_version is not None:
        write_version(next_version)
        git("add", "VERSION")
        git(*BOT_CONFIG, "commit", "-m", f"chore: start {next_version.removesuffix('-snapshot')} development")
    git("push", "origin", "HEAD:refs/heads/develop")
    print(f"develop now contains the release with VERSION={next_version or version}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("request", "prepare", "export", "publish", "finish"))
    parser.add_argument("--directory", type=Path, required=True)
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    if arguments.command == "request":
        request_release(os.environ["RELEASE_VERSION"], os.environ["RELEASE_NOTES"], directory)
    elif arguments.command == "prepare":
        prepare_release(os.environ["RELEASE_VERSION"], os.environ["RELEASE_NOTES"], directory,
                        confirmed_source=os.environ["RELEASE_SOURCE"])
    else:
        {"export": export_release, "publish": publish_release, "finish": finish_release}[arguments.command](directory)


if __name__ == "__main__":
    main()
