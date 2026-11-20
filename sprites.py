import json
import os
import random
import re
import tkinter as tk
from fractions import Fraction

import catalog
import paths

ROOT = paths.CHARACTERS
PLAY_FILE = paths.PLAY_FILE
TRASH = paths.TRASH
VARIANT_RE = re.compile(r"^вариант\s*(\d+)$", re.IGNORECASE)

TRIGGERS = {
    "random": "Иногда, сам(а) по себе",
    "click": "Когда тыкаешь мышкой",
    "drop": "Когда отпустили после переноски",
    "icon_bump": "Врезался(ась) в иконку рабочего стола",
    "icon_sit": "Сидит на иконке рабочего стола",
    "near:any": "Рядом кто-нибудь",
    "hungry": "Когда голодный",
    "tired": "Когда устал",
    "menu": "Только вручную (из меню ПКМ)",
}
LOOPING = catalog.LOOPING
FREQ = {"rare": ("Редко", 0.3), "sometimes": ("Иногда", 1.0), "often": ("Часто", 2.5)}
TIMES = {"any": ("Когда угодно", 0, 24), "morning": ("Утром (6–12)", 6, 12), "day": ("Днём (12–18)", 12, 18),
         "evening": ("Вечером (18–24)", 18, 24), "night": ("Ночью (0–6)", 0, 6)}
MOVE = {0: "Стоит на месте", 40: "Двигается медленно", 90: "Идёт", 180: "Быстро"}
SURFACES = {"any": "Где угодно", "floor": "Только на полу", "icon": "Только на иконке"}
VARIANT_MODES = {"order": "По очереди", "random": "Случайно"}
CUSTOM_DEFAULTS = {"fps": 8, "trigger": "random", "freq": "sometimes", "time": "any", "repeat": 2, "move": 0,
                   "say": [], "area": [0, 0, 1, 1], "surface": "any"}

STANDARD = {
    "idle": (6, 4, "стоит, дышит, моргает"),
    "walk": (8, 10, "шаг"),
    "run": (6, 14, "бег"),
    "held": (4, 6, "его держат мышкой"),
    "fall": (2, 8, "летит/падает"),
    "sleep": (4, 3, "спит"),
    "eat": (4, 6, "ест"),
    "tea": (6, 4, "пьёт чай"),
    "sport_jacks": (4, 8, "прыжки «ноги вместе — ноги врозь»"),
    "sport_squat": (4, 6, "приседания"),
    "laugh": (4, 12, "безумный смех"),
    "bang": (4, 10, "колотит в экран (экран справа)"),
    "climb": (4, 8, "лезет вверх по краю экрана"),
    "code": (4, 10, "работает с ноутбуком"),
    "read": (2, 2, "читает"),
    "scan": (6, 8, "идёт и сканирует (луч рисует программа)"),
    "knocked": (2, 3, "повержен, лежит"),
    "idle_alert": (2, 8, "необязательно: стоит в тревоге"),
    "run_alert": (6, 14, "необязательно: гонится в тревоге"),
    "icon": (2, 2, "притворился иконкой файла"),
    "flat": (2, 2, "притворился полоской пикселей"),
    "behind": (2, 3, "присел и прячется за защитником"),
    "whistle": (4, 5, "невинно насвистывает (прячет кого-то за спиной)"),
    "defend": (2, 4, "раскинул руки, защищает"),
    "facepalm": (2, 3, "рука на лице"),
}
EFFECTS = {"cloud": (6, 12, "облако драки (оба персонажа внутри)")}
NO_FALLBACK = {"icon", "flat"}
FALLBACK = {"run": "walk", "fall": "held", "run_alert": "run", "idle_alert": "idle"}


def _natural(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name.lower())]


def read_settings(path):
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    return out


def read_info(folder):
    try:
        with open(os.path.join(folder, "info.json"), encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_info(folder, info):
    with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)


def list_frames(folder):
    if not os.path.isdir(folder):
        return []
    return sorted((f for f in os.listdir(folder) if f.lower().endswith(".png")), key=_natural)


