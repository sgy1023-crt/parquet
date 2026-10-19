///|
fn group_fixture(name : String) -> Bytes raise {
  @fs.read_file_to_bytes("fixtures/row-groups/" + name + ".parquet")
}

///|
test "metadata inspection does not read data pages" {
  let metadata = @parquet.read_metadata(group_fixture("poison_skipped"))
  assert_eq(metadata.row_count(), 16L)
  assert_eq(metadata.row_group_count(), 4)
  let group = metadata.row_groups()[2]
  assert_eq(group.index(), 2)
  assert_eq(group.row_count(), 4L)
  let column = group.columns()[1]
  assert_eq(column.path_in_schema()[0], "i64")
  let stats = column.signed_integer_statistics().unwrap()
  assert_eq(stats.min_value(), Some(9007199254740993L))
  assert_eq(stats.max_value(), Some(9007199254740999L))
  assert_eq(stats.null_count(), Some(0L))
}

///|
test "selective reads preserve caller order and existing batch API" {
  let bytes = group_fixture("base")
  let batch = @parquet.read_row_groups_columnar(bytes, [2, 0])
  assert_eq(batch.row_count(), 8)
  assert_eq(batch.column_values()[0], [
    @parquet.Int32(100),
    @parquet.Int32(101),
    @parquet.Int32(102),
    @parquet.Int32(103),
    @parquet.Int32(-20),
    @parquet.Int32(-19),
    @parquet.Null,
    @parquet.Int32(-17),
  ])
  let single = @parquet.read_row_group_columnar(bytes, 2)
  assert_eq(single.row_count(), 4)
  let full = @parquet.read_bytes_columnar(bytes)
  let all = @parquet.read_row_groups_columnar(bytes, [0, 1, 2, 3])
  assert_eq(all.column_values(), full.column_values())
  assert_eq(all.columns(), full.columns())
  assert_eq(all.created_by(), full.created_by())
}

///|
test "empty selection keeps schema without decoding poisoned pages" {
  let batch = @parquet.read_row_groups_columnar(
    group_fixture("poison_skipped"),
    [],
  )
  assert_eq(batch.row_count(), 0)
  assert_eq(batch.columns().length(), 2)
  assert_eq(batch.column_values(), [[], []])
}

///|
test "skipped poisoned group proves no decode then filter" {
  let bytes = group_fixture("poison_skipped")
  assert_eq(@parquet.read_row_group_columnar(bytes, 2).row_count(), 4)
  let failed = try @parquet.read_bytes_columnar(bytes) catch {
    @parquet.ParquetError::InvalidData(_) => true
    err => raise err
  } noraise {
    _ => false
  }
  assert_true(failed)
}

///|
test "all requested indices are validated before the first decoder" {
  let bytes = group_fixture("poison_skipped")
  for indices in [[0, 4], [0, -1], [0, 0]] {
    let message = try @parquet.read_row_groups_columnar(bytes, indices) catch {
      @parquet.ParquetError::InvalidData(message) => message
      err => raise err
    } noraise {
      _ => "unexpected success"
    }
    assert_true(message.contains("row group index"))
  }
}

///|
test "schema chunk and column ordering mismatches fail even for empty selection" {
  for
    name in [
      "schema_path_mismatch", "schema_type_mismatch", "column_order_count_mismatch",
    ] {
    let bytes = group_fixture(name)
    let metadata_failed = try @parquet.read_metadata(bytes) catch {
      @parquet.InvalidData(_) => true
      err => raise err
    } noraise {
      _ => false
    }
    assert_true(metadata_failed)
    let empty_failed = try @parquet.read_row_groups_columnar(bytes, []) catch {
      @parquet.InvalidData(_) => true
      err => raise err
    } noraise {
      _ => false
    }
    assert_true(empty_failed)
  }
}

///|
test "large metadata is inspectable but selected row overflow fails before poison decode" {
  let bytes = group_fixture("selected_row_count_overflow")
  assert_eq(@parquet.read_metadata(bytes).row_count(), 2147483660L)
  assert_eq(@parquet.read_row_groups_columnar(bytes, []).row_count(), 0)
  let message = try @parquet.read_row_group_columnar(bytes, 0) catch {
    @parquet.InvalidData(message) => message
    err => raise err
  } noraise {
    _ => "unexpected success"
  }
  assert_eq(message, "Selected row count exceeds columnar batch Int capacity")
}
