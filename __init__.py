import datetime


def is_number(s):
    try:
        float(s)  # for int, long and float
    except ValueError:
        try:
            complex(s)  # for complex
        except ValueError:
            return False
    return True


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


class Q(QMixin):
    lookup_types = [
        'iexact', 'contains', 'icontains',
        'startswith', 'istartswith', 'endswith', 'iendswith', 'year',
        'month', 'day', 'week_day', 'hour', 'minute', 'second',
        'isnull', 'search', 'regex', 'iregex']

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
            return value

        if isinstance(value, datetime.datetime):
            return "'%s'" % value.strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(value, datetime.date):
            return "'%s'" % value.strftime("%Y-%m-%d")

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
                return "{0} like '%{1}%'".format(column, value)

            if lookup == "iendswith":
                return "{0} like '%{1}'".format(column, value)

            if lookup == "istartwith":
                return "{0} like '{1}%'".format(column, value)

            if lookup == 'isnull':
                op = ""
                if not value:
                    op = "NOT "
                return "{0} is {1}NULL".format(column, op)

            if lookup in ['year', 'month', 'day' 'hour', 'minute', 'second']:
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

    def __init__(self, table=None):
        if table:
            self._table = table
        self._values = []
        self._order_by = []
        self._group_by = []
        self._joins = []
        self._filters = Q()
        self._excludes = Q()
        self._extra = {}

    def values(self, *args):
        self._values = args
        return self

    def filter(self, *args, **kwargs):
        for arg in args:
            if issubclass(arg.__class__, QMixin):
                self._filters &= arg

        self._filters &= Q(**kwargs)
        return self

    def exclude(self, *args, **kwargs):
        for arg in args:
            if issubclass(arg.__class__, QMixin):
                self._excludes &= arg

        self._excludes &= Q(**kwargs)
        return self

    def order_by(self, *args):
        self._order_by = args
        return self

    def group_by(self, *args):
        self._group_by = args
        return self

    def join(self, table, on="", how="inner join"):
        if on:
            on = "ON " + on
            self._joins.append("{how} {table} {on}".format(how=how, table=table, on=on))
        return self

    def extra(self, extra):
        self._extra.update(extra)
        return self


class SQLCompiler(object):

    def get_columns(self,):
        if self._values:
            return ", ".join(self._values)
        return "*"

    def get_extra_columns(self,):
        select = self._extra.get("select", None)
        if select:
            return ", " + select
        return ""

    def get_table(self,):
        return self._table

    def get_where(self):
        filters = self._filters & ~self._excludes
        if filters:
            return "WHERE " + str(filters)

        return ""

    def get_order_by(self,):
        conds = []
        for cond in self._order_by:
            order = ""
            column = cond
            try:
                if cond[0] == "-":
                    order = "desc"
                    column = cond[1:]
            except:
                pass

            conds.append("{0} {1}".format(column, order))

        if conds:
            return "ORDER BY " + ", ".join(conds)
        return ""

    def get_group_by(self,):
        if self._group_by:
            return "GROUP BY " + ", ".join(self._group_by)
        return ""

    def get_joins(self,):
        if self._joins:
            return "  ".join(self._joins)
        return ""

    def _compile(self):
        sql = """
        SELECT {columns}{extra_columns}
        FROM {table}
        {joins}
        {where}
        {group_by}
        {order_by}
        """.format(
            columns=self.get_columns(),
            extra_columns=self.get_extra_columns(),
            table=self.get_table(),
            joins=self.get_joins(),
            where=self.get_where(),
            group_by=self.get_group_by(),
            order_by=self.get_order_by()
        )
        return sql

    def __repr__(self):
        return self._compile()

    __str__ = __repr__


class Queryset(SQLCompiler, SQLQuery):
    pass


class SQLModel(object):

    @classproperty
    def objects(cls):
        return Queryset(cls.table)
