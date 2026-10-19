///|
fn statistics_fixture(name : String) -> @parquet.ParquetMetadata raise {
  @parquet.read_metadata(
    @fs.read_file_to_bytes("fixtures/row-groups/" + name + ".parquet"),
  )
}

///|
test "signed statistics preserve negative values and all-null groups" {
  let groups = statistics_fixture("base").row_groups()
  let first = groups[0].columns()[0].signed_integer_statistics().unwrap()
  assert_eq(first.min_value(), Some(-20L))
  assert_eq(first.max_value(), Some(-17L))
  assert_eq(first.null_count(), Some(1L))
  let all_null = groups[3].columns()[0].signed_integer_statistics().unwrap()
  assert_eq(all_null.min_value(), None)
  assert_eq(all_null.max_value(), None)
  assert_eq(all_null.null_count(), Some(4L))
}

///|
test "missing statistics and missing optional counts stay distinct" {
  let absent = statistics_fixture("no_statistics").row_groups()[0].columns()[0]
  assert_true(absent.statistics() is None)
  assert_true(absent.signed_integer_statistics() is None)
  let missing = statistics_fixture("missing_null_count").row_groups()[0].columns()[0]
  assert_eq(missing.statistics().unwrap().null_count(), None)
  assert_eq(missing.statistics().unwrap().distinct_count(), None)
  assert_eq(missing.signed_integer_statistics().unwrap().null_count(), None)
  assert_eq(
    missing.signed_integer_statistics().unwrap().min_value(),
    Some(-20L),
  )
}

///|
test "legacy bounds remain raw and are never substituted for modern bounds" {
  let column = statistics_fixture("legacy_only").row_groups()[0].columns()[0]
  let raw = column.statistics().unwrap()
  assert_true(raw.legacy_min() is Some(_))
  assert_true(raw.legacy_max() is Some(_))
  assert_eq(raw.min_value(), None)
  assert_eq(raw.max_value(), None)
  assert_eq(raw.is_min_value_exact(), None)
  assert_eq(raw.is_max_value_exact(), None)
  let signed = column.signed_integer_statistics().unwrap()
  assert_eq(signed.min_value(), None)
  assert_eq(signed.max_value(), None)
  assert_eq(signed.null_count(), Some(1L))
}

///|
test "missing and unknown column order suppress bounds but keep null count" {
  for name in ["missing_column_orders", "unknown_column_order"] {
    let column = statistics_fixture(name).row_groups()[0].columns()[0]
    assert_true(column.statistics().unwrap().min_value() is Some(_))
    let signed = column.signed_integer_statistics().unwrap()
    assert_eq(signed.min_value(), None)
    assert_eq(signed.max_value(), None)
    assert_eq(signed.null_count(), Some(1L))
  }
  assert_true(
    statistics_fixture("missing_column_orders").row_groups()[0].columns()[0].column_order()
    is None,
  )
  assert_eq(
    statistics_fixture("unknown_column_order").row_groups()[0].columns()[0].column_order(),
    Some(@parquet.ColumnOrder::Unknown(42)),
  )
}

///|
test "inexact modern bounds remain usable conservative signed bounds" {
  let column = statistics_fixture("inexact_wide_bounds").row_groups()[2].columns()[0]
  let raw = column.statistics().unwrap()
  assert_eq(raw.is_min_value_exact(), Some(false))
  assert_eq(raw.is_max_value_exact(), Some(false))
  let signed = column.signed_integer_statistics().unwrap()
  assert_eq(signed.min_value(), Some(99L))
  assert_eq(signed.max_value(), Some(104L))
}

///|
test "modern single-sided bounds remain independently usable" {
  let minimum = statistics_fixture("min_only").row_groups()[0].columns()[0]
    .signed_integer_statistics()
    .unwrap()
  assert_eq(minimum.min_value(), Some(-20L))
  assert_eq(minimum.max_value(), None)
  let maximum = statistics_fixture("max_only").row_groups()[0].columns()[0]
    .signed_integer_statistics()
    .unwrap()
  assert_eq(maximum.min_value(), None)
  assert_eq(maximum.max_value(), Some(-17L))
}

///|
test "unsupported physical and annotated logical types have no signed view" {
  for
    name in [
      "unsupported_float", "unsupported_string", "unsupported_uint32", "unsupported_uint64",
      "unsupported_decimal", "unsupported_date",
    ] {
    for group in statistics_fixture(name).row_groups() {
      assert_true(group.columns()[0].signed_integer_statistics() is None)
    }
  }
}

///|
test "negative and excessive statistics counts fail explicitly" {
  for
    name in [
      "negative_null_count", "excess_null_count", "negative_distinct_count",
    ] {
    let failed = try statistics_fixture(name) catch {
      @parquet.InvalidData(_) => true
      err => raise err
    } noraise {
      _ => false
    }
    assert_true(failed)
  }
}

///|
test "invalid signed bounds fail even for an all-null group" {
  for
    (name, group, column) in [
      ("bad_i32_bound_length", 0, 0),
      ("bad_i64_bound_length", 0, 1),
      ("all_null_bad_i32_bound_length", 3, 0),
      ("reversed_bounds", 0, 0),
    ] {
    let chunk = statistics_fixture(name).row_groups()[group].columns()[column]
    let failed = try chunk.signed_integer_statistics() catch {
      @parquet.InvalidData(_) => true
      err => raise err
    } noraise {
      _ => false
    }
    assert_true(failed)
  }
}

///|
test "invalid footer inputs raise errors instead of successful empty metadata" {
  for
    name in [
      "bad_footer_magic", "bad_footer_length", "truncated_footer", "truncated_file",
    ] {
    let failed = try statistics_fixture(name) catch {
      @parquet.InvalidData(_) => true
      err => raise err
    } noraise {
      _ => false
    }
    assert_true(failed)
  }
}

///|
test "metadata sizes offsets and immutable collections describe real chunks" {
  let metadata = statistics_fixture("base")
  let group = metadata.row_groups()[0]
  let column = group.columns()[0]
  assert_true(group.total_byte_size() > 0L)
  assert_true(group.total_compressed_size().unwrap() > 0L)
  assert_true(column.data_page_offset() >= 4L)
  assert_true(column.total_uncompressed_size() > 0L)
  assert_true(column.total_compressed_size() > 0L)
  assert_eq(column.num_values(), 4L)
  let copy = column.path_in_schema().iter().collect()
  copy[0] = "changed by consumer"
  assert_eq(column.path_in_schema()[0], "i32")
  assert_eq(metadata.row_groups()[0].columns()[0].path_in_schema()[0], "i32")
}
