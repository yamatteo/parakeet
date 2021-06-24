import unittest

from rules import TR, SR, EX
from matches import CompleteMatch
from parser import Parser


class TestSuit(unittest.TestCase):
    def test_parser(self):
        p = Parser([
            TR("a", r"a"),
            TR("b", r"b"),
            TR("c", r"c"),
            SR("C", ("c",), left=EX("&", "b")),
            SR("C", ("c",), left=EX("&", "c")),
            SR("B", ("b",), left=EX("&", "a")),
            SR("B", ("b",), left=EX("&", "b")),
            SR("W", ("B",), right=EX("&", "C")),
            SR("Z", ("C",), left=EX("&", "W")),
            SR("C", ("W",), right=EX("&", "Z")),
            SR("B", ("Z",), left=EX("&", "C")),
            SR("S", ("a", "S", "B", "C")),
            SR("S", ("a", "B", "C",))
        ])

        m = p.parse("aaaaaaabbbbbbbccccccc")
        self.assertIsInstance(m[0], CompleteMatch)
        print("Solution:", m[0].crepr.hex())
        print(len(m), "solutions")
        print(len(p.fms.all_matches) + len(p.cms.all_matches),
              "generated matches")

    def test_parallel_deadlock(self):
        p = Parser([
            SR("S", ("a", "A")),
            SR("a", ("b",), right=EX("&", "A")),
            SR("A", ("B",), left=EX("&", "a")),
            TR("b", r"z"),
            TR("B", r"Z"),
        ])

        m = p.parse("zZ", expect="S", verbose=True)
        self.assertEqual([], m)

    def test_overcross_deadlock(self):
        p = Parser([
            SR("S", ("a", "A")),
            SR("a", ("b",)),
            SR("b", ("c",), right=EX("&", "A")),
            SR("A", ("B",)),
            SR("B", ("C",), left=EX("&", "a")),
            TR("c", r"z"),
            TR("C", r"Z"),
        ])

        m = p.parse("zZ", expect="S")
        self.assertEqual([], m)

    def test_sidecross_deadlock(self):
        p = Parser([
            SR("S", ("a", "A")),
            SR("a", ("b",), right=EX("&", "B")),
            SR("b", ("c",), right=EX("&", "A")),
            SR("A", ("B",)),
            SR("B", ("C",)),
            TR("c", r"z"),
            TR("C", "rZ"),
        ])

        m = p.parse("zZ", expect="S")
        self.assertEqual([], m)

    def test_upcycle(self):
        p = Parser([
            SR("S", ("A", "B", "C", "D")),  # , "C", "D")),
            SR("A", ("a",)),
            SR("B", ("b",), left=EX("&", "AW")),
            SR("AW", ("A",)),
            SR("A", ("AW",)),
            SR("C", ("c",), left=EX("&", "BW")),
            SR("BW", ("B",)),
            SR("B", ("BW",)),
            SR("D", ("d",), left=EX("&", "CW")),
            SR("CW", ("C",)),
            SR("C", ("CW",)),

            TR("a", r"a"),
            TR("b", r"b"),
            TR("c", r"c"),
            TR("d", r"d"),
        ])

        m = p.parse("abcd", expect="S")
        self.assertEqual(1, len(m))

    def test_wide_upcycle(self):
        p = Parser([
            SR("S", ("A", "B", "C")),
            SR("A", ("a",)),
            SR("B", ("b",)),
            SR("C", ("c",)),
            SR("A", ("AW",), right=EX("&", "B")),
            SR("B", ("BW",)),
            SR("C", ("CW",), left=EX("&", "B")),
            SR("AW", ("A",)),
            SR("BW", ("B",)),
            SR("CW", ("C",)),

            TR("a", r"a"),
            TR("b", r"b"),
            TR("c", r"c"),
        ])

        m = p.parse("abc")
        self.assertEqual(8, len(m))
        self.assertTrue(any(
            all(child.depth in {2, 4} for child in
                solution.children)
            for solution in m
        ))

    def test_hanging_expectation(self):
        p = Parser([
            SR("S", ("A", "B")),
            SR("A", ("a",), right=EX("&", "B")),
            SR("B", ("b",), right=EX("&", "A")),
            TR("a", r"a"),
            TR("b", r"b"),
        ])

        solutions = p.parse("ab")
        self.assertEqual([], solutions)

    def test_parse_without_expect(self):
        p = Parser([
            SR("S", ("A", "B", "C")),
            SR("W", ("A", "B")),
            SR("R", ("B", "C")),
            SR("A", ("a",)),
            SR("B", ("b",)),
            SR("C", ("c",)),

            TR("a", r"a"),
            TR("b", r"b"),
            TR("c", r"c"),
        ])

        m = p.parse("abc")
        self.assertEqual(1, len(m))
        self.assertEqual("S", m[0].external)

        p = Parser([
            SR("S1", ("A", "B", "C")),
            SR("S2", ("A", "R")),
            SR("W", ("A", "B")),
            SR("R", ("B", "C")),
            SR("A", ("a",)),
            SR("B", ("b",)),
            SR("C", ("c",)),

            TR("a", r"a"),
            TR("b", r"b"),
            TR("c", r"c"),
        ])

        solutions = p.parse("abc")
        self.assertEqual(2, len(solutions))
        self.assertEqual({m.external for m in solutions}, {"S1", "S2"})


if __name__ == "__main__":
    unittest.main()
