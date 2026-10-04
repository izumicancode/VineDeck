"""Single source of truth for the product name.

Rename the application by editing the constants below (plus the packaging files
in ``packaging/`` and the icon in ``resources/icons``). Nothing else in the code
base hardcodes the name.
"""

from . import __version__

APP_NAME = "VineDeck"                 # display name
APP_SLUG = "vinedeck"                 # directory names, logger name, executable
APP_DESKTOP_ID = "vinedeck"           # .desktop file / Wayland app-id
APP_TAGLINE = "A beautiful home for your Windows applications and games."
APP_VERSION = __version__
APP_LICENSE = "Apache-2.0"
APP_AUTHOR = "izumicancode"
APP_AUTHOR_URL = "https://github.com/izumicancode"
APP_COPYRIGHT = f"Copyright 2026 {APP_AUTHOR}"

# About-page profile (shown in Settings -> About)
APP_AUTHOR_NAME = "Izumi"
APP_AUTHOR_ROLE = "Full-Stack Developer  ·  React & Node.js  ·  Webflow  ·  AI"
APP_AUTHOR_BIO = (
    "Code first, design second. I like building clean interfaces, scalable systems and smooth "
    "experiences, from React and Node.js on the web to Python tools like this one. VineDeck is my "
    "take on giving your Windows apps and games on Linux a home that is actually nice to look at."
)
APP_AUTHOR_PASSIONS = ("Clean UI", "Scalable Systems", "Smooth UX")
APP_AUTHOR_PROJECTS = (          # (name, url, one-line description)
    ("Secure-Line", "https://github.com/izumicancode/Secure-Line",
     "End-to-end-encrypted, mesh-relayed chat for your LAN  ·  Python"),
    ("Manga-Reader", "https://github.com/izumicancode/Maga-Reader",
     "Polished Manga-reader" "clean UI  ·  Shadcn, TypeScript, tailwindcss"),
    ("ascii-studio", "https://github.com/izumicancode/ascii-studio",
     "Text-art, ascii-art ·  Next.js, TypeScript, tailwindcss"),
)
APP_AUTHOR_LINKS = (             # (label, url)
    ("GitHub", APP_AUTHOR_URL),
    ("Portfolio", "https://info-husayn.vercel.app"),
    ("LinkedIn", "https://www.linkedin.com/in/altav-husayn-4a03a0403"),
    ("X", "https://twitter.com/xxRokanxx"),
)
