from __future__ import annotations

from questionary import Style
from rich.theme import Theme

PALETTE = {
    "brand": "#ff6600",
    "accent": "#5f00d7",
    "info": "cyan",
    "warning": "magenta",
    "danger": "red",
    "success": "green",
    "muted": "grey50",
}

RICH_THEME = Theme(
    {
        "info": f"dim {PALETTE['info']}",
        "warning": PALETTE["warning"],
        "danger": f"bold {PALETTE['danger']}",
        "success": f"bold {PALETTE['success']}",
        "title": f"bold white on {PALETTE['accent']}",
        "key": f"bold {PALETTE['brand']}",
        "value": "white",
        "hint": f"italic {PALETTE['muted']}",
        "brand": f"bold {PALETTE['brand']}",
    }
)

QUESTIONARY_STYLE = Style(
    [
        ("qmark", f"fg:{PALETTE['brand']} bold"),
        ("question", "bold"),
        ("pointer", f"fg:{PALETTE['brand']} bold"),
        ("highlighted", f"fg:black bg:{PALETTE['brand']} bold"),
        ("selected", f"fg:{PALETTE['brand']} bold"),
        ("answer", f"fg:{PALETTE['brand']}"),
    ]
)

QUESTIONARY_STYLE_PLAIN = Style([])
