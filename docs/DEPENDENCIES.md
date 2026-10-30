# Reproducible dependency setup

## Fresh clone and required tools

```sh
git clone --branch feat/row-group-statistics https://github.com/sgy1023-crt/parquet.git
cd parquet
```

Install Git, the pinned [MoonBit toolchain](https://www.moonbitlang.com/download/),
Node.js 24, CPython 3.13.5 and a C compiler for native checks (MSVC on Windows,
Clang/GCC on macOS/Linux). The required compiler/core build in
[`.moonbit-version`](../.moonbit-version) is `0.10.16+b1a0e846e`.
It meets the participant-provided acceptance guide's minimum of 0.10.16.
Use the matching compiler and core rather than a floating latest installation.

On Linux/macOS, install the exact build through the official installer:

```sh
curl -fsSL https://cli.moonbitlang.com/install/unix.sh | bash -s -- "$(cat .moonbit-version)"
export MOON_HOME="$HOME/.moon"
export PATH="$MOON_HOME/bin:$PATH"
moon version --all
```

The official Windows installer reads `MOONBIT_INSTALL_VERSION`:

```powershell
$env:MOONBIT_INSTALL_VERSION = (Get-Content .moonbit-version -Raw).Trim()
$installer = Join-Path ([IO.Path]::GetTempPath()) 'moonbit-install.ps1'
Invoke-WebRequest -Uri 'https://cli.moonbitlang.com/install/powershell.ps1' -OutFile $installer
& $installer
$env:MOON_HOME = Join-Path $env:USERPROFILE '.moon'
$env:PATH = (Join-Path $env:MOON_HOME 'bin') + [IO.Path]::PathSeparator + $env:PATH
moon version --all
```

The corresponding [Windows binary archive](https://cli.moonbitlang.com/binaries/0.10.16%2Bb1a0e846e/moonbit-windows-x86_64.zip)
and [matching core archive](https://cli.moonbitlang.com/cores/core-0.10.16%2Bb1a0e846e.zip)
are also available. A compiler archive alone is not a complete installation.
The verified Windows build reports moon/moonrun `0.1.20261020 (2284bd2)` and
moonc `0.10.16+b1a0e846e`. The preparation script does not install a toolchain.

## Full acceptance checks

Create an isolated Python environment for fixture-generation tools. POSIX:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r scripts/row-group-requirements.txt
python scripts/prepare_dependency_cache.py --toolchain "$MOON_HOME"
python scripts/verify_delivery.py --toolchain "$MOON_HOME"
```

PowerShell, after setting `MOON_HOME` as above:

```powershell
py -3.13 -m venv .venv
& ./.venv/Scripts/Activate.ps1
python -m pip install -r scripts/row-group-requirements.txt
python scripts/prepare_dependency_cache.py --toolchain $env:MOON_HOME
python scripts/verify_delivery.py --toolchain $env:MOON_HOME
```

If activation is restricted, invoke `.venv/Scripts/python.exe` directly without
changing machine policy. Native checks require a working C compiler; they no
longer need DuckDB headers or a native DuckDB library. A missing compiler,
unavailable package or failed command is an explicit failure.

The development-only Python packages are pinned to PyArrow 18.0.0, NumPy 2.2.4
and Apache Thrift 0.22.0 in
[`row-group-requirements.txt`](../scripts/row-group-requirements.txt).
The footer editor uses Thrift's official pure-Python Compact protocol.

`verify_delivery.py` runs targeted tests, all four backends, formatting,
interface consistency, all-target checking/building, two consumer smoke tests,
32-fixture byte-for-byte replay and four-backend decoder-entry measurements.
Each child check has a hard 60-second timeout; a failure exits nonzero.
Local receipts go under ignored `validation/`; CI uploads its receipts to
[Actions](https://github.com/sgy1023-crt/parquet/actions/workflows/ci.yml).
Historical 0.10.15 results remain in [VALIDATION.md](VALIDATION.md) and the
[final checklist](HACKATHON_FINAL_CHECKLIST.md); they are not substituted for
new 0.10.16 results.

## Dependency graph and browser interoperability

The MoonBit module pins only `moonbitlang/x@0.5.5`. Its filesystem package is
used by file convenience APIs and examples. The browser playground already
has an npm dependency on `@duckdb/duckdb-wasm`, pinned by its pnpm lockfile.
The bridge now accesses that client directly: the old MoonBit DuckDB 0.6.4 /
QuickCheck 0.14 dependency chain used removed syntax and is no longer required.
No dependency source is patched and no newer database binding is substituted.

`prepare_dependency_cache.py` runs `moon update`, then a real
`moon check --target js`, checks the resolved name/version and verifies existing
dependency source and root manifest hashes. It sets `MOON_HOME` and `PATH`
only for its children. Timestamped logs, actual toolchain versions, exit codes
and source hashes are saved under `validation/dependency-bootstrap/`, including
on failure. Each external command has a 60-second hard timeout.

For the existing browser playground:

```sh
pnpm --dir playground install --frozen-lockfile
pnpm --dir playground test
pnpm --dir playground build
pnpm --dir playground dev
```

The separate command-line interoperability check requires the official
[DuckDB 1.4.4 CLI](https://github.com/duckdb/duckdb/releases/tag/v1.4.4)
on PATH, not its native library:

```sh
node scripts/duckdb_e2e.mjs
```

CI covers MoonBit checks, builds and tests, fixture replay, the browser build
and unit tests, and the two-way DuckDB CLI interoperability check. Scheduled
health checks remain read-only; they do not publish this package.

The repository's `.gitattributes` preserves LF source files and binary Parquet
fixtures across Windows/Unix checkouts, so fixture byte hashes remain stable.
