///|
fn fixture(name : String) -> Bytes raise {
  @fs.read_file_to_bytes("fixtures/row-groups/" + name + ".parquet")
}

///|
fn[T] copied(values : ReadOnlyArray[T]) -> Array[T] {
  values.iter().collect()
}

///|
test "external consumer prunes groups and retains the columnar batch" {
  let result = @row_group_scan.scan_ge(fixture("base"), ["i32"], 100L)
  assert_eq(copied(result.selected_row_groups()), [2])
  assert_eq(result.batch().row_count(), 4)
  assert_eq(result.batch().columns().length(), 2)
  assert_eq(copied(result.matching_rows()), [0, 1, 2, 3])
  assert_eq(copied(result.matching_file_rows()), [8L, 9L, 10L, 11L])
  assert_eq(result.matching_row_count(), 4)
  assert_eq(
    result.batch().column_data()[0],
    @parquet.Int32Values([100, 101, 102, 103]),
  )
}

///|
test "residual filtering removes false positives inside a retained group" {
  let result = @row_group_scan.scan_ge(fixture("base"), ["i32"], 102L)
  assert_eq(copied(result.selected_row_groups()), [2])
  assert_eq(result.batch().row_count(), 4)
  assert_eq(copied(result.matching_rows()), [2, 3])
  assert_eq(copied(result.matching_file_rows()), [10L, 11L])
  assert_eq(result.matching_row_count(), 2)
}

///|
test "missing statistics conservatively retains every nonempty group" {
  let result = @row_group_scan.scan_ge(fixture("no_statistics"), ["i32"], 102L)
  assert_eq(copied(result.selected_row_groups()), [0, 1, 2, 3])
  assert_eq(result.batch().row_count(), 16)
  assert_eq(copied(result.matching_rows()), [10, 11])
  assert_eq(copied(result.matching_file_rows()), [10L, 11L])
}

///|
test "signed Int64 filtering stays exact beyond JavaScript number precision" {
  let result = @row_group_scan.scan_ge(
    fixture("base"),
    ["i64"],
    9007199254740995L,
  )
  assert_eq(copied(result.selected_row_groups()), [2])
  assert_eq(copied(result.matching_rows()), [1, 2, 3])
  assert_eq(copied(result.matching_file_rows()), [9L, 10L, 11L])
  assert_eq(result.matching_row_count(), 3)
}

///|
test "empty selection retains schema and has no matching rows" {
  let result = @row_group_scan.scan_ge(fixture("base"), ["i32"], 104L)
  assert_eq(copied(result.selected_row_groups()), [])
  assert_eq(result.batch().row_count(), 0)
  assert_eq(result.batch().columns().length(), 2)
  assert_eq(copied(result.matching_rows()), [])
  assert_eq(copied(result.matching_file_rows()), [])
  assert_eq(result.matching_row_count(), 0)
}

///|
test "consumer rejects a nonexistent predicate column" {
  try @row_group_scan.scan_ge(fixture("base"), ["missing"], 0L) catch {
    @parquet.InvalidData(_) => ()
    error => fail("unexpected error: \{error}")
  } noraise {
    _ => fail("expected an explicit missing-column error")
  }
}

///|
test "consumer rejects an empty predicate path" {
  try @row_group_scan.scan_ge(fixture("base"), [], 0L) catch {
    @parquet.InvalidData(_) => ()
    error => fail("unexpected error: \{error}")
  } noraise {
    _ => fail("expected an explicit empty-path error")
  }
}

///|
test "unsupported predicate type fails explicitly" {
  let bytes = @parquet.write_bytes(
    @parquet.new_parquet_file(
      [@parquet.new_column("name", @parquet.String, @parquet.Required)],
      [[@parquet.Value::String("alice")]],
      None,
    ),
  )
  try @row_group_scan.scan_ge(bytes, ["name"], 0L) catch {
    @parquet.Unsupported(_) => ()
    error => fail("unexpected error: \{error}")
  } noraise {
    _ => fail("expected an explicit unsupported-column error")
  }
}

