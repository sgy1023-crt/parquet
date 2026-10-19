# SPDX-License-Identifier: Apache-2.0
"""Development-only Parquet footer tree editing through Apache Thrift.

This deliberately contains no Compact wire codec or statistics pruning logic.
Apache Thrift's pinned Python TCompactProtocol handles every wire value. The
small schema-independent tree preserves unknown fields and binary payloads.
"""

from __future__ import annotations

from dataclasses import dataclass

from thrift.Thrift import TType
from thrift.protocol.TCompactProtocol import TCompactProtocol
from thrift.transport.TTransport import TMemoryBuffer


@dataclass(frozen=True)
class Field:
    kind: int
    value: object


@dataclass(frozen=True)
class Sequence:
    kind: int
    values: tuple


@dataclass(frozen=True)
class Mapping:
    key_kind: int
    value_kind: int
    entries: tuple


SCALAR_METHODS = {
    TType.BOOL: "Bool",
    TType.BYTE: "Byte",
    TType.I16: "I16",
    TType.I32: "I32",
    TType.I64: "I64",
    TType.DOUBLE: "Double",
    TType.STRING: "Binary",
}


def read_value(protocol, kind):
    if kind in SCALAR_METHODS:
        return getattr(protocol, "read" + SCALAR_METHODS[kind])()
    if kind == TType.STRUCT:
        protocol.readStructBegin()
        fields = {}
        while True:
            _, field_kind, field_id = protocol.readFieldBegin()
            if field_kind == TType.STOP:
                break
            if field_id in fields:
                raise ValueError(f"Duplicate fixture field {field_id}")
            fields[field_id] = Field(field_kind, read_value(protocol, field_kind))
            protocol.readFieldEnd()
        protocol.readStructEnd()
        return fields
    if kind in (TType.LIST, TType.SET):
        method = "List" if kind == TType.LIST else "Set"
        element_kind, size = getattr(protocol, "read" + method + "Begin")()
        values = tuple(read_value(protocol, element_kind) for _ in range(size))
        getattr(protocol, "read" + method + "End")()
        return Sequence(element_kind, values)
    if kind == TType.MAP:
        key_kind, value_kind, size = protocol.readMapBegin()
        entries = tuple(
            (read_value(protocol, key_kind), read_value(protocol, value_kind))
            for _ in range(size)
        )
        protocol.readMapEnd()
        return Mapping(key_kind, value_kind, entries)
    raise ValueError(f"Unsupported Thrift fixture type {kind}")


def write_value(protocol, kind, value):
    if kind in SCALAR_METHODS:
        getattr(protocol, "write" + SCALAR_METHODS[kind])(value)
        return
    if kind == TType.STRUCT:
        protocol.writeStructBegin("")
        for field_id, field in value.items():
            protocol.writeFieldBegin("", field.kind, field_id)
            write_value(protocol, field.kind, field.value)
            protocol.writeFieldEnd()
        protocol.writeFieldStop()
        protocol.writeStructEnd()
        return
    if kind in (TType.LIST, TType.SET):
        method = "List" if kind == TType.LIST else "Set"
        getattr(protocol, "write" + method + "Begin")(value.kind, len(value.values))
        for item in value.values:
            write_value(protocol, value.kind, item)
        getattr(protocol, "write" + method + "End")()
        return
    if kind == TType.MAP:
        protocol.writeMapBegin(value.key_kind, value.value_kind, len(value.entries))
        for key, item in value.entries:
            write_value(protocol, value.key_kind, key)
            write_value(protocol, value.value_kind, item)
        protocol.writeMapEnd()
        return
    raise ValueError(f"Unsupported Thrift fixture type {kind}")


def decode_struct(payload):
    transport = TMemoryBuffer(payload)
    tree = read_value(TCompactProtocol(transport), TType.STRUCT)
    if transport.read(1):
        raise ValueError("Trailing bytes after fixture Compact struct")
    return tree


def encode_struct(tree):
    transport = TMemoryBuffer()
    write_value(TCompactProtocol(transport), TType.STRUCT, tree)
    return transport.getvalue()


def split_footer(payload):
    if len(payload) < 12 or payload[:4] != b"PAR1" or payload[-4:] != b"PAR1":
        raise ValueError("Fixture must have a complete PAR1 header and trailer")
    length = int.from_bytes(payload[-8:-4], "little")
    start = len(payload) - 8 - length
    if start < 4:
        raise ValueError("Fixture footer extends before the page data")
    return payload[:start], payload[start:-8]


def replace_footer(payload, tree):
    pages, _ = split_footer(payload)
    footer = encode_struct(tree)
    return pages + footer + len(footer).to_bytes(4, "little") + b"PAR1"


def column_metadata(tree, group_index, column_index):
    # FileMetaData.row_groups -> RowGroup.columns -> ColumnChunk.meta_data.
    group = tree[4].value.values[group_index]
    chunk = group[1].value.values[column_index]
    return chunk[3].value


def statistics(tree, group_index, column_index):
    return column_metadata(tree, group_index, column_index)[12].value
