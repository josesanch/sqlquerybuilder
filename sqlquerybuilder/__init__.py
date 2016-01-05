from __future__ import unicode_literals
import sys
import copy
import datetime

PYTHON3 = True
if sys.version_info[0] < 3:
    PYTHON3 = False

VERSION = "0.0.13"

def is_map(obj):
    return PYTHON3 and isinstance(obj, map)

def ensureUtf(s):
    try:
        if isinstance(s, str):
            return s
        else:
            return s.encode('utf8', 'ignore')
    except:
        return str(s)


class classproperty(object):

    def __init__(self, getter):
        self.getter = getter

    def __get__(self, instance, owner):
        return self.getter(owner)


class QMixin(object):
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
        return Operator(self.NOT, self)


class Operator(QMixin):

    def __init__(self, op=None, left=None, right=None):
        self.op = op
        self.left = left
        self.right = right

    def __repr__(self,):
        if self.left and self.right:
            return "(%s %s %s)" % (self.left, self.op, self.right)

        if self.right:
            return "%s" % (self.right)

        if self.left and self.op == "NOT":
            return "%s %s" % (self.op, self.left)

        return "%s" % self.left

    __str__ = __repr__

    def __bool__(self):
        return bool(self.right or self.left)

    __nonzero__ = __bool__


class F(object):

    def __init__(self, value):
        self.value = value

    def __repr__(self,):
        return "%s" % self.value

    __str__ = __repr__

    def __bool__(self):
        return bool(self.value)

    __nonzero__ = __bool__


class Q(QMixin):
    _mode = "MYSQL"

    lookup_types = [
        'icontains', 'istartswith',  'iendswith',
        'contains', 'startswith',  'endswith',
        'year', 'month', 'day', 'week_day', 'hour', 'minute', 'second',
        'isnull', 'in']

    op_map = {
        'lte': '<=',
        'gte': '>=',
        'lt': '<',
        'gt': '>',
    }

    def __init__(self, *args, **kwargs):
        self.conditions = kwargs
        for arg in args:
            self.conditions[arg] = None

    def __repr__(self,):
        return self._compile()

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
        if isinstance(value, int) or isinstance(value, float):
            return ensureUtf(value)

        if isinstance(value, datetime.datetime):
            return "'%s'" % value.strftime(self.datetime_format)

        if isinstance(value, datetime.date):
            return "'%s'" % value.strftime(self.date_format)

        if isinstance(value, list) or isinstance(value, set) or is_map(value):
            return ", ".join([self._get_value(item) for item in value])

        if isinstance(value, F) or isinstance(value, QMixin) or isinstance(value, SQLQuery):
            return ensureUtf(value)

        return "'%s'" % value

    def _process(self, compose_column, value):
        arr = compose_column.split("__")
        column = arr.pop(0)
        if column == '':
            column += "__" + arr.pop(0)

        try:
            lookup = arr.pop(0)
        except:
            lookup = None

        if lookup in self.lookup_types:
            if lookup == "icontains":
                return "{0} LIKE '%{1}%'".format(column, value)

            if lookup == "iendswith":
                return "{0} LIKE '%{1}'".format(column, value)

            if lookup == "istartswith":
                return "{0} LIKE '{1}%'".format(column, value)

            if lookup == "contains":
                return "{0} LIKE BINARY '%{1}%'".format(column, value)

            if lookup == "endswith":
                return "{0} LIKE BINARY '%{1}'".format(column, value)

            if lookup == "startswith":
                return "{0} LIKE BINARY '{1}%'".format(column, value)

            if lookup == "in":
                return "{0} in ({1})".format(column, self._get_value(value))

            if lookup == 'isnull':
                op = ""
                if not value:
                    op = "NOT "
                return "{0} is {1}NULL".format(column, op)

            if lookup in ['year', 'month', 'day', 'hour', 'minute', 'second']:
                if arr:
                    column = "DATEPART({0}, {1})__{2}".format(lookup, column, arr.pop(0))
                    return self._process(column, value)
                else:
                    return "DATEPART({0}, {1})={2}".format(lookup, column, value)

        if lookup in self.op_map.keys():
            return "{0}{1}{2}".format(column, self.op_map[lookup], self._get_value(value))

        if value is not None:
            return "{0}{1}{2}".format(column, "=", self._get_value(value))

        return column

    def _compile(self,):
        filters = []
        for k, v in self.conditions.items():
            filters.append(self._process(k, v))

        if filters:
            return "(%s)" % " AND ".join(filters)

        return ""


