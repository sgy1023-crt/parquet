# MoonBit Parquet Row Group Statistics & Selective Reading

## Submission identity and status

- Repository: [sgy1023-crt/parquet](https://github.com/sgy1023-crt/parquet).
- Contribution branch: [`feat/row-group-statistics`](https://github.com/sgy1023-crt/parquet/tree/feat/row-group-statistics).
- Contributor for this enhancement: [sgy1023-crt](https://github.com/sgy1023-crt).
- Original project and author: [mizchi/parquet](https://github.com/mizchi/parquet),
  [mizchi](https://github.com/mizchi).
- Registered category: **已有项目维护** (existing-project maintenance), because this
  work extends an existing implementation with public APIs, statistics
  interpretation, decoder selection and compatibility verification.

The participant confirmed registration-review approval on 2026-10-20 based on
the organizers' email. Final acceptance remains separate and evaluates completion,
quality, licensing and MoonBit relevance. See the [final checklist](HACKATHON_FINAL_CHECKLIST.md).

## Background and contribution boundary

Upstream supplies the reader/writer, codecs, DuckDB interoperability,
tests, benchmarks and browser playground. The
[consumer request in Issue #4](https://github.com/mizchi/parquet/issues/4)
motivates access to row-group statistics and selective reading.
At the [44d4dc9 baseline](https://github.com/mizchi/parquet/commit/44d4dc9c492008fce77e1a980f1048decbd7f1c9),
full reads visit all groups and Statistics are discarded during footer parsing.
This contribution does not claim authorship of the underlying format implementation.

| This period's work | Implementation and tests |
|---|---|
| Three new APIs: metadata, one group, multiple groups | [Public entries](../src/lib.mbt), [selection tests](../src/row_group_test.mbt) |
| Raw Statistics and optional fields | [Statistics](../src/statistics.mbt), [footer parsing](../src/metadata.mbt), [tests](../src/statistics_test.mbt) |
| Immutable group and column-chunk views | [Metadata views](../src/metadata_view.mbt), [public interface](../src/pkg.generated.mbti) |
| Conservative signed INT32/INT64 interpretation | [Typed statistics](../src/statistics.mbt), [API contract](ROW_GROUP_API.md) |
| Pre-decode selection using existing decoders | [Shared reader](../src/reader.mbt), [decoder measurement](../scripts/verify_decode_work.py) |
| Independent compatibility and malformed-input fixtures | [PyArrow generator](../scripts/generate_row_group_fixtures.py), [Thrift footer editor](../scripts/compact_fixture.py), [manifest](../fixtures/row-groups/manifest.json) |
| Consumer with residual filtering and exact Int64 thresholds | [Consumer](../src/examples/row_group_scan/scan.mbt), [CLI](../src/cmd/row_group_scan/main.mbt), [usage](ROW_GROUP_EXAMPLE.md) |
| Compact overflow fixes exposed by negative tests | [Compact reader](../src/compact.mbt), [whitebox tests](../src/statistics_wbtest.mbt) |

Existing full-read API signatures remain available. Selected reads preserve
requested order, reject duplicate or invalid indices before decoding, and keep
schema for an empty selection. They reuse existing decoding behavior.

## Quality and reproduction

The local run on 2026-10-19 passed **71/71 tests on each of JS, wasm, wasm-gc
and native**: 29 original tests, 25 new library tests and 17 consumer tests.
All-target checking/building passed without warnings. All 32 fixtures replayed
byte-for-byte: 16 valid files and 16 controlled negative cases.
The [validation record](VALIDATION.md) gives tool versions and limits;
[GitHub Actions](https://github.com/sgy1023-crt/parquet/actions/workflows/ci.yml)
gives actual remote status. Local success is not a claim of remote CI success.

Follow the [README](../README.md#reproduce-this-contribution) and
[Windows/POSIX setup](DEPENDENCIES.md). After setup:

```sh
python scripts/prepare_dependency_cache.py --toolchain "$MOON_HOME"
python scripts/verify_delivery.py --toolchain "$MOON_HOME"
moon run src/cmd/row_group_scan --target js -- fixtures/row-groups/base.parquet i32 102
```

The example selects one group, decodes four candidates and filters to two
matches. Threshold `9007199254740995` on `i64` matches three values exactly.
Each automated child check has a 60-second hard timeout.

Real decoder-entry measurements on four backends are full=8, selected=2 and
empty=0; a poisoned skipped group independently confirms pre-decode selection.
These measure decoder work only. No speed, memory or I/O gain is claimed.

## Technical limits and trust boundary

Only flat, unannotated physical INT32/INT64 have typed statistics. Modern bounds
require known column ordering. Unknown semantics, missing modern bounds and
unknown ordering cannot justify skipping by value range; a validated all-NULL
count can still exclude a group. Annotated, nested and other
types remain raw metadata; the example rejects predicates on them. Structural
validation cannot prove that a writer's otherwise valid bounds truthfully
describe its pages. Candidate values undergo a residual check in the consumer.

The complete file is loaded as `Bytes`. Page Index, Bloom Filter, Range I/O,
new codecs, SQL optimization, complex nested predicates and a new writer are
outside this submission.

## Open-source origin

Upstream ancestry, attribution and the [Apache-2.0 license](../LICENSE) remain.
Added synthetic fixtures and tooling are Apache-2.0, with
[provenance and hashes](../fixtures/row-groups/README.md). Existing Apache
fixtures retain their source information. Statistics semantics cite the fixed
[Apache parquet-format specification](https://github.com/apache/parquet-format/blob/53b8bd8576827080d4382fa457003f45b41cda6e/src/main/thrift/parquet.thrift).

## 可复制的中文项目名称与备注

**项目名称：MoonBit Parquet 行组统计与选择性读取**

基于 mizchi 的 Apache-2.0 Parquet 库，sgy1023-crt 新增 Statistics 解析、公开行组元数据及单组和多组选择性读取，复用原解码器并兼容旧 API，已按“已有项目维护”申报并通过报名初审。统计解释限定为扁平、无注解 INT32/INT64；消费者先选组，再做真实残余过滤。10/30 使用 moonc 0.10.16 复核，JS 74/74，wasm、wasm-gc、native 各 71/71；32 个独立 fixture 可重放，其中 16 个为故意负例。真实列块解码调用由 8 次降至 2 次，空选择为 0 次，并有毒页对照；尚未测量速度、内存或 I/O 收益。已发布 sgy1023-crt/parquet@0.3.0 至 Mooncakes，注册表独立安装、四后端各 5 项消费者测试与全目标构建均通过。代码与 CI 公开，最终验收以赛事规则为准。参赛者提供的群指南明确，初审通过后无需再次填写验收表。
