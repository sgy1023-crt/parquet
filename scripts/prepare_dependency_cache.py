"""Prepare pinned dependencies for the verified October 2026 MoonBit toolchain.

Only legacy manifests in this checkout's .mooncakes cache are converted. Every
command has a 60-second timeout; original diagnostics and SHA-256 receipts are
saved even when preparation fails. Dependency source files are never rewritten.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


DIRECT_DEPENDENCIES = {
    "moonbitlang/x": "0.5.5",
    "mizchi/duckdb": "0.6.4",
}
DEPENDENCIES = {**DIRECT_DEPENDENCIES, "moonbitlang/quickcheck": "0.14.0"}
TIMEOUT_SECONDS = 60


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(directory):
    return {
        path.relative_to(directory).as_posix(): sha256(path)
        for path in sorted(directory.rglob("*.mbt"))
    }


def manifest_identity(path):
    if path.suffix == ".json":
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return manifest["name"], manifest["version"]
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
    if imports != DIRECT_DEPENDENCIES:
        raise ValueError(f"Expected the pinned root dependencies {DIRECT_DEPENDENCIES}; got {imports}")
    return sha256(manifest)


def convert_cached_manifests(root, moonfmt, commands, report):
    converted = 0
    cache = (root / ".mooncakes").resolve()
    for module, version in DEPENDENCIES.items():
        directory = root / ".mooncakes" / module
        if not directory.exists():
            continue
        if not directory.resolve().is_relative_to(cache):
            raise ValueError(f"Dependency cache resolves outside this checkout: {directory}")
        legacy_module = directory / "moon.mod.json"
        modern_module = directory / "moon.mod"
        identity = manifest_identity(modern_module if modern_module.exists() else legacy_module)
        if identity != (module, version):
            raise ValueError(f"Expected {module}@{version}, found {identity} in {directory}")
        before_sources = source_hashes(directory)
        manifests = sorted(
            path for path in directory.rglob("*.json")
            if path.name in ("moon.mod.json", "moon.pkg.json")
        )
        for legacy in manifests:
            modern = legacy.with_suffix("")
            if modern.exists():
                continue
            before = sha256(legacy)
            relative = legacy.relative_to(root).as_posix()
            require_success(relative, commands.run("moonfmt", [moonfmt, legacy, "-o", modern]))
            if sha256(legacy) != before:
                raise RuntimeError(f"Formatter changed its input manifest: {legacy}")
            report["migrations"].append({
                "module": module,
                "version": version,
                "input": relative,
                "input_sha256": before,
                "output": modern.relative_to(root).as_posix(),
                "output_sha256": sha256(modern),
            })
            converted += 1
        after_sources = source_hashes(directory)
        if before_sources != after_sources:
            raise RuntimeError(f"Dependency .mbt source changed during migration: {module}")
        report["source_hashes"][module] = before_sources
    return converted


def prepare(root, toolchain, log_dir):
    suffix = ".exe" if os.name == "nt" else ""
    moon = toolchain / "bin" / f"moon{suffix}"
    moonfmt = toolchain / "bin" / f"moonfmt{suffix}"
    log_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "failed",
        "root": str(root),
        "toolchain": str(toolchain),
        "expected_dependencies": DEPENDENCIES,
        "commands": [],
        "migrations": [],
        "source_hashes": {},
    }
    commands = Commands(root, toolchain, log_dir, report)
    try:
        root_hash = validate_root(root)
        report["root_moon_mod_sha256"] = root_hash
        version = require_success("toolchain version", commands.run("version", [moon, "version", "--all"]))
        report["toolchain_version"] = version
        report["moonfmt_sha256"] = sha256(moonfmt)
        require_success("registry update", commands.run("registry-update", [moon, "update"]))
        # At most one discovery per pinned module, followed by one final check.
        for attempt in range(1, len(DEPENDENCIES) + 2):
            code, stdout, stderr = commands.run(f"check-{attempt}", [moon, "check", "--target", "js"])
            if code == 0:
                break
            diagnostic = stdout + stderr
            legacy_error = "is no longer supported" in diagnostic and (
                "moon.mod.json" in diagnostic or "moon.pkg.json" in diagnostic
            )
            if not legacy_error:
                raise RuntimeError(f"moon check failed with exit code {code}; see command logs")
            print(f"Dependency check {attempt} stopped on a legacy manifest (exit {code}); original diagnostic saved in {log_dir}.", flush=True)
            converted = convert_cached_manifests(root, moonfmt, commands, report)
            if converted == 0:
                raise RuntimeError("Legacy manifest diagnostic had no convertible pinned dependency manifest")
            print(f"Converted {converted} cached manifests with moonfmt; checking dependency resolution again.", flush=True)
        else:
            raise RuntimeError("Pinned dependency graph did not converge after manifest migration")
        for module, expected_version in DEPENDENCIES.items():
            directory = root / ".mooncakes" / module
            actual = manifest_identity(directory / "moon.mod")
            if actual != (module, expected_version):
                raise ValueError(f"Expected {module}@{expected_version}, found {actual}")
            current_hashes = source_hashes(directory)
            if module in report["source_hashes"] and current_hashes != report["source_hashes"][module]:
                raise RuntimeError(f"Dependency .mbt source changed after migration: {module}")
            report["source_hashes"][module] = current_hashes
        report["root_moon_mod_sha256_after"] = sha256(root / "moon.mod")
        if report["root_moon_mod_sha256_after"] != root_hash:
            raise RuntimeError("Root moon.mod changed during dependency preparation")
        report["dependency_sources_unchanged"] = True
        report["status"] = "success"
        print(f"Prepared all three pinned dependencies; receipts: {log_dir / 'summary.json'}", flush=True)
    finally:
        (log_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
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
