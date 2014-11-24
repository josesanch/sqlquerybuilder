import unittest
from . import Q


class TestSqlBuilder(unittest.TestCase):

    def test_q(self):
        self.assertEqual(str(Q(a=1)), "(a='1')")
        self.assertEqual(str(Q(a=1) & ~Q(b=2)), "((a='1') AND NOT (b='2'))")


if __name__ == '__main__':
    unittest.main()
