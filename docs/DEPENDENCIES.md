# Reproducible dependency setup

## Fresh clone and required tools

Start with the public contribution branch:

```sh
git clone --branch feat/row-group-statistics https://github.com/sgy1023-crt/parquet.git
cd parquet
```

Install Git, the [MoonBit toolchain](https://www.moonbitlang.com/download/),
Node.js 24, CPython 3.13.5 and a C compiler for native checks (MSVC on Windows,
Clang/GCC on macOS/Linux). The recorded local run used Node 24.12.0.
The measured MoonBit version is listed below; a changing latest installation
must pass real checks before its results can be claimed. No toolchain is
downloaded or silently substituted by the repository's preparation script.

Download the matching official native library from
[DuckDB 1.4.4 releases](https://github.com/duckdb/duckdb/releases/tag/v1.4.4):
`libduckdb-windows-amd64.zip`, `libduckdb-linux-amd64.zip` or
`libduckdb-osx-universal.zip`. Extract its `duckdb.h` and native library into
one directory, referred to below as `DUCKDB_DIR`. On Windows it must contain
`duckdb.h`, `duckdb.lib` and `duckdb.dll`; on Linux `duckdb.h` and
`libduckdb.so`; on macOS `duckdb.h` and `libduckdb.dylib`. Use the platform
matching your compiler and architecture. Native verification requires these
files in addition to the MoonBit compiler.

Create an isolated fixture-tool environment and run all checks from the
repository root. POSIX-shell example (replace `./.tools/duckdb` with the
directory where the archive was extracted):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r scripts/row-group-requirements.txt
export MOON_HOME="$HOME/.moon"
export PATH="$MOON_HOME/bin:$PATH"
export DUCKDB_DIR="$(pwd)/.tools/duckdb"
python scripts/prepare_dependency_cache.py --toolchain "$MOON_HOME"
python scripts/verify_delivery.py --toolchain "$MOON_HOME" --duckdb "$DUCKDB_DIR"
```

PowerShell example, also from the repository root:

```powershell
py -3.13 -m venv .venv
& ./.venv/Scripts/Activate.ps1
python -m pip install -r scripts/row-group-requirements.txt
$env:MOON_HOME = Join-Path $env:USERPROFILE '.moon'
$env:PATH = (Join-Path $env:MOON_HOME 'bin') + [IO.Path]::PathSeparator + $env:PATH
$duckdbDir = (Resolve-Path './.tools/duckdb').Path
python scripts/prepare_dependency_cache.py --toolchain $env:MOON_HOME
python scripts/verify_delivery.py --toolchain $env:MOON_HOME --duckdb $duckdbDir
```

If script activation is restricted, invoke `.venv/Scripts/python.exe` directly
instead of changing machine policy. The `--duckdb` argument sets header,
linker and runtime search paths for the verifier's child processes. If those
paths are already configured, the argument can be omitted. A missing compiler,
library, unavailable package or failed command is an explicit failure.

The pinned development packages are PyArrow 18.0.0, NumPy 2.2.4 and Apache
Thrift 0.22.0 in [`row-group-requirements.txt`](../scripts/row-group-requirements.txt).
They generate and replay fixtures; none is a runtime dependency of this MoonBit
library. Thrift's package installation may build its optional native extension,
so install it where build prerequisites are available. The footer editor uses
the official pure-Python Compact protocol, not the optional fastbinary path.

`verify_delivery.py` performs targeted tests, four-backend tests, formatting,
interface checks, all-target checking/building, consumer smoke tests, 32-fixture
replay and four-backend decoder-entry measurements. Each child check has a
60-second hard timeout and a failure exits nonzero. It generates local receipts
under `validation/`; do not commit machine-specific receipts or dependency
caches. Public results are summarized in [VALIDATION.md](VALIDATION.md) and
remote receipts are attached to [Actions runs](https://github.com/sgy1023-crt/parquet/actions/workflows/ci.yml).

## Verified dependency graph and cache preparation

The verified toolchain is `moon 0.1.20261012 (748b63c)` with
`moonc v0.10.15+943464bfa`. Use that toolchain for reproducing the measured
results. `prepare_dependency_cache.py` records actual versions and requires a
successful real compiler check; other toolchains are not rejected by name alone
and are not claimed to be verified. It does not install or upgrade the toolchain.
It uses Python 3.9 or
newer and the toolchain's own `moon` and `moonfmt` executables.

The root `moon.mod` pins the direct dependencies. The resolved graph verified
by the script is:

| Module | Version | Relationship |
| --- | --- | --- |
| `moonbitlang/x` | `0.5.5` | Direct |
| `mizchi/duckdb` | `0.6.4` | Direct |
| `moonbitlang/quickcheck` | `0.14.0` | DuckDB dependency |

From a fresh checkout, run:

```sh
python scripts/prepare_dependency_cache.py --toolchain "$HOME/.moon"
```

On PowerShell, pass the directory containing the installed toolchain's `bin`
and `lib`, for example:

```powershell
python scripts/prepare_dependency_cache.py --toolchain $env:MOON_HOME
```

The script sets `MOON_HOME` and `PATH` only for its child processes. It first
runs `moon update`, which is necessary when the toolchain has no registry index.
It then runs `moon check --target js`; dependency resolution downloads the
versions requested by the root manifest.

Those published DuckDB and QuickCheck releases contain legacy `moon.mod.json`
files. This toolchain rejects them before it can finish resolving the graph.
The first rejected module can vary with download order. The script treats only
the specific unsupported-legacy-manifest diagnostic as a compatibility step:

1. Save the nonzero exit code and original stdout/stderr.
2. Verify the downloaded module's name and pinned version.
3. Convert its cached legacy manifests using the official formatter, for example
   `moonfmt .mooncakes/mizchi/duckdb/moon.mod.json -o .mooncakes/mizchi/duckdb/moon.mod`.
4. Run dependency resolution and checking again. QuickCheck can first appear at
   this stage because DuckDB's manifest is now readable.
5. Require a successful check and verify all three resolved module versions.

The discovery loop is bounded to four checks for this three-module graph.
Other failures, including download errors, compiler errors, unexpected versions,
or timeouts, stop preparation with a nonzero exit. Every external command has a
hard 60-second timeout. An entire fresh setup contains several commands and can
take more than 60 seconds.

Only missing modern manifests under the checkout's `.mooncakes/` are written.
The original JSON manifests remain unchanged. The script does not rewrite the
root `moon.mod`, dependency `.mbt` sources, or application sources. In particular,
it does not run `moon fmt` over dependency source trees. `moonfmt -w` on a JSON
manifest is unsuitable here: it leaves the new syntax at the legacy filename;
the script uses an explicit modern output filename instead.

Each run creates a new UTC timestamp directory under
`validation/dependency-bootstrap/`, preserving earlier receipts. `--log-dir`
can choose a different receipt parent; `--root` can select a different checkout.
The console prints a short migration summary. The receipt directory contains
raw command stdout/stderr and `summary.json` with command exit codes, elapsed
times, the actual toolchain versions, formatter SHA-256, original/generated
manifest SHA-256 values, and individual dependency source hashes. A failed run
also writes its summary and retains the diagnostic that caused it to stop.

The Windows verification used a separate TEMP checkout with no `.mooncakes/`
directory and a separate `MOON_HOME` with no registry directory. Only the
verified toolchain's `bin`, `lib`, and `include` directories were shared through
junctions; dependency packages and registry metadata were downloaded afresh.
The observed sequence downloaded DuckDB, converted its module manifest,
downloaded `x` and QuickCheck, converted QuickCheck's module manifest, and then
completed `moon check --target js`. The two converted manifests and all 195
dependency `.mbt` files were checked by SHA-256; dependency sources and the root
manifest remained unchanged.

The repository's `.gitattributes` keeps source, generator and validation files
at LF on both Windows and Unix, and treats Parquet fixtures as binary. This
preserves the byte hashes in the fixture and decode-work manifests when Git's
Windows `core.autocrlf` setting is enabled. Source archives are also exported
with `git -c core.autocrlf=false archive` and checked against measured source
hashes before delivery.
