///|
/// Read a parquet document from bytes.
pub fn read_bytes(data : Bytes) -> ParquetFile raise ParquetError {
  decode_parquet(data)
}

///|
/// Read a parquet document from bytes without row materialization.
pub fn read_bytes_columnar(
  data : Bytes,
) -> ParquetColumnarFile raise ParquetError {
  decode_parquet_columnar(data)
}

///|
/// Decode one row group by its zero-based file index.
pub fn read_row_group_columnar(
  data : Bytes,
  index : Int32,
) -> ParquetColumnarFile raise ParquetError {
  decode_parquet_columnar(data, selected_groups=[index])
}

///|
/// Decode only the requested row groups, in caller order. Duplicate or invalid
/// indices are errors, checked before decoding. An empty selection keeps schema.
pub fn read_row_groups_columnar(
  data : Bytes,
  indices : Array[Int32],
) -> ParquetColumnarFile raise ParquetError {
  decode_parquet_columnar(data, selected_groups=indices)
}

///|
/// Encode a parquet document to bytes.
///
/// The current writer supports flat schemas of `Int32`, `Int64`, `String`,
/// and `Binary`, with `Required` or `Optional` repetition.
pub fn write_bytes(file : ParquetFile) -> Bytes raise ParquetError {
  encode_parquet(file)
}
