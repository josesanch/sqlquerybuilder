import unittest
import datetime
from sqlquerybuilder import Q, Queryset, F


class TestSqlBuilder(unittest.TestCase):

    def test_q(self):
        self.assertEqual(str(Q(a=1)), "(a=1)")
        self.assertEqual(str(Q(a=1) & ~Q(b=2)), "((a=1) AND NOT (b=2))")
        self.assertEqual(str(Q(nombre="jose")), "(nombre='jose')")
        self.assertEqual(str(Q(a__isnull=True)), "(a is NULL)")
        self.assertEqual(str(Q(a__isnull=False)), "(a is NOT NULL)")

        self.assertEqual(str(Q(a__startswith="a")), "(a LIKE BINARY 'a%')")
        self.assertEqual(str(Q(a__istartswith="a")), "(a LIKE 'a%')")

        self.assertEqual(str(Q(a__endswith="a")), "(a LIKE BINARY '%a')")
        self.assertEqual(str(Q(a__iendswith="a")), "(a LIKE '%a')")

        self.assertEqual(str(Q(a__contains="a")), "(a LIKE BINARY '%a%')")
        self.assertEqual(str(Q(a__icontains="a")), "(a LIKE '%a%')")

    def test_dates(self):
        date = datetime.date(2010, 1, 15)
        self.assertEqual(str(Q(fecha=date)), "(fecha='2010-01-15')")

        date = datetime.datetime(2010, 1, 15, 23, 59, 38)
        self.assertEqual(str(Q(fecha=date)), "(fecha='2010-01-15 23:59:38')")

        self.assertEqual(str(Q(fecha__year__lte=2012)), "(DATEPART(year, fecha)<=2012)")
        self.assertEqual(str(Q(fecha__year=2012)), "(DATEPART(year, fecha)=2012)")

    def test_limits(self):
        self.assertEqual(Queryset("table")[:10].get_limits(), "LIMIT 10")
        self.assertEqual(Queryset("table")[1:10].get_limits(), "LIMIT 9 OFFSET 1")

    def test_compound(self):
        qs = Queryset("users", "SQL_SERVER")\
            .filter(nombre="jose")\
            .order_by("nombre", "-fecha")\
            .filter(fecha__lte=F("now()"))[:10]

        self.assertEqual(
            str(qs), "SELECT TOP 10 * FROM users WHERE ((nombre='jose') AND (fecha<=now())) ORDER BY nombre, fecha DESC")

        qs = Queryset("users")\
            .filter(nombre="jose")\
            .order_by( "nombre", "-fecha")\
            .filter(fecha__lte=F("now()"))[:10]

        self.assertEqual(
            str(qs), "SELECT * FROM users WHERE ((nombre='jose') AND (fecha<=now())) ORDER BY nombre, fecha DESC LIMIT 10")

    def test_vars(self):
        sql = Queryset("users")
        sql = sql.filter(name="jhon")
        sql = sql.exclude(date__year__lte=1977)
        sql = sql.values("name", "date")
        self.assertEqual(
            str(sql), "SELECT name, date FROM users WHERE ((name='jhon') AND NOT (DATEPART(year, date)<=1977))")

        sql = sql.values("name", "date", "tlf")
        sql.filter(name="not")
        sql.filter(name="not")
        self.assertEqual(
            str(sql), "SELECT name, date, tlf FROM users WHERE ((name='jhon') AND NOT (DATEPART(year, date)<=1977))")

    def test_extra(self):
        sql = Queryset("users").values("name", "date", "tlf")
        sql = sql.extra({'select': 'count(*) as total'})
        self.assertEqual(
            str(sql), "SELECT name, date, tlf, count(*) as total FROM users")

        sql = Queryset("users")
        sql = sql.extra(where=["id=1", "name='jose'"])
        sql = sql.extra(select="count(*) as total")
        self.assertEqual(
            str(sql), "SELECT *, count(*) as total FROM users WHERE id=1 AND name='jose'")

        sql = sql.values(*[])
        self.assertEqual(
            str(sql), "SELECT count(*) as total FROM users WHERE id=1 AND name='jose'")

    def test_in(self,):
        sql = Queryset("users")
        sql = sql.filter(name__in=["jose", "andres"])
        self.assertEqual(
            str(sql), "SELECT * FROM users WHERE (name in ('jose', 'andres'))")

        sql = Queryset("users")
        sql = sql.filter(year__in=[2012, 2014, u"José"])
        self.assertEqual(
            unicode(sql), u"SELECT * FROM users WHERE (year in (2012, 2014, 'José'))")

        user = Queryset("users").filter(id=100).values("id")
        self.assertEqual(str(user), "SELECT id FROM users WHERE (id=100)")

        invoices = Queryset("invoices").filter(user_id__in=user)
        self.assertEqual(
            str(invoices), "SELECT * FROM invoices WHERE (user_id in (SELECT id FROM users WHERE (id=100)))")

if __name__ == '__main__':
    unittest.main()
