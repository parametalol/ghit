
COLORS: dict[str, int] = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "light gray": 37,
    "default": 39,
    "dark gray": 90,
    "light red": 91,
    "light green": 92,
    "light yellow": 93,
    "light blue": 94,
    "light magenta": 95,
    "light cyan": 96,
    "white": 97,
}
STYLES: dict[str, int] = {
    "bold": 1,
    "dim": 2,
    "italic": 3,
    "underlined": 4,
    "blink": 5,
    "reverse": 7,
    "hidden": 8,
    "strikethrough": 9,
}
ESC = "\033"


def with_color(color: str, m: str) -> str:
    return f"{ESC}[{COLORS[color]}m{m}{ESC}[{COLORS['default']}m"


def with_style(style: str, m: str) -> str:
    return f"{ESC}[{STYLES[style]}m{m}{ESC}[0m"


def normal(m: str) -> str:
    return m


def deleted(m: str) -> str:
    return with_style("strikethrough", m)


def inactive(m: str) -> str:
    return with_color("dark gray", m)


def danger(m: str) -> str:
    return with_color("red", m)


def good(m: str) -> str:
    return with_color("green", m)


def warning(m: str) -> str:
    return with_color("yellow", m)


def calm(m: str) -> str:
    return with_color("light blue", m)


def colorful(m: str) -> str:
    return with_color("magenta", m)


def emphasis(m: str) -> str:
    return with_color("cyan", m)
