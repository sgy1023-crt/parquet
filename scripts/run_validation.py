"""Capture a real validation command with a hard 60-second timeout.

This is audit infrastructure, not a Parquet implementation. Production checkouts
are never rewritten by this runner. Machine-specific paths are redacted in logs.
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--toolchain")
    argv = sys.argv[1:]
    if "--" not in argv:
        parser.error("separate the command with --")
    separator = argv.index("--")
    args = parser.parse_args(argv[:separator])
    command = argv[separator + 1:]
    if not command:
        parser.error("a command is required after --")
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "validation" / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if args.toolchain:
        toolchain = Path(args.toolchain).resolve()
        env["MOON_HOME"] = str(toolchain)
        env["PATH"] = str(toolchain / "bin") + os.pathsep + env["PATH"]
        if command[0] == "moon":
            command[0] = str(toolchain / "bin" / ("moon.exe" if os.name == "nt" else "moon"))
    replacements = [(str(root), "<REPO>"), (str(Path.home()), "<HOME>")]

    def redact(text):
        for path, label in replacements:
            text = text.replace(path, label).replace(path.replace("\\", "/"), label)
        return re.sub(r"(?m)[ \t]+$", "", text)

    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command, cwd=args.cwd, env=env, capture_output=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        stdout = stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
        code = None
    stdout, stderr = redact(stdout), redact(stderr)
    (output_dir / f"{args.label}.stdout.log").write_text(stdout, encoding="utf-8")
    (output_dir / f"{args.label}.stderr.log").write_text(stderr, encoding="utf-8")
    summary = {
        "label": args.label,
        "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": [redact(part) for part in command],
        "cwd": redact(str(Path(args.cwd).resolve())),
        "exit_code": code,
        "timed_out": timed_out,
        "timeout_seconds": 60,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "test_summaries": [
            {"total": int(t), "passed": int(p), "failed": int(f)}
            for t, p, f in re.findall(
                r"Total tests:\s*(\d+),\s*passed:\s*(\d+),\s*failed:\s*(\d+)",
                stdout + stderr,
            )
        ],
    }
    is_test = len(command) > 1 and command[1] == "test" and "--build-only" not in command
    if code == 0 and is_test and not any(item["total"] > 0 for item in summary["test_summaries"]):
        summary["validation_error"] = "Test command executed no tests"
        summary["exit_code"] = code = 1
    (output_dir / f"{args.label}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    print((stdout + stderr)[-2500:])
    return code if code is not None else 124


if __name__ == "__main__":
    raise SystemExit(main())
