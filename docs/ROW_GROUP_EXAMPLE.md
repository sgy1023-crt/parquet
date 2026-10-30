# Row-group scan consumer

`src/examples/row_group_scan` is a separate MoonBit package that imports
`sgy1023-crt/parquet`. Its `scan_ge(Bytes, Array[String], Int64)` function uses public
metadata and selected-read APIs to evaluate a single `column >= threshold`
predicate. Predicate logic lives entirely in the consumer.

Run from the repository root:

```sh
moon run src/cmd/row_group_scan --target js
moon run src/cmd/row_group_scan --target js -- fixtures/row-groups/base.parquet i32 102
moon run src/cmd/row_group_scan --target js -- fixtures/row-groups/base.parquet i64 9007199254740995
moon test src/examples/row_group_scan --target js
```

The default command reads `fixtures/row-groups/base.parquet`, selects column
`i32`, and uses threshold `100`. CLI thresholds are parsed directly as signed
64-bit integers, including values beyond JavaScript Number's exact range.

The consumer accepts flat, unannotated physical INT32 or INT64 columns. Logical
annotations, converted types, nested columns, and other physical types raise
`ParquetError::Unsupported`. A missing predicate column raises `InvalidData`.
The CLI accepts one flat column name; the package API accepts its schema path as
an array, for example `["i32"]`. It requires row-group column metadata and reports
an explicit unsupported error for files without any row groups.
Paths use the original schema spelling. The consumer keeps the metadata column
index for residual evaluation, even if decoded display names are normalized.

For each row group, the consumer skips zero-row groups, known all-NULL groups,
and groups whose signed maximum is below the threshold. Absent statistics,
absent bounds, and unknown ordering conservatively retain candidates. NULL
counts remain useful when ordering is unknown. The library's typed view validates
statistics; malformed statistics propagate as errors.

After selection, the example calls `read_row_groups_columnar` with candidate
indices, then evaluates every candidate value. NULL values do not match. This
residual filtering is necessary: min/max statistics identify possible matches,
not individual matching rows.

`ScanResult` exposes:

- `batch()`: the existing `ParquetColumnarFile` containing all decoded candidate
  rows and columns, including rows that fail the residual predicate.
- `selected_row_groups()`: candidate group indices in file order.
- `matching_rows()`: zero-based positions inside the candidate batch.
- `matching_file_rows()`: zero-based positions in the original file, as `Int64`.
- `matching_row_count()`: the number of residual matches.

For the base fixture, `i32 >= 102` selects group `[2]`, decodes four rows, and
matches batch positions `[2, 3]`, corresponding to file positions `[10, 11]`.
The CLI prints the candidate columnar data and those positions so the difference
between decoded candidates and actual matches is visible.

The entire file is read into `Bytes` before scanning. This example demonstrates
metadata-driven selective decoding; it does not implement range reads or claim
measured I/O, elapsed-time, or memory savings.
