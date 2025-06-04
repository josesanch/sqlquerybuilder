"""
A Python library for dynamically constructing SQL queries in a safe and flexible manner.

This module provides classes for building SQL queries programmatically,
focusing on preventing SQL injection vulnerabilities by using parameterized queries.
It allows for complex WHERE clauses, joins, ordering, grouping, and more.
"""
from __future__ import unicode_literals
import sys
import copy
import datetime

PYTHON3 = True
if sys.version_info[0] < 3:
    PYTHON3 = False

VERSION = "0.0.13"


def is_map(obj):
    """
    Checks if an object is a map object in Python 3.

    Args:
        obj: The object to check.

    Returns:
        bool: True if the object is a map, False otherwise.
    """
    return PYTHON3 and isinstance(obj, map)


def ensureUtf(s):
    """
    Ensures a string is UTF-8 encoded.

    Args:
        s: The input string or bytes.

    Returns:
        str: A UTF-8 encoded string.
    """
    try:
        if isinstance(s, str):
            return s
        else:
            return s.encode('utf8', 'ignore')
    except BaseException:
        return str(s)


class classproperty(object):
    """
    Decorator that converts a method with a single cls argument into a class property.

    Similar to @property, but for class-level attributes.
    """

    def __init__(self, getter):
        """
        Initializes the classproperty decorator.

        Args:
            getter: The function to be decorated.
        """
        self.getter = getter

    def __get__(self, instance, owner):
        """
        Called when the decorated property is accessed.

        Args:
            instance: The instance through which the property is accessed (None for class access).
            owner: The owner class.

        Returns:
            The result of calling the getter function with the owner class.
        """
        return self.getter(owner)


class QMixin(object):
    """
    A mixin class providing common boolean operations (&, |, ~) for Q-like objects.

    These operations allow for combining query conditions using AND, OR, and NOT logic.
    It also defines constants for these operators and UNION.
    """
    AND = 'AND'
    OR = 'OR'
    NOT = 'NOT'
    UNION = 'UNION'

    def _combine(self, other, conn):
        return Operator(conn, self, other)

    def __or__(self, other):
        if isinstance(other, Queryset):
            return self._combine(other, self.UNION)
        return self._combine(other, self.OR)

    def __and__(self, other):
        return self._combine(other, self.AND)

    def __invert__(self,):
        """
        Implements the NOT (~) operator for Q-like objects.

        Returns:
            Operator: An Operator instance representing the NOT condition.
        """
        return Operator(self.NOT, self)


class Operator(QMixin):
    """
    Represents a logical operator (AND, OR, NOT) combining query conditions.

    Operator objects are typically created by using &, |, or ~ on Q or Operator
    instances. They store the operator and the left/right operands.
    The `_compile` method generates the SQL string and parameters for the operation.
    """

    def __init__(self, op=None, left=None, right=None):
        """
        Initializes an Operator instance.

        Args:
            op (str, optional): The logical operator (e.g., 'AND', 'OR', 'NOT').
            left (QMixin, optional): The left operand (another Q or Operator instance).
            right (QMixin, optional): The right operand (another Q or Operator instance).
        """
        self.op = op
        self.left = left
        self.right = right
        self.params = []
        # Call _compile to ensure params are populated when an Operator is created
        # This is important if an Operator is used directly or its params are
        # accessed.
        self._compile()

    def _compile(self):
        """
        Compiles the operator into an SQL string and a list of parameters.
        Returns (sql_string, params_list)
        """
        left_sql, left_params = "", []
        if self.left:
            if hasattr(self.left, '_compile'):
                left_sql, left_params = self.left._compile()
            else:  # Should ideally not happen if operands are Q or Operator
                left_sql = str(self.left)

        right_sql, right_params = "", []
        if self.right:
            if hasattr(self.right, '_compile'):
                right_sql, right_params = self.right._compile()
            else:  # Should ideally not happen
                right_sql = str(self.right)

        self.params = left_params + right_params

        if self.left and self.right:
            # e.g., (Q_obj1 AND Q_obj2)
            return "(%s %s %s)" % (left_sql, self.op, right_sql), self.params
        if self.right:
            # This case is unusual for binary operators but could be for unary if 'left' is op
            # More relevant for NOT: if op is NOT and left is None, right is the operand
            # However, current __invert__ makes Operator(self.NOT, self), so
            # left is operand
            # Should typically be covered by NOT case
            return "%s" % (right_sql), self.params
        if self.left and self.op == self.NOT:  # NOT operator
            # e.g., NOT Q_obj
            return "%s %s" % (self.op, left_sql), self.params

        # Fallback or if only left is present (e.g. representing a single Q
        # object)
        return "%s" % left_sql, self.params

    def __repr__(self,):
        # As per instructions, tests will be updated.
        # So __repr__ should reflect the final string output.
        sql, _ = self._compile()
        return sql

    __str__ = __repr__

    def __bool__(self):
        return bool(self.right or self.left)

    __nonzero__ = __bool__


class F(object):
    """
    Represents an SQL expression or function call.

    F objects are used to refer to model fields or database functions directly
    in query construction, without them being treated as literal string values
    that need escaping or parameterization in the same way typical values are.
    For example, `F('col_name')` would refer to the column `col_name`, or
    `F('NOW()')` would insert the `NOW()` function call into the SQL.

    Currently, F objects themselves do not contribute parameters to the query.
    """

    def __init__(self, value):
        """
        Initializes an F object.

        Args:
            value (str): The SQL expression or field name.
        """
        self.value = value

    def __repr__(self,):
        """
        Returns the string representation of the F object, which is its SQL value.
        """
        return "%s" % self.value

    __str__ = __repr__

    def __bool__(self):
        return bool(self.value)

    __nonzero__ = __bool__


