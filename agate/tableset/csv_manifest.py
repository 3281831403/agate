"""
Helpers for round-tripping a :class:`TableSet` through a directory of CSVs.

:meth:`.TableSet.to_csv` writes a small JSON manifest alongside the CSV files
recording the keys (in order), the key name/type and the column types of the
set. :meth:`.TableSet.from_csv` uses the manifest, when present, to restore
all of that metadata exactly. Directories written by older versions of agate
(no manifest) are still read using the legacy filename-based behavior.

The manifest is a dotfile so it is ignored by the ``*.csv`` and ``*.json``
globs used by :meth:`.TableSet.from_csv` and :meth:`.TableSet.from_json`.
"""

import os

from agate import data_types
from agate.data_types.base import DEFAULT_NULL_VALUES
from agate.data_types.number import DEFAULT_CURRENCY_SYMBOLS

#: Name of the manifest file written by :meth:`.TableSet.to_csv`.
MANIFEST_FILENAME = '.agate-tableset.json'

#: Value of the ``format`` field in the manifest.
MANIFEST_FORMAT = 'agate-tableset'

#: Version of the manifest schema written by this module.
MANIFEST_VERSION = 1


def serialize_type(column_type):
    """
    Convert a :class:`.DataType` instance into a JSON-serializable spec that
    :func:`deserialize_type` can turn back into an equivalent instance.
    """
    params = {}

    if isinstance(column_type, data_types.Text):
        params['cast_nulls'] = column_type.cast_nulls
    elif isinstance(column_type, data_types.Number):
        params['locale'] = str(column_type.locale)
        params['group_symbol'] = column_type.group_symbol
        params['decimal_symbol'] = column_type.decimal_symbol
        params['no_leading_zeroes'] = column_type.no_leading_zeroes

        if list(column_type.currency_symbols) != list(DEFAULT_CURRENCY_SYMBOLS):
            params['currency_symbols'] = list(column_type.currency_symbols)
    elif isinstance(column_type, data_types.Boolean):
        params['true_values'] = list(column_type.true_values)
        params['false_values'] = list(column_type.false_values)
    elif isinstance(column_type, data_types.DateTime):
        params['datetime_format'] = column_type.datetime_format
        params['locale'] = column_type.locale
        # ZoneInfo instances expose their IANA key, which is all we can
        # reliably reconstruct.
        params['timezone'] = getattr(column_type.timezone, 'key', None)
    elif isinstance(column_type, data_types.Date):
        params['date_format'] = column_type.date_format
        params['locale'] = column_type.locale

    if list(column_type.null_values) != [v.lower() for v in DEFAULT_NULL_VALUES]:
        params['null_values'] = list(column_type.null_values)

    return {
        'type': type(column_type).__name__,
        'params': params
    }


def deserialize_type(spec):
    """
    Reconstruct a :class:`.DataType` instance from a spec produced by
    :func:`serialize_type`. Returns :code:`None` if the type can not be
    reconstructed (e.g. a custom :class:`.DataType` subclass).
    """
    if not isinstance(spec, dict):
        return None

    name = spec.get('type')
    params = dict(spec.get('params') or {})

    cls = getattr(data_types, name, None)

    if cls is None or cls is data_types.DataType:
        return None

    if name == 'DateTime' and params.get('timezone'):
        try:
            from zoneinfo import ZoneInfo

            params['timezone'] = ZoneInfo(params['timezone'])
        except Exception:
            params['timezone'] = None

    try:
        return cls(**params)
    except Exception:
        return None


def parse_type(column_type):
    """
    Return a :class:`.DataType` that can parse agate's canonical CSV output
    (what each type's :meth:`.DataType.csvify` writes) for values of the given
    type.

    This is needed because the canonical serialization is not always
    re-parseable by the original type instance: a ``Number(locale='de_DE')``
    would read ``1234.56`` as ``123456`` and a ``Date(date_format='%d/%m/%Y')``
    can not parse the ISO format that :meth:`~.Date.csvify` writes.
    """
    null_values = list(column_type.null_values)

    if isinstance(column_type, data_types.Number):
        return data_types.Number(null_values=null_values)
    if isinstance(column_type, data_types.Boolean):
        return data_types.Boolean(null_values=null_values)
    if isinstance(column_type, data_types.DateTime):
        return data_types.DateTime(null_values=null_values)
    if isinstance(column_type, data_types.Date):
        return data_types.Date(null_values=null_values)
    if isinstance(column_type, data_types.TimeDelta):
        return data_types.TimeDelta(null_values=null_values)
    if isinstance(column_type, data_types.Text):
        return data_types.Text(cast_nulls=column_type.cast_nulls, null_values=null_values)

    return data_types.Text(null_values=null_values)


def serialize_key(key_type, key):
    """
    Serialize a TableSet key to a JSON-safe value using the set's key type.
    """
    if key is None:
        return None

    return str(key_type.csvify(key))


def deserialize_key(parse_key_type, value):
    """
    Restore a key serialized by :func:`serialize_key`. The canonical parse
    type (see :func:`parse_type`) of the set's key type must be used so that
    e.g. localized numbers and ISO dates parse correctly.
    """
    if value is None:
        return None

    return parse_key_type.cast(value)


def safe_name(key, used, extension):
    """
    Generate a filesystem-safe file or directory name for a TableSet key.

    Plain string keys keep their natural ``<key><extension>`` form so the
    resulting files stay friendly to open by hand. Keys containing path
    separators, empty keys and non-string keys are mapped to safe names and
    deduplicated against names already in :code:`used`. The original key is
    always recoverable from the manifest.
    """
    if isinstance(key, str):
        name = key
    elif key is None:
        name = 'None'
    else:
        name = str(key)

    name = name.replace('/', '_').replace('\\', '_').replace('\0', '_')

    if not name or name in ('.', '..'):
        name = '_'

    candidate = '%s%s' % (name, extension)
    i = 2

    while candidate.casefold() in used:
        candidate = '%s_%d%s' % (name, i, extension)
        i += 1

    used.add(candidate.casefold())

    return candidate


def manifest_path(dir_path):
    """
    Path to the manifest file within a TableSet CSV directory.
    """
    return os.path.join(dir_path, MANIFEST_FILENAME)
