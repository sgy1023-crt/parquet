# SPDX-License-Identifier: Apache-2.0
"""Generate tiny, independently checked row-group Parquet fixtures.

Run with the pinned development dependencies documented in the fixture README.
INT64 values originate as Python integers and are decimal strings in the JSON
manifest so JavaScript consumers cannot accidentally round them.
"""

from __future__ import annotations

import hashlib
import argparse
import copy
import importlib.metadata
import json
import platform
import struct
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import thrift

from compact_fixture import (
    Field, Sequence, TType, column_metadata, decode_struct, encode_struct,
    replace_footer, split_footer, statistics,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures" / "row-groups"
COMMAND = "python scripts/generate_row_group_fixtures.py"
CHECK_COMMAND = COMMAND + " --check"
PROTOCOL_COMMIT = "53b8bd8576827080d4382fa457003f45b41cda6e"
ROW_GROUP_SIZE = 4
WRITE_OPTIONS = {
    "compression": "NONE",
    "use_dictionary": False,
    "version": "2.6",
    "data_page_version": "1.0",
    "row_group_size": ROW_GROUP_SIZE,
}


def json_scalar(value, arrow_type):
    if value is None:
        return None
    if pa.types.is_int64(arrow_type) or pa.types.is_uint64(arrow_type):
        return str(value)
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    if isinstance(value, (Decimal, date)):
        return str(value)
    return value


def json_rows(table, rows):
    return [
        {
            field.name: json_scalar(row[field.name], field.type)
            for field in table.schema
        }
        for row in rows
    ]


def bound_hex(value, physical_type):
    """Re-encode PyArrow's decoded raw bound; this is not a Thrift field dump."""
    if value is None:
        return None
    if physical_type == "INT32":
        return (value & 0xFFFFFFFF).to_bytes(4, "little").hex()
    if physical_type == "INT64":
        return (value & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little").hex()
    if physical_type == "FLOAT":
        return struct.pack("<f", value).hex()
    if physical_type == "DOUBLE":
        return struct.pack("<d", value).hex()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, str):
        return value.encode("utf-8").hex()
    raise TypeError(f"Unsupported bound representation: {value!r}")


def statistics_dict(statistics, arrow_type):
    if statistics is None:
        return None
    has_bounds = statistics.has_min_max
    raw_min = statistics.min_raw if has_bounds else None
    raw_max = statistics.max_raw if has_bounds else None
    return {
        "physical_type": statistics.physical_type,
        "has_min_max": has_bounds,
        "min": json_scalar(statistics.min, arrow_type) if has_bounds else None,
        "max": json_scalar(statistics.max, arrow_type) if has_bounds else None,
        "min_raw": json_scalar(raw_min, arrow_type),
        "max_raw": json_scalar(raw_max, arrow_type),
        "min_plain_hex_from_pyarrow_raw": bound_hex(
            raw_min, statistics.physical_type
        ),
        "max_plain_hex_from_pyarrow_raw": bound_hex(
            raw_max, statistics.physical_type
        ),
        "has_null_count": statistics.has_null_count,
        "null_count": statistics.null_count if statistics.has_null_count else None,
        "distinct_count": statistics.distinct_count,
        "num_non_null_values": statistics.num_values if statistics.has_null_count else None,
    }


def raw_statistics_dict(fields):
    if fields is None:
        return None
    names = {
        1: "legacy_max_hex", 2: "legacy_min_hex", 3: "null_count",
        4: "distinct_count", 5: "max_value_hex", 6: "min_value_hex",
        7: "is_max_value_exact", 8: "is_min_value_exact",
    }
    result = {name: None for name in names.values()}
    result["present_field_ids"] = list(fields)
    for field_id, name in names.items():
        if field_id not in fields:
            continue
        value = fields[field_id].value
        if field_id in (1, 2, 5, 6):
            value = value.hex()
        elif field_id in (3, 4):
            value = str(value)
        result[name] = value
    return result


def raw_footer_dict(payload):
    _, footer = split_footer(payload)
    tree = decode_struct(footer)
    assert encode_struct(tree) == footer, "Apache Thrift Compact round-trip differs"
    orders = None
    if 7 in tree:
        orders = [
            {"union_field_ids": list(order), "kind": "TYPE_ORDER" if list(order) == [1] else "UNKNOWN"}
            for order in tree[7].value.values
        ]
    schema = [
        {
            "name": element[4].value.decode("utf-8"),
            "physical_type_id": element[1].value if 1 in element else None,
            "converted_type_id": element[6].value if 6 in element else None,
            "logical_type_union_field_ids": list(element[10].value) if 10 in element else None,
        }
        for element in tree[2].value.values
    ]
    groups = []
    for group in tree[4].value.values:
        columns = []
        for chunk in group[1].value.values:
            metadata = chunk[3].value
            columns.append({
                "physical_type_id": metadata[1].value,
                "path_in_schema": [item.decode("utf-8") for item in metadata[3].value.values],
                "num_values": str(metadata[5].value),
                "data_page_offset": str(metadata[9].value),
                "statistics": raw_statistics_dict(metadata[12].value if 12 in metadata else None),
            })
        groups.append({"num_rows": str(group[3].value), "columns": columns})
    return {"file_num_rows": str(tree[3].value), "column_orders": orders, "schema": schema, "row_groups": groups}


def metadata_dict(path, table, include_decoded_statistics=True):
    parquet = pq.ParquetFile(path)
    metadata = parquet.metadata
    columns = []
    for index, field in enumerate(table.schema):
        column = parquet.schema.column(index)
        columns.append(
            {
                "name": field.name,
                "arrow_type": str(field.type),
                "nullable": field.nullable,
                "path": column.path,
                "physical_type": column.physical_type,
                "converted_type": column.converted_type,
                "logical_type": json.loads(column.logical_type.to_json()),
                "max_definition_level": column.max_definition_level,
                "max_repetition_level": column.max_repetition_level,
            }
        )
    groups = []
    row_start = 0
    for group_index in range(metadata.num_row_groups):
        group = metadata.row_group(group_index)
        chunks = []
        for column_index, field in enumerate(table.schema):
            chunk = group.column(column_index)
            chunks.append(
                {
                    "column_index": column_index,
                    "path_in_schema": chunk.path_in_schema,
                    "physical_type": chunk.physical_type,
                    "file_offset": chunk.file_offset,
                    "file_path": chunk.file_path,
                    "data_page_offset": chunk.data_page_offset,
                    "dictionary_page_offset": chunk.dictionary_page_offset,
                    "has_dictionary_page": chunk.has_dictionary_page,
                    "total_compressed_size": chunk.total_compressed_size,
                    "total_uncompressed_size": chunk.total_uncompressed_size,
                    "compression": chunk.compression,
                    "encodings": list(chunk.encodings),
                    "num_values": chunk.num_values,
                    "is_stats_set": chunk.is_stats_set,
                    "statistics": statistics_dict(chunk.statistics, field.type)
                    if include_decoded_statistics else None,
                }
            )
        groups.append(
            {
                "index": group_index,
                "row_start": row_start,
                "num_rows": group.num_rows,
                "first_page_offset": min(
                    chunk["dictionary_page_offset"]
                    if chunk["has_dictionary_page"]
                    else chunk["data_page_offset"]
                    for chunk in chunks
                ),
                "total_byte_size": group.total_byte_size,
                "total_compressed_size": sum(
                    chunk["total_compressed_size"] for chunk in chunks
                ),
                "columns": chunks,
            }
        )
        row_start += group.num_rows
    payload = path.read_bytes()
    footer_length = int.from_bytes(payload[-8:-4], "little")
    return {
        "path": path.name,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "num_rows": metadata.num_rows,
        "num_row_groups": metadata.num_row_groups,
        "num_columns": metadata.num_columns,
        "created_by": metadata.created_by,
        "format_version": metadata.format_version,
        "footer_offset": len(payload) - 8 - footer_length,
        "footer_length": footer_length,
        "schema": columns,
        "row_groups": groups,
        "rows": json_rows(table, table.to_pylist()),
        "footer_fields": raw_footer_dict(payload),
    }


def predicate_oracle(table, column, comparison, literal, retained_groups, reason):
    # This filters original in-memory rows. Group retention is supplied explicitly
    # by each scenario; this generator does not implement statistics pruning.
    comparisons = {
        ">=": lambda value: value >= literal,
        ">": lambda value: value > literal,
        "<": lambda value: value < literal,
    }
    matches = [
        (index, row)
        for index, row in enumerate(table.to_pylist())
        if row[column] is not None and comparisons[comparison](row[column])
    ]
    return {
        "column": column,
        "comparison": comparison,
        "literal": str(literal) if isinstance(literal, int) else literal,
        "literal_encoding": "decimal string" if isinstance(literal, int) else "JSON",
        "matching_row_indices": [index for index, _ in matches],
        "matching_row_group_indices": sorted(
            {index // ROW_GROUP_SIZE for index, _ in matches}
        ),
        "matching_rows": json_rows(table, [row for _, row in matches]),
        "expected_retained_row_group_indices": retained_groups,
        "retention_reason": reason,
    }


def write_valid_fixture(name, table, predicates, write_statistics=True, decode_statistics=True, **options):
    path = OUTPUT / name
    pq.write_table(table, path, write_statistics=write_statistics, **WRITE_OPTIONS, **options)
    read_back = pq.ParquetFile(path).read()
    assert read_back.schema == table.schema, name
    assert read_back.to_pylist() == table.to_pylist(), name
    entry = metadata_dict(path, table, include_decoded_statistics=decode_statistics)
    entry.update(
        {
            "validity": "valid parquet; independently read by PyArrow",
            "write_statistics": write_statistics,
            "predicates": predicates,
            "verification": {"full_round_trip_rows_equal": True},
            "expected_result": {"read_metadata": "success", "full_decode": "success"},
        }
    )
    source_rows = table.to_pylist()
    for group in entry["row_groups"]:
        rows = source_rows[group["row_start"]:group["row_start"] + group["num_rows"]]
        for column_index, column in enumerate(group["columns"]):
            statistics = column["statistics"]
            if statistics is None:
                continue
            name = table.schema[column_index].name
            values = [row[name] for row in rows if row[name] is not None]
            assert statistics["null_count"] == len(rows) - len(values), name
            assert statistics["has_min_max"] == bool(values), name
            if values:
                field_type = table.schema[column_index].type
                assert statistics["min"] == json_scalar(min(values), field_type), name
                assert statistics["max"] == json_scalar(max(values), field_type), name
    if decode_statistics:
        entry["verification"]["available_statistics_match_source_rows"] = True
    else:
        assert pa.types.is_decimal(table.schema[0].type)
        scale = table.schema[0].type.scale
        for group in entry["row_groups"]:
            rows = source_rows[group["row_start"]:group["row_start"] + group["num_rows"]]
            values = [row["value"] for row in rows if row["value"] is not None]
            raw = entry["footer_fields"]["row_groups"][group["index"]]["columns"][0]["statistics"]
            assert raw["null_count"] == str(len(rows) - len(values))
            for field, value in (("min_value_hex", min(values) if values else None), ("max_value_hex", max(values) if values else None)):
                expected = int(value.scaleb(scale)).to_bytes(4, "little", signed=True).hex() if value is not None else None
                assert raw[field] == expected
        entry["decoded_statistics_status"] = "PyArrow 18 cannot extract INT32 DECIMAL statistics; exact raw fields verified against scaled source decimals"
        entry["verification"]["raw_statistics_match_source_rows"] = True
    entry["write_option_overrides"] = options
    if not write_statistics:
        assert all(
            not column["is_stats_set"]
            for group in entry["row_groups"]
            for column in group["columns"]
        )
    return entry


def make_poison(base, table):
    base_path = OUTPUT / base["path"]
    original = base_path.read_bytes()
    changed = bytearray(original)
    offset = base["row_groups"][0]["columns"][0]["data_page_offset"]
    assert changed[offset] != 0
    old_byte = changed[offset]
    changed[offset] = 0  # Compact STOP truncates the page header before its fields.
    footer_start = base["footer_offset"]
    assert changed[footer_start:] == original[footer_start:]
    assert sum(left != right for left, right in zip(original, changed)) == 1
    path = OUTPUT / "poison_skipped.parquet"
    path.write_bytes(changed)
    parquet = pq.ParquetFile(path)
    assert parquet.read_row_group(2).to_pylist() == table.slice(8, 4).to_pylist()
    try:
        parquet.read()
    except (pa.ArrowException, OSError) as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    else:
        raise AssertionError("Poisoned group unexpectedly survived a full read")
    entry = metadata_dict(path, table)
    entry.update(
        {
            "validity": "INTENTIONALLY CORRUPT; metadata intact; not a valid file",
            "base_fixture": base["path"],
            "write_statistics": True,
            "corruption": {
                "row_group_index": 0,
                "column_index": 0,
                "absolute_offset": offset,
                "original_hex": f"{old_byte:02x}",
                "modified_hex": "00",
                "modified_byte_count": 1,
                "footer_and_trailer_byte_identical_to_base": True,
                "purpose": "A selected-group decode of group 2 must not touch group 0",
            },
            "predicates": [base["predicates"][0]],
            "verification": {
                "metadata_read_succeeds": True,
                "read_row_group_2_equals_base": True,
                "full_read_fails": failure,
            },
            "expected_result": {
                "read_metadata": "success", "full_decode": "error",
                "read_row_group_2": "success",
            },
        }
    )
    return entry


def footer_variant(base, table, name, mutation, description, retained_groups, error_stage=None, *, layout_change=False):
    source = (OUTPUT / base["path"]).read_bytes()
    pages, footer = split_footer(source)
    tree = decode_struct(footer)
    original_tree = copy.deepcopy(tree)
    mutation(tree)
    if not layout_change:
        for candidate in (original_tree, copy.deepcopy(tree)):
            candidate.pop(7, None)
            for group_index, group in enumerate(candidate[4].value.values):
                for column_index, _ in enumerate(group[1].value.values):
                    column_metadata(candidate, group_index, column_index).pop(12, None)
            if candidate is original_tree:
                expected_layout = candidate
            else:
                assert candidate == expected_layout, "A footer variant changed schema, page offsets, or other non-statistics fields"
    else:
        for group_index, group in enumerate(tree[4].value.values):
            for column_index, _ in enumerate(group[1].value.values):
                before = column_metadata(original_tree, group_index, column_index)
                after = column_metadata(tree, group_index, column_index)
                for field_id in (6, 7, 9, 10, 11):
                    assert before.get(field_id) == after.get(field_id), "A structural fixture changed codec, size, or page offsets"
    modified = replace_footer(source, tree)
    assert modified[:len(pages)] == pages
    path = OUTPUT / name
    path.write_bytes(modified)
    # Arrow 18 can abort the process on deliberately short bound payloads.
    # Legal variants receive an independent full read; invalid statistics use
    # the verified base layout plus the actual Thrift fields, never Arrow stats.
    if error_stage is None:
        entry = metadata_dict(path, table)
        read_back = pq.ParquetFile(path).read()
        assert read_back.schema == table.schema, name
        assert read_back.to_pylist() == table.to_pylist(), name
    else:
        entry = copy.deepcopy(base)
        entry.pop("corruption", None)
        entry.update({
            "path": name, "size_bytes": len(modified),
            "sha256": hashlib.sha256(modified).hexdigest(),
            "footer_offset": len(pages), "footer_length": len(modified) - len(pages) - 8,
            "footer_fields": raw_footer_dict(modified),
            "num_rows": tree[3].value,
        })
        row_start = 0
        for group in entry["row_groups"]:
            group["row_start"] = row_start
            group["num_rows"] = tree[4].value.values[group["index"]][3].value
            row_start += group["num_rows"]
            for column in group["columns"]:
                metadata = column_metadata(tree, group["index"], column["column_index"])
                column["num_values"] = metadata[5].value
                column["path_in_schema"] = ".".join(item.decode("utf-8") for item in metadata[3].value.values)
                column["physical_type"] = ("BOOLEAN", "INT32", "INT64", "INT96", "FLOAT", "DOUBLE", "BYTE_ARRAY", "FIXED_LEN_BYTE_ARRAY")[metadata[1].value]
                column["statistics"] = None
        entry["decoded_statistics_status"] = "not attempted on intentionally invalid statistics; see actual footer_fields"
        if layout_change:
            entry["rows_status"] = "original source page values; actual footer changes are recorded in footer_fields and mutation"
    entry.update({
        "base_fixture": base["path"],
        "validity": "valid parquet; independently read by PyArrow" if error_stage is None
        else "INTENTIONALLY INVALID FOOTER SEMANTICS; valid Compact footer and preserved page data" if layout_change
        else "INTENTIONALLY INVALID STATISTICS; valid Compact footer and preserved page data",
        "mutation": description,
        "predicates": [predicate_oracle(table, "i32", ">=", 100, retained_groups, description)]
        if error_stage is None else [],
        "expected_result": {
            "read_metadata": "InvalidData" if error_stage == "read_metadata" else "success",
            "signed_integer_statistics": "InvalidData" if error_stage == "signed_integer_statistics"
            else "unreachable; read_metadata is InvalidData" if error_stage == "read_metadata" else "success",
            "full_decode": "success" if error_stage is None else "not asserted; validation targets the stated metadata or typed-statistics API",
        },
        "verification": {
            "page_prefix_byte_identical_to_base": True,
            "all_non_statistics_footer_fields_unchanged_except_column_orders": not layout_change,
            "codec_sizes_and_page_offsets_unchanged": True,
            "page_prefix_length": len(pages),
            "page_prefix_sha256": hashlib.sha256(pages).hexdigest(),
            "apache_thrift_footer_round_trip_byte_identical": True,
            "pyarrow_full_read_equals_base": True if error_stage is None else None,
            "pyarrow_full_read_schema_equals_base": True if error_stage is None else None,
            "pyarrow_invalid_statistics_not_attempted": error_stage is not None,
        },
    })
    return entry


def mutate_statistics(tree, mutation):
    for group_index, group in enumerate(tree[4].value.values):
        for column_index, _ in enumerate(group[1].value.values):
            mutation(statistics(tree, group_index, column_index), group_index, column_index)


def remove_null_counts(tree):
    mutate_statistics(tree, lambda fields, _g, _c: fields.pop(3))


def remove_modern_bounds(tree):
    def remove(fields, _group, _column):
        for field_id in (5, 6, 7, 8):
            fields.pop(field_id, None)
    mutate_statistics(tree, remove)


def remove_modern_bound(tree, field_id):
    mutate_statistics(tree, lambda fields, _g, _c: fields.pop(field_id, None))


def unknown_column_order(tree):
    tree[7] = Field(TType.LIST, Sequence(TType.STRUCT, tuple(
        {42: Field(TType.STRUCT, {})} for _ in tree[7].value.values
    )))


def widen_bounds(tree):
    def widen(fields, _group, column):
        width = 4 if column == 0 else 8
        if 5 not in fields:
            return
        for field_id, delta in ((5, 1), (6, -1)):
            value = int.from_bytes(fields[field_id].value, "little", signed=True) + delta
            fields[field_id] = Field(TType.STRING, value.to_bytes(width, "little", signed=True))
        fields[7] = Field(TType.BOOL, False)
        fields[8] = Field(TType.BOOL, False)
    mutate_statistics(tree, widen)


def set_statistic(tree, group, column, field_id, kind, value):
    statistics(tree, group, column)[field_id] = Field(kind, value)


def change_schema_path(tree):
    column_metadata(tree, 0, 0)[3] = Field(TType.LIST, Sequence(TType.STRING, (b"renamed_i32",)))


def change_schema_type(tree):
    column_metadata(tree, 0, 0)[1] = Field(TType.I32, 2)  # INT64 contradicts INT32 leaf schema.


def shorten_column_orders(tree):
    tree[7] = Field(TType.LIST, Sequence(TType.STRUCT, tree[7].value.values[:-1]))


def overflow_row_count(tree):
    count = 2147483648
    tree[4].value.values[0][3] = Field(TType.I64, count)
    for column in (0, 1):
        column_metadata(tree, 0, column)[5] = Field(TType.I64, count)
    tree[3] = Field(TType.I64, sum(group[3].value for group in tree[4].value.values))
    assert tree[3].value == 2147483660


def malformed_file(base, name, transform, description):
    original = (OUTPUT / base["path"]).read_bytes()
    modified = transform(original)
    path = OUTPUT / name
    path.write_bytes(modified)
    try:
        pq.ParquetFile(path)
    except (pa.ArrowException, OSError) as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    else:
        raise AssertionError(f"PyArrow unexpectedly accepted {name}")
    return {
        "path": name, "base_fixture": base["path"], "size_bytes": len(modified),
        "sha256": hashlib.sha256(modified).hexdigest(),
        "validity": "INTENTIONALLY CORRUPT FILE; not a valid Parquet file",
        "mutation": description,
        "expected_result": {"read_metadata": "InvalidData", "full_decode": "error"},
        "verification": {"pyarrow_metadata_read_fails": failure},
    }


def generate():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = pa.table(
        {
            "i32": pa.array(
                [-20, -19, None, -17, 0, 1, None, 3, 100, 101, 102, 103]
                + [None] * 4,
                type=pa.int32(),
            ),
            "i64": pa.array(
                [
                    -9007199254741003, -9007199254741002, None, -9007199254741001,
                    -1, 0, None, 2,
                    9007199254740993, 9007199254740995,
                    9007199254740997, 9007199254740999,
                ] + [None] * 4,
                type=pa.int64(),
            ),
        }
    )
    base_predicates = [
        predicate_oracle(base, "i32", ">=", 100, [2], "Disjoint signed ranges; group 3 is all null"),
        predicate_oracle(base, "i64", ">=", 9007199254740995, [2], "Exact INT64 threshold above 2^53"),
        predicate_oracle(base, "i32", "<", -10, [0], "Negative signed bounds"),
    ]
    entries = [write_valid_fixture("base.parquet", base, base_predicates)]
    assert entries[0]["num_row_groups"] == 4
    assert all(
        column["logical_type"] == {"Type": "None"}
        and column["converted_type"] == "NONE"
        for column in entries[0]["schema"]
    )
    for column in entries[0]["row_groups"][3]["columns"]:
        assert column["statistics"]["null_count"] == 4
        assert not column["statistics"]["has_min_max"]
    entries.append(
        write_valid_fixture(
            "no_statistics.parquet", base,
            [predicate_oracle(base, "i32", ">=", 100, [0, 1, 2, 3], "No statistics: retain all groups")],
            write_statistics=False,
        )
    )
    empty = base.slice(0, 0)
    entries.append(
        write_valid_fixture(
            "zero_rows.parquet", empty,
            [predicate_oracle(empty, "i32", ">=", 100, [], "Zero rows: no decoded groups needed")],
        )
    )
    unsupported = [
        ("unsupported_float.parquet", pa.float32(), [-2.5, -1.5, None, -0.5, 100.5, 101.5, 102.5, 103.5] + [None] * 4, 100.0),
        ("unsupported_string.parquet", pa.string(), ["a", "b", None, "c", "x", "y", None, "z"] + [None] * 4, "x"),
        ("unsupported_uint32.parquet", pa.uint32(), [0, 1, None, 3, 2147483648, 2147483649, 4294967294, 4294967295] + [None] * 4, 2147483648),
    ]
    for name, arrow_type, values, literal in unsupported:
        table = pa.table({"value": pa.array(values, type=arrow_type)})
        entries.append(
            write_valid_fixture(
                name, table,
                [predicate_oracle(table, "value", ">=", literal, [0, 1, 2], "Outside signed INT32/INT64 PoC subset: retain all groups")],
            )
        )
    entries.append(make_poison(entries[0], base))
    base_entry = entries[0]
    variants = [
        ("missing_null_count.parquet", remove_null_counts,
         "Remove null_count from every Statistics struct; absence remains unknown", [2, 3], None),
        ("legacy_only.parquet", remove_modern_bounds,
         "Remove modern bounds and exact flags; legacy min/max remain distinct", [0, 1, 2], None),
        ("min_only.parquet", lambda tree: remove_modern_bound(tree, 5),
         "Remove every modern max_value field 5; preserve modern min_value and both legacy bounds", [0, 1, 2], None),
        ("max_only.parquet", lambda tree: remove_modern_bound(tree, 6),
         "Remove every modern min_value field 6; preserve modern max_value and both legacy bounds", [2], None),
        ("missing_column_orders.parquet", lambda tree: tree.pop(7),
         "Remove FileMetaData.column_orders; modern bounds cannot be interpreted", [0, 1, 2], None),
        ("unknown_column_order.parquet", unknown_column_order,
         "Replace TYPE_ORDER union with unknown field 42 containing an empty struct", [0, 1, 2], None),
        ("inexact_wide_bounds.parquet", widen_bounds,
         "Widen each nonempty modern signed bound by one and set both exact flags false", [2], None),
        ("bad_i32_bound_length.parquet",
         lambda tree: set_statistic(tree, 0, 0, 6, TType.STRING, b"\xec\xff\xff"),
         "Group 0 i32 min_value is 3 bytes, expected exactly 4", [], "signed_integer_statistics"),
        ("bad_i64_bound_length.parquet",
         lambda tree: set_statistic(tree, 0, 1, 6, TType.STRING, b"\xf5\xff\xff\xff\xff\xff\xdf"),
         "Group 0 i64 min_value is 7 bytes, expected exactly 8", [], "signed_integer_statistics"),
        ("all_null_bad_i32_bound_length.parquet",
         lambda tree: set_statistic(tree, 3, 0, 5, TType.STRING, b"\x00\x00\x00"),
         "Group 3 all-null i32 has invalid 3-byte max_value; all-null must not bypass validation", [], "signed_integer_statistics"),
        ("negative_null_count.parquet",
         lambda tree: set_statistic(tree, 0, 0, 3, TType.I64, -1),
         "Group 0 i32 null_count is negative (-1)", [], "read_metadata"),
        ("excess_null_count.parquet",
         lambda tree: set_statistic(tree, 0, 0, 3, TType.I64, 5),
         "Group 0 i32 null_count=5 exceeds ColumnMetaData.num_values=4", [], "read_metadata"),
        ("negative_distinct_count.parquet",
         lambda tree: set_statistic(tree, 0, 0, 4, TType.I64, -1),
         "Group 0 i32 distinct_count is negative (-1)", [], "read_metadata"),
        ("reversed_bounds.parquet",
         lambda tree: set_statistic(tree, 0, 0, 6, TType.STRING, (-16).to_bytes(4, "little", signed=True)),
         "Group 0 i32 min_value=-16 exceeds max_value=-17", [], "signed_integer_statistics"),
    ]
    for name, mutation, description, retained, stage in variants:
        entries.append(footer_variant(base_entry, base, name, mutation, description, retained, stage))
    structural = [
        ("schema_path_mismatch.parquet", change_schema_path, "Group 0 column 0 path_in_schema is renamed_i32, contradicting the i32 leaf schema"),
        ("schema_type_mismatch.parquet", change_schema_type, "Group 0 column 0 physical type is INT64, contradicting its INT32 leaf schema"),
        ("column_order_count_mismatch.parquet", shorten_column_orders, "column_orders contains one entry for two leaf columns"),
    ]
    for name, mutation, description in structural:
        entries.append(footer_variant(base_entry, base, name, mutation, description, [], "read_metadata", layout_change=True))
    poison_entry = next(entry for entry in entries if entry["path"] == "poison_skipped.parquet")
    overflow = footer_variant(
        poison_entry, base, "selected_row_count_overflow.parquet", overflow_row_count,
        "Use poisoned group 0 page prefix; claim 2147483648 rows and num_values for both group 0 chunks, and total file rows 2147483660",
        [], "selected_row_count", layout_change=True,
    )
    overflow["expected_result"].update({
        "read_metadata": "success", "read_row_groups_empty": "success with zero decoded chunks",
        "read_row_groups_0": "InvalidData: Selected row count exceeds columnar batch Int capacity; before poisoned page decoding",
        "full_decode": "InvalidData: Selected row count exceeds columnar batch Int capacity",
    })
    entries.append(overflow)
    inexact = next(entry for entry in entries if entry["path"] == "inexact_wide_bounds.parquet")
    inexact["predicates"].append(predicate_oracle(
        base, "i32", ">=", 104, [2],
        "False exact flags still describe conservative bounds; residual filtering yields no rows",
    ))
    logical_tables = [
        ("unsupported_uint64.parquet", pa.table({"value": pa.array(
            [0, 1, None, 3, 9223372036854775808, 9223372036854775809,
             18446744073709551614, 18446744073709551615] + [None] * 4, type=pa.uint64())}), {}),
        ("unsupported_decimal.parquet", pa.table({"value": pa.array(
            [Decimal("-2.00"), Decimal("-1.00"), None, Decimal("0.00"),
             Decimal("100.00"), Decimal("101.00"), Decimal("102.00"), Decimal("103.00")]
            + [None] * 4, type=pa.decimal128(9, 2))}), {"store_decimal_as_integer": True, "decode_statistics": False}),
        ("unsupported_date.parquet", pa.table({"value": pa.array(
            [date(1969, 12, 30), date(1969, 12, 31), None, date(1970, 1, 1),
             date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
            + [None] * 4, type=pa.date32())}), {}),
    ]
    for name, table, options in logical_tables:
        entry = write_valid_fixture(name, table, [], **options)
        entry["expected_signed_integer_view"] = "None: logical or converted annotation changes the physical signed integer meaning"
        entries.append(entry)
    for entry in entries:
        if entry["path"].startswith("unsupported_"):
            entry["expected_signed_integer_view"] = "None: outside the flat unannotated signed INT32/INT64 subset"
    corruptions = [
        ("bad_footer_magic.parquet", lambda data: data[:-4] + b"NOPE", "Replace final PAR1 magic with NOPE"),
        ("bad_footer_length.parquet", lambda data: data[:-8] + len(data).to_bytes(4, "little") + b"PAR1", "Footer length extends before file header"),
        ("truncated_file.parquet", lambda data: data[:-6], "Truncate six bytes from footer length and final magic"),
        ("truncated_footer.parquet", lambda data: data[:-9] + (int.from_bytes(data[-8:-4], "little") - 1).to_bytes(4, "little") + b"PAR1", "Remove final Compact STOP but preserve consistent trailer length"),
    ]
    for name, transform, description in corruptions:
        entries.append(malformed_file(base_entry, name, transform, description))
    source_paths = [ROOT / "scripts" / "generate_row_group_fixtures.py", ROOT / "scripts" / "compact_fixture.py"]
    source_hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    thrift_root = Path(thrift.__file__).parent
    runtime_hashes = {
        name: hashlib.sha256((thrift_root / name).read_bytes()).hexdigest()
        for name in ("Thrift.py", "protocol/TCompactProtocol.py", "protocol/TProtocol.py", "transport/TTransport.py")
    }
    manifest = {
        "manifest_version": 2,
        "license": "Apache-2.0; all rows are synthetic and generated for this project",
        "generation_command": COMMAND,
        "generation_command_sha256": hashlib.sha256(COMMAND.encode("utf-8")).hexdigest(),
        "verification_command": CHECK_COMMAND,
        "verification_command_sha256": hashlib.sha256(CHECK_COMMAND.encode("utf-8")).hexdigest(),
        "generator_relative_path": "scripts/generate_row_group_fixtures.py",
        "generator_source_sha256": source_hashes,
        "tools": {"python": platform.python_version(), "pyarrow": pa.__version__, "numpy": np.__version__, "apache_thrift": importlib.metadata.version("thrift")},
        "protocol_source": {
            "repository": "apache/parquet-format", "commit": PROTOCOL_COMMIT,
            "url": f"https://github.com/apache/parquet-format/blob/{PROTOCOL_COMMIT}/src/main/thrift/parquet.thrift",
            "field_paths": {"statistics": "FileMetaData.4[].RowGroup.1[].ColumnChunk.3.ColumnMetaData.12", "column_orders": "FileMetaData.7", "schema": "FileMetaData.2"},
        },
        "thrift_runtime_source": {
            "distribution": "thrift==0.22.0", "archive": "thrift-0.22.0.tar.gz",
            "archive_sha256": "42e8276afbd5f54fe1d364858b6877bc5e5a4a5ed69f6a005b94ca4918fe1466",
            "wire_codec": "Apache thrift.protocol.TCompactProtocol; no local Compact wire implementation",
            "runtime_source_sha256": runtime_hashes,
        },
        "writer_options": WRITE_OPTIONS,
        "integer_encoding": "INT64/UINT64 row values, bounds and predicate literals use decimal strings. Raw footer counts use decimal strings; absence is JSON null, never zero.",
        "bound_hex_encoding": "footer_fields stores actual binary Thrift fields in hex; min_plain_hex_from_pyarrow_raw is separately derived PLAIN encoding",
        "selection_policy": "Expected retained groups are explicit fixture expectations for the conservative signed INT32/INT64 PoC; no pruning engine is implemented here",
        "fixtures": entries,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (OUTPUT / "GENERATION_COMMAND.txt").write_text(COMMAND + "\n", encoding="utf-8", newline="\n")
    return entries


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Regenerate in a temporary directory and compare every generated byte")
    parser.add_argument("--output", type=Path, help="Generate into a separate directory")
    arguments = parser.parse_args()
    if arguments.output and arguments.check:
        parser.error("--output and --check are mutually exclusive")
    if arguments.output:
        OUTPUT = arguments.output.resolve()
    if arguments.check:
        checked_in = OUTPUT
        with tempfile.TemporaryDirectory(prefix="parquet-row-groups-check-") as temporary:
            OUTPUT = Path(temporary)
            entries = generate()
            generated_names = {path.name for path in OUTPUT.iterdir()}
            checked_names = {path.name for path in checked_in.iterdir() if path.suffix == ".parquet" or path.name in ("manifest.json", "GENERATION_COMMAND.txt")}
            if generated_names != checked_names:
                raise AssertionError(f"Fixture file set differs: {generated_names ^ checked_names}")
            for path in sorted(OUTPUT.iterdir()):
                expected = checked_in / path.name
                if not expected.exists() or path.read_bytes() != expected.read_bytes():
                    raise AssertionError(f"Fixture differs: {expected}")
        print(f"Verified {len(entries)} fixtures and deterministic manifest byte-for-byte")
        return
    entries = generate()
    print(json.dumps({"manifest": str(OUTPUT / "manifest.json"), "fixtures": len(entries), "valid_pyarrow_full_reads": sum(entry["expected_result"]["full_decode"] == "success" for entry in entries), "intentional_error_fixtures": sum("INTENTIONALLY" in entry["validity"] for entry in entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