class Q(QMixin):
    """
    Represents a query condition or a group of conditions.

    Q objects are used to build complex WHERE clauses by specifying field lookups
    and values. They can be combined using logical operators (&, |, ~).
    Internally, Q objects compile into an SQL string fragment with placeholders
    and a list of parameters to be used by the database driver, preventing
    SQL injection.

    Examples:
        Q(name="John")  # name = 'John'
        Q(age__gte=18)  # age >= 18
        Q(name="John") & Q(age__gte=18)  # (name = 'John' AND age >= 18)
    """
    _mode = "MYSQL"  # Default SQL mode, can be overridden by Queryset

    lookup_types = [
        'icontains', 'istartswith', 'iendswith',
        'contains', 'startswith', 'endswith',
        'year', 'month', 'day', 'week_day', 'hour', 'minute', 'second',
        'isnull', 'in']

    op_map = {
        'lte': '<=',
        'gte': '>=',
        'lt': '<',
        'gt': '>',
    }

    def __init__(self, *args, **kwargs):
        """
        Initializes a Q object.

        Conditions can be specified as keyword arguments (e.g., `name="John"`,
        `age__gte=18`) or as string arguments for simple existence checks
        (though less common with parameterized queries).

        Args:
            *args: Condition arguments (e.g., "name", "age__gte").
                   Typically used if the value is None or for specific lookups
                   like `isnull` where the value is boolean.
            **kwargs: Keyword arguments representing conditions (e.g., `name="value"`).
                      This is the most common way to define conditions.
        """
        self.conditions = kwargs
        for arg in args:
            # For args like Q('name__isnull'), the value is often passed in kwargs.
            # If an arg is passed without a kwarg value, it implies a specific
            # handling, often for `None` or boolean lookups.
            if arg not in self.conditions:
                self.conditions[arg] = None
        self.params = []  # Initialize params list, populated by _compile

    def __repr__(self,):
        """
        Returns the SQL string representation of the Q object.

        Note: This is primarily for debugging. For actual query execution,
        `_compile()` should be used to get both the SQL string and parameters.
        """
        # This will eventually be `sql, params = self._compile()`, returning sql for now
        # to minimize immediate breakage of unrelated tests.
        # However, the task requires _compile to return (sql, params)
        # and tests to be updated. So, let's reflect that.
        sql, _ = self._compile()
        return sql

    def __bool__(self):
        return bool(self.conditions)

    __nonzero__ = __bool__

    @property
    def date_format(self):
        if self._mode == 'SQL_SERVER':
            return "%Y-%d-%m"
        return "%Y-%m-%d"

    @property
    def datetime_format(self):
        if self._mode == 'SQL_SERVER':
            return "%Y-%d-%m %H:%M:%S"
        return "%Y-%m-%d %H:%M:%S"

    def _get_value(self, value):
        """
        Processes a value to determine its SQL representation and parameters.

        - For literal values (int, str, datetime, etc.), it returns a placeholder
          ('%s') and the value itself in a list (e.g., `("%s", [my_value])`).
        - For `SQLQuery` instances (subqueries), it compiles the subquery,
          returning its SQL string and its parameters.
        - For `F` objects, it returns the F object's string representation (raw SQL)
          and an empty parameter list.
        - For `Operator` (or `QMixin`) objects, it returns their string representation
          and their collected parameters.
        - For lists/sets (typically for 'IN' clauses), it recursively calls
          `_get_value` for each item, combining the SQL placeholders/fragments
          and parameters.

        Args:
            value: The value to process.

        Returns:
            tuple: A tuple containing:
                - str: The SQL string fragment or placeholder(s).
                - list: A list of parameters associated with the value.
        """
        if isinstance(
                value,
                SQLQuery):  # Handle SQLQuery specifically for subqueries
            # Explicitly clone the subquery before calling .sql on it
            # to ensure no state from a previous compilation (if any) interferes,
            # or no state from this compilation pollutes the original subquery object
            # if it's used elsewhere.
            cloned_value = value._clone()
            # .sql property returns (sql_str, params_list)
            sub_sql_str, sub_params_list = cloned_value.sql
            # Do not add extra parentheses here; the IN clause processing will
            # add them.
            return sub_sql_str, sub_params_list

        if isinstance(
                value, F) or isinstance(
                value, QMixin):  # Handles F and Operator
            # F objects don't have params.
            # Operator objects have their params on self.params attribute due
            # to their own _compile.
            return ensureUtf(value), getattr(value, 'params', [])

        if isinstance(value, list) or isinstance(value, set) or is_map(value):
            placeholders = []
            params = []
            for item in value:
                # Recursively call _get_value for each item in the list
                # This handles cases like a list of F objects or a list of
                # actual values
                item_placeholder, item_params = self._get_value(item)
                placeholders.append(item_placeholder)
                # item_params would be [item_value] or []
                params.extend(item_params)
            return ", ".join(placeholders), params

        # For all other types, return '%s' and the value in a list
        return "%s", [value]

    def _process(self, compose_column, value):
        """
        Processes a single column-value condition and generates its SQL and parameters.

        It parses the `compose_column` string (e.g., "name__startswith") to
        extract the column name and lookup type (e.g., "startswith", "gte").
        Based on the lookup type, it formats the SQL condition string with
        placeholders and collects the corresponding parameters using `_get_value`.

        Args:
            compose_column (str): The condition string, potentially including
                                  lookup types (e.g., "field__type").
            value: The value for the condition.

        Returns:
            tuple: A tuple containing:
                - str: The SQL fragment for this condition (e.g., "name LIKE %s").
                - list: A list of parameters for this condition (e.g., ["John%"]).
        """
        arr = compose_column.split("__")
        column = arr.pop(0)
        if column == '':  # Handle cases like __exact=value
            column += "__" + arr.pop(0)

        params = []
        try:
            lookup = arr.pop(0)
        except IndexError:
            lookup = None

        # Special handling for F objects, QMixin, SQLQuery - they don't use
        # placeholders themselves
        # This initial check for F, QMixin, SQLQuery as direct values is primarily
        # to ensure that _get_value is called on them if they are part of, for example,
        # a list in an IN clause. The actual parameter collection for these
        # types (especially SQLQuery and Operator) happens within _get_value.
        # For simple cases like Q(name=F('other_column')), the F object is
        # handled by _get_value called during _handle_default_lookup or _handle_comparison_lookup.
        # This block doesn't directly add params; _get_value does.
        if isinstance(value, (F, QMixin, SQLQuery)):
            pass # _get_value will be called by the specific handlers.

        # --- String Lookups ---
        if lookup in ('icontains', 'istartswith', 'iendswith',
                      'contains', 'startswith', 'endswith'):
            return self._handle_string_lookup(column, lookup, value)

        # --- IN Lookup ---
        if lookup == "in":
            return self._handle_in_lookup(column, value)

        # --- ISNULL Lookup ---
        if lookup == 'isnull':
            return self._handle_isnull_lookup(column, value)

        # --- Date Lookups ---
        if lookup in ('year', 'month', 'day', 'hour', 'minute', 'second'):
            # arr contains remaining parts of lookup, e.g., ['gte'] for 'year__gte'
            # or is empty for just 'year'
            return self._handle_date_lookup(column, [lookup] + arr, value)

        # --- Comparison Lookups (gte, lte, gt, lt) ---
        if lookup in self.op_map:
            return self._handle_comparison_lookup(column, lookup, value)

        # --- Default Lookup (equality or existence) ---
        # This is reached if lookup is None (e.g., Q(name="value"))
        # or if lookup was not any of the above special types (e.g. Q(name__exact="value") - 'exact' is not special)
        # If lookup is not None here, it implies an exact match or a lookup not explicitly handled above.
        # The original code effectively treated unhandled lookups as equality if value was not None.
        if lookup is None or lookup == 'exact' or lookup == 'iexact': # Treat 'exact' and 'iexact' as default equality too
            return self._handle_default_lookup(column, value)

        # If lookup is something else not covered (e.g. a typo or unsupported lookup),
        # it might fall through to just returning the column name if value is None.
        # Or, if strict, raise an error. Current behavior is to try default lookup.
        # If value is None at this point (e.g. Q("name") ), it's an existence check.
        if value is None:
             return column, [] # Existence check for the column itself

        # Fallback for any other unhandled lookup type with a value: treat as equality
        return self._handle_default_lookup(column, value)


    # --- Helper methods for _process ---

    def _handle_string_lookup(self, column, lookup, value):
        """
        Handles string-based lookups (LIKE, BINARY LIKE).
        e.g., 'contains', 'startswith', 'icontains'.
        """
        params = []
        sql_format = ""
        param_value_format = "{0}"
        binary = ""

        if lookup.startswith("i"):  # Case-insensitive
            lookup = lookup[1:]
        else:  # Case-sensitive
            binary = " BINARY" # For MySQL style LIKE BINARY

        if lookup == "contains":
            sql_format = "{0} LIKE{1} %s"
            param_value_format = "%{0}%"
        elif lookup == "startswith":
            sql_format = "{0} LIKE{1} %s"
            param_value_format = "{0}%"
        elif lookup == "endswith":
            sql_format = "{0} LIKE{1} %s"
            param_value_format = "%{0}"

        if not sql_format:
            # Should not happen if called correctly
            raise ValueError(f"Unsupported string lookup: {lookup}")

        placeholder, value_params = self._get_value(param_value_format.format(value))
        params.extend(value_params)
        return sql_format.format(column, binary), params

    def _handle_date_lookup(self, column, lookup_parts, value):
        """
        Handles date-based lookups (DATEPART).
        e.g., 'year', 'month__gte'.
        """
        params = []
        # lookup_parts is like ['year'], or ['year', 'gte']
        date_part = lookup_parts.pop(0)

        # Construct the DATEPART expression for the column
        # DATEPART syntax might vary slightly based on self._mode, but using generic for now
        # In the original code, it was DATEPART(part, column) for SQL Server.
        # For MySQL, it would be EXTRACT(part FROM column) or YEAR(column), MONTH(column) etc.
        # The original code used DATEPART for all, which is not universally correct but was the existing behavior.
        # We will stick to DATEPART as per original logic to avoid changing SQL dialect specifics here.
        datepart_column_expr = "DATEPART({0}, {1})".format(date_part, column)

        if not lookup_parts: # Direct equality, e.g., fecha__year=2020
            placeholder, value_params = self._get_value(value)
            params.extend(value_params)
            return "{0} = {1}".format(datepart_column_expr, placeholder), params
        else: # Chained lookup, e.g., fecha__year__gte=2020
            # The remaining part is the operator, e.g., 'gte'
            next_lookup = lookup_parts.pop(0)
            # Re-process with the DATEPART expression as the new "column"
            # This is a recursive call to the main _process logic with a modified column
            # and the next lookup part.
            # Example: _process("DATEPART(year, fecha)__gte", value)
            return self._process("{0}__{1}".format(datepart_column_expr, next_lookup), value)

    def _handle_isnull_lookup(self, column, value):
        """
        Handles 'isnull' lookups.
        """
        op = "IS"
        if not value:  # value is True for "IS NULL", False for "IS NOT NULL"
            op += " NOT"
        return "{0} {1} NULL".format(column, op), [] # No params for IS NULL

    def _handle_in_lookup(self, column, value):
        """
        Handles 'in' lookups.
        """
        params = []
        placeholders_str, value_params = self._get_value(value)
        params.extend(value_params)
        return "{0} IN ({1})".format(column, placeholders_str), params

    def _handle_comparison_lookup(self, column, lookup, value):
        """
        Handles comparison lookups (e.g., 'gte', 'lt').
        Uses self.op_map.
        """
        params = []
        placeholder, value_params = self._get_value(value)
        params.extend(value_params)
        return "{0} {1} {2}".format(column, self.op_map[lookup], placeholder), params

    def _handle_default_lookup(self, column, value):
        """
        Handles default equality lookup or existence check.
        """
        if value is not None:
            params = []
            placeholder, value_params = self._get_value(value)
            params.extend(value_params)
            return "{0} = {1}".format(column, placeholder), params
        return column, [] # For existence checks like Q('some_column')

    # --- End of helper methods ---

    def _compile(self,):
        """
        Compiles all conditions within this Q object into a single SQL string
        and an aggregated list of parameters.

        Conditions are joined by "AND". The resulting SQL string is typically
        enclosed in parentheses. This method is called recursively by `Operator`
        objects to build complex query structures.

        The parameters collected are stored in `self.params` and also returned.

        Returns:
            tuple: A tuple containing:
                - str: The compiled SQL string fragment for this Q object's conditions.
                - list: An aggregated list of parameters for all conditions.
        """
        filter_parts = []
        current_params = []
        for k, v in self.conditions.items():
            sql_part, item_params = self._process(k, v)
            filter_parts.append(sql_part)
            current_params.extend(item_params)

        self.params = current_params  # Store params on the Q object itself

        if not filter_parts:
            return "", []

        return "(%s)" % " AND ".join(filter_parts), current_params