def variant_dirs(folder):
    out = [(1, folder)]
    if os.path.isdir(folder):
        for d in os.listdir(folder):
            m = VARIANT_RE.match(d)
            if m and os.path.isdir(os.path.join(folder, d)):
                out.append((int(m.group(1)), os.path.join(folder, d)))
    return [p for _, p in sorted(out)]


def count_frames(folder):
    return sum(len(list_frames(v)) for v in variant_dirs(folder))


def time_ok(code, hour):
    _, a, b = TIMES.get(code, TIMES["any"])
    return a <= hour < b


def roles(cid, rels):
    out = []
    for a, kind, b in rels:
        if kind == "hunts":
            out += [("hunter", b)] if a == cid else [("prey", a)] if b == cid else []
        elif kind == "protects":
            out += [("protector", b)] if a == cid else [("protected", a)] if b == cid else []
        elif kind == "pesters":
            out += [("pester", b)] if a == cid else [("pestered", a)] if b == cid else []
        elif kind == "chats" and cid in (a, b):
            out.append(("chat", b if a == cid else a))
    return out


def standard_anims(cid, chars, rels):
    data = chars.get(cid, {})
    acts = data.get("actions", {})
    mapping = data.get("anims", {})
    names = ["idle", "walk", "run", "held", "fall"]
    for code, (_, anim, _) in catalog.ACTIONS.items():
        if acts.get(code, 0) > 0:
            anim = mapping.get(code, anim)
            names += {"sport": ["sport_jacks", "sport_squat"], "escape": ["bang", "climb"]}.get(code, [anim])
    for role, _ in roles(cid, rels):
        names += {"prey": ["knocked"] + (["icon", "flat"] if data.get("can_disguise") else []),
                  "protected": ["behind"], "hunter": ["scan", "knocked", "idle_alert", "run_alert"],
                  "protector": ["whistle", "defend", "facepalm"]}.get(role, [])
    out = []
    for n in names:
        if n in STANDARD and n not in out:
            out.append(n)
    return out


def anim_names(cid, chars=None, rels=None):
    if chars is None:
        import store
        chars = store.load_all()
        rels = store.relations(chars)
    names = standard_anims(cid, chars, rels or [])
    folder = os.path.join(ROOT, cid)
    if os.path.isdir(folder):
        for n in sorted(os.listdir(folder), key=_natural):
            if os.path.isdir(os.path.join(folder, n)) and not n.startswith("_") and n not in names:
                names.append(n)
    return names


def is_custom(name):
    return name not in STANDARD and name not in EFFECTS


def trigger_groups(cid, chars, rels):
    name = lambda k: chars.get(k, {}).get("name", k)
    general = dict(TRIGGERS)
    for other in chars:
        if other != cid:
            general[f"near:{other}"] = f"Рядом ({name(other)})"
            general[f"far:{other}"] = f"Далеко ({name(other)})"
    situ = {}
    for role, other in roles(cid, rels):
        for code, label in catalog.ROLE_SITUATIONS.get(role, []):
            situ[f"{code}:{other}"] = f"{label} ({name(other)})"
    groups = [("Общие", general), ("Ситуации с другими", situ)]
    for other in chars:
        if other != cid:
            groups.append((f"Реакция на анимации: {name(other)}",
                           {f"react:{other}:{a}": f"{a} ({name(other)})" for a in anim_names(other, chars, rels)}))
    return groups


def triggers_for(cid, chars, rels):
    out = {}
    for _, items in trigger_groups(cid, chars, rels):
        out.update(items)
    return out


def normalize(info):
    full = {**CUSTOM_DEFAULTS, **info}
    area = full.get("area")
    if not (isinstance(area, list) and len(area) == 4):
        full["area"] = [0, 0, 1, 1]
    return full


def _copy(img, opt, *args):
    out = tk.PhotoImage()
    out.tk.call(out, "copy", img, opt, *args)
    return out


