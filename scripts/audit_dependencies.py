"""Read-only vulnerability inventory. Sends only public package names/versions to OSV."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npm", action="store_true")
    args = parser.parse_args()
    queries = [{"package": {"name": d.metadata["Name"], "ecosystem": "PyPI"}, "version": d.version}
               for d in importlib.metadata.distributions()]
    request = Request("https://api.osv.dev/v1/querybatch", data=json.dumps({"queries": queries}).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        response_data = json.load(response)
    findings = [{"package": q["package"]["name"], "version": q["version"],
                 "advisories": [v["id"] for v in result.get("vulns", [])]}
                for q, result in zip(queries, response_data["results"]) if result.get("vulns")]
    report = {"packages_queried": len(queries), "findings": findings,
              "scope": "Installed environment, including tools; aliases can describe the same vulnerability. No exploitability claim."}
    if args.npm:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm:
            raise SystemExit("npm not found")
        env = os.environ.copy()
        env["npm_config_cache"] = str(ROOT / ".tmp-npm-audit-cache")
        result = subprocess.run([npm, "audit", "--json"], cwd=ROOT, env=env,
                                text=True, capture_output=True, timeout=90)
        report["npm"] = json.loads(result.stdout)
    target = ROOT / ".tmp-dependencies-audit.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": target.name, "python_distributions_with_advisories": len(findings)}))
    if findings or report.get("npm", {}).get("metadata", {}).get("vulnerabilities", {}).get("total", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
