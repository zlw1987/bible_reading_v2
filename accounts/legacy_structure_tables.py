from dataclasses import dataclass

from django.db import connection


@dataclass(frozen=True)
class LegacyStructureTable:
    object_type: str
    table_name: str
    row_count_key: str
    mapping_count_key: str
    checked_key: str
    mapped_key: str
    expected_unit_type: str
    label_column: str
    code_column: str = ""
    active_column: str = "is_active"
    mapping_column: str = "church_structure_unit_id"


LEGACY_STRUCTURE_TABLES = (
    LegacyStructureTable(
        object_type="SmallGroup",
        table_name="accounts_smallgroup",
        row_count_key="small_group_rows",
        mapping_count_key="small_group_mapping",
        checked_key="small_groups_checked",
        mapped_key="small_groups_with_mapping_unit",
        expected_unit_type="small_group",
        label_column="name",
    ),
    LegacyStructureTable(
        object_type="District",
        table_name="accounts_district",
        row_count_key="district_rows",
        mapping_count_key="district_mapping",
        checked_key="districts_checked",
        mapped_key="districts_with_mapping_unit",
        expected_unit_type="district",
        label_column="name",
    ),
    LegacyStructureTable(
        object_type="MinistryContext",
        table_name="accounts_ministrycontext",
        row_count_key="ministry_context_rows",
        mapping_count_key="ministry_context_mapping",
        checked_key="ministry_contexts_checked",
        mapped_key="ministry_contexts_with_mapping_unit",
        expected_unit_type="ministry_context",
        label_column="name",
        code_column="code",
    ),
)


def legacy_table_names():
    return set(connection.introspection.table_names())


def legacy_table_exists(table, *, table_names=None):
    table_names = table_names if table_names is not None else legacy_table_names()
    return table.table_name in table_names


def _quote(name):
    return connection.ops.quote_name(name)


def _table_columns(table_name):
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }


def legacy_table_count(table, *, where=None, params=None, table_names=None):
    if not legacy_table_exists(table, table_names=table_names):
        return 0
    sql = f"SELECT COUNT(*) FROM {_quote(table.table_name)}"
    if where:
        sql += f" WHERE {where}"
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchone()[0]


def legacy_structure_table_counts():
    table_names = legacy_table_names()
    counts = {}
    for table in LEGACY_STRUCTURE_TABLES:
        counts[table.row_count_key] = legacy_table_count(
            table,
            table_names=table_names,
        )
        if legacy_table_exists(table, table_names=table_names):
            counts[table.mapping_count_key] = legacy_table_count(
                table,
                where=f"{_quote(table.mapping_column)} IS NOT NULL",
                table_names=table_names,
            )
        else:
            counts[table.mapping_count_key] = 0
    return counts


def iter_legacy_structure_rows():
    table_names = legacy_table_names()
    for table in LEGACY_STRUCTURE_TABLES:
        if not legacy_table_exists(table, table_names=table_names):
            continue
        columns = _table_columns(table.table_name)
        selected = ["id", table.label_column]
        if table.code_column:
            selected.append(table.code_column)
        if table.active_column in columns:
            selected.append(table.active_column)
        if table.mapping_column in columns:
            selected.append(table.mapping_column)

        sql = "SELECT {columns} FROM {table} ORDER BY id".format(
            columns=", ".join(_quote(column) for column in selected),
            table=_quote(table.table_name),
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            for values in cursor.fetchall():
                row = dict(zip(selected, values))
                yield table, row
