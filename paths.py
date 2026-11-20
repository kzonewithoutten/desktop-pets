import os
import sys

FROZEN = getattr(sys, "frozen", False)
BASE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
CHARACTERS = os.path.join(DATA, "characters")
EFFECTS = os.path.join(DATA, "effects")
EVENTS = os.path.join(DATA, "events.json")
SETTINGS = os.path.join(DATA, "settings.json")
PLAY_FILE = os.path.join(DATA, "_play.txt")
TRASH = os.path.join(DATA, "_корзина")
FONTS = os.path.join(BASE, "fonts")
ICONS = os.path.join(BASE, "icons")
LOG = os.path.join(BASE, "crash.log")
