///|
extern "js" fn conversion_fixture() -> ArrowTable =
  #|() => ({
  #|  schema: { fields: ["null", "empty", "text", "bool", "big", "nan", "pos", "neg", "json", "missing"].map(name => ({ name })) },
  #|  toArray: () => [{ toJSON: () => ({
  #|    null: null, empty: "", text: "日历\nmoon", bool: false,
  #|    big: 9223372036854775807n, nan: NaN, pos: Infinity, neg: -Infinity,
  #|    json: { value: 7 }
  #|  }) }]
  #|})

///|
test "Arrow conversion retains null bitmap and exact scalar text" {
  let result = arrow_to_playground_table(conversion_fixture())
  assert_eq(result.columns, [
    "null", "empty", "text", "bool", "big", "nan", "pos", "neg", "json", "missing",
  ])
  assert_eq(result.rows, [
    [
      "", "", "日历\nmoon", "false", "9223372036854775807", "nan", "inf", "-inf",
      "{\"value\":7}", "",
    ],
  ])
  assert_eq(result.nulls, [
    [true, false, false, false, false, false, false, false, false, true],
  ])
}

///|
extern "js" fn empty_conversion_fixture() -> ArrowTable =
  #|() => ({ schema: { fields: [{ name: "id" }] }, toArray: () => [] })

///|
test "Arrow conversion retains schema for an empty query result" {
  let result = arrow_to_playground_table(empty_conversion_fixture())
  assert_eq(result.columns, ["id"])
  assert_eq(result.rows, [])
  assert_eq(result.nulls, [])
}

///|
extern "js" fn inferred_columns_fixture() -> ArrowTable =
  #|() => ({ toArray: () => [{ toJSON: () => ({ id: 42, value: "Infinity" }) }] })

///|
test "Arrow conversion infers missing schema without rewriting string values" {
  let result = arrow_to_playground_table(inferred_columns_fixture())
  assert_eq(result.columns, ["id", "value"])
  assert_eq(result.rows, [["42", "Infinity"]])
  assert_eq(result.nulls, [[false, false]])
}