class SQLQuery(object):
    """
    Represents a base SQL query structure that can be built upon.

    This class provides methods to define various parts of an SQL query such as
    selecting columns (`values`), filtering (`filter`, `exclude`), ordering
    (`order_by`), grouping (`group_by`), joining tables (`join`), and applying
    limits/offsets.

    It is not typically used directly by end-users but is inherited by `Queryset`.
    The methods in this class usually return a deep copy (clone) of the
    instance to allow for chaining and immutable query construction.
    """

    def __init__(self, table=None, sql_mode="MYSQL", sql=None, **kwargs):
        """
        Initializes an SQLQuery instance.

        Args:
            table (str, optional): The primary table name for the query.
            sql_mode (str, optional): The SQL dialect mode (e.g., "MYSQL", "SQL_SERVER").
                                      Defaults to "MYSQL". This affects date formatting
                                      and limit/offset clause generation.
            sql (str, optional): An initial raw SQL string to base this query on.
                                 Useful for creating a Queryset from an existing complex query.
            **kwargs: Additional keyword arguments (currently unused but captured).
        """
        self.kwargs = kwargs
        self._table = table
        self.sql_mode = sql_mode
        self._values = ["*"]
        self._order_by = []
        self._group_by = []
        self._joins = []
        self._filters = Q()  # Q object now has its own .params
        self._filters._mode = self.sql_mode
        self._excludes = Q()  # Q object now has its own .params
        self._excludes._mode = self.sql_mode
        self._extra = {}
        self._limits = None
        self._sql = sql
        self._nolock = False
        self.params = []  # For parameters collected by SQLCompiler

    def has_filters(self,):
        """
        Checks if the query has any clauses that would modify a simple "SELECT * FROM table".

        This includes filters, excludes, ordering, grouping, joins, custom column selections,
        limits, or extra clauses.

        Returns:
            bool: True if any such clauses are present, False otherwise.
        """
        return self._order_by or self._group_by or self._joins\
            or self._filters or self._excludes or self._extra \
            or self._limits or self._values != ['*']

    def _q(self, *args, **kwargs):
        """
        Helper method to create Q objects with the correct SQL mode.

        This ensures that Q objects created internally by the Queryset
        use the same SQL mode as the Queryset itself (important for date formatting, etc.).

        Args:
            *args: Positional arguments for the Q object.
            **kwargs: Keyword arguments for the Q object.

        Returns:
            Q: A Q object initialized with the Queryset's SQL mode.
        """
        conds = Q()
        conds._mode = self.sql_mode
        for arg in args:
            if issubclass(arg.__class__, QMixin):
                arg._mode = self.sql_mode
                conds &= arg

        _conds = Q(**kwargs)
        _conds._mode = self.sql_mode
        return conds & _conds

    def _clone(self,):
        """
        Creates a deep copy of the current SQLQuery instance.

        This is crucial for maintaining immutability when chaining query-building methods.

        Returns:
            SQLQuery: A deep copy of the instance.
        """
        return copy.deepcopy(self)

    def values(self, *args):
        """
        Specifies the columns to be selected in the query.

        If not called, defaults to selecting all columns ('*').

        Args:
            *args: A list of column names or expressions to select.

        Returns:
            SQLQuery: A new SQLQuery instance with the specified columns.
        """
        clone = self._clone()
        clone._values = list(args)
        return clone

    def with_nolock(self, enabled=True):
        """
        Enables or disables the 'WITH (NOLOCK)' hint (primarily for SQL Server).

        Args:
            enabled (bool, optional): True to enable NOLOCK, False to disable.
                                      Defaults to True.

        Returns:
            SQLQuery: A new SQLQuery instance with the NOLOCK hint setting.
        """
        clone = self._clone()
        clone._nolock = enabled
        return clone

    def filter(self, *args, **kwargs):
        """
        Adds filtering conditions (WHERE clause) to the query.

        Conditions are typically Q objects or keyword arguments that can be
        converted to Q objects. Multiple calls to filter() will AND the
        conditions together.

        Args:
            *args: Q objects or other filter arguments.
            **kwargs: Field lookups (e.g., `name="John"`, `age__gte=18`).

        Returns:
            SQLQuery: A new SQLQuery instance with the added filter conditions.
        """
        clone = self._clone()
        clone._filters &= self._q(*args, **kwargs)
        return clone

    def exclude(self, *args, **kwargs):
        """
        Adds exclusion conditions (NOT WHERE clause) to the query.

        These conditions specify records to exclude from the result set.
        Multiple calls to exclude() will AND the exclusion conditions together.

        Args:
            *args: Q objects or other filter arguments for exclusion.
            **kwargs: Field lookups for exclusion.

        Returns:
            SQLQuery: A new SQLQuery instance with the added exclusion conditions.
        """
        clone = self._clone()
        clone._excludes &= self._q(*args, **kwargs)
        return clone

    def order_by(self, *args):
        """
        Specifies the ordering of the result set (ORDER BY clause).

        Args:
            *args: Column names to order by. Prefix with '-' for descending order
                   (e.g., `"-age"` for descending age).

        Returns:
            SQLQuery: A new SQLQuery instance with the specified ordering.
        """
        clone = self._clone()
        clone._order_by = args
        return clone

    def group_by(self, *args):
        """
        Specifies grouping for the result set (GROUP BY clause).

        Args:
            *args: Column names to group by.

        Returns:
            SQLQuery: A new SQLQuery instance with the specified grouping.
        """
        clone = self._clone()
        clone._group_by = args
        return clone

    def join(self, table, on="", how="inner join"):
        """
        Adds a JOIN clause to the query.

        Args:
            table (str): The name of the table to join.
            on (str, optional): The JOIN condition (e.g., "other_table.id = main_table.fk_id").
                                Can use `{table}` as a placeholder for the primary table name.
            how (str, optional): The type of join (e.g., "INNER JOIN", "LEFT JOIN").
                                 Defaults to "inner join".

        Returns:
            SQLQuery: A new SQLQuery instance with the added JOIN clause.
        """
        clone = self._clone()
        if on:
            on = "ON " + on.format(table=self._table)
            clone._joins.append(
                "{how} {table} {on}".format(
                    how=how, table=table, on=on))
        return clone

    def extra(self, extra=None, **kwargs):
        """
        Adds extra, raw SQL snippets to various parts of the query.

        This method allows for advanced customization but should be used with caution
        as it can bypass parameterization for the provided raw SQL.

        Args:
            extra (dict, optional): A dictionary where keys are query parts (e.g., "select", "where")
                                    and values are SQL strings or lists of SQL strings.
            **kwargs: Can also be used to pass query parts, e.g., `select="COUNT(*) as total"`.

        Returns:
            SQLQuery: A new SQLQuery instance with the extra SQL snippets.
        """
        clone = self._clone()
        if extra:
            clone._extra.update(extra)
        if kwargs:
            clone._extra.update(kwargs)
        return clone

    def __getitem__(self, slice):
        """
        Implements slicing for limit/offset functionality (LIMIT/OFFSET clause).

        Args:
            slice (slice): A slice object (e.g., `[:10]`, `[5:15]`).

        Returns:
            SQLQuery: A new SQLQuery instance with the specified limit/offset.
        """
        clone = self._clone()
        clone._limits = slice
        return clone


