import json
import os
from collections import OrderedDict
from glob import glob

from agate.data_types import Text
from agate.table import Table
from agate.tableset.csv_manifest import (MANIFEST_FORMAT, deserialize_key, deserialize_type, manifest_path, parse_type)


@classmethod
def from_csv(cls, dir_path, column_names=None, column_types=None, row_names=None, header=True, **kwargs):
    """
    Create a new :class:`TableSet` from a directory of CSVs.

    If the directory contains a manifest written by :meth:`.TableSet.to_csv`
    the keys, their order, the key name, the key type and the column types
    recorded in it are restored exactly. Otherwise every CSV file in the
    directory is loaded with types inferred per file, keyed by filename.

    See :meth:`.Table.from_csv` for additional details.

    :param dir_path:
        Path to a directory full of CSV files. All CSV files in this
        directory will be loaded.
    :param column_names:
        See :meth:`Table.__init__`.
    :param column_types:
        See :meth:`Table.__init__`. If specified, these types are used to
        parse the CSV files directly, overriding the types recorded in the
        manifest.
    :param row_names:
        See :meth:`Table.__init__`.
    :param header:
        See :meth:`Table.from_csv`.
    """
    from agate.tableset import TableSet

    if not os.path.isdir(dir_path):
        raise OSError('Specified path doesn\'t exist or isn\'t a directory.')

    path = manifest_path(dir_path)

    if os.path.isfile(path):
        return _from_manifest(cls, dir_path, path, column_names, column_types, row_names, header, **kwargs)

    tables = OrderedDict()

    for path in sorted(glob(os.path.join(dir_path, '*.csv'))):
        if not os.path.isfile(path):
            continue

        name = os.path.splitext(os.path.basename(path))[0]

        tables[name] = Table.from_csv(path, column_names, column_types, row_names=row_names, header=header, **kwargs)

    return TableSet(tables.values(), tables.keys())


def _from_manifest(cls, dir_path, path, column_names, column_types, row_names, header, **kwargs):
    """
    Rebuild a :class:`TableSet` from a directory containing a manifest
    written by :meth:`.TableSet.to_csv`.
    """
    from agate.tableset import TableSet

    with open(path, encoding='utf-8') as f:
        manifest = json.load(f)

    if manifest.get('format') != MANIFEST_FORMAT:
        raise ValueError('File "%s" is not an agate TableSet manifest.' % path)

    key_type = deserialize_type(manifest.get('key_type')) or Text()
    parse_key_type = parse_type(key_type)

    if isinstance(parse_key_type, Text):
        # Null keys are recorded as JSON null, so key strings must never be
        # null-cast (an empty string is a valid key).
        parse_key_type = Text(cast_nulls=False, null_values=parse_key_type.null_values)

    if column_types is None:
        restored_types = []

        for spec in manifest.get('column_types', []):
            column_type = deserialize_type(spec)

            # Types that can not be reconstructed (e.g. custom DataType
            # subclasses) degrade to Text so the set stays consistent.
            restored_types.append(column_type if column_type is not None else Text())

        parse_types = [parse_type(column_type) for column_type in restored_types]
    else:
        restored_types = None
        parse_types = None

    tables = OrderedDict()

    for entry in manifest['tables']:
        key = deserialize_key(parse_key_type, entry['key'])

        if 'directory' in entry:
            table = cls.from_csv(
                os.path.join(dir_path, entry['directory']),
                column_names=column_names,
                column_types=column_types,
                row_names=row_names,
                header=header,
                **kwargs
            )
        elif column_types is not None:
            table = Table.from_csv(
                os.path.join(dir_path, entry['file']),
                column_names,
                column_types,
                row_names=row_names,
                header=header,
                **kwargs
            )
        else:
            table = Table.from_csv(
                os.path.join(dir_path, entry['file']),
                column_names,
                parse_types,
                row_names=row_names,
                header=header,
                **kwargs
            )

            # Re-cast the parsed (now native) values with the original types
            # so e.g. a Number column keeps its locale. Casting native values
            # is an identity operation for every data type.
            table = Table(table.rows, table.column_names, restored_types, row_names=row_names)

        tables[key] = table

    return TableSet(
        tables.values(),
        tables.keys(),
        key_name=manifest.get('key_name', 'group'),
        key_type=key_type
    )
