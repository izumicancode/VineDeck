"""Single source of truth for the product name.

Rename the application by editing the constants below (plus the packaging files
in ``packaging/`` and the icon in ``resources/icons``). Nothing else in the code
base hardcodes the name.
"""

from . import __version__

APP_NAME = "VineDeck"                 # display name
APP_SLUG = "vinedeck"                 # directory names, logger name, executable
APP_DESKTOP_ID = "vinedeck"           # .desktop file / Wayland app-id
APP_TAGLINE = "A polished home for your Windows games and apps."
APP_VERSION = __version__
APP_LICENSE = "Apache-2.0"
APP_AUTHOR = "izumicancode"
APP_AUTHOR_URL = "https://github.com/izumicancode"
APP_COPYRIGHT = f"Copyright 2026 {APP_AUTHOR}"

# About-page profile (shown in Settings -> About)
APP_AUTHOR_NAME = "Izumi Husayn"
APP_AUTHOR_ROLE = "Product Designer  ·  Full-Stack Engineer  ·  AI Builder"
APP_AUTHOR_BIO = (
    "I care about the little details that make software feel effortless. VineDeck is my take on "
    "turning your Windows games and apps on Linux into a clean, beautiful, and surprisingly joyful "
    "experience."
)
APP_AUTHOR_PASSIONS = ("Elegant UI", "Smooth UX", "Thoughtful Systems")
APP_AUTHOR_PROJECTS = (          # (name, url, one-line description)
    ("Secure-Line", "https://github.com/izumicancode/Secure-Line",
     "End-to-end encrypted local chat  ·  Python"),
    ("Manga-Reader", "https://github.com/izumicancode/Maga-Reader",
     "A refined reading experience  ·  TypeScript, Tailwind"),
    ("ascii-studio", "https://github.com/izumicancode/ascii-studio",
     "Generative text-art playground  ·  Next.js, TypeScript"),
)
APP_AUTHOR_LINKS = (             # (label, url)
    ("GitHub", APP_AUTHOR_URL),
    ("Portfolio", "https://info-husayn.vercel.app"),
    ("LinkedIn", "https://www.linkedin.com/in/altav-husayn-4a03a0403"),
    ("X", "https://twitter.com/xxRokanxx"),
)
