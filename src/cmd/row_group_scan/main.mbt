///|
/// JS env.args includes the runtime executable before the script name.
#cfg(target="js")
fn cli_args() -> Array[String] {
  @env.args()[1:].to_owned()
}

///|
#cfg(not(target="js"))
fn cli_args() -> Array[String] {
  @env.args()
}

///|
fn run(args : Array[String]) -> Unit raise {
  if args.length() != 1 && args.length() != 4 {
    abort(
      "usage: moon run src/cmd/row_group_scan --target js -- [path column threshold]",
    )
  }
  let path = if args.length() == 1 {
    "fixtures/row-groups/base.parquet"
  } else {
    args[1]
  }
  let column = if args.length() == 1 { "i32" } else { args[2] }
  let threshold = if args.length() == 1 {
    100L
  } else {
    @string.parse_int64(args[3], base=10)
  }
  let input = @fs.read_file_to_bytes(path)
  let result = @scan.scan_ge(input, [column], threshold)
  println("predicate: \{column} >= \{threshold}")
  println("selected_row_groups: \{@debug.Repr(result.selected_row_groups())}")
  println("decoded_rows: \{result.batch().row_count()}")
  println("matching_rows_in_batch: \{@debug.Repr(result.matching_rows())}")
  println("matching_rows_in_file: \{@debug.Repr(result.matching_file_rows())}")
  println("matching_row_count: \{result.matching_row_count()}")
  println("columnar_batch: \{result.batch()}")
  println("column_data: \{@debug.Repr(result.batch().column_data())}")
}

///|
fn main {
  try! run(cli_args())
}
