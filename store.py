import json
import os
import re
import shutil
import time

import catalog
import paths

SETTINGS_DEFAULTS = {"desktop_only": True, "fps": 30, "size": 1.15, "caps": True, "intro": True}


def _read(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def char_dir(cid):
    return os.path.join(paths.CHARACTERS, cid)


def list_ids():
    if not os.path.isdir(paths.CHARACTERS):
        return []
    ids = [d for d in os.listdir(paths.CHARACTERS)
           if not d.startswith("_") and os.path.exists(os.path.join(char_dir(d), "character.json"))]
    order = load_settings().get("order", [])
    return sorted(ids, key=lambda c: (order.index(c) if c in order else len(order), c))


def load_char(cid):
    data = _read(os.path.join(char_dir(cid), "character.json"), {})
    full = catalog.new_character(cid)
    full["lines"] = {}
    full.update(data if isinstance(data, dict) else {})
    acts = {k: 0.0 for k in catalog.ACTIONS}
    acts.update(full.get("actions") or {})
    full["actions"] = acts
    return full


def save_char(cid, data):
    _write(os.path.join(char_dir(cid), "character.json"), data)


def load_all():
    return {cid: load_char(cid) for cid in list_ids()}


def make_id(name):
    base = re.sub(r"[^\w\-]", "_", name.strip().lower()) or "pers"
    cid, n = base, 2
    while os.path.exists(char_dir(cid)):
        cid, n = f"{base}{n}", n + 1
    return cid


def create_char(name):
    cid = make_id(name)
    os.makedirs(char_dir(cid), exist_ok=True)
    save_char(cid, catalog.new_character(name))
    return cid


def trash(path, label):
    os.makedirs(paths.TRASH, exist_ok=True)
    dest = os.path.join(paths.TRASH, f"{label}_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.move(path, dest)
    return dest


def delete_char(cid):
    trash(char_dir(cid), f"персонаж_{cid}")
    events = [e for e in load_events() if cid not in e.get("who", [])]
    save_events(events)
    for other in list_ids():
        data = load_char(other)
        rel = [r for r in data.get("relations", []) if r.get("target") != cid]
        if rel != data.get("relations", []):
            data["relations"] = rel
            save_char(other, data)


def relations(chars):
    out = []
    for cid, data in chars.items():
        for r in data.get("relations", []):
            if r.get("target") in chars and r.get("type") in catalog.RELATIONS:
                out.append((cid, r["type"], r["target"]))
    return out


def load_events():
    data = _read(paths.EVENTS, [])
    return data if isinstance(data, list) else []


def save_events(events):
    _write(paths.EVENTS, events)


def new_event_id(events):
    used = {e.get("id") for e in events}
    n = 1
    while f"e{n}" in used:
        n += 1
    return f"e{n}"


def load_settings():
    data = _read(paths.SETTINGS, {})
    return {**SETTINGS_DEFAULTS, **(data if isinstance(data, dict) else {})}


def save_settings(data):
    _write(paths.SETTINGS, data)
