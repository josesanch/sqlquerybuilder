import unittest
import datetime
from . import Q, Queryset, F


class TestSqlBuilder(unittest.TestCase):

    def test_q(self):
        self.assertEqual(str(Q(a=1)), "(a=1)")
        self.assertEqual(str(Q(a=1) & ~Q(b=2)), "((a=1) AND NOT (b=2))")
        self.assertEqual(str(Q(nombre="jose")), "(nombre='jose')")
        self.assertEqual(str(Q(a__isnull=True)), "(a is NULL)")
        self.assertEqual(str(Q(a__isnull=False)), "(a is NOT NULL)")

    def test_dates(self):
        date = datetime.date(2010, 1, 15)
        self.assertEqual(str(Q(fecha=date)), "(fecha='2010-01-15')")

        date = datetime.datetime(2010, 1, 15, 23, 59, 38)
        self.assertEqual(str(Q(fecha=date)), "(fecha='2010-01-15 23:59:38')")

        self.assertEqual(str(Q(fecha__year__lte=2012)), "(DATEPART('year', fecha)<=2012)")
        self.assertEqual(str(Q(fecha__year=2012)), "(DATEPART('year', fecha)=2012)")

    def test_limits(self):
        self.assertEqual(Queryset("table")[:10].get_limits(), "LIMIT 10")
        self.assertEqual(Queryset("table")[1:10].get_limits(), "LIMIT 9 OFFSET 1")

    def test_compound(self):
        qs = Queryset("users", "SQL_SERVER")\
            .filter(nombre="jose")\
            .order_by( "nombre", "-fecha")\
            .filter(fecha__lte=F("now()"))[:10]

        self.assertEqual(
            str(qs), "SELECT TOP 10 * FROM users WHERE ((nombre='jose') AND (fecha<=now())) ORDER BY nombre, fecha DESC")

        qs = Queryset("users")\
            .filter(nombre="jose")\
            .order_by( "nombre", "-fecha")\
            .filter(fecha__lte=F("now()"))[:10]

        self.assertEqual(
            str(qs), "SELECT * FROM users WHERE ((nombre='jose') AND (fecha<=now())) ORDER BY nombre, fecha DESC LIMIT 10")


if __name__ == '__main__':
    unittest.main()