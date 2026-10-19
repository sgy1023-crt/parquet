///|
pub(all) enum PhysicalType {
  Boolean
  Int32
  Int64
  Int96
  Float
  Double
  ByteArray
  FixedLenByteArray
  Unknown(Int32)
} derive(Eq, Debug)

///|
pub extend PhysicalType with Eq::{equal, not_equal}

///|
pub extend PhysicalType with @debug.Debug::{to_repr}

///|
pub(all) enum ColumnOrder {
  TypeDefined
  Unknown(Int32)
} derive(Eq, Debug)

///|
pub extend ColumnOrder with Eq::{equal, not_equal}

///|
pub extend ColumnOrder with @debug.Debug::{to_repr}

///|
fn read_column_order(reader : CompactReader) -> ColumnOrder raise ParquetError {
  reader.begin_struct()
  let mut order : ColumnOrder? = None
  let mut done = false
  while !done {
    match reader.read_field_begin() {
      None => {
        reader.end_struct()
        done = true
      }
      Some((id, wire)) => {
        if order is Some(_) {
          invalid_data("Multiple ColumnOrder union fields")
        }
        if id == 1 {
          expect_wire(wire, thrift_wire_struct)
          reader.skip(wire)
          order = Some(TypeDefined)
        } else {
          reader.skip(wire)
          order = Some(Unknown(id))
        }
      }
    }
  }
  match order {
    Some(value) => value
    None => raise ParquetError::InvalidData("Empty ColumnOrder union")
  }
}

///|
pub struct ParquetMetadata {
  groups : ReadOnlyArray[RowGroupMetadata]
  rows : Int64
  writer : String?
}

///|
pub struct RowGroupMetadata {
  group_index : Int32
  rows : Int64
  chunks : ReadOnlyArray[ColumnChunkMetadata]
  byte_size : Int64
  compressed_size : Int64?
  offset : Int64?
}

///|
pub struct ColumnChunkMetadata {
  path : ReadOnlyArray[String]
  type_code : Int32
  logical_type : Bool
  converted : Int32?
  flat : Bool
  raw_statistics : Statistics?
  values : Int64
  compressed_size : Int64
  uncompressed_size : Int64
  page_offset : Int64
  dictionary_offset : Int64?
  order : ColumnOrder?
}

///|
pub fn ParquetMetadata::row_groups(
  self : ParquetMetadata,
) -> ReadOnlyArray[RowGroupMetadata] {
  self.groups
}

///|
pub fn ParquetMetadata::row_group_count(self : ParquetMetadata) -> Int32 {
  self.groups.length()
}

///|
pub fn ParquetMetadata::row_count(self : ParquetMetadata) -> Int64 {
  self.rows
}

///|
pub fn ParquetMetadata::created_by(self : ParquetMetadata) -> String? {
  self.writer
}

///|
pub fn RowGroupMetadata::index(self : RowGroupMetadata) -> Int32 {
  self.group_index
}

///|
pub fn RowGroupMetadata::row_count(self : RowGroupMetadata) -> Int64 {
  self.rows
}

///|
pub fn RowGroupMetadata::columns(
  self : RowGroupMetadata,
) -> ReadOnlyArray[ColumnChunkMetadata] {
  self.chunks
}

///|
pub fn RowGroupMetadata::total_byte_size(self : RowGroupMetadata) -> Int64 {
  self.byte_size
}

///|
pub fn RowGroupMetadata::total_compressed_size(
  self : RowGroupMetadata,
) -> Int64? {
  self.compressed_size
}

///|
pub fn RowGroupMetadata::file_offset(self : RowGroupMetadata) -> Int64? {
  self.offset
}

///|
pub fn ColumnChunkMetadata::path_in_schema(
  self : ColumnChunkMetadata,
) -> ReadOnlyArray[String] {
  self.path
}

///|
pub fn ColumnChunkMetadata::physical_type(
  self : ColumnChunkMetadata,
) -> PhysicalType {
  match self.type_code {
    0 => Boolean
    1 => Int32
    2 => Int64
    3 => Int96
    4 => Float
    5 => Double
    6 => ByteArray
    7 => FixedLenByteArray
    value => Unknown(value)
  }
}

///|
pub fn ColumnChunkMetadata::statistics(
  self : ColumnChunkMetadata,
) -> Statistics? {
  self.raw_statistics
}

///|
pub fn ColumnChunkMetadata::has_logical_type(
  self : ColumnChunkMetadata,
) -> Bool {
  self.logical_type
}

