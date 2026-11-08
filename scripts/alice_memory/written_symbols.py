"""Bounded written surface identity, independent of neural inference imports."""
import unicodedata


def symbol(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("A written name must be a string.")
    value = unicodedata.normalize("NFKC", value).casefold()
    if not 1 <= len(value) <= 32 or len(value.encode("utf-8")) > 64 or not value.isalnum():
        raise ValueError("Names must be bounded alphanumeric symbols without whitespace.")
    return value
