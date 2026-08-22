"""
Pattern matching system for phone numbers based on letter-to-digit relations.
"""

from dataclasses import dataclass
import re
from typing import List, Dict, Optional, Tuple, Set


@dataclass
class MatchResult:
    matched: bool
    pattern: str = ""
    reason: str = ""


PRESET_PATTERNS: List[str] = [
    "XXX AA XX",
    "XXX XX AA",
    "XX AAA XX",
    "XX AA XXX",
    "AAA XX AA",
    "AA XXX AA",
    "XXX AA BB",
    "XX AA BB",
    "AA BB AA",
    "XXX AAA",
    "AAA AAA",
    "AB AB AB",
    "ABC ABC",
    "ABCCBA",
]


def clean_pattern_str(pattern: str) -> str:
    """Removes spaces, hyphens, and formats to uppercase."""
    return re.sub(r"[^A-Za-z0-9]", "", pattern).upper()


def validate_pattern(pattern: str) -> bool:
    """
    Validates user-submitted pattern string.
    Must contain only letters, digits, spaces, hyphens, and be 3-12 characters long.
    """
    cleaned = clean_pattern_str(pattern)
    if not (3 <= len(cleaned) <= 12):
        return False
    return bool(re.match(r"^[A-Z0-9\s\-]+$", pattern, re.IGNORECASE))


def match_pattern_on_window(digits: str, clean_pattern: str) -> bool:
    """
    Checks if a string of digits exactly matches a pattern of the same length.
    - Upper-case letters (A-Z): same letters = same digits, different letters = different digits.
    - Fixed digits (0-9): must match exact digit value.
    """
    if len(digits) != len(clean_pattern):
        return False

    letter_to_digit: Dict[str, str] = {}
    used_digits: Set[str] = set()

    for p_char, d_char in zip(clean_pattern, digits):
        if p_char.isdigit():
            if p_char != d_char:
                return False
        elif p_char.isalpha():
            p_upper = p_char.upper()
            if p_upper in letter_to_digit:
                if letter_to_digit[p_upper] != d_char:
                    return False
            else:
                if d_char in used_digits:
                    # Digit is already assigned to a different letter
                    return False
                letter_to_digit[p_upper] = d_char
                used_digits.add(d_char)
        else:
            return False

    return True


def match_pattern(phone_number: str, pattern: str) -> bool:
    """
    Matches pattern against subscriber part (7 digits) or national number (9 digits).
    Supports sliding windows for shorter patterns.
    """
    clean_p = clean_pattern_str(pattern)
    if not clean_p:
        return False

    digits = re.sub(r"\D", "", phone_number)
    if digits.startswith("998") and len(digits) == 12:
        nat_digits = digits[3:]      # 9 digits
        sub_digits = digits[5:]      # 7 digits
    elif len(digits) == 9:
        nat_digits = digits          # 9 digits
        sub_digits = digits[2:]      # 7 digits
    elif len(digits) == 7:
        nat_digits = digits
        sub_digits = digits
    else:
        nat_digits = digits
        sub_digits = digits

    p_len = len(clean_p)

    # 1. Exact match on 7-digit subscriber number
    if p_len == len(sub_digits):
        if match_pattern_on_window(sub_digits, clean_p):
            return True

    # 2. Exact match on 9-digit national number
    if p_len == len(nat_digits):
        if match_pattern_on_window(nat_digits, clean_p):
            return True

    # 3. Sliding windows on subscriber part (7 digits)
    if p_len < len(sub_digits):
        for i in range(len(sub_digits) - p_len + 1):
            window = sub_digits[i : i + p_len]
            if match_pattern_on_window(window, clean_p):
                return True

    # 4. Sliding windows on national digits (9 digits) if pattern is longer than 7
    if p_len < len(nat_digits) and p_len > len(sub_digits):
        for i in range(len(nat_digits) - p_len + 1):
            window = nat_digits[i : i + p_len]
            if match_pattern_on_window(window, clean_p):
                return True

    return False


def check_auto_rules(phone_number: str) -> Optional[Tuple[str, str]]:
    """
    Checks built-in automatic rules:
    - 000, 777, 1111
    - 4 identical digits (e.g. 8888)
    - Ascending sequences (1234, 2345, 5678, etc.)
    - Descending sequences (4321, 9876, etc.)
    - Mirror combinations (palindromes)
    - Repeating blocks (ABABAB, ABCABC)
    """
    digits = re.sub(r"\D", "", phone_number)
    if digits.startswith("998") and len(digits) == 12:
        sub_digits = digits[5:]
    elif len(digits) == 9:
        sub_digits = digits[2:]
    else:
        sub_digits = digits

    # Specific fixed strings
    if "1111" in sub_digits:
        return ("1111", "содержит 1111")
    if "777" in sub_digits:
        return ("777", "содержит 777")
    if "000" in sub_digits:
        return ("000", "содержит 000")

    # 4 identical digits
    for d in "0123456789":
        if d * 4 in sub_digits:
            return ("4_SAME", f"4 одинаковые цифры ({d * 4})")

    # Ascending sequences
    seqs = ["0123", "1234", "2345", "3456", "4567", "5678", "6789", "12345", "23456", "34567", "45678", "56789"]
    for s in seqs:
        if s in sub_digits:
            return ("SEQ_ASC", f"последовательность ({s})")

    # Descending sequences
    rev_seqs = ["3210", "4321", "5432", "6543", "7654", "8765", "9876", "54321", "65432", "76543", "87654", "98765"]
    for rs in rev_seqs:
        if rs in sub_digits:
            return ("SEQ_DESC", f"обратная последовательность ({rs})")

    # Mirror / Palindrome (length 6 or 7)
    if len(sub_digits) >= 6:
        tail6 = sub_digits[-6:]
        if tail6 == tail6[::-1] and len(set(tail6)) > 1:
            return ("MIRROR", f"зеркальная комбинация ({tail6})")
        if len(sub_digits) == 7 and sub_digits == sub_digits[::-1] and len(set(sub_digits)) > 1:
            return ("MIRROR", f"зеркальная комбинация ({sub_digits})")

    # Repeating blocks
    if len(sub_digits) >= 6:
        if match_pattern_on_window(sub_digits[-6:], "ABABAB"):
            return ("REPEAT_2", f"повторяющийся блок ABABAB ({sub_digits[-6:]})")
        if match_pattern_on_window(sub_digits[-6:], "ABCABC"):
            return ("REPEAT_3", f"повторяющийся блок ABCABC ({sub_digits[-6:]})")

    return None


def check_number_match(
    phone_number: str,
    enabled_patterns: Optional[List[str]] = None,
    check_auto: bool = True,
) -> MatchResult:
    """
    Checks if phone number matches any enabled patterns or automatic rules.
    Returns MatchResult(matched=True/False, pattern=..., reason=...).
    """
    if enabled_patterns:
        for p in enabled_patterns:
            if match_pattern(phone_number, p):
                return MatchResult(
                    matched=True,
                    pattern=p,
                    reason=f"совпадение с {p}",
                )

    if check_auto:
        auto_res = check_auto_rules(phone_number)
        if auto_res:
            p_name, reason = auto_res
            return MatchResult(
                matched=True,
                pattern=p_name,
                reason=reason,
            )

    return MatchResult(matched=False, pattern="", reason="")