class SQLCompiler(object):
    """
    Compiles the SQLQuery object's state into an executable SQL string and parameters.

    This class takes the structured query information from an SQLQuery instance
    (which it's typically mixed into via Queryset) and translates it into the
    final SQL query string with placeholders, along with a list of parameters
    for safe execution.
    """

    def get_columns(self,):
        """
        Constructs the column selection part of the SQL query.

        Combines explicitly selected columns (from `_values`) with any
        columns added via the `extra(select=...)` mechanism.

        Returns:
            str: The SQL string for column selection (e.g., "col1, col2, COUNT(*)").
        """
        extra_columns = self.get_extra_columns()
        columns = ", ".join(self._values)
        return ", ".join([item for item in [columns, extra_columns] if item])

    def get_extra_columns(self,):
        """
        Retrieves extra columns specified via `extra(select=...)`.

        Returns:
            str: SQL string for extra selected columns, or empty string if none.
        """
        return self._extra.get("select", "")

    def get_extra_where(self,):
        """
        Retrieves extra WHERE conditions specified via `extra(where=...)`.

        These are typically raw SQL strings.

        Returns:
            str: An "AND"-joined SQL string of extra WHERE conditions, or None.
        """
        where = self._extra.get("where", [])
        if where:
            return " AND ".join(where)

    def get_table(self,):
        """
        Gets the primary table name for the query.

        Returns:
            str: The table name.
        """
        return self._table

    def get_where(self):
        """
        Generates the WHERE clause SQL string and collects its parameters.

        It compiles the `_filters` and `_excludes` Q objects (handling the
        `NOT` for excludes) and combines their SQL and parameters. It also
        appends any raw SQL from `extra(where=...)`.

        Returns:
            tuple or None: A tuple `(sql_where_clause, params_list)` if there are
                           conditions, otherwise None.
                           Example: `("WHERE (name = %s) AND NOT (age < %s)", ["John", 10])`
        """
        # _filters and _excludes are Q objects (or Operators).
        # Their combination using & and ~ will result in an Operator instance.
        # This Operator instance's _compile method will return (sql, params).

        # Compile filters
        filters_sql, filters_params = "", []
        if self._filters:  # Check if _filters (Q object) has any conditions
            filters_sql, filters_params = self._filters._compile()

        # Compile excludes
        excludes_sql, excludes_params = "", []
        if self._excludes:  # Check if _excludes (Q object) has any conditions
            # Note: The ~ operator is handled by Operator._compile if self._excludes is part of a larger expression.
            # Here, we are specifically compiling the _excludes Q object itself.
            # The negation (NOT) is applied when combining with filters.
            excludes_sql, excludes_params = self._excludes._compile()

        # Combine filter and exclude SQL and params
        # The actual "NOT" logic for excludes is handled by how these are combined.
        # self._filters & ~self._excludes creates an Operator.
        # We need to get params from that combined operation.

        final_combined_q = self._filters
        if excludes_sql:  # Only add NOT if there's something to exclude
            final_combined_q = self._filters & ~self._excludes

        # Now compile the potentially combined Q/Operator object
        combined_sql, combined_params = final_combined_q._compile()

        extra_where = self.get_extra_where()  # Assumed to be raw SQL string, no params

        if not combined_sql and not extra_where:
            return None  # No WHERE clause needed

        where_parts = []
        # Start with params from Q/Operator
        current_params = list(combined_params)

        if combined_sql:
            where_parts.append(ensureUtf(combined_sql))

        if extra_where:
            if isinstance(extra_where, list):
                where_parts.extend(extra_where)
            else:
                where_parts.append(extra_where)

        if not where_parts:
            return None  # Should not happen if combined_sql or extra_where was present

        return "WHERE " + " AND ".join(where_parts), current_params

    def get_order_by(self,):
        """
        Constructs the ORDER BY clause of the SQL query.

        Handles ascending and descending order (prefix column with '-').

        Returns:
            str or None: The SQL ORDER BY clause (e.g., "ORDER BY name, age DESC"),
                         or None if no ordering is specified.
        """
        conds = []
        for cond in self._order_by:
            order = ""
            if cond is None:
                continue

            column = cond
            try:
                if cond[0] == "-":
                    order = " DESC"
                    column = cond[1:]
            except BaseException:
                pass

            conds.append("{0}{1}".format(column, order))

        if conds:
            return "ORDER BY " + ", ".join(conds)

    def get_group_by(self,):
        """
        Constructs the GROUP BY clause of the SQL query.

        Returns:
            str or None: The SQL GROUP BY clause (e.g., "GROUP BY department"),
                         or None if no grouping is specified.
        """
        if self._group_by:
            return "GROUP BY " + ", ".join(self._group_by)

    def get_joins(self,):
        """
        Constructs the JOIN clauses of the SQL query.

        Returns:
            str or None: The SQL JOIN clauses (e.g., "INNER JOIN table2 ON ..."),
                         or None if no joins are specified.
        """
        if self._joins:
            return "  ".join(self._joins)

    def get_nolock(self,):
        """
        Returns the 'WITH (NOLOCK)' hint string if enabled (for SQL Server).

        Returns:
            str: " WITH (NOLOCK)" if enabled, otherwise an empty string.
        """
        if self._nolock:
            return " WITH (NOLOCK)"
        return ""

    def get_limits(self,):
        """
        Constructs the LIMIT/OFFSET clause (for MySQL/PostgreSQL style databases).

        Not used for SQL Server TOP clause.

        Returns:
            str or None: The SQL LIMIT/OFFSET clause (e.g., "LIMIT 10 OFFSET 5"),
                         or None if no limits/offset are specified or if in SQL Server mode.
        """
        if self._limits and self.sql_mode != "SQL_SERVER":
            offset = self._limits.start
            limit = self._limits.stop
            if offset:
                limit = limit - offset
            s = "LIMIT {0}".format(limit)  # Renamed str to s
            if offset:
                s += " OFFSET {0}".format(offset)
            return s
        return None # Ensure None is returned if not applicable

    def get_top(self,):
        """
        Constructs the TOP clause (for SQL Server).

        Used when limits are specified but no offset (start is None).

        Returns:
            str or None: The SQL TOP clause (e.g., "TOP 10"), or None if not applicable.
        """
        if self._limits and self.sql_mode == "SQL_SERVER" and not self._limits.start:
            return "TOP {0}".format(self._limits.stop)
        return None # Ensure None is returned if not applicable

    def get_sql_structure(self):
        """
        Assembles the main structure of the SQL query as a list of its component strings.

        This method calls other `get_*` methods (like `get_columns`, `get_where`, etc.)
        to build the different parts of the query. It also handles SQL Server's
        ROW_NUMBER() OVER() pagination logic if applicable.

        The parameters from the WHERE clause are also retrieved here and passed along.

        Returns:
            tuple: A tuple containing:
                - list: A list of SQL string components (e.g., ["SELECT", "col1", "FROM", "table", ...]).
                - list: A list of parameters collected from the WHERE clause.
        """
        if self._sql:  # If raw SQL is provided initially
            if not self.has_filters():  # And no other modifications, return it as is
                # If self._sql was from a previous Queryset, it might have params.
                # This case needs careful handling if we want to chain parameterized raw SQL.
                # For now, assume self._sql does not come with its own params
                # that need merging.
                return [self._sql], []
            # Wrap raw SQL if filters are added
            table = "(%s) as union1" % self._sql
        else:
            table = self.get_table()

        # Prepare components. get_where() now returns (sql_str, params_list) or
        # None
        where_clause_tuple = self.get_where()
        where_sql = None
        where_params = []
        if where_clause_tuple:
            where_sql, where_params = where_clause_tuple

        # Base SQL structure
        sql_parts = ["SELECT", self.get_top(), self.get_columns(),
                     "FROM", table,
                     self.get_nolock(),
                     self.get_joins(), where_sql,  # where_sql might be None
                     self.get_group_by(), self.get_order_by(),
                     self.get_limits()]

        # SQL Server specific pagination
        if self.sql_mode == "SQL_SERVER" and self._limits and \
           self._limits.start is not None and self._limits.stop is not None:

            # These limit values are directly embedded. If parameterization is needed here,
            # this part would also need to return placeholders and params.
            # For now, assuming they are not parameterized as per typical SQL
            # Server TOP/ROW_NUMBER usage.
            conds_list = []
            if self._limits.start is not None:
                # This is SQL string construction, not parameterization.
                # If these numbers were from user input, they should be parameterized.
                # However, slice indices are usually developer-defined.
                conds_list.append("row_number > %s" % self._limits.start)
            if self._limits.stop is not None:
                conds_list.append("row_number <= %s" % self._limits.stop)
            conds_str = " AND ".join(conds_list)

            paginate_order_by = self.get_order_by()  # ORDER BY for ROW_NUMBER()
            if not paginate_order_by:  # ROW_NUMBER() requires an ORDER BY clause
                # Default order by if none provided, to make ROW_NUMBER syntactically correct
                # This might need to pick a default column, e.g., PK if known, or first selected column
                # For now, this is a simplification. A robust solution would ensure a valid column.
                # Or raise an error if order_by is missing for pagination.
                # This aspect is outside the primary goal of SQL injection for
                # WHERE clause.
                if self._values and self._values != ['*']:
                    paginate_order_by = "ORDER BY " + \
                        self._values[0].split(' ')[0]  # Order by first column
                else:  # Cannot determine a column, this will likely be a SQL syntax error if not handled
                    paginate_order_by = "ORDER BY (SELECT NULL)"

            paginate_clause = "ROW_NUMBER() OVER (%s) as row_number" % paginate_order_by

            # The WHERE clause for the outer query (tbl_paginated) is conds_str
            # The inner query might have its own WHERE clause (where_sql from
            # get_where())

            sql_parts = ["SELECT * FROM (",
                         "SELECT", ",".join(
                             [item for item in [paginate_clause, self.get_columns()] if item]),
                         "FROM", table,
                         self.get_joins(),
                         where_sql,  # Inner WHERE clause
                         self.get_group_by(),  # Inner GROUP BY
                         # self.get_order_by(), # Order by is in ROW_NUMBER()
                         # self.get_limits(), # Limits are applied by
                         # ROW_NUMBER and outer WHERE
                         ") as tbl_paginated WHERE ", conds_str]
            # Params from the inner where_sql are already in where_params
            # conds_str currently doesn't add params.

        return sql_parts, where_params  # Return parts and params from where clause

    def _compile(self):
        """
        Compiles the entire SQL query into its final SQL string and parameter list.

        This method orchestrates the assembly of all SQL parts by calling
        `get_sql_structure`. It then joins the SQL parts into a single string
        and returns this string along with the aggregated list of parameters
        (primarily from the WHERE clause, as other parts like LIMIT/OFFSET are
        not currently parameterized).

        The collected parameters are stored in `self.params` for the instance
        and also returned.

        Returns:
            tuple: A tuple `(final_sql_string, all_params_list)`.
        """
        self.params = []  # Reset params for this compilation run.

        sql_structure_parts, where_params = self.get_sql_structure()
        self.params.extend(where_params)

        # Parameters from F objects used in _values, _order_by etc. are not handled yet.
        # The current focus is on WHERE clause parameterization.
        # For example, if an F object in values() was `F("CONCAT(%s, %s)")` and had its own params,
        # they would need to be collected here. Current F object is simpler.

        final_sql = " ".join([ensureUtf(item)
                             for item in sql_structure_parts if item])
        return final_sql, self.params

    def __repr__(self):
        """
        Returns the compiled SQL string representation of the query.

        Note: This is primarily for debugging. For actual query execution,
        the `sql` property should be used to get both SQL and parameters.
        """
        # Per instructions, __repr__ should return the SQL string part for now.
        sql_string, _ = self._compile()
        return sql_string

    __str__ = __repr__

    @property
    def sql(self):
        """
        The primary interface to get the compiled SQL query and its parameters.

        Returns:
            tuple: A tuple `(sql_string, params_list)` ready for database execution.
        """
        # This property should return the (sql_string, params_list) tuple.
        return self._compile()

    def __or__(self, other):
        """
        Implements the UNION operation between this Queryset and another.

        If `other` is also a Queryset, their compiled SQL strings are joined by
        "UNION", and their parameter lists are concatenated.
        If `other` is a string, it's treated as a raw SQL string for the UNION.

        Args:
            other (Queryset or str): The Queryset or SQL string to UNION with.

        Returns:
            Queryset: A new Queryset instance representing the UNION.
                      Note: If further filters are applied to this new Queryset,
                      the parameter handling for the UNIONed parts might be limited
                      as the UNION is currently constructed from compiled SQL strings.
        """
        # Handling UNION with parameters is complex.
        # If 'other' is also a Queryset, its SQL and params must be retrieved.
        # Then, the params lists need to be concatenated.
        # The SQL string would be "self_sql UNION other_sql".
        # For now, this remains as string formatting, which is a known limitation
        # if either side of UNION has parameters that are not part of this string.
        # This is acceptable given the primary focus on WHERE clause injection.

        # If self.sql or other.sql now returns (s, p), this needs adjustment.
        # self.sql is now a property returning (s,p)
        self_sql_str, self_params = self.sql

        if isinstance(other, self.__class__):  # other is also a Queryset
            other_sql_str, other_params = other.sql
            # Combine SQL strings
            union_sql_str = "%s UNION %s" % (self_sql_str, other_sql_str)
            # Create a new Queryset with this combined SQL
            # The parameters would be self_params + other_params
            # However, the Queryset constructor with raw SQL doesn't currently take params.
            # This is a limitation we'll accept for now.
            # The created Queryset will not have the combined params correctly associated
            # if it's further modified.
            new_qs = self.__class__(sql=union_sql_str, sql_mode=self.sql_mode)
            # Manually set params for the new Queryset for this specific UNION case.
            # This is a bit of a hack, ideally constructor should handle it.
            new_qs.params = self_params + other_params
            return new_qs
        else:  # other is likely a string or something not a Queryset
            # Original behavior, assuming other is a string of SQL
            return self.__class__(
                sql="%s UNION %s" %
                (self_sql_str, str(other)))


