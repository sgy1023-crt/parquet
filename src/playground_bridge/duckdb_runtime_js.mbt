///|
#external
priv type WasmConnection

///|
#external
priv type ArrowTable

///|
extern "js" fn js_clone_bytes(bytes : Bytes) -> Bytes =
  #|(bytes) => new Uint8Array(bytes)

///|
extern "js" fn js_connect_local_wasm(
  on_ok : (WasmConnection) -> Unit,
  on_err : (String) -> Unit,
) -> Unit =
  #|(on_ok, on_err) => {
  #|  const toError = (err) => err && err.message ? err.message : String(err);
  #|  const run = async () => {
  #|    const duckdb = await import("@duckdb/duckdb-wasm");
  #|    const mvpWorker = (await import("@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url")).default;
  #|    const ehWorker = (await import("@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url")).default;
  #|    const mvpModule = (await import("@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url")).default;
  #|    const ehModule = (await import("@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url")).default;
  #|    const bundle = await duckdb.selectBundle({
  #|      mvp: { mainModule: mvpModule, mainWorker: mvpWorker },
  #|      eh: { mainModule: ehModule, mainWorker: ehWorker },
  #|    });
  #|    const logger = new duckdb.ConsoleLogger();
  #|    const worker = new Worker(bundle.mainWorker);
  #|    const db = new duckdb.AsyncDuckDB(logger, worker);
  #|    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  #|    const conn = await db.connect();
  #|    on_ok({ kind: "wasm", db, conn, worker });
  #|  };
  #|  run().catch((err) => on_err(toError(err)));
  #|}

///|
extern "js" fn js_register_file_buffer(
  conn : WasmConnection,
  file_name : String,
  bytes : Bytes,
  on_ok : () -> Unit,
  on_err : (String) -> Unit,
) -> Unit =
  #|(conn, file_name, bytes, on_ok, on_err) => {
  #|  const toError = (err) => err && err.message ? err.message : String(err);
  #|  const run = async () => {
  #|    if (!conn || conn.kind !== "wasm" || !conn.db) {
  #|      throw new Error("registerFileBuffer requires DuckDB WASM backend");
  #|    }
  #|    if (typeof conn.db.dropFile === "function") {
  #|      try {
  #|        await conn.db.dropFile(file_name);
  #|      } catch (_) {
  #|      }
  #|    }
  #|    await conn.db.registerFileBuffer(file_name, bytes);
  #|    on_ok();
  #|  };
  #|  run().catch((err) => on_err(toError(err)));
  #|}

///|
fn register_file_buffer(
  conn : WasmConnection,
  file_name : String,
  bytes : Bytes,
  on_done : (Result[Unit, String]) -> Unit,
) -> Unit {
  js_register_file_buffer(
    conn,
    file_name,
    js_clone_bytes(bytes),
    fn() { on_done(Ok(())) },
    fn(message) { on_done(Err(message)) },
  )
}

///|
fn connect_local_wasm(
  on_done : (Result[WasmConnection, String]) -> Unit,
) -> Unit {
  js_connect_local_wasm(fn(conn) { on_done(Ok(conn)) }, fn(message) {
    on_done(Err(message))
  })
}

///|
extern "js" fn js_query(
  conn : WasmConnection,
  sql : String,
  on_ok : (ArrowTable) -> Unit,
  on_err : (String) -> Unit,
) -> Unit =
  #|(conn, sql, on_ok, on_err) => {
  #|  const run = async () => on_ok(await conn.conn.query(sql));
  #|  run().catch(err => on_err(err && err.message ? err.message : String(err)));
  #|}

