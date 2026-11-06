import unittest

from kurz.parser import Query, parse_amount, parse_query

KNOWN = frozenset({"eur", "usd", "czk", "uah", "gbp", "btc", "pln", "mxn", "krw"})


class ParseAmountTest(unittest.TestCase):
    def test_variants(self):
        cases = {
            "500": 500.0,
            "1 000": 1000.0,
            "1,000": 1000.0,
            "1,000.50": 1000.5,
            "1.000,50": 1000.5,
            "12,5": 12.5,
            "12.5": 12.5,
            "2k": 2000.0,
            "1.5m": 1_500_000.0,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(parse_amount(text), expected)

    def test_more_variants(self):
        cases = {
            "1,000,000": 1_000_000.0,
            "1'000": 1000.0,
            "1\u00a0000": 1000.0,
            "1,5k": 1500.0,
            "0.5": 0.5,
            "2 K": 2000.0,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(parse_amount(text), expected)

    def test_garbage(self):
        for text in ("k", "", "abc", "1.2.3"):
            with self.subTest(text=text):
                self.assertIsNone(parse_amount(text))


class ParseQueryTest(unittest.TestCase):
    def test_matches(self):
        cases = {
            "500 EUR to UAH": Query(500, "eur", "uah"),
            "500 eur uah": Query(500, "eur", "uah"),
            "500eur in czk": Query(500, "eur", "czk"),
            "500 eur = czk": Query(500, "eur", "czk"),
            "500 eur -> czk": Query(500, "eur", "czk"),
            "500 eur": Query(500, "eur", None),
            "€20 to czk": Query(20, "eur", "czk"),
            "20€ to ₴": Query(20, "eur", "uah"),
            "usd 10": Query(10, "usd", None),
            "$10 to gbp": Query(10, "usd", "gbp"),
            "100 Kč to eur": Query(100, "czk", "eur"),
            "2k usd to uah": Query(2000, "usd", "uah"),
            "500 mxn to eur": Query(500, "mxn", "eur"),
            "100 krw": Query(100, "krw", None),
            "2k krw to usd": Query(2000, "krw", "usd"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_query(text, KNOWN), expected)

    def test_symbol_normalization(self):
        self.assertEqual(parse_query("10 zł to eur", KNOWN), Query(10, "pln", "eur"))
        self.assertEqual(parse_query("£5 to eur", KNOWN), Query(5, "gbp", "eur"))
        self.assertEqual(parse_query("₿1 to usd", KNOWN), Query(1, "btc", "usd"))

    def test_case_and_whitespace(self):
        self.assertEqual(parse_query("  500   EuR   TO   uAh  ", KNOWN), Query(500, "eur", "uah"))

    def test_separator_variants(self):
        for sep in (" to ", " in ", "=", " = ", "=>", " => ", "->", " -> ", " "):
            with self.subTest(sep=sep):
                self.assertEqual(parse_query(f"5 eur{sep}czk", KNOWN), Query(5, "eur", "czk"))

    def test_unknown_currency_rejected(self):
        self.assertIsNone(parse_query("500 xyz to eur", KNOWN))
        self.assertIsNone(parse_query("500 eur to xyz", KNOWN))
        self.assertIsNone(parse_query("500 eur to uah", frozenset()))

    def test_non_matches(self):
        for text in ("500 km to mi", "hello", "500", "eur to usd", "500 eur to eur", "firefox"):
            with self.subTest(text=text):
                self.assertIsNone(parse_query(text, KNOWN))


if __name__ == "__main__":
    unittest.main()
