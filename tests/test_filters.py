"""
Unit tests for filters.py pattern matching system.
"""

import unittest
from filters import (
    match_pattern,
    check_number_match,
    validate_pattern,
    check_auto_rules,
    PRESET_PATTERNS,
)


class TestFilters(unittest.TestCase):
    def test_pattern_validation(self):
        self.assertTrue(validate_pattern("XXX AA XX"))
        self.assertTrue(validate_pattern("AB AB AB"))
        self.assertTrue(validate_pattern("ABC ABC"))
        self.assertFalse(validate_pattern("A"))  # Too short
        self.assertFalse(validate_pattern("XXX AA XX YY ZZ WW"))  # Too long

    def test_xxx_aa_xx(self):
        pattern = "XXX AA XX"
        # Should match:
        self.assertTrue(match_pattern("+998937775577", pattern))
        self.assertTrue(match_pattern("998931114411", pattern))
        self.assertTrue(match_pattern("939992299", pattern))

        # Should NOT match (X and A are same digit '7'):
        self.assertFalse(match_pattern("+998937777777", pattern))

    def test_ab_ab_ab(self):
        pattern = "AB AB AB"
        self.assertTrue(match_pattern("+99890121212", pattern))
        self.assertTrue(match_pattern("99893353535", pattern))
        # False if A == B
        self.assertFalse(match_pattern("+99890111111", pattern))

    def test_abc_abc(self):
        pattern = "ABC ABC"
        self.assertTrue(match_pattern("+99890123123", pattern))
        self.assertTrue(match_pattern("99893527527", pattern))
        self.assertFalse(match_pattern("+99890111111", pattern))

    def test_abccba(self):
        pattern = "ABCCBA"
        self.assertTrue(match_pattern("+99890123321", pattern))
        self.assertTrue(match_pattern("99893457754", pattern))
        self.assertFalse(match_pattern("+99890123456", pattern))

    def test_all_preset_patterns(self):
        test_cases = {
            "XXX XX AA": "+998937777755",
            "XX AAA XX": "+998935577755",
            "XX AA XXX": "+998937755777",
            "AAA XX AA": "+998937775577",
            "AA XXX AA": "+998935577755",
            "XXX AA BB": "+998937775522",
            "XX AA BB": "+99893557722",
            "AA BB AA": "+99893552255",
            "XXX AAA": "+99893777555",
            "AAA AAA": "+99893777777",
        }
        for pat, phone in test_cases.items():
            self.assertTrue(
                match_pattern(phone, pat),
                f"Failed matching {phone} with pattern {pat}",
            )

    def test_auto_rules(self):
        # 000
        res = check_number_match("+998901200045", enabled_patterns=[], check_auto=True)
        self.assertTrue(res.matched)
        self.assertIn("000", res.reason)

        # 777
        res = check_number_match("+998901277745", enabled_patterns=[], check_auto=True)
        self.assertTrue(res.matched)
        self.assertIn("777", res.reason)

        # 1111
        res = check_number_match("+998901111145", enabled_patterns=[], check_auto=True)
        self.assertTrue(res.matched)
        self.assertIn("1111", res.reason)

        # Sequence 1234
        res = check_number_match("+998905012345", enabled_patterns=[], check_auto=True)
        self.assertTrue(res.matched)
        self.assertIn("последовательность", res.reason)

        # Reverse sequence 9876
        res = check_number_match("+998905098765", enabled_patterns=[], check_auto=True)
        self.assertTrue(res.matched)
        self.assertIn("обратная последовательность", res.reason)

    def test_match_reason_output(self):
        res = check_number_match(
            "+998937775577", enabled_patterns=["XXX AA XX"], check_auto=False
        )
        self.assertTrue(res.matched)
        self.assertEqual(res.pattern, "XXX AA XX")
        self.assertEqual(res.reason, "совпадение с XXX AA XX")


if __name__ == "__main__":
    unittest.main()
