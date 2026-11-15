import json
import os

from agate.tableset.csv_manifest import (MANIFEST_FORMAT, MANIFEST_VERSION, manifest_path, safe_name, serialize_key,
                                         serialize_type)


def to_csv(self, dir_path, **kwargs):
    """
    Write each table in this set to a separate CSV in a given
    directory.

    In addition to the CSV files, a manifest file is written to the
    directory recording the keys (in order), the key name, the key type and
    the column types of this set. :meth:`.TableSet.from_csv` uses it to
    restore all of that metadata, so a set written with this method can be
    read back identically.

    Tables whose keys are plain strings are written to ``<key>.csv``. Keys
    that are not strings, are empty, or contain path separators are mapped to
    safe filenames; the mapping is recorded in the manifest.

    See :meth:`.Table.to_csv` for additional details.

    :param dir_path:
        Path to the directory to write the CSV files to.
    """
    from agate.tableset import TableSet

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    used = set()
    entries = []

    for key, table in self.items():
        if isinstance(table, TableSet):
            name = safe_name(key, used, '')

            table.to_csv(os.path.join(dir_path, name), **kwargs)

            entries.append({
                'key': serialize_key(self._key_type, key),
                'directory': name
            })
        else:
            name = safe_name(key, used, '.csv')

            table.to_csv(os.path.join(dir_path, name), **kwargs)

            entries.append({
                'key': serialize_key(self._key_type, key),
                'file': name
            })

    manifest = {
        'format': MANIFEST_FORMAT,
        'version': MANIFEST_VERSION,
        'key_name': self._key_name,
        'key_type': serialize_type(self._key_type),
        'column_names': list(self._column_names),
        'column_types': [serialize_type(column_type) for column_type in self._column_types],
        'tables': entries
    }

    with open(manifest_path(dir_path), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
