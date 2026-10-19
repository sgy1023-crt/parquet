"""Run the complete local delivery checks; every child check has a 60s limit."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("js", "wasm", "wasm-gc", "native")


def interface_hashes():
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "src").rglob("*.generated.mbti"))}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--duckdb", type=Path, help="Optional directory containing duckdb.h and native library")
    args = parser.parse_args()
    toolchain = args.toolchain.resolve()
    env = os.environ.copy()
    env["MOON_HOME"] = str(toolchain)
    env["PATH"] = str(toolchain / "bin") + os.pathsep + env["PATH"]
    if args.duckdb:
        duckdb = str(args.duckdb.resolve())
        for name in ("INCLUDE", "LIB", "CPATH", "LIBRARY_PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "PATH"):
            env[name] = duckdb + os.pathsep + env.get(name, "")
    receipt = {"started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "status": "failed", "unit_tests": {}, "checks": []}
    destination = ROOT / "validation" / "delivery-summary.json"

    def run(label, command):
        subprocess.run([sys.executable, "scripts/run_validation.py", label, "--cwd", ".",
                        "--toolchain", str(toolchain), "--", *command],
                       cwd=ROOT, env=env, check=True, timeout=65)
        result = json.loads((ROOT / "validation" / "runs" / (label + ".json")).read_text(encoding="utf-8"))
        receipt["checks"].append({"label": label, "exit_code": result["exit_code"],
                                  "receipt": "validation/runs/" + label + ".json"})
        return result

    try:
        run("delivery-version", ["moon", "version", "--all"])
        run("delivery-targeted-js", ["moon", "test", "--target", "js", "src/row_group_test.mbt",
                                     "src/statistics_test.mbt", "src/statistics_wbtest.mbt", "--no-render"])
        for target in TARGETS:
            result = run("delivery-test-" + target, ["moon", "test", "--target", target, "--no-render"])
            receipt["unit_tests"][target] = result["test_summaries"]
        run("delivery-format", ["moon", "fmt", "--check"])
        before = interface_hashes()
        run("delivery-info", ["moon", "info"])
        if interface_hashes() != before:
            raise RuntimeError("Generated public interfaces were stale; inspect the changed files")
        run("delivery-check-all", ["moon", "check", "--target", "all", "--deny-warn", "--no-render"])
        run("delivery-build-all", ["moon", "build", "--target", "all", "--deny-warn", "--no-render"])
        run("delivery-consumer-js", ["moon", "run", "src/cmd/row_group_scan", "--target", "js", "--",
                                     "fixtures/row-groups/base.parquet", "i32", "102"])
        run("delivery-consumer-int64", ["moon", "run", "src/cmd/row_group_scan", "--target", "js", "--",
                                        "fixtures/row-groups/base.parquet", "i64", "9007199254740995"])
        run("delivery-fixtures", [sys.executable, "scripts/generate_row_group_fixtures.py", "--check"])
        receipt["decode_work"] = {}
        for target in TARGETS:
            run("delivery-trace-" + target, [sys.executable, "scripts/verify_decode_work.py",
                                            "--toolchain", str(toolchain), "--target", target])
            result = json.loads((ROOT / "validation" / ("decode-work-" + target) / "summary.json").read_text(encoding="utf-8"))
            if not result["verified"]:
                raise RuntimeError("Decoder work verification failed: " + target)
            receipt["decode_work"][target] = result["measured_counts"]
        receipt["interfaces_unchanged"] = True
        receipt["status"] = "passed"
    finally:
        receipt["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Delivery checks passed; receipt: validation/delivery-summary.json")


if __name__ == "__main__":
    main()
