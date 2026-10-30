"""Download and verify pinned dependencies without rewriting their source.

Every command has a 60-second timeout; diagnostics and SHA-256 receipts are
saved even when preparation fails.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


DEPENDENCIES = {
    "moonbitlang/x": "0.5.5",
}
TIMEOUT_SECONDS = 60


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(directory):
    return {
        path.relative_to(directory).as_posix(): sha256(path)
        for path in sorted(directory.rglob("*.mbt"))
    }


def manifest_identity(path):
    text = path.read_text(encoding="utf-8")
    fields = {}
    for field in ("name", "version"):
        match = re.search(rf'(?m)^\s*{field}\s*=\s*"([^"\n]+)"', text)
        if match is None:
            raise ValueError(f"Missing {field} in {path}")
        fields[field] = match.group(1)
    return fields["name"], fields["version"]


class Commands:
    def __init__(self, root, toolchain, log_dir, report):
        self.root = root
        self.log_dir = log_dir
        self.report = report
        self.env = os.environ.copy()
        self.env["MOON_HOME"] = str(toolchain)
        self.env["PATH"] = str(toolchain / "bin") + os.pathsep + self.env["PATH"]

    def run(self, label, command):
        prefix = f"{len(self.report['commands']) + 1:03d}-{label}"
        started = time.monotonic()
        timed_out = False
        try:
            result = subprocess.run(
                list(map(str, command)), cwd=self.root, env=self.env,
                capture_output=True, timeout=TIMEOUT_SECONDS,
            )
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code = error.stdout or b"", error.stderr or b"", None
            timed_out = True
        (self.log_dir / f"{prefix}.stdout.log").write_bytes(stdout)
        (self.log_dir / f"{prefix}.stderr.log").write_bytes(stderr)
        self.report["commands"].append({
            "label": prefix,
            "command": list(map(str, command)),
            "exit_code": code,
            "timed_out": timed_out,
            "timeout_seconds": TIMEOUT_SECONDS,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        })
        if code != 0:
            for output in (stdout, stderr):
                if output:
                    print(output.decode("utf-8", "replace"), file=sys.stderr, flush=True)
        if timed_out:
            raise TimeoutError(f"{prefix} exceeded {TIMEOUT_SECONDS} seconds")
        return code, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


def require_success(label, result):
    code, stdout, stderr = result
    if code != 0:
        raise RuntimeError(f"{label} failed with exit code {code}; see command logs")
    return stdout + stderr


def validate_root(root):
    manifest = root / "moon.mod"
    imports = dict(re.findall(r'"([^"\n]+)@([^"\n]+)"', manifest.read_text(encoding="utf-8")))
    if imports != DEPENDENCIES:
        raise ValueError(f"Expected the pinned root dependencies {DEPENDENCIES}; got {imports}")
    return sha256(manifest)


def prepare(root, toolchain, log_dir):
    suffix = ".exe" if os.name == "nt" else ""
    moon = toolchain / "bin" / f"moon{suffix}"
    log_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "failed",
        "root": str(root),
        "toolchain": str(toolchain),
        "expected_dependencies": DEPENDENCIES,
        "commands": [],
        "source_hashes": {},
    }
    commands = Commands(root, toolchain, log_dir, report)
    try:
        root_hash = validate_root(root)
        report["root_moon_mod_sha256"] = root_hash
        version = require_success("toolchain version", commands.run("version", [moon, "version", "--all"]))
        report["toolchain_version"] = version
        require_success("registry update", commands.run("registry-update", [moon, "update"]))
        for module in DEPENDENCIES:
            directory = root / ".mooncakes" / module
            if directory.exists():
                report["source_hashes"][module] = source_hashes(directory)
        require_success("dependency check", commands.run("check", [moon, "check", "--target", "js"]))
        for module, expected_version in DEPENDENCIES.items():
            directory = root / ".mooncakes" / module
            actual = manifest_identity(directory / "moon.mod")
            if actual != (module, expected_version):
                raise ValueError(f"Expected {module}@{expected_version}, found {actual}")
            current_hashes = source_hashes(directory)
            if module in report["source_hashes"] and current_hashes != report["source_hashes"][module]:
                raise RuntimeError(f"Dependency .mbt source changed during preparation: {module}")
            report["source_hashes"][module] = current_hashes
        report["root_moon_mod_sha256_after"] = sha256(root / "moon.mod")
        if report["root_moon_mod_sha256_after"] != root_hash:
            raise RuntimeError("Root moon.mod changed during dependency preparation")
        report["dependency_sources_unchanged"] = True
        report["status"] = "success"
        print(f"Prepared {len(DEPENDENCIES)} pinned dependency; receipts: {log_dir / 'summary.json'}", flush=True)
    finally:
        (log_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--toolchain", type=Path, required=True, help="MOON_HOME containing the verified bin/ and lib/")
    parser.add_argument("--log-dir", type=Path, help="Receipt parent; default: ROOT/validation/dependency-bootstrap")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    log_parent = arguments.log_dir.resolve() if arguments.log_dir else root / "validation" / "dependency-bootstrap"
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    prepare(root, arguments.toolchain.resolve(), log_parent / run_id)


if __name__ == "__main__":
    main()