class Queryset(SQLCompiler, SQLQuery):
    """
    The main user-facing class for building and representing an SQL query.

    It inherits query construction capabilities from `SQLQuery` and compilation
    logic from `SQLCompiler`. Queryset instances are designed to be immutable;
    most methods that modify the query (e.g., `filter`, `values`) return a new
    Queryset instance.

    Typical usage involves creating a Queryset for a table and then chaining
    methods to define the query:
    ```python
    qs = Queryset("users").filter(age__gt=18).values("name", "email").order_by("name")
    sql_string, params = qs.sql  # Get the SQL and parameters
    # Execute with a database cursor: cursor.execute(sql_string, params)
    ```
    """
    def __init__(self, table=None, sql_mode="MYSQL", sql=None, **kwargs):
        """
        Initializes a Queryset instance.

        Args:
            table (str, optional): The name of the database table.
            sql_mode (str, optional): The SQL dialect/mode (e.g., "MYSQL", "SQL_SERVER").
                                      Defaults to "MYSQL".
            sql (str, optional): An initial raw SQL string. If provided, the Queryset
                                 can represent a more complex starting query.
                                 Associated parameters can be passed via `kwargs['params']`.
            **kwargs: Additional arguments. `params` can be passed here if `sql` is provided,
                      representing the parameters for that raw SQL.
        """
        # Initialize SQLQuery parts (including _filters, _excludes as Q
        # objects)
        SQLQuery.__init__(
            self,
            table=table,
            sql_mode=sql_mode,
            sql=sql,
            **kwargs)
        # SQLCompiler parts don't have a separate __init__ typically.
        # self.params is initialized in SQLQuery's __init__ now.
        if sql and kwargs.get('params'):  # If raw SQL and params are passed
            self.params = kwargs.get('params')


class SQLModel(object):
    """
    A base class for model-like objects that can integrate with Queryset.

    This class provides a convenient way to associate a Queryset with a "model"
    by defining a `table` name and optionally an `sql_mode` at the class level.
    The `objects` class property then acts as a manager, returning a new
    Queryset instance for that model's table.

    Example:
    ```python
    class User(SQLModel):
        table = "auth_user"
        sql_mode = "POSTGRESQL"

    # Get a Queryset for the User model
    user_queryset = User.objects.filter(is_active=True)
    ```
    """

    @classproperty
    def objects(cls):
        """
        A class property that acts as a manager, returning a Queryset for the model.

        It uses the `table` and `sql_mode` attributes defined on the class.

        Args:
            cls: The class itself.

        Returns:
            Queryset: A new Queryset instance configured for the model's table and SQL mode.
        """
        return Queryset(cls.table, getattr(cls, 'sql_mode', None))
