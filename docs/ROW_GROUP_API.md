# Row-group metadata and selective columnar reads

All three entry points raise `ParquetError`:

| API | Result and behavior |
|---|---|
| `read_metadata(Bytes)` | Footer inspection, with no column/page decoding |
| `read_row_group_columnar(Bytes, Int)` | One zero-based row group |
| `read_row_groups_columnar(Bytes, Array[Int])` | Unique groups in caller order |

The two selected-read functions return the existing `ParquetColumnarFile`.
All columns of each selected group are decoded using the existing column
decoders. Column projection and row predicates are outside these APIs. The
existing `read_bytes`, `read_bytes_columnar`, and file convenience APIs retain
their signatures and use the same decode loop.

An empty selection preserves column schema, with a zero row count and empty
data for each column. Every requested index and duplicate is validated before
the first column decoder call. Negative and out-of-range indices, duplicate
indices, and a selected row count above the batch's Int capacity are
`InvalidData`. Footer row counts remain Int64 and can be inspected even when a
selected batch would be too large.

## Metadata views

`ParquetMetadata` exposes row count, row-group count, writer identity and
read-only row groups. Each `RowGroupMetadata` exposes its file index, row count,
read-only column chunks, uncompressed byte size, optional compressed size and
file offset. `ColumnChunkMetadata` exposes the original schema path, physical
type, logical annotation presence, optional converted-type code, flatness,
optional column order, value count, compressed/uncompressed sizes, data-page
and dictionary-page offsets, and optional raw `Statistics`.

The views have immutable fields and collections; raw bound `Bytes` are immutable
in MoonBit. The parser validates chunk/schema physical type and raw path
agreement, column-order cardinality, nonnegative row/value counts and the file
row-count total. For flat columns, chunk value count includes NULLs and must
match its row-group row count. These checks also apply to empty selections.
Malformed metadata is an explicit error, rather than an empty successful read.

## Statistics contract

Statistics follow Apache parquet-format
[`53b8bd8`](https://github.com/apache/parquet-format/blob/53b8bd8576827080d4382fa457003f45b41cda6e/src/main/thrift/parquet.thrift).
`min_value` and `max_value` are the modern binary fields; `legacy_min` and
`legacy_max` are the deprecated binary fields. They are never substituted for
each other. NULL count, distinct count and both exactness flags preserve
absence as `None`. Unknown fields are skipped by the Compact reader.

`ColumnChunkMetadata::signed_integer_statistics()` returns a typed view only
for a flat, non-repeated, unannotated physical INT32 or INT64 column. Any
`logicalType` presence, any converted annotation, a nested/repeated column or
another physical type returns `None`. Missing raw statistics also returns
`None`; it does not mean zero NULLs or an empty group.

Modern bounds are interpreted only with the corresponding `TYPE_ORDER` column
order. Absent or unknown order suppresses bounds, while a known NULL count
remains available. Single-sided bounds are supported. The `exact=false` and
absent exactness flags do not invalidate conservative bounds. INT32/INT64
PLAIN little-endian bounds are decoded directly to signed Int64; no floating
point conversion is involved.

Negative statistics counts or NULL counts above chunk value count are errors
during metadata parsing. For a supported typed view with known order, invalid
bound widths and minimum greater than maximum are errors, even on all-NULL
groups. Unsupported semantics remain uninterpreted raw data. These checks do
not prove that a writer's structurally valid bounds tell the truth about its
pages; doing that would require decoding the pages.

## Selection is not a row filter

The external [consumer](ROW_GROUP_EXAMPLE.md) implements `column >= threshold`.
It validates signed semantics, discards known all-NULL groups and groups whose
known maximum is below the threshold, and retains uncertain cases. It then
decodes selected groups and applies the predicate to actual values. False
positives inside a retained group are expected and removed by that residual
step. No SQL engine or public test-only decoder hook is added.

Input is the whole in-memory file. There is no range I/O, async streaming,
new codec, nested predicate support or measured speed/memory improvement in
this change.
