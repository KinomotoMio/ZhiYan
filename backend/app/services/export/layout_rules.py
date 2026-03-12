"""Shared export layout rules to keep HTML and PPTX outputs aligned."""


def get_outline_slide_columns(section_count: int) -> int:
    return 3 if section_count >= 5 else 2


def get_bullet_with_icons_columns(item_count: int) -> int:
    return 3 if item_count <= 3 else 4


def is_bullet_icons_only_compact(item_count: int) -> bool:
    return item_count >= 7
