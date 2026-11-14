"""Copy current source candidates into an ignored review directory, without Git history.

Never commits, fetches, pushes, deletes files, or overwrites the original worktree.
This is a review artifact, not an authorization to publish.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from audit_release import ROOT, GIT, findings
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != ROOT or not output.name.startswith(".tmp-release-preview-"):
        parser.error("Output must be a new .tmp-release-preview-* directory directly inside UFHOB.")
    if output.exists():
        parser.error("Output already exists; choose a new review directory.")
    paths = subprocess.check_output(GIT + [
        "ls-files", "--cached", "--others", "--exclude-standard", "-z",
    ], cwd=ROOT).decode().strip("\0").split("\0")
    ignored = set(subprocess.check_output(GIT + [
        "ls-files", "--cached", "--ignored", "--exclude-standard", "-z",
    ], cwd=ROOT).decode().strip("\0").split("\0"))
    folders = {
        p.name for p in ROOT.iterdir() if p.is_dir()
        and ((p / "apps.py").is_file() or (p / "models.py").is_file())
    } | {"config", "finance", "templates", "static", "ui", "docs", "bootstrap", "brand_assets", "tests", "scripts", "deploy"}
    root_files = {
        ".gitignore", ".gitattributes", ".env.example", "AGENTS.md", "CLAUDE.md", "manage.py",
        "requirements.txt", "requirements-ubuntu.lock", "requirements-ubuntu.constraints.txt", "package.json", "package-lock.json",
        "postcss.config.js", "tailwind.config.js", "tailwind.app.config.js", "test_urls.py",
    }
    known = {
        key: value.encode() for key, value in dotenv_values(ROOT / ".env").items()
        if value and len(value) >= 10 and any(word in key for word in ("SECRET", "PASSWORD", "TOKEN", "ACCESS_KEY"))
    }
    selected, omitted, reviews = [], [], []
    for name in sorted(set(paths) - ignored):
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            continue
        relative = Path(name)
        if name not in root_files and relative.parts[0] not in folders:
            omitted.append(name)
            continue
        data = path.read_bytes()
        if len(data) > 10 * 1024 * 1024:
            raise SystemExit("Large source file requires explicit review; see source inventory.")
        if b"\0" not in data:
            detected = findings(data, known)
            if any(rule != "credential_literal_review" for rule in detected):
                raise SystemExit("Potential live secret detected in source; consult private audit before export.")
            if detected:
                reviews.append({"path": name, "rules": detected})
        selected.append((name, hashlib.sha256(data).hexdigest()))
    if any(Path(name).suffix == ".py" for name in omitted):
        raise SystemExit("Unclassified Python source: review its runtime role before export.")
    output.mkdir()
    for name, _digest in selected:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    manifest = {"files": [{"path": n, "sha256": d} for n, d in selected],
                "omitted_nonruntime_root_files": omitted, "literal_candidates_for_review": reviews,
                "history_copied": False, "publication_authorized": False}
    (ROOT / ".tmp-deployment-audit" / (output.name + ".json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps({"review_directory": output.name, "source_files": len(selected),
                      "omitted_root_files": len(omitted), "literal_candidates_for_review": len(reviews),
                      "history_copied": False, "commits_created": 0}))


if __name__ == "__main__":
    main()
