///|
test "Compact statistics preserve true false absent flags and unknown fields" {
  // field 3 null_count=0, field 4 distinct_count=2, fields 7=true/8=false,
  // unknown field 9 i32=1, STOP. Booleans live in Compact field headers.
  let stats = read_statistics(
    CompactReader::new(b"\x36\x00\x16\x04\x31\x12\x15\x02\x00", 0),
  )
  assert_eq(stats.null_count(), Some(0L))
  assert_eq(stats.distinct_count(), Some(2L))
  assert_eq(stats.is_max_value_exact(), Some(true))
  assert_eq(stats.is_min_value_exact(), Some(false))
  let empty = read_statistics(CompactReader::new(b"\x00", 0))
  assert_eq(empty.null_count(), None)
  assert_eq(empty.is_max_value_exact(), None)
  assert_eq(empty.is_min_value_exact(), None)
}

///|
test "Compact statistics reject wrong field wire types and truncated values" {
  for data in [b"\x35\x00\x00", b"\x75\x00\x00", b"\x58\x08\x01"] {
    let failed = try read_statistics(CompactReader::new(data, 0)) catch {
      ParquetError::InvalidData(_) => true
      err => raise err
    } noraise {
      _ => false
    }
    assert_true(failed)
  }
}

///|
test "Compact lengths reject values that truncate to a small Int" {
  // Unsigned varint 2^32 used as a binary length must not wrap to zero.
  let failed = try
    CompactReader::new(b"\x80\x80\x80\x80\x10", 0).read_binary()
  catch {
    ParquetError::InvalidData(_) => true
    err => raise err
  } noraise {
    _ => false
  }
  assert_true(failed)
}

///|
test "Compact unsigned varints reject an overflowing tenth byte" {
  let failed = try
    CompactReader::new(b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\x02", 0).read_varint64()
  catch {
    ParquetError::InvalidData(_) => true
    err => raise err
  } noraise {
    _ => false
  }
  assert_true(failed)
}

///|
test "Compact ensure rejects Int overflow in an external length" {
  let failed = try CompactReader::new(b"\x00", 1).ensure(2147483647) catch {
    ParquetError::InvalidData(_) => true
    err => raise err
  } noraise {
    _ => false
  }
  assert_true(failed)
}

///|
test "column order unions reject empty or multiple alternatives" {
  for data in [b"\x00", b"\x1c\x00\x1c\x00\x00"] {
    let failed = try read_column_order(CompactReader::new(data, 0)) catch {
      ParquetError::InvalidData(_) => true
      err => raise err
    } noraise {
      _ => false
    }
    assert_true(failed)
  }
}

///|
test "signed PLAIN bounds preserve complete Int32 and Int64 ranges" {
  assert_eq(
    signed_bound(Some(b"\x00\x00\x00\x80"), parquet_type_int32),
    Some(-2147483648L),
  )
  assert_eq(
    signed_bound(Some(b"\xff\xff\xff\x7f"), parquet_type_int32),
    Some(2147483647L),
  )
  assert_eq(
    signed_bound(Some(b"\x00\x00\x00\x00\x00\x00\x00\x80"), parquet_type_int64),
    Some(-9223372036854775808L),
  )
  assert_eq(
    signed_bound(Some(b"\xff\xff\xff\xff\xff\xff\xff\x7f"), parquet_type_int64),
    Some(9223372036854775807L),
  )
}
