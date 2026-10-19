# Validation record

This record describes the completed local acceptance run on 2026-10-19.
Remote runs have their own observable status in
[GitHub Actions](https://github.com/sgy1023-crt/parquet/actions/workflows/ci.yml).
A successful local check is not a claim that a GitHub-hosted job has passed.
The workflow uploads receipts for the commands it actually runs.

## Completed local checks

| Check | Recorded result |
|---|---|
| JS tests | 71 passed, 0 failed |
| wasm tests | 71 passed, 0 failed |
| wasm-gc tests | 71 passed, 0 failed |
| native tests | 71 passed, 0 failed |
| Original tests | 29 retained: 27 root-package tests and two playground-bridge tests |
| New library tests | 25 selection, metadata/statistics and malformed Compact input tests |
| Separate consumer tests | 17 tests covering selection, residuals, NULLs and unsupported semantics |
| All-target checking | `moon check --target all --deny-warn`: exit 0 |
| All-target build | `moon build --target all --deny-warn`: exit 0 |
| Formatting and interfaces | `moon fmt --check` passed; `moon info` left generated interfaces unchanged |
| Independent fixtures | 32 files and the manifest replayed byte-for-byte |
| Existing playground | Vitest 4/4 and production build passed |
| Separate DuckDB interoperability CLI | `node scripts/duckdb_e2e.mjs`: exit 0, `duckdb e2e ok`, using DuckDB CLI 1.4.4 and current MoonBit JS; not part of the 71 tests |
| Fresh dependency cache | Real registry/package downloads and compilation succeeded; all 195 dependency source hashes unchanged |
| Consumer CLI, i32 | `i32 >= 102`: selected `[2]`, four candidate rows, two residual matches |
| Consumer CLI, i64 | `i64 >= 9007199254740995`: three exact residual matches |

The measured setup was moon `0.1.20261012 (748b63c)`, moonc
`0.10.15+943464bfa`, moonrun `0.1.20261012`, Node `24.12.0`, CPython `3.13.5`,
PyArrow `18.0.0`, NumPy `2.2.4` and Apache Thrift `0.22.0`.
Native testing used DuckDB `1.4.4` and MSVC. These numbers describe this setup;
they do not promise that a changing latest toolchain produces the same result.
The separate DuckDB interoperability check was rerun during public delivery;
it is reported separately from the 71 tests.

## Evidence that unselected groups are not decoded

[`verify_decode_work.py`](../scripts/verify_decode_work.py) copies the current
source to a temporary directory and instruments only the private column-chunk
decoder entry. The production source has no test-only tracing API. The script
checks that original decoder statements and returns stay byte-identical, the
injection is reversible and production source hashes remain unchanged.
It checks real values and page-offset order, as well as counting entries.

| Public API request | Actual column-chunk decoder entries, on each of four backends |
|---|---:|
| Full read: four groups, two columns | 8 |
| Selected `[2]` | 2 |
| Empty `[]` | 0 |
| Ordered `[2,0]` | 4 |
| Invalid `[0,4]` on the poisoned file | 0 |

The [poisoned fixture](../fixtures/row-groups/README.md) changes a page header
in group 0 while preserving the footer. Metadata inspection and reading group
2 succeed; full reading fails. Invalid selection and selected-row overflow
errors occur before entering that poisoned decoder. Together these tests
distinguish pre-decode selection from post-read filtering.

The change is **8 → 2 decoder entries**, not a measured 75% speed improvement.
Elapsed time, peak memory and I/O benefits have not been measured. The entire
file is still supplied in memory.

## Independent fixture coverage

The [fixture manifest](../fixtures/row-groups/manifest.json) and
[fixture documentation](../fixtures/row-groups/README.md) record generator,
tool/runtime and output hashes, exact rows, raw bounds and protocol provenance.
Large integer values are decimal strings to avoid JSON Number rounding.

There are **16 valid files** and **16 deliberately invalid cases** among the
32 files. Valid fixtures are fully read with PyArrow. The invalid cases cover
bad bound lengths/order, invalid counts, schema/column inconsistencies, selected
row-count overflow, a poisoned page and corrupt/truncated footers. They are
expected errors, not successful round trips. Malformed statistics are not fed
to PyArrow's native statistics interpretation: it can terminate the process on
short bounds. Apache Thrift footer round trips and unchanged page-prefix checks
instead verify those controlled mutations; MoonBit tests assert explicit errors.

Protocol fields follow
[Apache parquet-format commit 53b8bd8](https://github.com/apache/parquet-format/blob/53b8bd8576827080d4382fa457003f45b41cda6e/src/main/thrift/parquet.thrift).
The generator uses PyArrow to create pages and Apache Thrift's official Compact
protocol to edit footer fields independently of the MoonBit implementation.
It does not implement the consumer's pruning logic.

## Repeat the checks

Use the fresh-clone instructions and isolated development dependencies in
[DEPENDENCIES.md](DEPENDENCIES.md), then run:

```sh
python scripts/verify_delivery.py --toolchain "$MOON_HOME" --duckdb "$DUCKDB_DIR"
```

[`verify_delivery.py`](../scripts/verify_delivery.py) invokes real commands for
targeted tests, four complete suites, formatting/interface checks, all-target
checking/building, consumer smoke tests, fixture replay and four decoder-entry
measurements. [`run_validation.py`](../scripts/run_validation.py) records exit
status and enforces a hard 60-second timeout per child check. A failure remains
a nonzero result; no snapshot update or substituted success path is used.
Generated receipts remain local outputs; GitHub-hosted receipts are attached
to their actual [Actions runs](https://github.com/sgy1023-crt/parquet/actions/workflows/ci.yml).
