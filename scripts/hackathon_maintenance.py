"""Read-only remote checks and dated CI routing; write local receipts only."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = dt.timezone(dt.timedelta(hours=8))
START = dt.date(2026, 10, 20)
STOP = dt.date(2026, 11, 1)
BRANCH = "feat/row-group-statistics"
UPSTREAM_BASE = "44d4dc9c492008fce77e1a980f1048decbd7f1c9"
RULES_BLOB = "e27e1d752b573ad88dccf6da681a1492c7dcfe0c"
RULES_URL = "https://moonbitlang.github.io/Hackathon2026/"
KNOWN_PR_HEADS = {3: "3e72356fd14a9a15155347e51ba81abf80572b82"}
OWN_API = "https://api.github.com/repos/sgy1023-crt/parquet"


def execution_plan(event, mode, now):
    day = now.astimezone(SHANGHAI).date()
    plan = dict(health=False, light_tests=False, full_matrix=False,
                acceptance=False, date=str(day), phase=event)
    if event in ("push", "pull_request"):
        plan["full_matrix"] = True
    elif event == "workflow_dispatch":
        if mode not in ("full", "health"):
            raise ValueError("Manual mode must be full or health")
        plan.update(acceptance=mode == "full", health=mode == "health",
                    light_tests=mode == "health", phase="manual-" + mode)
    elif event == "schedule":
        if not START <= day < STOP:
            plan["phase"] = "outside-monitoring-window"
            return plan
        plan["health"] = True
        plan["full_matrix"] = day.day == 25
        plan["acceptance"] = day.day == 28
        plan["light_tests"] = not (plan["full_matrix"] or plan["acceptance"])
        plan["phase"] = {25: "midpoint-review", 28: "final-review"}.get(day.day, "daily-health")
    else:
        raise ValueError("Unsupported workflow event: " + event)
    return plan


def fetch(url, authenticated=False):
    headers = {"User-Agent": "parquet-hackathon-health"}
    if authenticated:
        if url != OWN_API and not url.startswith(OWN_API + "/"):
            raise ValueError("The Actions token is restricted to this repository's API")
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
        return response.read()


def api(path, authenticated=False):
    return json.loads(fetch("https://api.github.com/repos/" + path, authenticated))


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=60, text=True).strip()


def write_report(name, report):
    destination = ROOT / "validation" / (name + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    content = "# " + name + "\n\n```json\n" + json.dumps(report, indent=2, ensure_ascii=False) + "\n```\n"
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write(content)
    print(json.dumps(report, ensure_ascii=False))


def health():
    report = {"status": "failed", "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "scope": "metadata checks; build/test results are separate receipts and the job conclusion",
              "commit": git("rev-parse", "HEAD")}
    try:
        repo = api("sgy1023-crt/parquet", True)
        if repo["private"] or repo["default_branch"] != BRANCH:
            raise RuntimeError("Repository visibility or default branch changed")
        if not repo["fork"] or repo["parent"]["full_name"] != "mizchi/parquet":
            raise RuntimeError("Upstream fork relationship changed")
        subprocess.run(["git", "merge-base", "--is-ancestor", UPSTREAM_BASE, "HEAD"],
                       cwd=ROOT, check=True, timeout=60)
        page = fetch(repo["html_url"])
        if b"2026 MoonBit Hackathon" not in page:
            raise RuntimeError("The public repository homepage does not show the contribution")
        for relative in ("LICENSE", "README.md", "docs/HACKATHON_SUBMISSION.md",
                         "docs/HACKATHON_FINAL_CHECKLIST.md"):
            if not (ROOT / relative).is_file():
                raise RuntimeError("Missing acceptance material: " + relative)
        if "Apache License" not in (ROOT / "LICENSE").read_text(encoding="utf-8"):
            raise RuntimeError("The recorded Apache license is missing")
        report["repository"] = {"url": repo["html_url"], "public": True,
                                "default_branch": repo["default_branch"], "upstream_history_preserved": True}
        runs = api("sgy1023-crt/parquet/actions/workflows/ci.yml/runs?per_page=30&branch=" +
                   urllib.parse.quote(BRANCH, safe=""), True)["workflow_runs"]
        completed = [run for run in runs if run["event"] == "push" and run["status"] == "completed"]
        if completed:
            run = completed[0]
            report["latest_completed_push_ci"] = {key: run[key] for key in ("head_sha", "conclusion", "html_url")}
            if run["conclusion"] in ("failure", "timed_out", "action_required"):
                raise RuntimeError("The latest completed push CI needs attention: " + run["html_url"])
        else:
            report["latest_completed_push_ci"] = {"status": "not_yet_completed"}
        upstream = api("mizchi/parquet/commits/main")
        tags = api("mizchi/parquet/tags?per_page=5")
        prs = api("mizchi/parquet/pulls?state=open&per_page=30")
        advisories = api("mizchi/parquet/security-advisories")
        review_needed = (upstream["sha"] != UPSTREAM_BASE or
                         bool(tags and tags[0]["name"] != "v0.2.2") or bool(advisories) or
                         any(KNOWN_PR_HEADS.get(pr["number"]) != pr["head"]["sha"] for pr in prs))
        report["upstream"] = {"head": upstream["sha"], "baseline": UPSTREAM_BASE,
                              "review_needed": review_needed,
                              "tags": [{"name": tag["name"], "sha": tag["commit"]["sha"]} for tag in tags],
                              "open_prs": [{"number": pr["number"], "title": pr["title"], "url": pr["html_url"],
                                            "head_sha": pr["head"]["sha"]} for pr in prs],
                              "public_advisories": [item["html_url"] for item in advisories],
                              "policy": "record changes for review; never merge or infer compatibility automatically"}
        rules = api("moonbitlang/Hackathon2026/contents/src/App.tsx")
        official_page = fetch(RULES_URL)
        report["official_rules"] = {"source": rules["html_url"], "blob_sha": rules["sha"],
                                    "review_needed": rules["sha"] != RULES_BLOB, "page": RULES_URL,
                                    "page_sha256": hashlib.sha256(official_page).hexdigest(),
                                    "private_announcements_checked": False}
        report["pinned_toolchain"] = (ROOT / ".moonbit-version").read_text().strip()
        report["status"] = "passed"
    finally:
        write_report("hackathon-health", report)


def acceptance_report():
    receipt_path = ROOT / "validation" / "delivery-summary.json"
    report = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {"status": "not_run"}
    report["commit"] = git("rev-parse", "HEAD")
    report["workflow_run"] = (os.environ["GITHUB_SERVER_URL"] + "/" + os.environ["GITHUB_REPOSITORY"] +
                              "/actions/runs/" + os.environ["GITHUB_RUN_ID"])
    report["executed_commands"] = []
    for check in report.get("checks", []):
        receipt = json.loads((ROOT / check["receipt"]).read_text(encoding="utf-8"))
        report["executed_commands"].append({key: receipt[key] for key in
                                            ("command", "exit_code", "test_summaries", "timed_out")})
    report["engineering_checks_passed"] = report["status"] == "passed"
    report["limits"] = ["Whole Bytes input; speed, memory and I/O gains are not measured",
                        "Initial registration approval does not replace final contest acceptance",
                        "Final form and private announcement checks remain manual"]
    write_report("hackathon-acceptance", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "health", "report"))
    args = parser.parse_args()
    if args.command == "plan":
        plan = execution_plan(os.environ["GITHUB_EVENT_NAME"], os.environ.get("INPUT_MODE", "full"),
                              dt.datetime.now(dt.timezone.utc))
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            for key, value in plan.items():
                output.write(key + "=" + (str(value).lower() if isinstance(value, bool) else value) + "\n")
        print(json.dumps(plan))
    elif args.command == "health":
        health()
    else:
        acceptance_report()


if __name__ == "__main__":
    main()
