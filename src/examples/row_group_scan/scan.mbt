///|
/// The decoded candidate batch and row positions that satisfy the predicate.
/// Both position arrays are zero based; file positions use Int64.
pub struct ScanResult {
  batch : @parquet.ParquetColumnarFile
  selected_row_groups : ReadOnlyArray[Int32]
  matching_rows : ReadOnlyArray[Int32]
  matching_file_rows : ReadOnlyArray[Int64]
}

///|
pub fn ScanResult::batch(self : ScanResult) -> @parquet.ParquetColumnarFile {
  self.batch
}

///|
pub fn ScanResult::selected_row_groups(
  self : ScanResult,
) -> ReadOnlyArray[Int32] {
  self.selected_row_groups
}

///|
pub fn ScanResult::matching_rows(self : ScanResult) -> ReadOnlyArray[Int32] {
  self.matching_rows
}

///|
pub fn ScanResult::matching_file_rows(
  self : ScanResult,
) -> ReadOnlyArray[Int64] {
  self.matching_file_rows
}

///|
pub fn ScanResult::matching_row_count(self : ScanResult) -> Int32 {
  self.matching_rows.length()
}

///|
fn path_matches(
  actual : ReadOnlyArray[String],
  expected : Array[String],
) -> Bool {
  actual.length() == expected.length() &&
  actual.iter().zip(expected.iter()).all(fn(pair) { pair.0 == pair.1 })
}

///|
fn predicate_column_index(
  group : @parquet.RowGroupMetadata,
  path : Array[String],
) -> Int32 raise @parquet.ParquetError {
  let columns = group.columns()
  for index in 0..<columns.length() {
    if path_matches(columns[index].path_in_schema(), path) {
      return index
    }
  }
  raise @parquet.InvalidData(
    "predicate column was not found: \{@debug.Repr(path)}",
  )
}

///|
fn validate_signed_column(
  column : @parquet.ColumnChunkMetadata,
) -> Unit raise @parquet.ParquetError {
  let signed_physical = match column.physical_type() {
    @parquet.PhysicalType::Int32 | @parquet.PhysicalType::Int64 => true
    _ => false
  }
  if !column.is_flat() ||
    !signed_physical ||
    column.has_logical_type() ||
    column.converted_type() is Some(_) {
    raise @parquet.Unsupported(
      "scan_ge requires a flat, unannotated signed INT32 or INT64 column",
    )
  }
}

///|
fn can_match(
  group : @parquet.RowGroupMetadata,
  column : @parquet.ColumnChunkMetadata,
  threshold : Int64,
) -> Bool raise @parquet.ParquetError {
  if group.row_count() == 0L {
    return false
  }
  match column.signed_integer_statistics() {
    None => true
    Some(statistics) => {
      if statistics.null_count() == Some(group.row_count()) {
        return false
      }
      match statistics.max_value() {
        Some(upper) => upper >= threshold
        None => true
      }
    }
  }
}

///|
fn signed_value_at(
  data : @parquet.ParquetColumnData,
  row : Int32,
) -> Int64? raise @parquet.ParquetError {
  match data {
    @parquet.Int32Values(values) => Some(values[row].to_int64())
    @parquet.NullableInt32Values(values) => values[row].map(Int32::to_int64)
    @parquet.Int64Values(values) => Some(values[row])
    @parquet.NullableInt64Values(values) => values[row]
    @parquet.Values(values) =>
      match values[row] {
        @parquet.Value::Int32(value) => Some(value.to_int64())
        @parquet.Value::Int64(value) => Some(value)
        @parquet.Value::Null => None
        _ => raise @parquet.Unsupported("unexpected noninteger residual value")
      }
    _ => raise @parquet.Unsupported("unexpected residual column representation")
  }
}

///|
/// Execute `column >= threshold` using only the parquet package's public API.
/// Statistics select candidate groups; decoded values decide actual matches.
/// The full input Bytes are already in memory: this does not perform range I/O.
pub fn scan_ge(
  input : Bytes,
  column_path : Array[String],
  threshold : Int64,
) -> ScanResult raise @parquet.ParquetError {
  if column_path.is_empty() {
    raise @parquet.InvalidData("predicate column path must not be empty")
  }
  let metadata = @parquet.read_metadata(input)
  let groups = metadata.row_groups()
  if groups.is_empty() {
    raise @parquet.Unsupported("scan_ge requires row-group column metadata")
  }
  // Public metadata validates every chunk's schema position. Keep that index
  // because decoded display names may normalize the original schema spelling.
  let predicate_index = predicate_column_index(groups[0], column_path)
  let selected : Array[Int32] = []
  let file_offsets : Array[Int64] = []
  let mut file_offset = 0L
  for group in groups {
    file_offsets.push(file_offset)
    file_offset += group.row_count()
    let column = group.columns()[predicate_index]
    validate_signed_column(column)
    if can_match(group, column, threshold) {
      selected.push(group.index())
    }
  }
  let batch = @parquet.read_row_groups_columnar(input, selected)
  let predicate_data = batch.column_data()[predicate_index]
  let matching_rows : Array[Int32] = []
  let matching_file_rows : Array[Int64] = []
  let mut batch_row = 0
  for group_index in selected {
    let group = groups[group_index]
    for local_row in 0..<group.row_count().to_int() {
      if signed_value_at(predicate_data, batch_row) is Some(value) &&
        value >= threshold {
        matching_rows.push(batch_row)
        matching_file_rows.push(
          file_offsets[group_index] + local_row.to_int64(),
        )
      }
      batch_row += 1
    }
  }
  {
    batch,
    selected_row_groups: ReadOnlyArray::from_array(selected[:]),
    matching_rows: ReadOnlyArray::from_array(matching_rows[:]),
    matching_file_rows: ReadOnlyArray::from_array(matching_file_rows[:]),
  }
}
