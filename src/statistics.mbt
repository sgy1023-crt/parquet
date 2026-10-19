///|
/// Raw footer statistics. Modern bounds and deprecated legacy bounds are kept
/// separately. A missing count or exactness flag remains `None`.
pub struct Statistics {
  maximum : Bytes?
  minimum : Bytes?
  legacy_maximum : Bytes?
  legacy_minimum : Bytes?
  nulls : Int64?
  distinct : Int64?
  maximum_exact : Bool?
  minimum_exact : Bool?
}

///|
pub fn Statistics::max_value(self : Statistics) -> Bytes? {
  self.maximum
}

///|
pub fn Statistics::min_value(self : Statistics) -> Bytes? {
  self.minimum
}

///|
pub fn Statistics::legacy_max(self : Statistics) -> Bytes? {
  self.legacy_maximum
}

///|
pub fn Statistics::legacy_min(self : Statistics) -> Bytes? {
  self.legacy_minimum
}

///|
pub fn Statistics::null_count(self : Statistics) -> Int64? {
  self.nulls
}

///|
pub fn Statistics::distinct_count(self : Statistics) -> Int64? {
  self.distinct
}

///|
pub fn Statistics::is_max_value_exact(self : Statistics) -> Bool? {
  self.maximum_exact
}

///|
pub fn Statistics::is_min_value_exact(self : Statistics) -> Bool? {
  self.minimum_exact
}

///|
fn expect_wire(actual : Int32, expected : Int32) -> Unit raise ParquetError {
  if actual != expected {
    invalid_data("Invalid metadata field wire type")
  }
}

///|
fn read_statistics(reader : CompactReader) -> Statistics raise ParquetError {
  reader.begin_struct()
  let mut maximum : Bytes? = None
  let mut minimum : Bytes? = None
  let mut legacy_maximum : Bytes? = None
  let mut legacy_minimum : Bytes? = None
  let mut nulls : Int64? = None
  let mut distinct : Int64? = None
  let mut maximum_exact : Bool? = None
  let mut minimum_exact : Bool? = None
  let mut done = false
  while !done {
    match reader.read_field_begin() {
      None => {
        reader.end_struct()
        done = true
      }
      Some((id, wire)) =>
        match id {
          1 | 2 | 5 | 6 => {
            expect_wire(wire, thrift_wire_binary)
            let value = Some(reader.read_binary().to_owned())
            match id {
              1 => legacy_maximum = value
              2 => legacy_minimum = value
              5 => maximum = value
              _ => minimum = value
            }
          }
          3 | 4 => {
            expect_wire(wire, thrift_wire_i64)
            let value = reader.read_i64()
            if value < 0L {
              invalid_data("Negative statistics count")
            }
            if id == 3 {
              nulls = Some(value)
            } else {
              distinct = Some(value)
            }
          }
          7 | 8 => {
            expect_wire(wire, thrift_wire_bool)
            let value = Some(reader.read_bool())
            if id == 7 {
              maximum_exact = value
            } else {
              minimum_exact = value
            }
          }
          _ => reader.skip(wire)
        }
    }
  }
  {
    maximum,
    minimum,
    legacy_maximum,
    legacy_minimum,
    nulls,
    distinct,
    maximum_exact,
    minimum_exact,
  }
}

///|
/// Signed physical integer bounds. They may be conservative bounds rather than
/// observed extrema, even when the writer omits the exactness flags.
pub struct SignedIntegerStatistics {
  minimum : Int64?
  maximum : Int64?
  nulls : Int64?
}

///|
pub fn SignedIntegerStatistics::min_value(
  self : SignedIntegerStatistics,
) -> Int64? {
  self.minimum
}

///|
pub fn SignedIntegerStatistics::max_value(
  self : SignedIntegerStatistics,
) -> Int64? {
  self.maximum
}

///|
pub fn SignedIntegerStatistics::null_count(
  self : SignedIntegerStatistics,
) -> Int64? {
  self.nulls
}

///|
fn signed_bound(value : Bytes?, type_code : Int32) -> Int64? raise ParquetError {
  match value {
    None => None
    Some(bytes) => {
      let width = if type_code == parquet_type_int32 { 4 } else { 8 }
      if bytes.length() != width {
        invalid_data("Invalid signed integer statistics bound length")
      }
      Some(
        if width == 4 {
          read_i32_le(bytes, 0).to_int64()
        } else {
          read_i64_le(bytes, 0)
        },
      )
    }
  }
}

///|
/// Only flat, unannotated INT32/INT64 have validated signed semantics here.
/// Missing/unknown column order disables bounds, but preserves a known null count.
/// Legacy bounds are never substituted. `exact=false` still permits safe bounds.
pub fn ColumnChunkMetadata::signed_integer_statistics(
  self : ColumnChunkMetadata,
) -> SignedIntegerStatistics? raise ParquetError {
  if !self.is_flat() ||
    self.logical_type ||
    self.converted is Some(_) ||
    (
      self.type_code != parquet_type_int32 &&
      self.type_code != parquet_type_int64
    ) {
    return None
  }
  match self.raw_statistics {
    None => None
    Some(stats) => {
      let use_bounds = self.order is Some(TypeDefined)
      let minimum = if use_bounds {
        signed_bound(stats.minimum, self.type_code)
      } else {
        None
      }
      let maximum = if use_bounds {
        signed_bound(stats.maximum, self.type_code)
      } else {
        None
      }
      if minimum is Some(lo) && maximum is Some(hi) && lo > hi {
        invalid_data("Reversed signed integer statistics bounds")
      }
      Some({ minimum, maximum, nulls: stats.nulls, })
    }
  }
}
