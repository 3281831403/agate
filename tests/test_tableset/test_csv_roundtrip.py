import datetime
import os
import shutil
from collections import OrderedDict
from decimal import Decimal

from agate import Table, TableSet
from agate.data_types import Boolean, Date, DateTime, Number, Text, TimeDelta
from agate.testcase import AgateTestCase


class TestCSVRoundTrip(AgateTestCase):
    """
    A TableSet written with to_csv must be restored identically by from_csv:
    keys (values, order and type), key_name, column types and row data.
    """
    def setUp(self):
        self.dir = '.test-tableset-roundtrip'

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def roundtrip(self, tableset):
        tableset.to_csv(self.dir)

        return TableSet.from_csv(self.dir)

    def assertTableSetsEqual(self, a, b):
        self.assertSequenceEqual(a.keys(), b.keys())
        self.assertEqual(a.key_name, b.key_name)
        self.assertIs(type(a.key_type), type(b.key_type))

        for key in a.keys():
            ta, tb = a[key], b[key]

            self.assertSequenceEqual(ta.column_names, tb.column_names)
            self.assertSequenceEqual(
                [type(t) for t in ta.column_types],
                [type(t) for t in tb.column_types]
            )

            for ra, rb in zip(ta.rows, tb.rows):
                self.assertSequenceEqual(ra, rb)

    def test_string_keys(self):
        table = Table([
            ('scores', 1), ('scores', 2), ('c', 3), ('a/b', 4), (None, 5), ('x', 6)
        ], ['grp', 'val'], [Text(), Number()])

        tableset = table.group_by('grp')

        # group_by can never produce an empty-string key, add one manually
        tables = OrderedDict(tableset.items())
        tables[''] = table.where(lambda r: r['grp'] == 'x')
        tableset = TableSet(tables.values(), tables.keys(), key_name='grp')

        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)
        self.assertSequenceEqual(list(back.keys()), ['scores', 'c', 'a/b', None, 'x', ''])

    def test_plain_names_keep_plain_files(self):
        table = Table([('one', 1), ('two', 2)], ['grp', 'val'], [Text(), Number()])

        table.group_by('grp').to_csv(self.dir)

        self.assertTrue(os.path.isfile(os.path.join(self.dir, 'one.csv')))
        self.assertTrue(os.path.isfile(os.path.join(self.dir, 'two.csv')))

    def test_single_row_and_empty_columns(self):
        # Inference would read 1/0 as Boolean and an all-null column as Text,
        # then fail on inconsistent column types across the set
        table = Table([
            ('x', 1, None),
            ('y', 0, None),
            ('z', 5, None)
        ], ['g', 'n', 'e'], [Text(), Number(), Number()])

        tableset = table.group_by('g')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)
        self.assertIsInstance(back['x'].columns['n'].data_type, Number)
        self.assertEqual(back['x'].rows[0]['n'], Decimal(1))
        self.assertIsNone(back['x'].rows[0]['e'])

    def test_locale_number_column(self):
        number_type = Number(locale='de_DE')

        table = Table([
            ('a', '1.234,56'),
            ('b', '7.890,12')
        ], ['g', 'n'], [Text(), number_type])

        tableset = table.group_by('g')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)
        self.assertEqual(back['a'].rows[0]['n'], Decimal('1234.56'))
        self.assertEqual(str(back['a'].columns['n'].data_type.locale), 'de_DE')

    def test_number_keys(self):
        table = Table([
            (Decimal('1.5'), 'x'),
            (Decimal('2.5'), 'y')
        ], ['k', 'v'], [Number(), Text()])

        tableset = table.group_by('k')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)
        self.assertSequenceEqual(back.keys(), [Decimal('1.5'), Decimal('2.5')])

    def test_date_keys(self):
        table = Table([
            (datetime.date(2026, 1, 1), 'x'),
            (datetime.date(2026, 1, 2), 'y')
        ], ['k', 'v'], [Date(), Text()])

        tableset = table.group_by('k')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)
        self.assertSequenceEqual(back.keys(), [datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)])

    def test_datetime_keys(self):
        table = Table([
            (datetime.datetime(2026, 1, 1, 12, 30), 'x'),
            (datetime.datetime(2026, 1, 2, 8, 0), 'y')
        ], ['k', 'v'], [DateTime(), Text()])

        tableset = table.group_by('k')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)

    def test_timedelta_keys(self):
        table = Table([
            (datetime.timedelta(hours=4, minutes=15), 'x'),
            (datetime.timedelta(days=1), 'y')
        ], ['k', 'v'], [TimeDelta(), Text()])

        tableset = table.group_by('k')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)

    def test_boolean_keys(self):
        table = Table([(True, 'x'), (False, 'y')], ['k', 'v'], [Boolean(), Text()])

        tableset = table.group_by('k')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)
        self.assertSequenceEqual(back.keys(), [True, False])

    def test_all_column_types(self):
        table = Table([
            ('a', 'x', 1, True, '2026-01-01', '2026-01-01 10:00', '4:15'),
            ('a', 'y', 2, False, '2026-01-02', '2026-01-02 11:00', '6:30'),
            ('b', 'z', 3, None, None, None, None)
        ], ['g', 't', 'n', 'b', 'd', 'dt', 'td'],
            [Text(), Text(), Number(), Boolean(), Date(), DateTime(), TimeDelta()])

        tableset = table.group_by('g')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)

    def test_colliding_safe_names(self):
        table = Table([
            ('a/b', 1),
            ('a_b', 2),
            ('a\\b', 3)
        ], ['g', 'n'], [Text(), Number()])

        tableset = table.group_by('g')
        back = self.roundtrip(tableset)

        self.assertTableSetsEqual(tableset, back)

    def test_nested_tableset(self):
        table = Table([
            ('r1', 'x', 1),
            ('r1', 'y', 2),
            ('r2', 'x', 3)
        ], ['region', 'sub', 'n'], [Text(), Text(), Number()])

        nested = table.group_by('region').group_by('sub')
        nested.to_csv(self.dir)

        back = TableSet.from_csv(self.dir)

        self.assertSequenceEqual(back.keys(), nested.keys())
        self.assertIsInstance(back['r1'], TableSet)
        self.assertSequenceEqual(back['r1'].keys(), nested['r1'].keys())
        self.assertEqual(back['r1']['x'].rows[0]['n'], 1)
        self.assertEqual(back['r2']['x'].rows[0]['n'], 3)

    def test_legacy_directory_without_manifest(self):
        tableset = TableSet.from_csv('examples/tableset', ['letter', 'number'])

        self.assertSequenceEqual(sorted(tableset.keys()), ['table1', 'table2', 'table3'])
        self.assertSequenceEqual(tableset['table1'].rows[0], ('a', 1))

    def test_legacy_type_error_still_raises(self):
        with self.assertRaises(ValueError):
            TableSet.from_csv('examples/tableset/type_error')
