from __future__ import unicode_literals
import datetime
import copy

VERSION = "0.0.6"


class classproperty(object):

    def __init__(self, getter):
        self.getter = getter

    def __get__(self, instance, owner):
        return self.getter(owner)


class QMixin(object):
    AND = 'AND'
    OR = 'OR'
    NOT = 'NOT'

    def _combine(self, other, conn):
        return Operator(conn, self, other)

    def __or__(self, other):
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

    def __repr__(self,):
        return self._compile()

    def __bool__(self):
        return bool(self.conditions)

    __nonzero__ = __bool__

    def _get_value(self, value):
        if isinstance(value, int) or isinstance(value, float):
            return unicode(value)

        if isinstance(value, datetime.datetime):
            return "'%s'" % value.strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(value, datetime.date):
            return "'%s'" % value.strftime("%Y-%m-%d")

        if isinstance(value, list) or isinstance(value, set):
            return ", ".join([self._get_value(item) for item in value])

        if isinstance(value, F) or isinstance(value, QMixin) or isinstance(value, SQLQuery):
            return unicode(value)

        return "'%s'" % value

    def _process(self, compose_column, value):
        arr = compose_column.split("__")
        column = arr.pop(0)
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
                    column = "DATEPART('{0}', {1})__{2}".format(lookup, column, arr.pop(0))
                    return self._process(column, value)
                else:
                    return "DATEPART('{0}', {1})={2}".format(lookup, column, value)

        if lookup in self.op_map.keys():
            return "{0}{1}{2}".format(column, self.op_map[lookup], self._get_value(value))

        return "{0}{1}{2}".format(column, "=", self._get_value(value))

    def _compile(self,):
        filters = []
        for k, v in self.conditions.items():
            filters.append(self._process(k, v))

        if filters:
            return "(%s)" % " AND ".join(filters)

        return ""


class SQLQuery(object):

    def __init__(self, table=None, sql_mode="MYSQL"):
        if table:
            self._table = table
        self.sql_mode = sql_mode
        self._values = []
        self._order_by = []
        self._group_by = []
        self._joins = []
        self._filters = Q()
        self._excludes = Q()
        self._extra = {}
        self._limits = None

    def _clone(self,):
        return copy.deepcopy(self)

    def values(self, *args):
        clone = self._clone()
        clone._values = args
        return clone

    def filter(self, *args, **kwargs):
        clone = self._clone()
        for arg in args:
            if issubclass(arg.__class__, QMixin):
                clone._filters &= arg

        clone._filters &= Q(**kwargs)
        return clone

    def exclude(self, *args, **kwargs):
        clone = self._clone()
        for arg in args:
            if issubclass(arg.__class__, QMixin):
                clone._excludes &= arg

        clone._excludes &= Q(**kwargs)
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
            on = "ON " + on
            clone._joins.append("{how} {table} {on}".format(how=how, table=table, on=on))
        return clone

    def extra(self, extra):
        clone = self._clone()
        clone._extra.update(extra)
        return clone

    def __getitem__(self, slice):
        clone = self._clone()
        clone._limits = slice
        return clone


class SQLCompiler(object):

    def get_columns(self,):
        if self._values:
            return ", ".join(self._values)
        return "*"

    def get_extra_columns(self,):
        select = self._extra.get("select", None)
        if select:
            return ", " + select

    def get_table(self,):
        return self._table

    def get_where(self):
        filters = self._filters & ~self._excludes
        if filters:
            return "WHERE " + unicode(filters)

    def get_order_by(self,):
        conds = []
        for cond in self._order_by:
            order = ""
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
        if self._limits and self.sql_mode == "SQL_SERVER":
            return "TOP {0}".format(self._limits.stop)

    def _compile(self):
        sql_all = [
            "SELECT", self.get_top(), self.get_columns(), self.get_extra_columns(),
            "FROM", self.get_table(), self.get_joins(), self.get_where(),
            self.get_group_by(), self.get_order_by(), self.get_limits()]

        return " ".join([item for item in sql_all if item])

    def __repr__(self):
        return self._compile()

    __str__ = __repr__

    @property
    def sql(self,):
        return self.__str__()


class Queryset(SQLCompiler, SQLQuery):
    pass


class SQLModel(object):

    @classproperty
    def objects(cls):
        return Queryset(cls.table, getattr(cls, 'sql_mode', None))