///|
// DuckDB's Arrow values cross the JS boundary as FixedArray; public tables keep
// their existing growable Array representation, including the separate null map.
// Scalar conversion preserves mizchi/duckdb 0.6.4's Apache-2.0 JS/WASM behavior.
// Adapted from duckdb.mbt ab32b92d9102d2549156a83cf3e3a8ea09356402,
// src/duckdb_js.mbt: only the WASM query/close and Arrow conversion paths remain.
extern "js" fn js_convert_arrow_table(
  table : ArrowTable,
  make_table : (
    FixedArray[String],
    FixedArray[FixedArray[String]],
    FixedArray[FixedArray[Bool]],
  ) -> PlaygroundTable,
) -> PlaygroundTable =
  #|(table, make_table) => {
  #|  const toCell = value => {
  #|    if (value === null || value === undefined) return ["", true];
  #|    if (typeof value === "string") return [value, false];
  #|    if (typeof value === "number") {
  #|      if (Number.isNaN(value)) return ["nan", false];
  #|      if (value === Infinity) return ["inf", false];
  #|      if (value === -Infinity) return ["-inf", false];
  #|      return [String(value), false];
  #|    }
  #|    if (typeof value === "boolean" || typeof value === "bigint") return [String(value), false];
  #|    return [JSON.stringify(value), false];
  #|  };
  #|  let columns = table.schema && table.schema.fields ? table.schema.fields.map(field => field.name) : [];
  #|  const rowObjects = table.toArray().map(row => row.toJSON());
  #|  if (columns.length === 0 && rowObjects.length > 0) columns = Object.keys(rowObjects[0]);
  #|  const rows = [];
  #|  const nulls = [];
  #|  for (const row of rowObjects) {
  #|    const values = [];
  #|    const rowNulls = [];
  #|    for (const name of columns) {
  #|      const cell = toCell(row[name]);
  #|      values.push(cell[0]);
  #|      rowNulls.push(cell[1]);
  #|    }
  #|    rows.push(values);
  #|    nulls.push(rowNulls);
  #|  }
  #|  return make_table(columns, rows, nulls);
  #|}

///|
fn arrow_to_playground_table(table : ArrowTable) -> PlaygroundTable {
  js_convert_arrow_table(table, fn(columns, rows, nulls) {
    {
      columns: columns.iter().to_array(),
      rows: rows.iter().map(row => row.iter().to_array()).to_array(),
      nulls: nulls.iter().map(row => row.iter().to_array()).to_array(),
    }
  })
}

///|
extern "js" fn js_close(
  conn : WasmConnection,
  on_ok : () -> Unit,
  on_err : (String) -> Unit,
) -> Unit =
  #|(conn, on_ok, on_err) => {
  #|  const run = async () => {
  #|    if (conn.conn && typeof conn.conn.close === "function") await conn.conn.close();
  #|    if (conn.db && typeof conn.db.terminate === "function") await conn.db.terminate();
  #|    if (conn.worker && typeof conn.worker.terminate === "function") conn.worker.terminate();
  #|    on_ok();
  #|  };
  #|  run().catch(err => on_err(err && err.message ? err.message : String(err)));
  #|}

///|
pub fn query_registered_parquet(
  parquet_bytes : Bytes,
  file_name : String,
  sql : String,
  on_done : (Result[PlaygroundTable, String]) -> Unit,
) -> Unit {
  connect_local_wasm(fn(connect_result) {
    match connect_result {
      Err(message) => on_done(Err("duckdb connect failed: " + message))
      Ok(conn) =>
        register_file_buffer(conn, file_name, parquet_bytes, fn(
          register_result,
        ) {
          match register_result {
            Err(message) =>
              close_with_result(
                conn,
                Err("duckdb register failed: " + message),
                on_done,
              )
            Ok(_) =>
              js_query(
                conn,
                sql,
                fn(table) {
                  close_with_result(
                    conn,
                    Ok(arrow_to_playground_table(table)),
                    on_done,
                  )
                },
                fn(message) {
                  close_with_result(
                    conn,
                    Err("duckdb query failed: " + message),
                    on_done,
                  )
                },
              )
          }
        })
    }
  })
}

///|
fn close_with_result(
  conn : WasmConnection,
  result : Result[PlaygroundTable, String],
  on_done : (Result[PlaygroundTable, String]) -> Unit,
) -> Unit {
  js_close(conn, fn() { on_done(result) }, fn(message) {
    match result {
      Ok(_) => on_done(Err("duckdb close failed: " + message))
      Err(error) =>
        on_done(Err(error + "; duckdb close also failed: " + message))
    }
  })
}
