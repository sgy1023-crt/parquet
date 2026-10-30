# MoonBit Parquet — row-group statistics and selective reading

Parquet reader/writer for MoonBit, maintained here as `sgy1023-crt/parquet`
with the original `mizchi/parquet` attribution and Apache-2.0 license preserved.

## 2026 MoonBit Hackathon — Row Group Statistics & Selective Decoding

This is a substantive enhancement of [mizchi/parquet](https://github.com/mizchi/parquet),
originally developed by [mizchi](https://github.com/mizchi), rather than a new
Parquet implementation. [sgy1023-crt](https://github.com/sgy1023-crt) contributed
the row-group statistics, metadata and selective-decoding work in this fork,
based on upstream commit
[`44d4dc9`](https://github.com/mizchi/parquet/commit/44d4dc9c492008fce77e1a980f1048decbd7f1c9).
The upstream [consumer request, Issue #4](https://github.com/mizchi/parquet/issues/4),
provides the use case. Existing reader/writer, codecs, DuckDB integration,
playground and benchmarks remain upstream contributions. The browser bridge's
scalar conversion preserves the behavior of the Apache-2.0
[mizchi/duckdb 0.6.4 binding](https://github.com/mizchi/duckdb.mbt);
the bridge now uses the existing npm DuckDB WASM client directly for compatibility
with MoonBit 0.10.16.

| Before, at the upstream baseline | This contribution |
|---|---|
| Every row group enters full reading | Single or multiple groups can be decoded directly |
| Statistics are not exposed | Raw Statistics and a validated signed-integer view are public |
| No public row-group inspection | Footer metadata, row groups and column chunks are inspectable |
| Consumers cannot select groups before decoding | Consumers can retain candidate groups and then filter actual rows |

The three new APIs are `read_metadata`, `read_row_group_columnar` and
`read_row_groups_columnar`. Existing `read_bytes`, `read_bytes_columnar` and
file convenience APIs keep their signatures; full and selected reads share
the existing decoders. See the [public entries](src/lib.mbt),
[metadata views](src/metadata_view.mbt), [statistics implementation](src/statistics.mbt)
and [API contract](docs/ROW_GROUP_API.md).

```moonbit
let metadata = @parquet.read_metadata(bytes)
let group = metadata.row_groups()[2]
let statistics = group.columns()[0].signed_integer_statistics()
let batch = @parquet.read_row_groups_columnar(bytes, [2])
```

Selections preserve caller order. Duplicates and invalid indices fail before
decoding; an empty selection retains the schema. The typed statistics view
interprets only flat, unannotated INT32/INT64. Unknown semantics or ordering
cannot justify skipping by value range; a validated all-NULL count can still
eliminate a group. Raw fields preserve modern/legacy bounds,
optional NULL/distinct counts and exactness flags separately.

The separate [consumer package and CLI](docs/ROW_GROUP_EXAMPLE.md) implement
`column >= threshold`: select candidate groups, decode them, then apply a real
residual filter. For `i32 >= 102`, the base fixture selects group `[2]`, decodes
four rows and matches two. INT64 thresholds beyond `2^53` remain exact.

**Verified locally on 2026-10-19:** JS, wasm, wasm-gc and native each passed
**71/71** tests; **32 fixtures** replayed byte-for-byte, comprising 16 valid
files and 16 intentional negative cases. Four-backend instrumentation measured
column-chunk decoder entries **8 → 2** for one of four groups and **0** for an
empty selection. Poisoned-page tests independently show that unselected pages
are not decoded. These are decoding-work measurements; speed, peak memory and
file I/O benefits have not been measured. Input is still the whole file as
`Bytes`; there is no Range I/O, predicate engine or column projection.

**Revalidated locally on 2026-10-30 with moonc 0.10.16:** JS **74/74**
(three additional browser conversion regressions), wasm / wasm-gc / native
**71/71** each, all 17 delivery checks passed, and all 32 fixtures replayed.
Decoder-entry counts remain **8/2/0/4/0**. The production browser build also
passed actual DuckDB WASM queries, including exact INT64, empty-result schema,
NULL versus empty string, and recovery after an expected SQL error.

### Reproduce this contribution

Install the [documented tools and native prerequisites](docs/DEPENDENCIES.md):
the MoonBit build fixed in [`.moonbit-version`](.moonbit-version)
(`moonc 0.10.16+b1a0e846e`), Node.js 24 and CPython 3.13.5.
The full native checks require a C compiler. DuckDB CLI 1.4.4 is used only by
the separate interoperability check; no DuckDB native library is required.
Use an isolated Python environment for fixture tools. A POSIX-shell example is:

```sh
git clone --branch feat/row-group-statistics https://github.com/sgy1023-crt/parquet.git
cd parquet
curl -fsSL https://cli.moonbitlang.com/install/unix.sh | bash -s -- "$(cat .moonbit-version)"
export MOON_HOME="$HOME/.moon"
export PATH="$MOON_HOME/bin:$PATH"
moon version --all
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r scripts/row-group-requirements.txt
python scripts/prepare_dependency_cache.py --toolchain "$HOME/.moon"
python scripts/verify_delivery.py --toolchain "$HOME/.moon"
```

The compiler and core must match this pinned build. It meets the acceptance
guide's minimum compiler version of 0.10.16. The outdated MoonBit DuckDB /
QuickCheck dependency chain has been removed; dependency source is not patched.
Complete PowerShell commands are in [DEPENDENCIES.md](docs/DEPENDENCIES.md).
The verification script runs tests,
checks, builds, consumer smoke tests, fixture replay and real decoder-entry
measurements, with a hard 60-second limit for each child check. It exits nonzero
on failure. For a quick consumer run after setup:

```sh
moon run src/cmd/row_group_scan --target js -- fixtures/row-groups/base.parquet i32 102
moon run src/cmd/row_group_scan --target js -- fixtures/row-groups/base.parquet i64 9007199254740995
```

Read the [validation record](docs/VALIDATION.md),
[delivery scope](docs/DELIVERY.md) and
[hackathon submission notes](docs/HACKATHON_SUBMISSION.md).
[GitHub Actions run 41002594210](https://github.com/sgy1023-crt/parquet/actions/runs/41002594210)
passed all nine active CI jobs for code commit
`408c274e9560cad91eee1403b89b2094c295b536` with the pinned 0.10.16 toolchain,
including checks, explicit builds, tests, macOS native and DuckDB interoperability.
[Fresh-checkout acceptance run 41002685678](https://github.com/sgy1023-crt/parquet/actions/runs/41002685678)
also passed all 17 checks for that commit. Exact commands and raw receipts are
attached to these runs; the final checklist records the remaining release step.
The participant reports that this existing-project maintenance entry passed
registration review. Final acceptance remains a separate assessment. See the
[maintenance schedule and final checklist](docs/HACKATHON_FINAL_CHECKLIST.md)
for actual automation, evidence and the remaining manual procedures.

The fork preserves the upstream [Apache-2.0 license](LICENSE).
[Synthetic fixtures and their provenance](fixtures/row-groups/README.md) are
Apache-2.0; the upstream Apache test corpus retains its existing source and
license information. Statistics follow a
[pinned Apache parquet-format specification](https://github.com/apache/parquet-format/blob/53b8bd8576827080d4382fa457003f45b41cda6e/src/main/thrift/parquet.thrift).

### Mooncakes package preparation

The release candidate is `sgy1023-crt/parquet@0.3.0` in this contributor's
own namespace. Publication is pending explicit approval; the candidate is not
yet advertised as installable from Mooncakes. Once released, consumers use
`sgy1023-crt/parquet` in their `moon.pkg` imports. Function and type contracts
are preserved; the fork's import prefix differs from upstream `mizchi/parquet`.

## Status

- Reader passes the vendored `apache-parquet-testing` fixtures used in this repo:
  - `delta_binary_packed`
  - `delta_byte_array`
  - `delta_encoding_optional_column`
  - `delta_encoding_required_column`
  - `int32_with_null_pages`
  - `fixed_length_byte_array`
  - `datapage_v2_empty_datapage.snappy.parquet`
  - `int96_from_spark`
  - `alltypes_plain`
  - `alltypes_dictionary`
- Writer currently supports flat schemas with `Int32`, `Int64`, `String`, and `Binary`, with `Required` / `Optional` repetition.
- DuckDB interoperability is checked both ways:
  - DuckDB-written parquet can be read by this implementation.
  - MoonBit-written parquet can be read by DuckDB.

## Benchmark

The following upstream benchmarks predate this contribution and do not measure
the new selective-reading APIs.

Measured on 2026-03-09 on `Apple M5`, `macOS 26.2`, `Darwin arm64`.

Reproduce:

```bash
just bench-compare-all
just bench-compare-rust
```

Comparison table from `just bench-compare-all`:

| benchmark | moon(js) | moon(wasm-gc) | moon(native) | rust |
|---|---:|---:|---:|---:|
| read delta binary packed benchmark | 512.22 us | 127.01 us | 645.99 us | 203.85 us |
| read int32 null pages benchmark | 17.34 us | 10.85 us | 43.60 us | 7.61 us |
| read fixed length byte array benchmark | 87.17 us | 10.41 us | 54.68 us | unsupported |
| read alltypes plain benchmark | 20.49 us | 12.02 us | 45.42 us | 19.57 us |
| read alltypes dictionary benchmark | 16.83 us | 11.04 us | 42.53 us | 17.31 us |
| read int96 from spark benchmark | 10.90 us | 3.52 us | 16.19 us | 3.28 us |
| read empty snappy datapage v2 benchmark | 3.46 us | 1.72 us | 6.27 us | 2.58 us |

Notes:

- Rust is the local baseline in `tools/rust-bench`, built on top of Apache's `parquet` crate.
- `fixed_length_byte_array` is marked `unsupported` because the current Rust benchmark tool does not read that fixture.
- On this machine, `wasm-gc` is the fastest MoonBit target for the read-side microbenchmarks above.

## Development

```bash
just                  # check + test
just target=js bench
just target=wasm-gc bench
just target=native bench
just bench-compare-all
just e2e-duckdb
moon info
```

## Browser Playground

The repository includes a browser playground that generates parquet on DuckDB WASM and lets you try SQL against it immediately.

```bash
just playground-install
just playground-dev
```

Production build:

```bash
just playground-build
just playground-build-pages
```

In the UI, edit schema JSON / rows JSON / SQL, generate parquet bytes with this
Parquet implementation, and execute `read_parquet('playground.parquet')` on
the existing npm DuckDB WASM client through the MoonBit playground bridge.

GitHub Pages:

`https://mizchi.github.io/parquet/`

## License

Apache-2.0
