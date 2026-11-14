"""Read-only Git/release inventory. Reports locations, never credential values.

Run with the UFHOB virtualenv. --history scans reachable Git blobs as well.
The JSON report can contain private filenames: keep it outside version control.
This heuristic audit does not replace review or a dedicated secret scanner.
"""

import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
GIT = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
SIGNATURES = {
    "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "github_token": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "aws_access_key": rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
    "brevo_key": rb"xkeysib-[A-Za-z0-9_-]{35,}",
}
ASSIGNMENT = re.compile(
    rb"(?im)(?:SECRET_KEY|CARD_SIGNING_KEY|DB_PASSWORD|EMAIL_HOST_PASSWORD|"
    rb"BBB_SECRET|AWS_SECRET_ACCESS_KEY|S3_SECRET_KEY|B2_SECRET_ACCESS_KEY)"
    rb"[\"']?\s*[:=]\s*[\"']([^\"'\r\n]{8,})[\"']"
)


def git(*args):
    return subprocess.check_output(GIT + list(args), cwd=ROOT, stderr=subprocess.DEVNULL)


def safe_remote(value):
    if "://" not in value:
        return value
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def findings(data, known):
    result = {name for name, pattern in SIGNATURES.items() if re.search(pattern, data)}
    result.update("local_secret:" + key for key, value in known.items() if value in data)
    for match in ASSIGNMENT.finditer(data):
        value = match.group(1).lower()
        if not any(token in value for token in (
            b"test", b"dummy", b"example", b"replace", b"generate", b"change",
            b"placeholder", b"your-", b"your_", b"os.getenv", b"environ", b"local-",
        )) and len(set(value)) >= 5:
            result.add("credential_literal_review")
    return sorted(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp-release-audit.json")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if not args.output.is_relative_to(ROOT):
        parser.error("Keep private audit reports inside the UFHOB workspace.")
    from dotenv import dotenv_values

    known = {
        key: value.encode() for key, value in dotenv_values(ROOT / ".env").items()
        if value and len(value) >= 10 and any(word in key for word in (
            "SECRET", "PASSWORD", "TOKEN", "ACCESS_KEY",
        )) and not any(word in value.lower() for word in ("replace-me", "example", "generate-"))
    }
    tracked = git("ls-files", "-z").decode().strip("\0").split("\0")
    candidates = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    candidates = sorted(set(candidates.decode().strip("\0").split("\0")))
    status = git("status", "--porcelain=v1", "-z").decode().strip("\0").split("\0")
    sizes, secrets, missing = [], [], []
    for name in candidates:
        path = ROOT / name
        if not path.is_file():
            missing.append(name)
            continue
        size = path.stat().st_size
        if size >= 5 * 1024 * 1024:
            sizes.append({"path": name, "bytes": size})
        # Binary media are classified by path/size; credential signatures are
        # inspected in text candidates only. Report this scope transparently.
        if size <= 10 * 1024 * 1024:
            data = path.read_bytes()
            if b"\0" not in data:
                detected = findings(data, known)
                if detected:
                    secrets.append({"path": name, "kinds": detected})
    remotes = {
        name: safe_remote(git("remote", "get-url", name).decode().strip())
        for name in git("remote").decode().splitlines()
    }
    report = {
        "branch": git("branch", "--show-current").decode().strip(),
        "head": git("rev-parse", "HEAD").decode().strip(),
        "remotes": remotes,
        "status_counts": dict(Counter(line[:2] for line in status if line)),
        "tracked_count": len(tracked),
        "tracked_top_folders": dict(Counter(p.split("/")[0] for p in tracked)),
        "tracked_but_ignored": git(
            "ls-files", "--cached", "--ignored", "--exclude-standard", "-z"
        ).decode().strip("\0").split("\0"),
        "large_worktree_files": sorted(sizes, key=lambda item: -item["bytes"]),
        "secret_locations_worktree": secrets,
        "missing_tracked_paths": missing,
        "management_commands": sorted(str(p.relative_to(ROOT)).replace("\\", "/")
            for p in ROOT.glob("*/management/commands/*.py") if p.name != "__init__.py"),
        "test_modules": sorted(str(p.relative_to(ROOT)).replace("\\", "/")
            for folder in ROOT.iterdir() if folder.is_dir() and not folder.name.startswith((".", "_"))
            and folder.name not in {"node_modules", "media", "private_media", "SITE", "backups"}
            for p in folder.rglob("test*.py") if "__pycache__" not in p.parts),
        "installed_distributions": sorted(
            f'{dist.metadata["Name"]}=={dist.version}' for dist in importlib.metadata.distributions()
        ),
        "scope": "Text worktree files <=10 MiB; optional reachable history blobs <=10 MiB. Heuristic, not proof of absence.",
    }
    if args.history:
        history_hits, large_blobs, scanned = [], [], 0
        objects = git("rev-list", "--objects", "--all").decode().splitlines()
        with subprocess.Popen(GIT + ["cat-file", "--batch"], cwd=ROOT,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
            for entry in objects:
                oid, _, name = entry.partition(" ")
                process.stdin.write((oid + "\n").encode())
                process.stdin.flush()
                header = process.stdout.readline().decode().split()
                if len(header) != 3:
                    continue
                kind, size = header[1], int(header[2])
                data = process.stdout.read(size)
                process.stdout.read(1)
                if kind != "blob":
                    continue
                scanned += 1
                if size >= 10 * 1024 * 1024:
                    large_blobs.append({"object": oid, "path": name, "bytes": size})
                if size <= 10 * 1024 * 1024 and b"\0" not in data:
                    detected = findings(data, known)
                    if detected:
                        history_hits.append({"object": oid, "path": name, "kinds": detected})
            process.stdin.close()
        report["history"] = {"blobs_scanned": scanned, "secret_locations": history_hits,
                             "large_blobs": sorted(large_blobs, key=lambda item: -item["bytes"])}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(args.output.relative_to(ROOT)),
                      "tracked": len(tracked), "status": report["status_counts"],
                      "secret_candidate_files": len(secrets), "large_files": len(sizes),
                      "history_secret_blobs": len(report.get("history", {}).get("secret_locations", [])) if args.history else None}, indent=2))


if __name__ == "__main__":
    main()
