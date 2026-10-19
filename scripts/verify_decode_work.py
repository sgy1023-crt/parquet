# SPDX-License-Identifier: Apache-2.0
"""Measure real decoder entry calls in an isolated copy of the current source.

No production hooks, PoC overlay, substituted results, or decoder implementation
are added. The only existing-source replacement declares a private trace next to
the private columnar chunk decoder and pushes its actual page offset on entry.
All original decoder statements and return paths remain byte-for-byte intact.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 60
READER = "reader.mbt"
PROBE_NAME = "decode_work_probe_wbtest.mbt"
ENTRY = """fn decode_column_chunk_columnar(
  data : Bytes,
  chunk : ColumnChunkMeta,
  column : LeafColumnMeta,
) -> ParquetColumnData raise ParquetError {
"""
DECLARATION = "let decode_work_probe : Array[Int64] = []\n\n///|\n"
TRACE = "  decode_work_probe.push(chunk.meta_data.data_page_offset)\n"
EXPECTED_COUNTS = {"full": 8, "selected": 2, "empty": 0, "ordered": 4, "invalid": 0}
PROBE = r'''// Generated only in a disposable validation copy.
///|
test "decode work probe counts real public API chunk calls" {
  let data = @fs.read_file_to_bytes("fixtures/row-groups/base.parquet")
  let metadata = parse_parquet_metadata(data)
  let offsets = metadata.row_groups.map(group =>
    group.columns.map(chunk => chunk.meta_data.data_page_offset))

  decode_work_probe.clear()
  let full = read_bytes_columnar(data)
  let full_calls = decode_work_probe.length()
  assert_eq(full_calls, 8)
  assert_eq(decode_work_probe, [
    offsets[0][0], offsets[0][1], offsets[1][0], offsets[1][1],
    offsets[2][0], offsets[2][1], offsets[3][0], offsets[3][1],
  ])
  assert_eq(full.row_count(), 16)
  assert_eq(full.column_values()[0], [
    Int32(-20), Int32(-19), Null, Int32(-17),
    Int32(0), Int32(1), Null, Int32(3),
    Int32(100), Int32(101), Int32(102), Int32(103),
    Null, Null, Null, Null,
  ])
  assert_eq(full.column_values()[1][8], Int64(9007199254740993L))

  decode_work_probe.clear()
  let selected = read_row_groups_columnar(data, [2])
  let selected_calls = decode_work_probe.length()
  assert_eq(selected_calls, 2)
  assert_eq(decode_work_probe, offsets[2])
  assert_eq(selected.row_count(), 4)
  assert_eq(selected.column_values(), [
    [Int32(100), Int32(101), Int32(102), Int32(103)],
    [Int64(9007199254740993L), Int64(9007199254740995L),
     Int64(9007199254740997L), Int64(9007199254740999L)],
  ])

  decode_work_probe.clear()
  let empty = read_row_groups_columnar(data, [])
  let empty_calls = decode_work_probe.length()
  assert_eq(empty_calls, 0)
  assert_eq(empty.row_count(), 0)
  assert_eq(empty.columns(), full.columns())
  assert_eq(empty.column_values(), [[], []])

  decode_work_probe.clear()
  let ordered = read_row_groups_columnar(data, [2, 0])
  let ordered_calls = decode_work_probe.length()
  assert_eq(ordered_calls, 4)
  assert_eq(decode_work_probe,
    [offsets[2][0], offsets[2][1], offsets[0][0], offsets[0][1]])
  assert_eq(ordered.row_count(), 8)
  assert_eq(ordered.column_values()[0], [
    Int32(100), Int32(101), Int32(102), Int32(103),
    Int32(-20), Int32(-19), Null, Int32(-17),
  ])

  decode_work_probe.clear()
  let poison = @fs.read_file_to_bytes("fixtures/row-groups/poison_skipped.parquet")
  let message = try read_row_groups_columnar(poison, [0, 4]) catch {
    ParquetError::InvalidData(message) => message
    err => raise err
  } noraise {
    _ => "unexpected success"
  }
  let invalid_calls = decode_work_probe.length()
  assert_eq(invalid_calls, 0)
  assert_true(message.contains("row group index"))
  println("DECODE_WORK full=\{full_calls} selected=\{selected_calls} empty=\{empty_calls} ordered=\{ordered_calls} invalid=\{invalid_calls}")
}
'''


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def source_hashes(directory):
    return {
        path.relative_to(directory).as_posix(): sha256(path.read_bytes())
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def tree_hash(hashes):
    return sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode())


def instrument(original):
    newline = "\r\n" if "\r\n" in original else "\n"
    entry = ENTRY.replace("\n", newline)
    declaration = DECLARATION.replace("\n", newline)
    trace = TRACE.replace("\n", newline)
    if original.count(entry) != 1:
        raise ValueError("Expected exactly one private columnar chunk decoder entry")
    if "decode_work_probe" in original:
        raise ValueError("Production reader already contains a decode-work probe")
    replacement = declaration + entry + trace
    modified = original.replace(entry, replacement, 1)
    if modified.replace(replacement, entry, 1) != original:
        raise AssertionError("Instrumentation changed code outside the single entry replacement")
    return modified


def reuse_dependencies(destination):
    dependencies = ROOT / ".mooncakes"
    if not dependencies.is_dir():
        raise FileNotFoundError("Run moon update before validation; .mooncakes is required")
    if os.name == "nt":
        # A junction can reuse dependencies across volumes without administrator
        # symlink privileges. It is never traversed during temporary-tree cleanup.
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(destination), str(dependencies)],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise RuntimeError("Dependency junction creation failed: " + result.stderr)
        return "Windows directory junction; moon --frozen"
    destination.symlink_to(dependencies, target_is_directory=True)
    return "directory symlink; moon --frozen"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True, help="MoonBit toolchain root used as MOON_HOME")
    parser.add_argument("--target", choices=("js", "wasm", "wasm-gc", "native"), default="js")
    parser.add_argument("--output", type=Path, help="Evidence directory; defaults to validation/decode-work-TARGET")
    arguments = parser.parse_args()
    toolchain = arguments.toolchain.resolve()
    moon = toolchain / "bin" / ("moon.exe" if os.name == "nt" else "moon")
    if not moon.is_file():
        raise FileNotFoundError(moon)
    output = (arguments.output or ROOT / "validation" / ("decode-work-" + arguments.target)).resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["MOON_HOME"] = str(toolchain)
    environment["PATH"] = str(toolchain / "bin") + os.pathsep + environment.get("PATH", "")
    production_hashes = source_hashes(ROOT / "src")
    started = time.monotonic()
    summary = {
        "target": arguments.target, "timeout_seconds_per_subprocess": TIMEOUT_SECONDS,
        "probe_script_sha256": sha256(Path(__file__).read_bytes()),
        "production_source_tree_sha256": tree_hash(production_hashes),
        "production_source_files_sha256": production_hashes,
        "base_fixture_sha256": sha256((ROOT / "fixtures/row-groups/base.parquet").read_bytes()),
        "expected_counts": EXPECTED_COUNTS,
        "claim_scope": "actual entries into private decode_column_chunk_columnar; no wall-time, memory, or I/O performance claim",
    }
    with tempfile.TemporaryDirectory(prefix="parquet-decode-work-") as temporary:
        work = Path(temporary).resolve()
        if work.parent != Path(tempfile.gettempdir()).resolve():
            raise ValueError("Temporary copy must remain under the explicitly selected OS temp directory")
        replacements = [(str(work), "<TEMP>"), (str(ROOT), "<REPO>"), (str(toolchain), "<TOOLCHAIN>"), (str(Path.home()), "<HOME>")]

        def redact(value):
            for path, label in replacements:
                value = value.replace(path, label).replace(path.replace("\\", "/"), label)
            return value

        shutil.copytree(ROOT / "src", work / "src")
        shutil.copytree(ROOT / "fixtures", work / "fixtures")
        module_files = [path for path in (ROOT / "moon.mod", ROOT / "moon.mod.json") if path.exists()]
        if len(module_files) != 1:
            raise ValueError("Expected one MoonBit module manifest")
        for path in module_files:
            shutil.copy2(path, work / path.name)
        for name in ("moon.lock", ".moon-lock"):
            if (ROOT / name).is_file():
                shutil.copy2(ROOT / name, work / name)
        if (work / ".git").exists() or (work / "_build").exists():
            raise AssertionError("A source copy must not contain .git or _build")
        summary["dependency_reuse"] = reuse_dependencies(work / ".mooncakes")
        copied_hashes = source_hashes(work / "src")
        if copied_hashes != production_hashes:
            raise AssertionError("Current source changed while the isolated copy was prepared")
        reader = work / "src" / READER
        original = reader.read_bytes().decode("utf-8")
        modified = instrument(original)
        reader.write_bytes(modified.encode("utf-8"))
        probe = work / "src" / PROBE_NAME
        if probe.exists():
            raise FileExistsError("Refusing to overwrite an existing source file: " + PROBE_NAME)
        probe.write_text(PROBE, encoding="utf-8", newline="\n")
        patch = "".join(difflib.unified_diff(original.splitlines(True), modified.splitlines(True), fromfile="a/src/reader.mbt", tofile="b/src/reader.mbt"))
        (output / "instrumentation.patch").write_text(patch, encoding="utf-8", newline="\n")
        (output / PROBE_NAME).write_text(PROBE, encoding="utf-8", newline="\n")
        changed = source_hashes(work / "src")
        altered = sorted(name for name in changed if copied_hashes.get(name) != changed[name])
        if altered != sorted([READER, PROBE_NAME]):
            raise AssertionError("Unexpected instrumented source changes: " + repr(altered))
        summary.update({
            "instrumented_source_tree_sha256": tree_hash(changed),
            "existing_source_files_changed": ["src/reader.mbt"],
            "new_whitebox_test": "src/" + PROBE_NAME,
            "reader_before_sha256": sha256(original.encode()),
            "reader_instrumented_sha256": sha256(modified.encode()),
            "instrumentation_diff_sha256": sha256(patch.encode()),
            "whitebox_test_sha256": sha256(PROBE.encode()),
            "single_entry_replacement_reversible_byte_for_byte": True,
            "all_original_decoder_statements_and_returns_preserved": True,
        })
        version = subprocess.run([str(moon), "version", "--all"], cwd=work, env=environment, capture_output=True, encoding="utf-8", errors="replace", check=True, timeout=TIMEOUT_SECONDS)
        summary["toolchain_versions"] = redact(version.stdout + version.stderr).strip()
        command = [str(moon), "test", "src/" + PROBE_NAME, "--target", arguments.target, "--frozen"]
        summary["command"] = [redact(item) for item in command]
        summary["command_sha256"] = sha256(json.dumps(summary["command"], separators=(",", ":")).encode())
        try:
            result = subprocess.run(command, cwd=work, env=environment, capture_output=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
            stdout, stderr = result.stdout, result.stderr
            code, timed_out = result.returncode, False
        except subprocess.TimeoutExpired as error:
            stdout = (error.stdout or b"").decode("utf-8", "replace")
            stderr = (error.stderr or b"").decode("utf-8", "replace")
            code, timed_out = 124, True
        stdout, stderr = redact(stdout), redact(stderr)
        (output / "stdout.log").write_text(stdout, encoding="utf-8")
        (output / "stderr.log").write_text(stderr, encoding="utf-8")
        match = re.search(r"DECODE_WORK full=(\d+) selected=(\d+) empty=(\d+) ordered=(\d+) invalid=(\d+)", stdout + stderr)
        counts = dict(zip(EXPECTED_COUNTS, map(int, match.groups()))) if match else None
        totals = re.findall(r"Total tests:\s*(\d+),\s*passed:\s*(\d+),\s*failed:\s*(\d+)", stdout + stderr)
        sources_unchanged = source_hashes(ROOT / "src") == production_hashes
        isolated_sources_unchanged = source_hashes(work / "src") == changed
        success = code == 0 and counts == EXPECTED_COUNTS and totals == [("1", "1", "0")] and sources_unchanged and isolated_sources_unchanged
        summary.update({
            "exit_code": code, "timed_out": timed_out, "measured_counts": counts,
            "test_summaries": totals, "production_sources_unchanged": sources_unchanged,
            "instrumented_sources_unchanged_during_test": isolated_sources_unchanged,
            "elapsed_seconds": round(time.monotonic() - started, 3), "verified": success,
        })
        (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"evidence": redact(str(output)), "target": arguments.target, "measured_counts": counts, "verified": success}, ensure_ascii=False))
        if not success:
            print((stdout + stderr)[-6000:], file=sys.stderr)
        return 0 if success else code or 1


if __name__ == "__main__":
    raise SystemExit(main())