///|
test "matching file positions span selected groups and exclude NULL rows" {
  let result = @row_group_scan.scan_ge(fixture("base"), ["i32"], 0L)
  assert_eq(copied(result.selected_row_groups()), [1, 2])
  assert_eq(result.batch().row_count(), 8)
  assert_eq(copied(result.matching_rows()), [0, 1, 3, 4, 5, 6, 7])
  assert_eq(copied(result.matching_file_rows()), [4L, 5L, 7L, 8L, 9L, 10L, 11L])
  assert_eq(result.matching_row_count(), 7)
}

///|
test "unknown ordering retains bounds candidates but can still prune all NULL" {
  for name in ["missing_column_orders", "unknown_column_order", "legacy_only"] {
    let result = @row_group_scan.scan_ge(fixture(name), ["i32"], 102L)
    assert_eq(copied(result.selected_row_groups()), [0, 1, 2])
    assert_eq(result.batch().row_count(), 12)
    assert_eq(copied(result.matching_rows()), [10, 11])
    assert_eq(copied(result.matching_file_rows()), [10L, 11L])
  }
}

///|
test "unknown NULL count retains a group with no nonnull bounds" {
  let result = @row_group_scan.scan_ge(
    fixture("missing_null_count"),
    ["i32"],
    102L,
  )
  assert_eq(copied(result.selected_row_groups()), [2, 3])
  assert_eq(result.batch().row_count(), 8)
  assert_eq(copied(result.matching_rows()), [2, 3])
  assert_eq(copied(result.matching_file_rows()), [10L, 11L])
}

///|
test "inexact conservative bound is followed by residual filtering" {
  let result = @row_group_scan.scan_ge(
    fixture("inexact_wide_bounds"),
    ["i32"],
    104L,
  )
  assert_eq(copied(result.selected_row_groups()), [2])
  assert_eq(result.batch().row_count(), 4)
  assert_eq(result.matching_row_count(), 0)
}

///|
test "skipped poisoned page is never decoded by the consumer" {
  let result = @row_group_scan.scan_ge(fixture("poison_skipped"), ["i32"], 100L)
  assert_eq(copied(result.selected_row_groups()), [2])
  assert_eq(result.batch().row_count(), 4)
  assert_eq(copied(result.matching_file_rows()), [8L, 9L, 10L, 11L])
}

///|
test "zero row group yields an empty schema preserving batch" {
  let result = @row_group_scan.scan_ge(fixture("zero_rows"), ["i32"], 0L)
  assert_eq(copied(result.selected_row_groups()), [])
  assert_eq(result.batch().row_count(), 0)
  assert_eq(result.batch().columns().length(), 2)
  assert_eq(result.matching_row_count(), 0)
}

///|
test "consumer rejects unsigned and logical integer annotations" {
  for
    name in [
      "unsupported_uint32", "unsupported_uint64", "unsupported_decimal", "unsupported_date",
    ] {
    let input = fixture(name)
    let path = copied(
      @parquet.read_metadata(input).row_groups()[0].columns()[0].path_in_schema(),
    )
    try @row_group_scan.scan_ge(input, path, 0L) catch {
      @parquet.Unsupported(_) => ()
      error => fail("unexpected error for \{name}: \{error}")
    } noraise {
      _ => fail("expected explicit unsupported-column error for \{name}")
    }
  }
}

///|
test "malformed predicate statistics propagate an error" {
  for
    name in [
      "bad_i32_bound_length", "negative_null_count", "excess_null_count", "reversed_bounds",
    ] {
    try @row_group_scan.scan_ge(fixture(name), ["i32"], 100L) catch {
      @parquet.InvalidData(_) => ()
      error => fail("unexpected error for \{name}: \{error}")
    } noraise {
      _ => fail("expected an explicit malformed-statistics error for \{name}")
    }
  }
}

///|
test "predicate path uses original schema spelling rather than normalized names" {
  let input = @parquet.write_bytes(
    @parquet.new_parquet_file(
      [@parquet.new_column(" a.b: ", @parquet.Int32, @parquet.Optional)],
      [
        [@parquet.Value::Int32(1)],
        [@parquet.Value::Int32(3)],
        [@parquet.Value::Null],
      ],
      None,
    ),
  )
  let result = @row_group_scan.scan_ge(input, [" a.b: "], 2L)
  assert_eq(copied(result.selected_row_groups()), [0])
  assert_eq(result.batch().row_count(), 3)
  assert_eq(copied(result.matching_rows()), [1])
  assert_eq(copied(result.matching_file_rows()), [1L])
}