class SQLQuery(object):

    def __init__(self, table=None, sql_mode="MYSQL", sql=None, **kwargs):
        self.kwargs = kwargs
        self._table = table
        self.sql_mode = sql_mode
        self._values = ["*"]
        self._order_by = []
        self._group_by = []
        self._joins = []
        self._filters = Q()
        self._excludes = Q()
        self._extra = {}
        self._limits = None
        self._sql = sql
        self._nolock = False

    def has_filters(self,):
        return self._order_by or self._group_by or self._joins\
            or self._filters or self._excludes or self._extra \
            or self._limits or self._values != ['*']

    def _q(self, *args, **kwargs):
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
        return copy.deepcopy(self)

    def values(self, *args):
        clone = self._clone()
        clone._values = list(args)
        return clone

    def with_nolock(self, enabled=True):
        clone = self._clone()
        clone._nolock = enabled
        return clone

    def filter(self, *args, **kwargs):
        clone = self._clone()
        clone._filters &= self._q(*args, **kwargs)
        return clone

    def exclude(self, *args, **kwargs):
        clone = self._clone()
        clone._excludes &= self._q(*args, **kwargs)
        return clone

    def order_by(self, *args):
        clone = self._clone()
        clone._order_by = args
        return clone

    def group_by(self, *args):
        clone = self._clone()
        clone._group_by = args
        return clone

    def join(self, table, on="", how="inner join"):
        clone = self._clone()
        if on:
            on = "ON " + on.format(table=self._table)
            clone._joins.append("{how} {table} {on}".format(how=how, table=table, on=on))
        return clone

    def extra(self, extra=None, **kwargs):
        clone = self._clone()
        if extra:
            clone._extra.update(extra)
        if kwargs:
            clone._extra.update(kwargs)
        return clone

    def __getitem__(self, slice):
        clone = self._clone()
        clone._limits = slice
        return clone


class SQLCompiler(object):

    def get_columns(self,):
        extra_columns = self.get_extra_columns()
        columns = ", ".join(self._values)
        return ", ".join([item for item in [columns, extra_columns] if item])

    def get_extra_columns(self,):
        return self._extra.get("select", "")

    def get_extra_where(self,):
        where = self._extra.get("where", [])
        if where:
            return " AND ".join(where)

    def get_table(self,):
        return self._table

    def get_where(self):
        filters = ensureUtf(self._filters & ~self._excludes)
        extra_where = self.get_extra_where()

        if filters or extra_where:
            return "WHERE " + " AND ".join([item for item in [filters, extra_where] if item])

    def get_order_by(self,):
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
            except:
                pass

            conds.append("{0}{1}".format(column, order))

        if conds:
            return "ORDER BY " + ", ".join(conds)

    def get_group_by(self,):
        if self._group_by:
            return "GROUP BY " + ", ".join(self._group_by)

    def get_joins(self,):
        if self._joins:
            return "  ".join(self._joins)

    def get_nolock(self,):
        if self._nolock:
            return " WITH (NOLOCK)"
        return ""

    def get_limits(self,):
        if self._limits and self.sql_mode != "SQL_SERVER":
            offset = self._limits.start
            limit = self._limits.stop
            if offset:
                limit = limit - offset
            str = "LIMIT {0}".format(limit)
            if offset:
                str += " OFFSET {0}".format(offset)
            return str

    def get_top(self,):
        if self._limits and self.sql_mode == "SQL_SERVER" and not self._limits.start:
            return "TOP {0}".format(self._limits.stop)

    def get_sql_structure(self):
        if self._sql:
            if not self.has_filters():
                return [self._sql]
            table = "(%s) as union1" % self._sql
        else:
            table = self.get_table()

        sql = ["SELECT", self.get_top(), self.get_columns(),
               "FROM", table,
               self.get_nolock(),
               self.get_joins(), self.get_where(),
               self.get_group_by(), self.get_order_by(),
               self.get_limits()]

        if self.sql_mode == "SQL_SERVER" and self._limits and \
           self._limits.start is not None and self._limits.stop is not None:
            conds = []
            if self._limits.start is not None:
                conds.append("row_number > %s" % self._limits.start)

            if self._limits.stop is not None:
                conds.append("row_number <= %s" % self._limits.stop)

            conds = " AND ".join(conds)
            paginate = "ROW_NUMBER() OVER (%s) as row_number" % self.get_order_by()

            return ["SELECT * FROM (", "SELECT", ",".join([paginate, self.get_columns()]),
                    "FROM", table,
                    self.get_joins(),
                    self.get_where(),
                    self.get_group_by(),
                    self.get_limits(), ") as tbl_paginated WHERE ", conds]

        return sql

    def _compile(self):
        return " ".join([ensureUtf(item) for item in self.get_sql_structure() if item])

    def __repr__(self):
        return self._compile()

    __str__ = __repr__

    @property
    def sql(self,):
        return self.__str__()

    def __or__(self, other):
        return self.__class__(sql="%s UNION %s" % (self, other))


class Queryset(SQLCompiler, SQLQuery):
    pass


class SQLModel(object):

    @classproperty
    def objects(cls):
        return Queryset(cls.table, getattr(cls, 'sql_mode', None))
