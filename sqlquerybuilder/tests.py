#encoding: utf-8
"""
Unit tests for the sqlquerybuilder module.

This module contains a comprehensive suite of tests for verifying the
functionality of the SQL query builder library, including Q objects,
Queryset operations, SQL compilation, and parameter generation for
preventing SQL injection.
"""
from __future__ import unicode_literals
import unittest
import datetime
from sqlquerybuilder import Q, Queryset, F


class TestSqlBuilder(unittest.TestCase):
    """
    Test suite for the SQL query builder components.

    This class tests the functionality of Q objects for condition building,
    Queryset methods for constructing complex queries, and the SQL compilation
    process, including correct SQL string generation with placeholders and
    the associated parameter lists.
    """

    def test_q(self):
        """
        Tests the basic functionality of Q objects.

        This includes creating simple Q objects, combining them with AND (&)
        and NOT (~) operators, and verifying the generated SQL string and
        parameter lists for various lookup types (exact, isnull, startswith,
        endswith, contains, and their case-insensitive versions).
        """
        q_obj = Q(a=1)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a = %s)")
        self.assertEqual(params, [1])

        q_obj = Q(a=1) & ~Q(b=2)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "((a = %s) AND NOT (b = %s))")
        self.assertEqual(params, [1, 2])

        q_obj = Q(nombre="jose")
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(nombre = %s)")
        self.assertEqual(params, ["jose"])

        q_obj = Q(a__isnull=True)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a IS NULL)")
        self.assertEqual(params, [])

        q_obj = Q(a__isnull=False)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a IS NOT NULL)")
        self.assertEqual(params, [])

        q_obj = Q(a__startswith="a")
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a LIKE BINARY %s)")
        self.assertEqual(params, ["a%"])

        q_obj = Q(a__istartswith="a")
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a LIKE %s)")
        self.assertEqual(params, ["a%"])

        q_obj = Q(a__endswith="a")
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a LIKE BINARY %s)")
        self.assertEqual(params, ["%a"])

        q_obj = Q(a__iendswith="a")
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a LIKE %s)")
        self.assertEqual(params, ["%a"])

        q_obj = Q(a__contains="a")
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a LIKE BINARY %s)")
        self.assertEqual(params, ["%a%"])

        q_obj = Q(a__icontains="a")
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(a LIKE %s)")
        self.assertEqual(params, ["%a%"])

    def test_dates(self):
        """
        Tests Q object functionality with date and datetime values.

        Verifies that date and datetime objects are correctly parameterized and
        that date-specific lookups (like year__lte, year) generate the
        correct SQL (using DATEPART for compatibility) and parameters.
        """
        date_val = datetime.date(2010, 1, 15)
        q_obj = Q(fecha=date_val)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(fecha = %s)")
        self.assertEqual(params, [date_val])

        datetime_val = datetime.datetime(2010, 1, 15, 23, 59, 38)
        q_obj = Q(fecha=datetime_val)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(fecha = %s)")
        self.assertEqual(params, [datetime_val])

        # For DATEPART, the value being compared should be a parameter
        q_obj = Q(fecha__year__lte=2012)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(DATEPART(year, fecha) <= %s)")
        self.assertEqual(params, [2012])

        q_obj = Q(fecha__year=2012)
        sql, params = q_obj._compile()
        self.assertEqual(sql, "(DATEPART(year, fecha) = %s)")
        self.assertEqual(params, [2012])

    def test_limits(self):
        """
        Tests the limit and offset functionality of Queryset.

        Verifies that slicing a Queryset correctly generates the LIMIT and OFFSET
        clauses in the SQL. It also checks that the `.get_limits()` helper method
        returns the correct string fragment and that the overall compiled query
        (SQL and params) is accurate. Parameters are not expected from limits themselves.
        """
        # .get_limits() is an internal helper for SQL string construction,
        # it does not deal with parameters directly. No change needed here if it only returns strings.
        # However, the overall Queryset().sql will be (sql, params)
        qs = Queryset("table")[:10]
        self.assertEqual(qs.get_limits(), "LIMIT 10")
        sql, params = qs.sql
        self.assertEqual(sql, "SELECT * FROM table LIMIT 10")
        self.assertEqual(params, [])


        qs = Queryset("table")[1:10]
        self.assertEqual(qs.get_limits(), "LIMIT 9 OFFSET 1")
        sql, params = qs.sql
        self.assertEqual(sql, "SELECT * FROM table LIMIT 9 OFFSET 1")
        self.assertEqual(params, [])


    def test_compound(self):
        """
        Tests building more complex queries with multiple clauses.

        This includes filtering, ordering, using F objects (for raw SQL
        expressions like 'now()'), and slicing for limits, for both
        SQL Server and default (MySQL/PostgreSQL-like) SQL modes.
        Verifies the generated SQL string and parameter lists.
        """
        qs = Queryset("users", "SQL_SERVER")\
            .filter(nombre="jose")\
            .order_by("nombre", "-fecha")\
            .filter(fecha__lte=F("now()"))[:10] # F("now()") is not parameterized

        sql, params = qs.sql
        self.assertEqual(
            sql, "SELECT TOP 10 * FROM users WHERE ((nombre = %s) AND (fecha <= now())) ORDER BY nombre, fecha DESC")
        self.assertEqual(params, ["jose"])

        qs = Queryset("users")\
            .filter(nombre="jose")\
            .order_by( "nombre", "-fecha")\
            .filter(fecha__lte=F("now()"))[:10]

        sql, params = qs.sql
        self.assertEqual(
            sql, "SELECT * FROM users WHERE ((nombre = %s) AND (fecha <= now())) ORDER BY nombre, fecha DESC LIMIT 10")
        self.assertEqual(params, ["jose"])

    def test_vars(self):
        """
        Tests query construction with chained filter, exclude, and values calls.

        Verifies that conditions are correctly ANDed, NOTed (for exclude),
        and that parameters are aggregated in the correct order. Also checks
        that selected columns are reflected in the final SQL.
        """
        sql_qs = Queryset("users")
        sql_qs = sql_qs.filter(name="jhon")
        sql_qs = sql_qs.exclude(date__year__lte=1977)
        sql_qs = sql_qs.values("name", "date")

        sql, params = sql_qs.sql
        self.assertEqual(
            sql, "SELECT name, date FROM users WHERE ((name = %s) AND NOT (DATEPART(year, date) <= %s))")
        self.assertEqual(params, ["jhon", 1977])

        # Test that filter() is ANDed correctly and params are aggregated
        # Test that filter() is ANDed correctly and params are aggregated
        # Re-assign sql_qs after .values() to ensure further filters apply to the correct object state
        sql_qs = sql_qs.values("name", "date", "tlf")
        sql_after_values, params_after_values = sql_qs.sql

        # Now add another filter
        sql_qs_filtered = sql_qs.filter(name="not")
        sql_f, params_f = sql_qs_filtered.sql

        # Parameters should be from the state after exclude() and the new filter()
        # Initial: name="jhon" -> ["jhon"]
        # Exclude: date__year__lte=1977 -> ["jhon", 1977]
        # Parameters order will be from _filters then _excludes.
        # _filters is (Q(name="jhon") & Q(name="not")), so params ["jhon", "not"]
        # _excludes is Q(date__year__lte=1977), so params [1977] for the NOT part.
        # So, combined params from (_filters & ~_excludes) should be ["jhon", "not", 1977].
        expected_params = ["jhon", "not", 1977]
        # The SQL structure is ((filter1 AND filter2) AND NOT exclude1)
        expected_sql_substring = "(((name = %s) AND (name = %s)) AND NOT (DATEPART(year, date) <= %s))"
        self.assertTrue(expected_sql_substring in sql_f)
        self.assertEqual(params_f, expected_params)

        # Verify the selected columns are correct after re-assigning sql_qs
        self.assertTrue(sql_f.startswith("SELECT name, date, tlf FROM users"))


    def test_extra(self):
        """
        Tests the `extra()` method for adding raw SQL snippets.

        Confirms that `extra()` can be used to add custom selections and
        WHERE clauses. It also notes that these raw SQL snippets are not
        parameterized by the current refactoring, which focuses on Q objects.
        Parameters are expected to be empty for queries solely using `extra`.
        """
        # .extra() method as currently implemented seems to inject raw SQL.
        # This test might highlight that .extra() is not subject to parameterization by this refactoring.
        # This is acceptable as the focus is on Q objects.
        sql_qs = Queryset("users").values("name", "date", "tlf")
        sql_qs = sql_qs.extra({'select': 'count(*) as total'})

        sql, params = sql_qs.sql
        self.assertEqual(
            sql, "SELECT name, date, tlf, count(*) as total FROM users")
        self.assertEqual(params, []) # No params from .extra select

        sql_qs = Queryset("users")
        sql_qs = sql_qs.extra(where=["id=1", "name='jose'"]) # These are raw SQL, not parameterized
        sql_qs = sql_qs.extra(select="count(*) as total")

        sql, params = sql_qs.sql
        # The 'extra' where clauses are joined by AND with Q-generated clauses.
        # Since there are no Q-generated clauses here, it's just the extra "WHERE id=1 AND name='jose'"
        self.assertEqual(
            sql, "SELECT *, count(*) as total FROM users WHERE id=1 AND name='jose'")
        self.assertEqual(params, [])

        sql_qs = sql_qs.values(*[]) # Clear values to only select the extra
        sql, params = sql_qs.sql
        self.assertEqual(
            sql, "SELECT count(*) as total FROM users WHERE id=1 AND name='jose'")
        self.assertEqual(params, [])

    def test_in(self,):
        """
        Tests the 'in' lookup type for WHERE clauses.

        Verifies correct SQL generation (e.g., "col IN (%s, %s)") and parameter
        collection for lists of values.
        Also tests using a subquery (another Queryset) in an IN clause,
        ensuring the subquery's SQL is correctly embedded and its parameters
        are prepended to the main query's parameters.
        Additionally, tests IN clauses with F objects and lists containing F objects.
        """
        sql_qs = Queryset("users")
        sql_qs = sql_qs.filter(name__in=["jose", "andres"])
        sql, params = sql_qs.sql
        self.assertEqual(
            sql, "SELECT * FROM users WHERE (name IN (%s, %s))")
        self.assertEqual(params, ["jose", "andres"])

        sql_qs = Queryset("users")
        sql_qs = sql_qs.filter(year__in=[2012, 2014, "Jose"]) # Mixed types
        sql, params = sql_qs.sql
        self.assertEqual(sql, "SELECT * FROM users WHERE (year IN (%s, %s, %s))")
        self.assertEqual(params, [2012, 2014, "Jose"])

        # Test with a subquery from another Queryset for IN clause
        # The inner Queryset (user_qs) will produce its own SQL and params
        # The outer Queryset (invoices_qs) should embed the inner SQL
        # and incorporate its params before its own.
        user_qs = Queryset("users").filter(id=100).values("id")
        user_sql, user_params = user_qs.sql
        self.assertEqual(user_sql, "SELECT id FROM users WHERE (id = %s)")
        self.assertEqual(user_params, [100])

        invoices_qs = Queryset("invoices").filter(user_id__in=user_qs)
        inv_sql, inv_params = invoices_qs.sql
        expected_inv_sql = "SELECT * FROM invoices WHERE (user_id IN (SELECT id FROM users WHERE (id = %s)))"
        self.assertEqual(inv_sql, expected_inv_sql)
        self.assertEqual(inv_params, [100]) # Params from the inner query

        # Test IN with an F object (not typically parameterized itself, but value of F might be)
        # This specific F object usage (column name) doesn't add params
        invoices_qs_f = Queryset("invoices").filter(user_id__in=F('some_column'))
        inv_f_sql, inv_f_params = invoices_qs_f.sql
        self.assertEqual(inv_f_sql, "SELECT * FROM invoices WHERE (user_id IN (some_column))")
        self.assertEqual(inv_f_params, [])

        # Test IN with a list containing an F object
        # The F object is part of the SQL, other items are params
        complex_in_qs = Queryset("data").filter(val__in=[1, F('another_col'), 3])
        ci_sql, ci_params = complex_in_qs.sql
        self.assertEqual(ci_sql, "SELECT * FROM data WHERE (val IN (%s, another_col, %s))")
        self.assertEqual(ci_params, [1, 3])

if __name__ == '__main__':
    unittest.main()
