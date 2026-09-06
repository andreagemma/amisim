"""Reusable CLI/settings option parsing helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def nested_dict_from_key_value_list(
    pairs: Mapping[str, str] | Iterable[tuple[str, str]],
) -> dict[str, object]:
    """Convert colon-separated keys into a nested dictionary.

    Example key format:
        "a:b:c" -> {"a": {"b": {"c": value}}}

    :param pairs: Mapping or iterable of key/value tuples.
    :return: Nested dictionary representation.
    :raises ValueError: If a key has empty path segments.
    """
    items = pairs.items() if isinstance(pairs, Mapping) else pairs
    result: dict[str, object] = {}

    for key, value in items:
        parts = [part.strip() for part in key.split(":")]
        if not all(parts):
            raise ValueError(f"Invalid key path {key!r}: empty path segment")

        current = result
        for part in parts[:-1]:
            existing = current.get(part)
            if existing is None:
                child: dict[str, object] = {}
                current[part] = child
                current = child
                continue
            if not isinstance(existing, dict):
                raise ValueError(f"Invalid key path {key!r}: {part!r} is already assigned as a value")
            current = existing

        current[parts[-1]] = value

    return result


def parse_section_option_overrides(values: Iterable[str]) -> dict[str, dict[str, str]]:
    """Parse CLI options in SECTION:NAME=VALUE format.

    :param values: Raw option tokens from CLI.
    :return: Nested section->name->value dictionary.
    :raises ValueError: If token format is invalid.
    """
    flat: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Invalid -O/--option value: {item!r}. Expected SECTION:NAME=VALUE")
        key_path, raw_value = item.split("=", 1)
        key_path = key_path.strip()
        if not key_path or ":" not in key_path:
            raise ValueError(f"Invalid -O/--option value: {item!r}. Expected SECTION:NAME=VALUE")
        flat[key_path] = raw_value

    nested = nested_dict_from_key_value_list(flat)
    normalized: dict[str, dict[str, str]] = {}
    for section, maybe_map in nested.items():
        if not isinstance(maybe_map, dict):
            raise ValueError(f"Invalid option path for section {section!r}: missing variable name")
        section_map: dict[str, str] = {}
        for key, value in maybe_map.items():
            if isinstance(value, dict):
                raise ValueError(
                    f"Invalid option path for section {section!r}: only one variable level is supported"
                )
            section_map[str(key)] = str(value)
        normalized[str(section)] = section_map

    return normalized
