"""
Модуль фильтрации и проверки шаблонов номеров.
Поддерживает точные цифры, буквы и смешанные комбинации.
"""

from dataclasses import dataclass
import re
from typing import List, Dict, Optional, Tuple, Set


@dataclass
class MatchResult:
    matched: bool
    pattern: str = ""
    reason: str = ""


# По умолчанию список предустановленных шаблонов пуст,
# чтобы пользователь мог сам задавать нужные правила.
PRESET_PATTERNS: List[str] = []


def clean_pattern_str(pattern: str) -> str:
    """Удаляет пробелы и дефисы, приводит к верхнему регистру."""
    return re.sub(r"[^A-Za-z0-9]", "", pattern).upper()


def validate_pattern(pattern: str) -> bool:
    """
    Проверяет корректность шаблона.
    Может содержать буквы A-Z, цифры 0-9, пробелы и дефисы. Длина от 2 до 12 символов.
    """
    cleaned = clean_pattern_str(pattern)
    if not (2 <= len(cleaned) <= 12):
        return False
    return bool(re.match(r"^[A-Z0-9\s\-]+$", pattern, re.IGNORECASE))


def match_pattern_on_window(digits: str, clean_pattern: str) -> bool:
    """
    Сравнивает цепочку цифр с очищенным шаблоном равной длины.
    - Цифра в шаблоне должна точно совпадать с цифрой в номере.
    - Одинаковые буквы обозначают одинаковые цифры.
    - Разные буквы обозначают разные цифры.
    """
    if len(digits) != len(clean_pattern):
        return False

    letter_map: Dict[str, str] = {}
    used_digits: Set[str] = set()

    for p_char, d_char in zip(clean_pattern, digits):
        if p_char.isdigit():
            if p_char != d_char:
                return False
        elif p_char.isalpha():
            p_upper = p_char.upper()
            if p_upper in letter_map:
                if letter_map[p_upper] != d_char:
                    return False
            else:
                if d_char in used_digits:
                    return False
                letter_map[p_upper] = d_char
                used_digits.add(d_char)
        else:
            return False

    return True


def match_pattern(phone_number: str, pattern: str) -> bool:
    """
    Проверяет совпадение шаблона с номером телефона.
    Учитывает 7-значный номер абонента и 9-значный номер с кодом оператора.
    """
    clean_p = clean_pattern_str(pattern)
    if not clean_p:
        return False

    digits = re.sub(r"\D", "", phone_number)
    if digits.startswith("998") and len(digits) == 12:
        nat_digits = digits[3:]      # 9 цифр
        sub_digits = digits[5:]      # 7 цифр
    elif len(digits) == 9:
        nat_digits = digits
        sub_digits = digits[2:]
    elif len(digits) == 7:
        nat_digits = digits
        sub_digits = digits
    else:
        nat_digits = digits
        sub_digits = digits

    p_len = len(clean_p)

    # Точное совпадение с 7-значным номером
    if p_len == len(sub_digits):
        if match_pattern_on_window(sub_digits, clean_p):
            return True

    # Точное совпадение с 9-значным номером
    if p_len == len(nat_digits):
        if match_pattern_on_window(nat_digits, clean_p):
            return True

    # Скользящее окно по 7-значному номеру (например, шаблоны из 3-6 символов)
    if p_len < len(sub_digits):
        for i in range(len(sub_digits) - p_len + 1):
            window = sub_digits[i : i + p_len]
            if match_pattern_on_window(window, clean_p):
                return True

    # Скользящее окно по 9-значному номеру
    if p_len < len(nat_digits) and p_len > len(sub_digits):
        for i in range(len(nat_digits) - p_len + 1):
            window = nat_digits[i : i + p_len]
            if match_pattern_on_window(window, clean_p):
                return True

    return False


def check_auto_rules(phone_number: str) -> Optional[Tuple[str, str]]:
    """
    Автоматические базовые правила красоты.
    """
    digits = re.sub(r"\D", "", phone_number)
    if digits.startswith("998") and len(digits) == 12:
        sub_digits = digits[5:]
    elif len(digits) == 9:
        sub_digits = digits[2:]
    else:
        sub_digits = digits

    if "1111" in sub_digits:
        return ("1111", "содержит 1111")
    if "777" in sub_digits:
        return ("777", "содержит 777")
    if "000" in sub_digits:
        return ("000", "содержит 000")

    for d in "0123456789":
        if d * 4 in sub_digits:
            return ("4_SAME", f"4 одинаковые цифры ({d * 4})")

    seqs = ["0123", "1234", "2345", "3456", "4567", "5678", "6789"]
    for s in seqs:
        if s in sub_digits:
            return ("SEQ_ASC", f"последовательность ({s})")

    rev_seqs = ["3210", "4321", "5432", "6543", "7654", "8765", "9876"]
    for rs in rev_seqs:
        if rs in sub_digits:
            return ("SEQ_DESC", f"обратная последовательность ({rs})")

    if len(sub_digits) >= 6:
        tail6 = sub_digits[-6:]
        if tail6 == tail6[::-1] and len(set(tail6)) > 1:
            return ("MIRROR", f"зеркальная комбинация ({tail6})")

    return None


def check_number_match(
    phone_number: str,
    enabled_patterns: Optional[List[str]] = None,
    check_auto: bool = True,
) -> MatchResult:
    """
    Главная функция проверки номера по шаблонам и правилам.
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