def _scaled(img, frac):
    if frac.numerator != 1:
        img = _copy(img, "-zoom", frac.numerator)
    if frac.denominator != 1:
        img = _copy(img, "-subsample", frac.denominator)
    return img


def _bbox(img):
    w, h = img.width(), img.height()
    step = max(1, min(w, h) // 80)
    xs, ys = [], []
    for y in range(0, h, step):
        for x in range(0, w, step):
            if not img.transparency_get(x, y):
                xs.append(x)
                ys.append(y)
    if not xs:
        return -w / 2, h, w / 2
    return min(xs) - w / 2, h - min(ys), max(xs) - w / 2


class Anim:
    def __init__(self, variants, fps, mode="order"):
        self.variants = [(frames, [_copy(f, "-subsample", -1, 1) for f in frames], _bbox(frames[0]))
                         for frames in variants]
        self.fps = fps
        self.mode = mode
        self.right = self.variants[0][0]
        self.bbox = self.variants[0][2]

    def duration(self, vi=0):
        return len(self.variants[vi % len(self.variants)][0]) / self.fps

    def next_variant(self, vi):
        n = len(self.variants)
        if n == 1:
            return 0
        if self.mode == "random":
            return random.choice([i for i in range(n) if i != vi])
        return (vi + 1) % n

    def bbox_of(self, vi):
        return self.variants[vi % len(self.variants)][2]

    def frame(self, t, facing, vi=0):
        right, left, _ = self.variants[vi % len(self.variants)]
        frames = right if facing > 0 else left
        return frames[int(t * self.fps) % len(frames)]

    def total_frames(self):
        return sum(len(v[0]) for v in self.variants)


class SpriteSet:
    def __init__(self, key, folder=None):
        self.key = key
        self.anims = {}
        self.customs = {}
        self.errors = []
        folder = folder or os.path.join(ROOT, key)
        if not os.path.isdir(folder):
            return
        cfg = read_settings(os.path.join(folder, "settings.txt"))
        try:
            scale = Fraction(cfg.get("scale", "1")).limit_denominator(8)
        except (ValueError, ZeroDivisionError):
            scale = Fraction(1)
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if not os.path.isdir(path) or name.startswith("_"):
                continue
            variants = []
            for vdir in variant_dirs(path):
                frames = []
                for f in list_frames(vdir):
                    try:
                        frames.append(_scaled(tk.PhotoImage(file=os.path.join(vdir, f)), scale))
                    except tk.TclError as e:
                        self.errors.append(f"{key}/{name}/{f}: {e}")
                if frames:
                    variants.append(frames)
            if not variants:
                continue
            info = read_info(path)
            default = (STANDARD.get(name) or EFFECTS.get(name) or (0, 8))[1]
            try:
                fps = float(info.get("fps") or cfg.get(name) or default)
            except (TypeError, ValueError):
                fps = 8
            self.anims[name] = Anim(variants, max(0.5, fps), info.get("variants", "order"))
            if is_custom(name):
                self.customs[name] = normalize(info)

    def __bool__(self):
        return "idle" in self.anims

    def get(self, name, alert=False):
        if alert and name + "_alert" in self.anims:
            return self.anims[name + "_alert"]
        seen = set()
        while name not in self.anims:
            if name in NO_FALLBACK or name in seen:
                return None
            seen.add(name)
            name = FALLBACK.get(name, "idle")
        return self.anims[name]

    def with_trigger(self, prefix):
        return [n for n, i in self.customs.items() if str(i.get("trigger", "")).startswith(prefix)]


def signature():
    out = []
    for dirpath, dirnames, filenames in os.walk(paths.DATA):
        dirnames[:] = [d for d in dirnames if not d.startswith("_")]
        for f in filenames:
            if f.startswith("_") or f.endswith(".tmp"):
                continue
            try:
                st = os.stat(os.path.join(dirpath, f))
            except OSError:
                continue
            out.append((dirpath, f, st.st_mtime_ns, st.st_size))
    return tuple(sorted(out))