///|
pub fn ColumnChunkMetadata::converted_type(
  self : ColumnChunkMetadata,
) -> Int32? {
  self.converted
}

///|
pub fn ColumnChunkMetadata::is_flat(self : ColumnChunkMetadata) -> Bool {
  self.flat
}

///|
pub fn ColumnChunkMetadata::column_order(
  self : ColumnChunkMetadata,
) -> ColumnOrder? {
  self.order
}

///|
pub fn ColumnChunkMetadata::num_values(self : ColumnChunkMetadata) -> Int64 {
  self.values
}

///|
pub fn ColumnChunkMetadata::total_compressed_size(
  self : ColumnChunkMetadata,
) -> Int64 {
  self.compressed_size
}

///|
pub fn ColumnChunkMetadata::total_uncompressed_size(
  self : ColumnChunkMetadata,
) -> Int64 {
  self.uncompressed_size
}

///|
pub fn ColumnChunkMetadata::data_page_offset(
  self : ColumnChunkMetadata,
) -> Int64 {
  self.page_offset
}

///|
pub fn ColumnChunkMetadata::dictionary_page_offset(
  self : ColumnChunkMetadata,
) -> Int64? {
  self.dictionary_offset
}

///|
fn parse_parquet_metadata(data : Bytes) -> FileMetaDataMeta raise ParquetError {
  check_magic(data)
  let footer_len = read_u32_le(data, data.length() - 8)
  if footer_len <= 0 || footer_len > data.length() - 12 {
    invalid_data("Invalid parquet footer length")
  }
  read_file_metadata(data, data.length() - 8 - footer_len, footer_len)
}

///|
fn validate_row_groups(
  metadata : FileMetaDataMeta,
  leaves : Array[LeafColumnMeta],
) -> Unit raise ParquetError {
  if metadata.column_orders is Some(orders) &&
    orders.length() != leaves.length() {
    invalid_data("Column order count does not match schema leaf count")
  }
  let mut rows = 0L
  for group in metadata.row_groups {
    if group.num_rows < 0L || group.num_rows > 9223372036854775807L - rows {
      invalid_data("Invalid row group row count")
    }
    rows += group.num_rows
    if group.columns.length() != leaves.length() {
      invalid_data("RowGroup column count does not match schema leaf count")
    }
    for i in 0..<leaves.length() {
      let chunk = group.columns[i].meta_data
      let leaf = leaves[i]
      if chunk.type_code != leaf.type_code || chunk.path_in_schema != leaf.path {
        invalid_data("Column chunk type or path does not match schema")
      }
      if leaf.path.length() == 1 &&
        leaf.max_repetition_level == 0 &&
        chunk.num_values != group.num_rows {
        invalid_data(
          "Flat column value count does not match row group row count",
        )
      }
    }
  }
  if rows != metadata.num_rows {
    invalid_data("File row count does not match row groups")
  }
}

///|
/// Inspect footer metadata without decoding column chunks. Byte input is still
/// the whole file; this API does not perform range I/O.
pub fn read_metadata(data : Bytes) -> ParquetMetadata raise ParquetError {
  let metadata = parse_parquet_metadata(data)
  let leaves = build_leaf_columns(metadata.schema)
  validate_row_groups(metadata, leaves)
  let groups = metadata.row_groups.mapi(fn(index, group) {
    let chunks = group.columns.mapi(fn(i, chunk) {
      let leaf = leaves[i]
      let meta = chunk.meta_data
      {
        path: ReadOnlyArray::from_array(meta.path_in_schema),
        type_code: meta.type_code,
        logical_type: leaf.has_logical_type,
        converted: leaf.converted_type,
        flat: leaf.path.length() == 1 && leaf.max_repetition_level == 0,
        raw_statistics: meta.statistics,
        values: meta.num_values,
        compressed_size: meta.total_compressed_size,
        uncompressed_size: meta.total_uncompressed_size,
        page_offset: meta.data_page_offset,
        dictionary_offset: meta.dictionary_page_offset,
        order: metadata.column_orders.map(orders => orders[i]),
      }
    })
    {
      group_index: index,
      rows: group.num_rows,
      chunks: ReadOnlyArray::from_array(chunks),
      byte_size: group.total_byte_size,
      compressed_size: group.total_compressed_size,
      offset: group.file_offset,
    }
  })
  {
    groups: ReadOnlyArray::from_array(groups),
    rows: metadata.num_rows,
    writer: metadata.created_by,
  }
}
