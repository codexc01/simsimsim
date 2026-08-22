"""
Unit-тесты для модуля filters.py.
"""

import unittest
from filters import (
    match_pattern,
    check_number_match,
    validate_pattern,
    check_auto_rules,
)


class TestFilters(unittest.TestCase):
    def test_pattern_validation(self):
        self.assertTrue(validate_pattern("XXX AA XX"))
        self.assertTrue(validate_pattern("777 AA XX"))
        self.assertTrue(validate_pattern("555 12 34"))
        self.assertTrue(validate_pattern("777"))
        self.assertFalse(validate_pattern("A"))  # Слишком короткий
        self.assertFalse(validate_pattern("XXX AA XX YY ZZ WW"))  # Слишком длинный

    def test_xxx_aa_xx(self):
        pattern = "XXX AA XX"
        self.assertTrue(match_pattern("+998937775577", pattern))
        self.assertTrue(match_pattern("998931114411", pattern))
        self.assertTrue(match_pattern("939992299", pattern))
        self.assertFalse(match_pattern("+998937777777", pattern))

    def test_exact_numbers_and_mixed_patterns(self):
        # Шаблон с точными цифрами и буквами
        self.assertTrue(match_pattern("+998937775577", "777 AA XX"))
        self.assertTrue(match_pattern("+998935551234", "555 12 34"))
        self.assertTrue(match_pattern("+998937775577", "777"))
        self.assertTrue(match_pattern("+998935577755", "55 777 55"))
        self.assertFalse(match_pattern("+998931115577", "777 AA XX"))

    def test_ab_ab_ab(self):
        pattern = "AB AB AB"
        self.assertTrue(match_pattern("+99890121212", pattern))
        self.assertTrue(match_pattern("99893353535", pattern))
        self.assertFalse(match_pattern("+99890111111", pattern))

    def test_auto_rules(self):
        res = check_number_match("+998901200045", enabled_patterns=[], check_auto=True)
        self.assertTrue(res.matched)
        self.assertIn("000", res.reason)

        res = check_number_match("+998901277745", enabled_patterns=[], check_auto=True)
        self.assertTrue(res.matched)
        self.assertIn("777", res.reason)


if __name__ == "__main__":
    unittest.main()
