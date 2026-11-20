import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import paths
import store

WORK = os.path.join(BASE, "_build")

README = """DESKTOP PETS — КАК ПОЛЬЗОВАТЬСЯ

«Desktop Pets.exe» — запускает персонажей на рабочем столе.
«Desktop Pets — редактор.exe» — тут всё настраивается: персонажи, их рисунки, реплики, события.
Python и что-то ещё ставить не нужно.

Персонажи
  • ЛКМ — перетащить или тыкнуть, ПКМ по персонажу — меню (покормить, действия, события, выход).
  • По умолчанию они видны только на рабочем столе и прячутся, когда открыта программа (галочка в меню).
  • Автозапуск с Windows — тоже галочка в меню.

Редактор
  • «+ Персонаж» — новый персонаж. Без картинок он рисуется простым кругляшом твоего цвета.
  • Вкладка «Персонаж»: имя, цвет, скорость, что делает сам (вес = как часто) и отношения:
    охотится на / защищает / пристаёт к / болтает с.
  • Вкладка «Анимации»: вставляешь свои покадровые PNG (холст ~200×200, лицом вправо, ноги на нижнем краю,
    прозрачный фон). Можно делать свои анимации и решать, когда они играют.
  • Вкладка «Реплики»: что персонаж говорит в разных ситуациях.
  • Вкладка «События»: свои сценки — кто, когда (иногда, рядом, далеко, по клику, при перетаскивании…),
    и по шагам: кто что говорит и какую анимацию играет. У событий есть версии «рядом» и «далеко».
  • Всё сохраняется само, запущенные персонажи подхватывают изменения через пару секунд.

Шрифты для облачков лежат в папке fonts (там же инструкция, как поставить свой).
Всё, что удаляешь в редакторе, уходит в data/_корзина — оттуда можно вернуть.
"""

SPEC = r'''
# -*- mode: python ; coding: utf-8 -*-
base = {base!r}
common = dict(pathex=[base], hiddenimports=[], excludes=["numpy", "PIL", "matplotlib", "test", "unittest"] + {extra!r})
a1 = Analysis([base + r"\main.py"], **common)
a2 = Analysis([base + r"\editor.py"], **common)
pyz1 = PYZ(a1.pure)
pyz2 = PYZ(a2.pure)
e1 = EXE(pyz1, a1.scripts, [], exclude_binaries=True, name="Pets", console=False, icon={pets_icon!r})
e2 = EXE(pyz2, a2.scripts, [], exclude_binaries=True, name="Editor", console=False, icon={editor_icon!r})
coll = COLLECT(e1, a1.binaries, a1.datas, e2, a2.binaries, a2.datas, name="app")
'''


def desktop():
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


def log(text):
    print(text, flush=True)


def ensure_pyinstaller():
    try:
        import PyInstaller
        return
    except ImportError:
        pass
    log("Ставлю PyInstaller (один раз, нужен только для сборки)…")
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "pyinstaller"],
                   check=True)


def build_exe(extra_excludes):
    os.makedirs(WORK, exist_ok=True)
    spec = os.path.join(WORK, "pets.spec")
    with open(spec, "w", encoding="utf-8") as f:
        f.write(SPEC.format(base=BASE, extra=extra_excludes, pets_icon=os.path.join(BASE, "icons", "pets.ico"),
                            editor_icon=os.path.join(BASE, "icons", "editor.ico")))
    log("Собираю программы (PyInstaller)…")
    p = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN",
                        "--distpath", os.path.join(WORK, "dist"), "--workpath", os.path.join(WORK, "build"), spec],
                       cwd=WORK, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       encoding="utf-8", errors="replace")
    for line in p.stdout.splitlines()[-15:]:
        log("  " + line)
    if p.returncode != 0:
        raise SystemExit("PyInstaller не смог собрать программу.")
    return os.path.join(WORK, "dist", "app")


def copy_data(dest, chars):
    data = os.path.join(dest, "data")
    os.makedirs(os.path.join(data, "characters"), exist_ok=True)
    keep = set(chars)
    for cid in chars:
        shutil.copytree(store.char_dir(cid), os.path.join(data, "characters", cid),
                        ignore=shutil.ignore_patterns("*.tmp", "_*.txt"))
        cfg_path = os.path.join(data, "characters", cid, "character.json")
        with open(cfg_path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
        cfg["relations"] = [r for r in cfg.get("relations", []) if r.get("target") in keep]
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    if os.path.isdir(paths.EFFECTS):
        shutil.copytree(paths.EFFECTS, os.path.join(data, "effects"))
    events = [e for e in store.load_events() if set(e.get("who", [])) <= keep]
    with open(os.path.join(data, "events.json"), "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    settings = dict(store.SETTINGS_DEFAULTS, order=list(chars))
    with open(os.path.join(data, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return len(events)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Desktop Pets")
    ap.add_argument("--chars", default="")
    ap.add_argument("--out", default=desktop())
    args = ap.parse_args()
    chars = [c for c in args.chars.split(",") if c and c in store.list_ids()]
    started = time.time()

    ensure_pyinstaller()
    try:
        import my_characters
        own = set(my_characters.NAMES)
    except ImportError:
        own = set()
    needed = any(store.load_char(c).get("drawing") in own for c in chars)
    app = build_exe([] if needed else ["my_characters"])

    stage = os.path.join(WORK, "package", args.name)
    shutil.rmtree(os.path.join(WORK, "package"), ignore_errors=True)
    shutil.copytree(app, stage)
    os.replace(os.path.join(stage, "Pets.exe"), os.path.join(stage, "Desktop Pets.exe"))
    os.replace(os.path.join(stage, "Editor.exe"), os.path.join(stage, "Desktop Pets — редактор.exe"))
    n_events = copy_data(stage, chars)
    shutil.copytree(paths.FONTS, os.path.join(stage, "fonts"))
    shutil.copytree(paths.ICONS, os.path.join(stage, "icons"), ignore=shutil.ignore_patterns("cascada.*"))
    with open(os.path.join(stage, "Как пользоваться.txt"), "w", encoding="utf-8-sig") as f:
        f.write(README)
    log(f"Положил персонажей: {len(chars)}, событий: {n_events}.")

    zip_base = os.path.join(args.out, args.name)
    log("Упаковываю в zip…")
    archive = shutil.make_archive(zip_base, "zip", os.path.join(WORK, "package"), args.name)
    size = os.path.getsize(archive) / 1024 / 1024
    log(f"Размер архива: {size:.1f} МБ, сборка заняла {time.time() - started:.0f} с.")
    log(f"ГОТОВО: {archive}")


if __name__ == "__main__":
    main()
