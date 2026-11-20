import ctypes
import os
import struct

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
SHOUT_WORDS = ("крик", "shout", "sfx")


def family_name(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        base = struct.unpack(">I", data[12:16])[0] if data[:4] == b"ttcf" else 0
        for i in range(struct.unpack(">H", data[base + 4:base + 6])[0]):
            rec = base + 12 + 16 * i
            if data[rec:rec + 4] != b"name":
                continue
            off = struct.unpack(">I", data[rec + 8:rec + 12])[0]
            _, count, strings = struct.unpack(">HHH", data[off:off + 6])
            found = {}
            for j in range(count):
                pid, _, lang, nid, length, so = struct.unpack(">HHHHHH", data[off + 6 + 12 * j:off + 18 + 12 * j])
                if nid != 1:
                    continue
                raw = data[off + strings + so:off + strings + so + length]
                name = raw.decode("utf-16-be", "ignore") if pid in (0, 3) else raw.decode("latin-1", "ignore")
                found[(pid == 3, lang == 0x409)] = name
            for key in ((True, True), (True, False), (False, True), (False, False)):
                if key in found:
                    return found[key].strip("\x00 ")
    except (OSError, struct.error, IndexError):
        pass
    return None


def load():
    roles = {"main": None, "shout": None}
    if not os.path.isdir(DIR):
        return roles
    for f in sorted(os.listdir(DIR)):
        if not f.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        path = os.path.join(DIR, f)
        try:
            ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0)
        except Exception:
            continue
        fam = family_name(path)
        if not fam:
            continue
        role = "shout" if any(w in f.lower() for w in SHOUT_WORDS) else "main"
        roles[role] = roles[role] or fam
    return roles
