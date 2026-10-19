# Row Group Statistics & Selective Decoding delivery

The core enhancement and local acceptance checks completed on 2026-10-19.
The public repository is [sgy1023-crt/parquet](https://github.com/sgy1023-crt/parquet),
on `feat/row-group-statistics`, based on
[mizchi/parquet at 44d4dc9](https://github.com/mizchi/parquet/commit/44d4dc9c492008fce77e1a980f1048decbd7f1c9).
The original implementation belongs to mizchi; the enhancement is contributed
by sgy1023-crt. This is existing-project maintenance, not a new Parquet engine.

## Delivered behavior

| Upstream baseline | Enhancement |
|---|---|
| Statistics discarded while parsing | Preserve modern/legacy bounds, optional NULL/distinct counts and exactness flags |
| No public row-group metadata | Inspect immutable file, group and column-chunk views without decoding pages |
| Full reading enters every row group | Read one or multiple specified groups through the existing decoders |
| No selection contract | Preserve requested order, reject duplicate/invalid indices before decoding, retain schema for an empty selection |
| No typed statistics access | Validate conservative flat, unannotated INT32/INT64 bounds with known ordering |
| No consumer for metadata selection | Separate package and CLI with group selection, residual filtering and original-file row positions |

The three entry points are [`read_metadata`, `read_row_group_columnar` and
`read_row_groups_columnar`](../src/lib.mbt). Existing full-read signatures are
unchanged, and both paths use the [shared read loop](../src/reader.mbt).
There is no new decoder, SQL engine or public test-only hook.

The [parser](../src/metadata.mbt), [views](../src/metadata_view.mbt) and
[statistics implementation](../src/statistics.mbt) validate schema/chunk
agreement, metadata counts and supported integer bounds. Tests also exposed
three Compact decoding defects: oversized length truncation, UInt64 varint
overflow in the tenth byte and integer overflow in bounds checking. The
[Compact reader](../src/compact.mbt) now rejects those malformed inputs.
See the [API contract](ROW_GROUP_API.md) for precise semantics.

## Verified results

The [validation record](VALIDATION.md) separates recorded local results from
[remote GitHub Actions status](https://github.com/sgy1023-crt/parquet/actions/workflows/ci.yml).
The completed local run passed 71/71 tests on each of JS, wasm, wasm-gc and
native, all-target checks/builds without warnings, and byte-for-byte replay of
32 fixtures. Of those fixtures, 16 are valid files and 16 are deliberate
negative cases. They are not 32 successfully readable datasets.

The [consumer](ROW_GROUP_EXAMPLE.md) actually runs: `i32 >= 102` matches two
rows, while `i64 >= 9007199254740995` matches three without a floating-point
conversion. Real decoder instrumentation on all four backends records full=8,
selected `[2]`=2, empty=0, ordered `[2,0]`=4 and invalid `[0,4]`=0. A poisoned
unselected page independently distinguishes selective decoding from filtering
after a full read.

This demonstrates a 75% reduction in decoder entries for that four-group,
two-column fixture. Runtime, peak memory and file I/O benefits remain
unmeasured; the input is still a complete in-memory `Bytes` value.

## Reproduction and scope

Start with the [README](../README.md#reproduce-this-contribution), then follow
the platform-specific [dependency setup](DEPENDENCIES.md). Run:

```sh
python scripts/prepare_dependency_cache.py --toolchain "$MOON_HOME"
python scripts/verify_delivery.py --toolchain "$MOON_HOME" --duckdb "$DUCKDB_DIR"
```

The toolchain root and DuckDB directory are explicit inputs. The verifier runs
real tests, checks, builds, consumer commands, independent fixture replay and
decoder instrumentation. Each child check has a 60-second timeout; errors stop
the run with a nonzero exit. Python packages are development-only tools, not
runtime dependencies of the MoonBit library.

Modern bounds are used only for known signed integer semantics and column
ordering. Missing modern bounds and unknown ordering cannot justify skipping
by value range; validated all-NULL counts remain independently useful.
The consumer retains uncertain candidates and tests
their actual values. Structurally valid metadata cannot prove that a writer's
statistics truthfully describe its pages. Unsupported annotations, nested
predicates, Page Index, Bloom Filter, Range I/O or a new writer are outside this
contribution.

The original Apache-2.0 [license](../LICENSE), upstream commit ancestry and
[fixture provenance](../fixtures/row-groups/README.md) are retained. The
[submission notes](HACKATHON_SUBMISSION.md) describe the proposed maintenance
category; acceptance of an unmerged fork has not been guaranteed.
