"""
generators.py — Cryptographically secure password generator.

Uses Python's secrets module (backed by OS CSPRNG) for all randomness.
"""

from __future__ import annotations

import secrets
import string
from typing import Optional


# ---------------------------------------------------------------------------
# Character pools
# ---------------------------------------------------------------------------
LOWERCASE = string.ascii_lowercase
UPPERCASE = string.ascii_uppercase
DIGITS = string.digits
SYMBOLS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

ALL_CHARACTERS = LOWERCASE + UPPERCASE + DIGITS + SYMBOLS


class PasswordGenerator:
    """
    Generate random passwords with configurable rules.

    Example:
        gen = PasswordGenerator(length=24, use_symbols=True, use_numbers=True)
        pwd = gen.generate()
    """

    def __init__(
        self,
        length: int = 24,
        use_lowercase: bool = True,
        use_uppercase: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
        exclude_ambiguous: bool = False,
        custom_symbols: Optional[str] = None,
    ):
        self.length = max(4, length)
        self.use_lowercase = use_lowercase
        self.use_uppercase = use_uppercase
        self.use_digits = use_digits
        self.use_symbols = use_symbols
        self.exclude_ambiguous = exclude_ambiguous
        self.custom_symbols = custom_symbols

    # ------------------------------------------------------------------
    # Character pool construction
    # ------------------------------------------------------------------
    def _build_pool(self) -> str:
        pool_parts: list[str] = []

        if self.use_lowercase:
            pool_parts.append(LOWERCASE)
        if self.use_uppercase:
            pool_parts.append(UPPERCASE)
        if self.use_digits:
            pool_parts.append(DIGITS)
        if self.use_symbols:
            pool_parts.append(self.custom_symbols if self.custom_symbols else SYMBOLS)

        pool = "".join(pool_parts)

        if not pool:
            pool = ALL_CHARACTERS  # safe fallback

        if self.exclude_ambiguous:
            # Remove characters commonly confused: l, 1, I, O, 0
            ambiguous = set("l1IO0")
            pool = "".join(c for c in pool if c not in ambiguous)

        if not pool:
            pool = "abcdef"  # absolute fallback (should never hit)

        return pool

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(self) -> str:
        """
        Generate a random password satisfying the configured constraints.

        Guarantees at least one character from each enabled category
        (when the pool would allow it), then fills the rest randomly.
        """
        pool = self._build_pool()

        # Determine required character sets
        required_sets: list[str] = []
        if self.use_lowercase:
            required_sets.append(LOWERCASE)
        if self.use_uppercase:
            required_sets.append(UPPERCASE)
        if self.use_digits:
            required_sets.append(DIGITS)
        if self.use_symbols:
            required_sets.append(self.custom_symbols if self.custom_symbols else SYMBOLS)

        # Strip ambiguous chars from required sets too
        if self.exclude_ambiguous:
            ambiguous = set("l1IO0")
            required_sets = [
                "".join(c for c in s if c not in ambiguous) for s in required_sets
            ]

        # Build password: first satisfy each required set, then random fill
        password_chars: list[str] = []

        for char_set in required_sets:
            if char_set:  # only if the set is non-empty
                password_chars.append(secrets.choice(char_set))

        remaining = self.length - len(password_chars)
        if remaining > 0:
            password_chars.extend(secrets.choice(pool) for _ in range(remaining))

        # Shuffle to avoid predictable positions of required chars
        # Fisher-Yates shuffle using secrets
        for i in range(len(password_chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            password_chars[i], password_chars[j] = password_chars[j], password_chars[i]

        return "".join(password_chars)

    # ------------------------------------------------------------------
    # Convenience: generate-and-show variant for the UI
    # ------------------------------------------------------------------
    @staticmethod
    def generate_strong_default() -> str:
        """Generate a strong 24-char password with all character types."""
        gen = PasswordGenerator(length=24)
        return gen.generate()


# ---------------------------------------------------------------------------
# Password strength estimate (for UI feedback — NOT security critical)
# ---------------------------------------------------------------------------
def estimate_strength(password: str) -> dict:
    """
    Return a dict with 'score' (0-4), 'label', 'entropy_bits', and 'feedback'.
    Purely informational — not used for any security decision.
    """
    length = len(password)
    pool_size = 0
    has_lower = any(c in LOWERCASE for c in password)
    has_upper = any(c in UPPERCASE for c in password)
    has_digit = any(c in DIGITS for c in password)
    has_symbol = any(c in SYMBOLS for c in password)

    if has_lower:
        pool_size += len(LOWERCASE)
    if has_upper:
        pool_size += len(UPPERCASE)
    if has_digit:
        pool_size += len(DIGITS)
    if has_symbol:
        pool_size += len(SYMBOLS)

    if pool_size == 0:
        return {"score": 0, "label": "None", "entropy_bits": 0, "feedback": "Enter a password."}

    import math
    entropy = length * math.log2(pool_size)

    if length < 8:
        score = 1
        label = "Weak"
        feedback = "Use at least 8 characters."
    elif entropy < 50:
        score = 1
        label = "Weak"
        feedback = "Add more character variety."
    elif entropy < 70:
        score = 2
        label = "Fair"
        feedback = "Reasonable, but could be stronger."
    elif entropy < 90:
        score = 3
        label = "Strong"
        feedback = "Good password!"
    else:
        score = 4
        label = "Very Strong"
        feedback = "Excellent password!"

    # Penalise if length is short even with variety
    if length < 12 and score > 2:
        score = max(2, score - 1)

    return {
        "score": score,
        "label": label,
        "entropy_bits": round(entropy, 1),
        "feedback": feedback,
    }
