import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from fractions import Fraction
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog
import paths
import sprites as SP
import store

try:
    import desktop_icons
except Exception:
    desktop_icons = None

BG, PANEL, INK, MUTED, ACCENT, WARN, OK = "#1f1b24", "#2a2531", "#f1ecf6", "#a79fb3", "#ff3d8b", "#ffb347", "#5fe3a1"
FONT = ("Segoe UI", 10)
NAME_RE = re.compile(r"^[\w\-а-яА-ЯёЁ]+$")
MAP_W = 300
EFFECTS_KEY = "__effects__"
BODY_NAMES = {"simple": "Простой кругляш (своего цвета)"}
try:
    import my_characters
    BODY_NAMES.update(my_characters.NAMES)
except ImportError:
    pass
BUBBLES = {"manga": "Манга (сам выбирает: речь, крик, шёпот)", "robot": "Роботская плашка"}
POSES = ["", "laugh", "facepalm", "defend", "whistle", "eat", "tea", "code", "read", "sleep", "scan", "knocked",
         "bang", "climb", "sport_jacks", "sport_squat", "run", "walk"]


def work_bottom(root):
    try:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
        r = RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)
        return r.b
    except Exception:
        return root.winfo_screenheight() - 40


def inv(d, value, f=lambda x: x):
    return next((k for k, v in d.items() if f(v) == value), None)


class Saver:

    def __init__(self, root, fn, status):
        self.root, self.fn, self.status, self.job = root, fn, status, None
        self.paused = False

    def __call__(self, *_):
        if self.paused:
            return
        if self.job:
            self.root.after_cancel(self.job)
        self.job = self.root.after(500, self.flush)

    def flush(self):
        if self.job:
            self.root.after_cancel(self.job)
        self.job = None
        try:
            if self.fn() is not False:
                self.status(f"Сохранено ✓  {time.strftime('%H:%M:%S')}", OK)
        except Exception as e:
            self.status(f"Не сохранилось: {e}", WARN)


class Editor:
    def __init__(self):
        self.root = root = tk.Tk()
        root.title("Desktop Pets — редактор")
        height = min(820, work_bottom(root) - 50)
        root.geometry(f"1300x{height}+20+10")
        root.minsize(1140, min(720, height))
        try:
            root.iconbitmap(os.path.join(paths.ICONS, "editor.ico"))
        except tk.TclError:
            pass
        root.configure(bg=BG)
        self.style()
        os.makedirs(paths.CHARACTERS, exist_ok=True)
        self.key = None
        self.reload_data()
        self.build()
        ids = store.list_ids()
        self.select_char(ids[0] if ids else EFFECTS_KEY)

    def reload_data(self):
        self.chars = store.load_all()
        self.rels = store.relations(self.chars)

    def name_of(self, cid):
        return self.chars.get(cid, {}).get("name", cid)

    def style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=INK, fieldbackground=PANEL, font=FONT)
        st.configure("TFrame", background=BG)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("TLabel", background=BG, foreground=INK)
        st.configure("Panel.TLabel", background=PANEL, foreground=INK)
        st.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("Head.TLabel", background=PANEL, foreground=INK, font=("Segoe UI", 11, "bold"))
        st.configure("Title.TLabel", background=BG, foreground=INK, font=("Segoe UI", 15, "bold"))
        st.configure("TButton", background="#3a3344", foreground=INK, borderwidth=0, padding=(10, 5))
        st.map("TButton", background=[("active", "#4a4256"), ("disabled", "#2e2936")],
               foreground=[("disabled", "#6c6577")])
        st.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        st.map("Accent.TButton", background=[("active", "#ff5ea0")])
        st.configure("Small.TButton", padding=(7, 3))
        st.configure("VarOn.TButton", padding=(9, 3), background=ACCENT, foreground="#ffffff")
        st.configure("Var.TButton", padding=(9, 3))
        st.configure("TCheckbutton", background=PANEL, foreground=INK)
        st.map("TCheckbutton", background=[("active", PANEL)])
        st.configure("TCombobox", fieldbackground=PANEL, background="#3a3344", foreground=INK, arrowcolor=INK)
        st.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", INK)])
        st.configure("TSpinbox", fieldbackground=PANEL, foreground=INK, arrowcolor=INK, background="#3a3344")
        st.configure("TEntry", fieldbackground=PANEL, foreground=INK, insertcolor=INK)
        st.configure("Char.TButton", padding=(12, 6))
        st.configure("CharOn.TButton", padding=(12, 6), background=ACCENT, foreground="#ffffff")
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background="#2e2936", foreground=MUTED, padding=(16, 7), font=("Segoe UI", 10, "bold"))
        st.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", INK)])
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", INK)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def listbox(self, parent, **kw):
        return tk.Listbox(parent, bg=PANEL, fg=INK, selectbackground=ACCENT, selectforeground="#ffffff",
                          highlightthickness=0, borderwidth=0, activestyle="none", font=FONT,
                          exportselection=False, **kw)

    def textbox(self, parent, **kw):
        return tk.Text(parent, bg="#1f1b24", fg=INK, insertbackground=INK, relief="flat", font=FONT, wrap="word", **kw)

    def say(self, text, color=MUTED):
        self.status.config(text=text, fg=color)

    def build(self):
        root = self.root
        top = ttk.Frame(root, padding=(14, 10, 14, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Desktop Pets", style="Title.TLabel").pack(side="left")
        self.char_bar = ttk.Frame(top)
        self.char_bar.pack(side="left", padx=10)
        if not paths.FROZEN:
            ttk.Button(top, text="📦 Собрать пакет для друга…", command=lambda: BuildDialog(self)).pack(side="right")
        ttk.Button(top, text="Открыть папку", command=self.open_folder).pack(side="right", padx=6)

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(6, 4))
        self.anim_tab = AnimTab(self, self.nb)
        self.char_tab = CharTab(self, self.nb)
        self.lines_tab = LinesTab(self, self.nb)
        self.events_tab = EventsTab(self, self.nb)
        self.nb.add(self.anim_tab.frame, text="Анимации")
        self.nb.add(self.char_tab.frame, text="Персонаж")
        self.nb.add(self.lines_tab.frame, text="Реплики")
        self.nb.add(self.events_tab.frame, text="События")
        self.nb.bind("<<NotebookTabChanged>>", self.on_tab)

        self.status = tk.Label(root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w", padx=16)
        self.status.pack(fill="x", pady=(0, 8))

    def refresh_char_bar(self):
        for w in self.char_bar.winfo_children():
            w.destroy()
        for cid in store.list_ids():
            ttk.Button(self.char_bar, text=self.name_of(cid), style="CharOn.TButton" if cid == self.key else "Char.TButton",
                       command=lambda c=cid: self.select_char(c)).pack(side="left", padx=2)
        ttk.Button(self.char_bar, text="+ Персонаж", command=self.new_char).pack(side="left", padx=(8, 2))
        ttk.Button(self.char_bar, text="Эффекты", style="CharOn.TButton" if self.key == EFFECTS_KEY else "Char.TButton",
                   command=lambda: self.select_char(EFFECTS_KEY)).pack(side="left", padx=2)

    def flush_all(self):
        for tab in (self.anim_tab, self.char_tab, self.lines_tab, self.events_tab):
            tab.saver.flush()

    def select_char(self, cid):
        self.flush_all()
        self.reload_data()
        self.key = cid
        self.refresh_char_bar()
        effects = cid == EFFECTS_KEY
        for i in (1, 2):
            self.nb.tab(i, state="disabled" if effects else "normal")
        if effects and self.nb.index("current") in (1, 2):
            self.nb.select(0)
        self.anim_tab.load()
        if not effects:
            self.char_tab.load()
            self.lines_tab.load()
        self.events_tab.load()

    def on_tab(self, _e=None):
        self.flush_all()
        self.reload_data()
        current = self.nb.index("current")
        if current == 0:
            self.anim_tab.load(keep=True)
        elif current == 3:
            self.events_tab.load(keep=True)

    def new_char(self):
        name = simpledialog.askstring("Новый персонаж", "Как зовут?", parent=self.root)
        if not name or not name.strip():
            return
        self.flush_all()
        cid = store.create_char(name.strip())
        settings = store.load_settings()
        settings["order"] = settings.get("order", []) + [cid]
        store.save_settings(settings)
        self.select_char(cid)
        self.nb.select(1)
        self.say(f"Создан «{name}». Настрой его тут, потом добавь анимации и реплики.", OK)

    def char_dir(self):
        return os.path.join(paths.EFFECTS, "fight") if self.key == EFFECTS_KEY else store.char_dir(self.key)

    def open_folder(self):
        path = self.anim_tab.vdir() if self.anim_tab.anim else self.char_dir()
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

    def play(self, kind, rest):
        with open(paths.PLAY_FILE, "w", encoding="utf-8") as f:
            f.write(f"{kind}\n{rest}")
        self.root.after(2500, self.check_played)
        self.say("Отправил персонажам…")

    def check_played(self):
        if os.path.exists(paths.PLAY_FILE):
            os.remove(paths.PLAY_FILE)
            self.say("Персонажи не запущены — открой их и нажми ещё раз.", WARN)
        else:
            self.say("Играет на рабочем столе ✓", OK)


class AnimTab:
    def __init__(self, ed, parent):
        self.ed = ed
        self.root = ed.root
        self.frame = ttk.Frame(parent)
        self.saver = Saver(self.root, self.save, ed.say)
        self.anim = None
        self.vi = 0
        self.frames = []
        self.frame_i = 0
        self.playing = True
        self.loading = False
        self.area = [0, 0, 1, 1]
        self.trigger_codes = []
        self.last_trigger = ""
        self.screen_w = self.root.winfo_screenwidth()
        self.ground = work_bottom(self.root)
        try:
            self.icons = desktop_icons.icon_rects() if desktop_icons else []
        except Exception:
            self.icons = []
        self.build()
        self.tick()

    def combo(self, parent, label, values):
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, style="Panel.TLabel").pack(side="left")
        var = tk.StringVar(value=values[0])
        ttk.Combobox(row, textvariable=var, values=values, state="readonly", width=24).pack(side="right")
        var.trace_add("write", lambda *a: self.changed())
        return var

    def build(self):
        ed = self.ed
        body = ttk.Frame(self.frame, padding=(0, 8, 0, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Panel.TFrame", padding=10)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        ttk.Label(left, text="Анимации", style="Head.TLabel").pack(anchor="w")
        ttk.Label(left, text="✓ нарисовано   ○ пусто   ★ своя", style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.anim_list = ed.listbox(left, width=32, height=22)
        self.anim_list.pack(fill="both", expand=True)
        self.anim_list.bind("<<ListboxSelect>>", self.on_anim_select)
        self.new_btn = ttk.Button(left, text="+ Новая анимация", style="Accent.TButton", command=self.new_anim)
        self.new_btn.pack(fill="x", pady=(8, 4))
        self.del_anim_btn = ttk.Button(left, text="Удалить анимацию", command=self.delete_anim)
        self.del_anim_btn.pack(fill="x")

        mid = ttk.Frame(body, style="Panel.TFrame", padding=10)
        mid.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self.anim_title = ttk.Label(mid, text="", style="Head.TLabel")
        self.anim_title.pack(anchor="w")
        self.anim_desc = ttk.Label(mid, text="", style="Muted.TLabel", wraplength=560, justify="left")
        self.anim_desc.pack(anchor="w", pady=(0, 6))
        self.canvas = tk.Canvas(mid, width=420, height=230, highlightthickness=0, bg="#141118")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw_preview())
        ctrl = ttk.Frame(mid, style="Panel.TFrame")
        ctrl.pack(fill="x", pady=(8, 0))
        self.play_btn = ttk.Button(ctrl, text="⏸ Пауза", command=self.toggle_play)
        self.play_btn.pack(side="left")
        ttk.Button(ctrl, text="◀", width=3, command=lambda: self.step(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(ctrl, text="▶", width=3, command=lambda: self.step(1)).pack(side="left", padx=(2, 0))
        self.mirror_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Влево (зеркально)", variable=self.mirror_var,
                        command=self.reload_preview).pack(side="left", padx=10)
        self.zoom_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Крупнее ×2", variable=self.zoom_var, command=self.reload_preview).pack(side="left")
        self.bg_var = tk.StringVar(value="Тёмный фон")
        ttk.Combobox(ctrl, textvariable=self.bg_var, width=12, state="readonly",
                     values=["Тёмный фон", "Светлый фон", "Шахматка"]).pack(side="right")
        self.bg_var.trace_add("write", lambda *a: self.draw_preview())
        self.frame_label = ttk.Label(mid, text="", style="Muted.TLabel")
        self.frame_label.pack(anchor="w", pady=(4, 0))
        self.warn_label = tk.Label(mid, text="", bg=PANEL, fg=WARN, font=("Segoe UI", 9), justify="left",
                                   wraplength=620, anchor="w")
        self.warn_label.pack(fill="x", pady=(2, 0))

        self.custom_box = ttk.Frame(mid, style="Panel.TFrame")
        cb = self.custom_box
        cb.columnconfigure(0, weight=1)
        when = ttk.Frame(cb, style="Panel.TFrame")
        when.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(when, text="Когда играть", style="Head.TLabel").pack(anchor="w")
        row = ttk.Frame(when, style="Panel.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Событие:", style="Panel.TLabel").pack(side="left")
        self.trigger_var = tk.StringVar()
        self.trigger_box = ttk.Combobox(row, textvariable=self.trigger_var, state="readonly", width=46, height=25)
        self.trigger_box.pack(side="right", fill="x", expand=True, padx=(6, 0))
        self.trigger_var.trace_add("write", lambda *a: self.on_trigger())
        self.freq_var = self.combo(when, "Как часто:", [v[0] for v in SP.FREQ.values()])
        self.time_var = self.combo(when, "Время суток:", [v[0] for v in SP.TIMES.values()])
        self.move_var = self.combo(when, "Движение:", list(SP.MOVE.values()))
        row = ttk.Frame(when, style="Panel.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Сколько раз проиграть:", style="Panel.TLabel").pack(side="left")
        self.repeat_var = tk.StringVar(value="2")
        ttk.Spinbox(row, from_=1, to=30, textvariable=self.repeat_var, width=5).pack(side="right")
        self.repeat_var.trace_add("write", lambda *a: self.changed())
        ttk.Label(when, text="Реплики (одна случайная, каждая с новой строки):", style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        self.say_text = ed.textbox(when, height=3, width=40)
        self.say_text.pack(fill="x")
        self.say_text.bind("<<Modified>>", self.on_say_modified)

        where = ttk.Frame(cb, style="Panel.TFrame")
        where.grid(row=0, column=1, sticky="n")
        ttk.Label(where, text="Где можно играть", style="Head.TLabel").pack(anchor="w")
        ttk.Label(where, text="Обведи мышкой область на экране", style="Muted.TLabel").pack(anchor="w")
        self.map = tk.Canvas(where, width=MAP_W, height=170, highlightthickness=0, bg="#141118", cursor="crosshair")
        self.map.pack(pady=(4, 4))
        self.map.bind("<ButtonPress-1>", self.map_press)
        self.map.bind("<B1-Motion>", self.map_drag)
        self.map.bind("<ButtonRelease-1>", self.map_release)
        row = ttk.Frame(where, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Весь экран", style="Small.TButton", command=self.map_reset).pack(side="left")
        self.surface_var = tk.StringVar(value=SP.SURFACES["any"])
        ttk.Combobox(row, textvariable=self.surface_var, values=list(SP.SURFACES.values()),
                     state="readonly", width=17).pack(side="right")
        self.surface_var.trace_add("write", lambda *a: self.changed())

        right = ttk.Frame(body, style="Panel.TFrame", padding=10)
        right.grid(row=0, column=2, sticky="ns")
        sc = ttk.Frame(right, style="Panel.TFrame")
        sc.pack(fill="x", pady=(0, 10))
        ttk.Label(sc, text="Масштаб кадров:", style="Panel.TLabel").pack(side="left")
        self.scale_var = tk.StringVar(value="1")
        ttk.Combobox(sc, textvariable=self.scale_var, width=6,
                     values=["1/4", "1/3", "1/2", "2/3", "3/4", "1", "3/2", "2", "3", "4"]).pack(side="right")
        self.scale_var.trace_add("write", lambda *a: self.changed())
        ttk.Label(right, text="Варианты", style="Head.TLabel").pack(anchor="w")
        ttk.Label(right, text="Разные версии одного действия — играются\nпо очереди или случайно",
                  style="Muted.TLabel", justify="left").pack(anchor="w")
        self.var_row = ttk.Frame(right, style="Panel.TFrame")
        self.var_row.pack(fill="x", pady=(4, 2))
        row = ttk.Frame(right, style="Panel.TFrame")
        row.pack(fill="x", pady=(2, 0))
        self.vmode_var = tk.StringVar(value=SP.VARIANT_MODES["order"])
        ttk.Combobox(row, textvariable=self.vmode_var, values=list(SP.VARIANT_MODES.values()),
                     state="readonly", width=12).pack(side="left")
        self.vmode_var.trace_add("write", lambda *a: self.changed())
        self.del_var_btn = ttk.Button(row, text="Удалить вариант", style="Small.TButton", command=self.delete_variant)
        self.del_var_btn.pack(side="right")

        ttk.Label(right, text="Кадры", style="Head.TLabel").pack(anchor="w", pady=(12, 0))
        self.frame_list = ed.listbox(right, width=30, height=9)
        self.frame_list.pack(fill="x")
        self.frame_list.bind("<<ListboxSelect>>", self.on_frame_select)
        row = ttk.Frame(right, style="Panel.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Добавить кадры…", style="Accent.TButton", command=self.add_frames).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Заменить все…", command=lambda: self.add_frames(replace=True)).pack(side="left", padx=(4, 0))
        row = ttk.Frame(right, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="↑", width=3, command=lambda: self.move_frame(-1)).pack(side="left")
        ttk.Button(row, text="↓", width=3, command=lambda: self.move_frame(1)).pack(side="left", padx=2)
        ttk.Button(row, text="Дублировать", command=self.dup_frame).pack(side="left", padx=2)
        ttk.Button(row, text="Удалить", command=self.delete_frame).pack(side="left", fill="x", expand=True)
        row = ttk.Frame(right, style="Panel.TFrame")
        row.pack(fill="x", pady=(12, 0))
        ttk.Label(row, text="Скорость (кадров/сек):", style="Panel.TLabel").pack(side="left")
        self.fps_var = tk.StringVar(value="8")
        ttk.Spinbox(row, from_=1, to=60, increment=1, textvariable=self.fps_var, width=5).pack(side="right")
        self.fps_var.trace_add("write", lambda *a: self.changed())
        ttk.Button(right, text="▶ Показать на рабочем столе", style="Accent.TButton",
                   command=self.show_on_desktop).pack(fill="x", side="bottom", pady=(10, 0))

    @property
    def effects(self):
        return self.ed.key == EFFECTS_KEY

    def anim_dir(self, name=None):
        return os.path.join(self.ed.char_dir(), name or self.anim)

    def variants(self):
        return SP.variant_dirs(self.anim_dir())

    def vdir(self):
        v = self.variants()
        return v[min(self.vi, len(v) - 1)]

    def all_anims(self):
        if self.effects:
            names = list(SP.EFFECTS)
        else:
            names = SP.anim_names(self.ed.key, self.ed.chars, self.ed.rels)
        return names

    def is_custom(self, name=None):
        return not self.effects and SP.is_custom(name or self.anim)

    def describe(self, name):
        return SP.EFFECTS.get(name) if self.effects else SP.STANDARD.get(name)

    def load(self, keep=False):
        self.saver.flush()
        os.makedirs(self.ed.char_dir(), exist_ok=True)
        cfg = SP.read_settings(os.path.join(self.ed.char_dir(), "settings.txt"))
        self.loading = True
        self.scale_var.set(cfg.get("scale", "1"))
        self.loading = False
        self.new_btn.state(["disabled"] if self.effects else ["!disabled"])
        names = self.all_anims()
        select = self.anim if keep and self.anim in names else names[0]
        self.anim = None
        self.refresh_anim_list(select=select)

    def refresh_anim_list(self, select=None):
        names = self.all_anims()
        self.anim_list.delete(0, "end")
        for n in names:
            d = self.anim_dir(n)
            count = SP.count_frames(d)
            nvar = sum(1 for v in SP.variant_dirs(d) if SP.list_frames(v))
            mark = "★" if self.is_custom(n) else ("✓" if count else "○")
            frames = f"{count} кадр." if count else "пусто"
            if nvar > 1:
                frames += f", {nvar} вар."
            self.anim_list.insert("end", f" {mark} {n}  ·  {frames}")
            self.anim_list.itemconfig("end", fg=INK if count else MUTED)
        self.names = names
        if select in names:
            i = names.index(select)
            self.anim_list.selection_clear(0, "end")
            self.anim_list.selection_set(i)
            self.anim_list.see(i)
            if select != self.anim:
                self.select_anim(select)
        elif self.anim in names:
            self.anim_list.selection_set(names.index(self.anim))

    def on_anim_select(self, _e=None):
        sel = self.anim_list.curselection()
        if sel and self.names[sel[0]] != self.anim:
            self.saver.flush()
            self.select_anim(self.names[sel[0]])

    def select_anim(self, name):
        self.anim = name
        self.vi = 0
        os.makedirs(self.anim_dir(), exist_ok=True)
        info = SP.read_info(self.anim_dir())
        custom = self.is_custom()
        who = "Эффекты" if self.effects else self.ed.name_of(self.ed.key)
        self.anim_title.config(text=f"{who} — {name}" + ("  ★ своя анимация" if custom else ""))
        if custom:
            self.anim_desc.config(text="Своя анимация. Внизу выбери событие и место, где она может играть.")
        else:
            n, fps, desc = self.describe(name) or (4, 8, "")
            self.anim_desc.config(text=f"{desc}. Советую {n} кадр(ов) на скорости {fps:g}.")
        self.del_anim_btn.state(["!disabled"] if custom else ["disabled"])

        self.loading = True
        cfg = SP.read_settings(os.path.join(self.ed.char_dir(), "settings.txt"))
        fps = info.get("fps") or cfg.get(name) or (self.describe(name) or (0, 8))[1]
        self.fps_var.set(f"{float(fps):g}")
        self.vmode_var.set(SP.VARIANT_MODES.get(info.get("variants", "order"), SP.VARIANT_MODES["order"]))
        if custom:
            full = SP.normalize(info)
            labels, self.trigger_codes = [], []
            for title, items in SP.trigger_groups(self.ed.key, self.ed.chars, self.ed.rels):
                if not items:
                    continue
                labels.append(f"━━━ {title} ━━━")
                self.trigger_codes.append(None)
                labels += [f"   {v}" for v in items.values()]
                self.trigger_codes += list(items)
            self.trigger_box.configure(values=labels)
            code = full["trigger"] if full["trigger"] in self.trigger_codes else "random"
            self.trigger_var.set(labels[self.trigger_codes.index(code)])
            self.last_trigger = self.trigger_var.get()
            self.freq_var.set(SP.FREQ.get(full["freq"], SP.FREQ["sometimes"])[0])
            self.time_var.set(SP.TIMES.get(full["time"], SP.TIMES["any"])[0])
            self.repeat_var.set(str(full["repeat"]))
            move = min(SP.MOVE, key=lambda v: abs(v - float(full.get("move") or 0)))
            self.move_var.set(SP.MOVE[move])
            self.say_text.delete("1.0", "end")
            self.say_text.insert("1.0", "\n".join(full.get("say") or []))
            self.say_text.edit_modified(False)
            self.area = [float(v) for v in full["area"]]
            self.surface_var.set(SP.SURFACES.get(full.get("surface"), SP.SURFACES["any"]))
            self.custom_box.pack(fill="x", pady=(10, 0))
            self.draw_map()
        else:
            self.custom_box.pack_forget()
        self.loading = False
        self.refresh_variants()

    def changed(self):
        if not self.loading and self.anim:
            self.saver()

    def refresh_variants(self):
        for w in self.var_row.winfo_children():
            w.destroy()
        vs = self.variants()
        self.vi = min(self.vi, len(vs) - 1)
        for i, v in enumerate(vs):
            n = len(SP.list_frames(v))
            ttk.Button(self.var_row, text=f"{i + 1}" + ("" if n else "·"), width=3,
                       style="VarOn.TButton" if i == self.vi else "Var.TButton",
                       command=lambda i=i: self.pick_variant(i)).pack(side="left", padx=(0, 3))
        ttk.Button(self.var_row, text="+ вариант", style="Small.TButton", command=self.add_variant).pack(side="left", padx=(4, 0))
        self.del_var_btn.state(["!disabled"] if self.vi > 0 else ["disabled"])
        self.refresh_frames()

    def pick_variant(self, i):
        self.vi = i
        self.frame_i = 0
        self.refresh_variants()

    def add_variant(self):
        vs = self.variants()
        if not SP.list_frames(vs[-1]):
            self.vi = len(vs) - 1
            self.refresh_variants()
            self.ed.say("Последний вариант ещё пустой — добавь в него кадры.", WARN)
            return
        nums = [1] + [int(SP.VARIANT_RE.match(os.path.basename(v)).group(1)) for v in vs[1:]]
        os.makedirs(os.path.join(self.anim_dir(), f"вариант {max(nums) + 1}"), exist_ok=True)
        self.vi = len(vs)
        self.refresh_variants()
        self.ed.say("Новый вариант создан. Добавь в него кадры.", OK)
        self.add_frames()

    def delete_variant(self):
        if self.vi == 0:
            return
        v = self.vdir()
        if SP.list_frames(v) and not messagebox.askyesno(
                "Удалить вариант?", f"Вариант {self.vi + 1} уйдёт в папку data/_корзина. Удалить?"):
            return
        store.trash(v, f"{self.ed.key}_{self.anim}_v{self.vi + 1}")
        rest = self.variants()[1:]
        tmp = []
        for i, d in enumerate(rest):
            t = os.path.join(self.anim_dir(), f"__tmpvar_{i}_{time.time_ns()}")
            os.rename(d, t)
            tmp.append(t)
        for i, t in enumerate(tmp, 2):
            os.rename(t, os.path.join(self.anim_dir(), f"вариант {i}"))
        self.vi -= 1
        self.refresh_anim_list()
        self.refresh_variants()
        self.ed.say("Вариант убран в корзину.", OK)

    def frame_files(self):
        return SP.list_frames(self.vdir())

    def refresh_frames(self, select=None):
        files = self.frame_files()
        self.frame_list.delete(0, "end")
        for i, f in enumerate(files, 1):
            self.frame_list.insert("end", f" {i:>2}.  {f}")
        if select is not None and files:
            select = max(0, min(select, len(files) - 1))
            self.frame_list.selection_set(select)
            self.frame_list.see(select)
        self.reload_preview()

    def selected_frame(self):
        sel = self.frame_list.curselection()
        return sel[0] if sel else None

    def renumber(self, order):
        d = self.vdir()
        tmp = []
        for i, f in enumerate(order):
            t = f"__tmp_{i}_{time.time_ns()}.png"
            os.rename(os.path.join(d, f), os.path.join(d, t))
            tmp.append(t)
        for i, t in enumerate(tmp, 1):
            os.rename(os.path.join(d, t), os.path.join(d, f"{i:03d}.png"))

    def after_frames_changed(self, select=None):
        self.refresh_anim_list()
        self.refresh_variants()
        if select is not None:
            self.refresh_frames(select=select)

    def add_frames(self, replace=False):
        paths_ = filedialog.askopenfilenames(
            title="Выбери кадры (PNG). Можно выделить сразу все — порядок по номерам в имени.",
            filetypes=[("Картинки PNG", "*.png")])
        if not paths_:
            return
        bad = []
        for p in paths_:
            try:
                tk.PhotoImage(file=p)
            except tk.TclError:
                bad.append(os.path.basename(p))
        if bad:
            messagebox.showerror("Не получилось открыть", "Эти файлы не открылись как PNG:\n" + "\n".join(bad))
            return
        d = self.vdir()
        if replace and self.frame_files():
            if not messagebox.askyesno("Заменить все кадры?",
                                       f"Старые кадры ({len(self.frame_files())}) уйдут в папку data/_корзина. Заменить?"):
                return
            self.trash_files(self.frame_files())
        existing = self.frame_files()
        new = []
        for i, p in enumerate(sorted(paths_, key=lambda x: SP._natural(os.path.basename(x)))):
            name = f"__new_{i}_{time.time_ns()}.png"
            shutil.copy2(p, os.path.join(d, name))
            new.append(name)
        self.renumber(existing + new)
        self.after_frames_changed()
        self.ed.say(f"Добавлено кадров: {len(new)}. Всего в варианте: {len(existing) + len(new)}.", OK)

    def move_frame(self, delta):
        i = self.selected_frame()
        files = self.frame_files()
        if i is None or not 0 <= i + delta < len(files):
            return
        files[i], files[i + delta] = files[i + delta], files[i]
        self.renumber(files)
        self.refresh_frames(select=i + delta)

    def dup_frame(self):
        i = self.selected_frame()
        files = self.frame_files()
        if i is None:
            self.ed.say("Сначала выбери кадр в списке.", WARN)
            return
        d = self.vdir()
        copy = f"__dup_{time.time_ns()}.png"
        shutil.copy2(os.path.join(d, files[i]), os.path.join(d, copy))
        files.insert(i + 1, copy)
        self.renumber(files)
        self.after_frames_changed(select=i + 1)

    def delete_frame(self):
        i = self.selected_frame()
        files = self.frame_files()
        if i is None:
            self.ed.say("Сначала выбери кадр в списке.", WARN)
            return
        self.trash_files([files[i]])
        self.renumber([f for j, f in enumerate(files) if j != i])
        self.after_frames_changed(select=i)
        self.ed.say("Кадр убран в data/_корзина.", OK)

    def trash_files(self, files):
        dest = os.path.join(paths.TRASH, f"{self.ed.key}_{self.anim}_{time.strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(dest, exist_ok=True)
        for f in files:
            shutil.move(os.path.join(self.vdir(), f), os.path.join(dest, f"{time.time_ns()}_{f}"))

    def new_anim(self):
        name = simpledialog.askstring(
            "Новая анимация",
            "Как назовём? (одно слово, можно по-русски: танец, чихает, обида…)", parent=self.root)
        if not name:
            return
        name = name.strip().replace(" ", "_")
        if not NAME_RE.match(name):
            messagebox.showerror("Название", "Только буквы, цифры, «_» и «-», без пробелов.")
            return
        if name in self.all_anims() or not SP.is_custom(name):
            messagebox.showerror("Название", "Такая анимация уже есть.")
            return
        self.saver.flush()
        os.makedirs(self.anim_dir(name), exist_ok=True)
        SP.write_info(self.anim_dir(name), dict(SP.CUSTOM_DEFAULTS))
        self.refresh_anim_list(select=name)
        self.ed.say(f"Создана «{name}». Теперь добавь кадры и выбери, когда она играет.", OK)
        self.add_frames()

    def delete_anim(self):
        if not self.anim or not self.is_custom():
            return
        if not messagebox.askyesno("Удалить анимацию?",
                                   f"«{self.anim}» уйдёт в папку data/_корзина (оттуда можно вернуть). Удалить?"):
            return
        self.saver.job and self.root.after_cancel(self.saver.job)
        self.saver.job = None
        store.trash(self.anim_dir(), f"{self.ed.key}_{self.anim}")
        self.anim = None
        self.refresh_anim_list(select=self.all_anims()[0])
        self.ed.say("Анимация убрана в корзину.", OK)

    def map_size(self):
        return MAP_W, int(MAP_W * self.ground / max(1, self.screen_w))

    def draw_map(self):
        w, h = self.map_size()
        m = self.map
        m.configure(width=w, height=h + 10)
        m.delete("all")
        m.create_rectangle(0, 0, w, h, fill="#1d1a22", outline="#4a4256")
        m.create_rectangle(0, h, w, h + 10, fill="#3a3344", width=0)
        m.create_text(w - 4, h + 5, text="панель задач", anchor="e", fill="#8a8095", font=("Segoe UI", 7))
        kx, ky = w / self.screen_w, h / self.ground
        for l, t, r, b in self.icons:
            m.create_rectangle(l * kx + 1, t * ky + 1, r * kx - 1, b * ky - 1, fill="#5a5266", width=0)
        x0, y0, x1, y1 = self.area
        m.create_rectangle(x0 * w, y0 * h, x1 * w, y1 * h, outline=ACCENT, width=2, fill=ACCENT, stipple="gray25")
        if self.area == [0, 0, 1, 1]:
            m.create_text(w / 2, h / 2, text="весь экран", fill="#ffffff", font=("Segoe UI", 9, "bold"))

    def map_point(self, e):
        w, h = self.map_size()
        return min(max(e.x / w, 0), 1), min(max(e.y / h, 0), 1)

    def map_press(self, e):
        self.drag_from = self.map_point(e)

    def map_drag(self, e):
        (ax, ay), (bx, by) = self.drag_from, self.map_point(e)
        self.area = [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]
        self.draw_map()

    def map_release(self, _e):
        x0, y0, x1, y1 = self.area
        if x1 - x0 < 0.03 or y1 - y0 < 0.03:
            self.area = [0, 0, 1, 1]
        self.area = [round(v, 3) for v in self.area]
        self.draw_map()
        self.changed()

    def map_reset(self):
        self.area = [0, 0, 1, 1]
        self.draw_map()
        self.changed()

    def on_trigger(self):
        values = list(self.trigger_box.cget("values"))
        label = self.trigger_var.get()
        if label in values and self.trigger_codes[values.index(label)] is None:
            self.trigger_var.set(self.last_trigger)
            return
        self.last_trigger = label
        self.changed()

    def on_say_modified(self, _e=None):
        if self.say_text.edit_modified():
            self.say_text.edit_modified(False)
            self.changed()

    def save(self):
        if not self.anim or not os.path.isdir(self.anim_dir()):
            return False
        try:
            fps = max(0.5, min(60.0, float(self.fps_var.get().replace(",", "."))))
        except ValueError:
            self.ed.say("Скорость должна быть числом.", WARN)
            return False
        info = SP.read_info(self.anim_dir())
        info["fps"] = fps
        info["variants"] = inv(SP.VARIANT_MODES, self.vmode_var.get()) or "order"
        if self.is_custom():
            label = self.trigger_var.get()
            values = list(self.trigger_box.cget("values"))
            code = self.trigger_codes[values.index(label)] if label in values else None
            info["trigger"] = code or info.get("trigger", "random")
            info["freq"] = inv(SP.FREQ, self.freq_var.get(), lambda x: x[0]) or "sometimes"
            info["time"] = inv(SP.TIMES, self.time_var.get(), lambda x: x[0]) or "any"
            info["move"] = inv(SP.MOVE, self.move_var.get()) or 0
            try:
                info["repeat"] = max(1, int(self.repeat_var.get()))
            except ValueError:
                info["repeat"] = 2
            info["say"] = [s.strip() for s in self.say_text.get("1.0", "end").splitlines() if s.strip()]
            info["area"] = self.area
            info["surface"] = inv(SP.SURFACES, self.surface_var.get()) or "any"
        SP.write_info(self.anim_dir(), info)
        self.save_scale()

    def save_scale(self):
        value = self.scale_var.get().strip()
        try:
            Fraction(value)
        except (ValueError, ZeroDivisionError):
            return
        path = os.path.join(self.ed.char_dir(), "settings.txt")
        old = open(path, encoding="utf-8-sig").read() if os.path.exists(path) else ""
        if re.search(r"(?m)^scale\s*=", old):
            text = re.sub(r"(?m)^scale\s*=.*$", f"scale = {value}", old)
        else:
            text = f"scale = {value}\n" + old
        if text != old:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.reload_preview()

    def reload_preview(self):
        self.frames = []
        warnings = []
        files = self.frame_files() if self.anim else []
        try:
            scale = Fraction(self.scale_var.get().strip()).limit_denominator(8)
        except (ValueError, ZeroDivisionError):
            scale = Fraction(1)
        sizes = set()
        for f in files:
            try:
                img = tk.PhotoImage(file=os.path.join(self.vdir(), f))
            except tk.TclError:
                warnings.append(f"Не открылся файл {f}.")
                continue
            sizes.add((img.width(), img.height()))
            if not self.frames:
                gap = self.bottom_gap(img)
                if gap > 3 and self.anim not in ("held", "fall", "climb", "cloud"):
                    warnings.append(f"Ноги не касаются нижнего края картинки: персонаж будет висеть в воздухе "
                                    f"на {gap} px. Сдвинь его вниз или обрежь холст снизу.")
            img = SP._scaled(img, scale)
            if self.zoom_var.get():
                img = SP._copy(img, "-zoom", 2)
            if self.mirror_var.get():
                img = SP._copy(img, "-subsample", -1, 1)
            self.frames.append(img)
        if len(sizes) > 1:
            warnings.append("Кадры разного размера (" + ", ".join(f"{w}×{h}" for w, h in sorted(sizes)) +
                            ") — персонаж будет дёргаться. Сделай все кадры на одном холсте.")
        if sizes and scale == 1:
            w, h = max(sizes)
            if max(w, h) > 450:
                warnings.append(f"Кадры большие ({w}×{h}), на экране персонаж будет огромным. "
                                f"Попробуй масштаб 1/{round(max(w, h) / 200)}.")
        if self.frames and self.frame_i >= len(self.frames):
            self.frame_i = 0
        if self.anim and not files:
            warnings.append("Кадров пока нет — нажми «Добавить кадры…».")
        self.warn_label.config(text="\n".join("⚠ " + w for w in warnings))
        self.draw_preview()

    @staticmethod
    def bottom_gap(img):
        w, h = img.width(), img.height()
        step = max(1, w // 100)
        for gap in range(h):
            y = h - 1 - gap
            if any(not img.transparency_get(x, y) for x in range(0, w, step)):
                return gap
        return 0

    def draw_preview(self):
        cv = self.canvas
        cv.delete("all")
        w, h = max(cv.winfo_width(), 100), max(cv.winfo_height(), 100)
        mode = self.bg_var.get()
        if mode == "Шахматка":
            s = 16
            for yy in range(0, h, s):
                for xx in range(0, w, s):
                    cv.create_rectangle(xx, yy, xx + s, yy + s, width=0,
                                        fill="#3a3640" if (xx // s + yy // s) % 2 else "#2c2932")
        else:
            cv.create_rectangle(0, 0, w, h, width=0, fill="#141118" if mode == "Тёмный фон" else "#f4f1ea")
        floor = h - 30
        cv.create_line(0, floor, w, floor, fill="#5a4f66", dash=(4, 4))
        cv.create_text(8, floor + 6, text="пол (панель задач)", anchor="nw", fill="#7d728a", font=("Segoe UI", 8))
        if self.frames:
            img = self.frames[self.frame_i % len(self.frames)]
            cv.create_image(w // 2, floor, image=img, anchor="s")
            n = len(self.frames)
            try:
                loop = f" · цикл {n / float(self.fps_var.get().replace(',', '.')):.1f} с"
            except (ValueError, ZeroDivisionError):
                loop = ""
            var = f"Вариант {self.vi + 1} · " if len(self.variants()) > 1 else ""
            self.frame_label.config(text=f"{var}Кадр {self.frame_i % n + 1} из {n}{loop}")
        else:
            cv.create_text(w // 2, h // 2, text="Тут будет превью", fill="#7d728a", font=("Segoe UI", 12))
            self.frame_label.config(text="")

    def tick(self):
        delay = 125
        if self.playing and self.frames:
            self.frame_i = (self.frame_i + 1) % len(self.frames)
            self.draw_preview()
            try:
                delay = int(1000 / max(0.5, float(self.fps_var.get().replace(",", "."))))
            except ValueError:
                pass
        self.root.after(max(16, delay), self.tick)

    def toggle_play(self):
        self.playing = not self.playing
        self.play_btn.config(text="⏸ Пауза" if self.playing else "▶ Играть")

    def step(self, d):
        if self.frames:
            self.playing = False
            self.play_btn.config(text="▶ Играть")
            self.frame_i = (self.frame_i + d) % len(self.frames)
            self.draw_preview()

    def on_frame_select(self, _e=None):
        i = self.selected_frame()
        if i is not None and self.frames:
            self.step(0)
            self.frame_i = i % len(self.frames)
            self.draw_preview()

    def show_on_desktop(self):
        self.saver.flush()
        if not self.anim or not SP.count_frames(self.anim_dir()):
            self.ed.say("Сначала добавь кадры.", WARN)
            return
        self.ed.play("fight" if self.effects else self.ed.key, self.anim)


class CharTab:
    def __init__(self, ed, parent):
        self.ed = ed
        self.root = ed.root
        self.frame = ttk.Frame(parent)
        self.saver = Saver(self.root, self.save, ed.say)
        self.rel_rows = []
        self.build()

    def build(self):
        body = ttk.Frame(self.frame, padding=(0, 8, 0, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        left = ttk.Frame(body, style="Panel.TFrame", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(left, text="Кто это", style="Head.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.vars = {}

        def field(r, label, key, widget):
            ttk.Label(left, text=label, style="Panel.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            widget.grid(row=r, column=1, sticky="ew", pady=3)
            left.columnconfigure(1, weight=1)

        self.vars["name"] = tk.StringVar()
        field(1, "Имя:", "name", ttk.Entry(left, textvariable=self.vars["name"]))
        self.vars["drawing"] = tk.StringVar()
        field(2, "Без картинок рисуется:", "drawing",
              ttk.Combobox(left, textvariable=self.vars["drawing"], values=list(BODY_NAMES.values()), state="readonly"))
        crow = ttk.Frame(left, style="Panel.TFrame")
        self.color_btn = tk.Button(crow, text="   ", width=4, relief="flat", command=self.pick_color)
        self.color_btn.pack(side="left")
        self.vars["color"] = tk.StringVar()
        ttk.Entry(crow, textvariable=self.vars["color"], width=10).pack(side="left", padx=6)
        field(3, "Цвет (кругляш, частицы):", "color", crow)
        self.vars["speed"] = tk.StringVar()
        field(4, "Скорость ходьбы:", "speed", ttk.Spinbox(left, from_=20, to=300, increment=5, textvariable=self.vars["speed"]))
        self.vars["height"] = tk.StringVar()
        field(5, "Рост кругляша:", "height", ttk.Spinbox(left, from_=40, to=200, increment=5, textvariable=self.vars["height"]))
        self.vars["bubble"] = tk.StringVar()
        field(6, "Облачка:", "bubble",
              ttk.Combobox(left, textvariable=self.vars["bubble"], values=list(BUBBLES.values()), state="readonly"))
        self.vars["can_disguise"] = tk.BooleanVar()
        field(7, "Прятки:", "can_disguise",
              ttk.Checkbutton(left, text="Умеет притворяться иконкой, если на него охотятся",
                              variable=self.vars["can_disguise"]))
        self.vars["icon_label"] = tk.StringVar()
        field(8, "Подпись «иконки»:", "icon_label", ttk.Entry(left, textvariable=self.vars["icon_label"]))
        self.vars["p_work"] = tk.StringVar()
        field(9, "Летит, когда работает:", "p_work", ttk.Entry(left, textvariable=self.vars["p_work"]))
        self.vars["p_laugh"] = tk.StringVar()
        field(10, "Летит, когда смеётся:", "p_laugh", ttk.Entry(left, textvariable=self.vars["p_laugh"]))
        ttk.Label(left, text="(через запятую)", style="Muted.TLabel").grid(row=11, column=1, sticky="w")

        ttk.Label(left, text="Отношения", style="Head.TLabel").grid(row=12, column=0, columnspan=2, sticky="w", pady=(14, 2))
        ttk.Label(left, text="Охотник ищет добычу сканером и гоняется; защитник прячет и заступается;\n"
                             "«пристаёт к» и «болтает с» запускают события «Пристаёт» и «Болтают».",
                  style="Muted.TLabel", justify="left").grid(row=13, column=0, columnspan=2, sticky="w")
        self.rel_box = ttk.Frame(left, style="Panel.TFrame")
        self.rel_box.grid(row=14, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(left, text="+ Отношение", style="Small.TButton", command=self.add_rel).grid(row=15, column=0, sticky="w")
        ttk.Button(left, text="Удалить персонажа", command=self.delete_char).grid(row=16, column=1, sticky="e", pady=(20, 0))

        right = ttk.Frame(body, style="Panel.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="Что делает сам", style="Head.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(right, text="Вес — как часто выбирает это занятие (0 — никогда). Анимация — какую играть.",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.act_vars = {}
        for i, (code, (label, anim, _)) in enumerate(catalog.ACTIONS.items(), 2):
            ttk.Label(right, text=label, style="Panel.TLabel").grid(row=i, column=0, sticky="w", pady=2)
            wv, av = tk.StringVar(), tk.StringVar()
            ttk.Spinbox(right, from_=0, to=10, increment=0.2, textvariable=wv, width=6).grid(row=i, column=1, padx=8)
            box = ttk.Combobox(right, textvariable=av, width=16)
            box.grid(row=i, column=2, sticky="w")
            self.act_vars[code] = (wv, av, box)
            wv.trace_add("write", self.saver)
            av.trace_add("write", self.saver)
        for v in self.vars.values():
            v.trace_add("write", self.saver)

    def load(self):
        self.saver.paused = True
        cid = self.ed.key
        data = store.load_char(cid)
        self.data = data
        v = self.vars
        v["name"].set(data.get("name", cid))
        v["drawing"].set(BODY_NAMES.get(data.get("drawing"), BODY_NAMES["simple"]))
        v["color"].set(data.get("color", "#7c6cff"))
        self.color_btn.config(bg=data.get("color", "#7c6cff"), activebackground=data.get("color", "#7c6cff"))
        v["speed"].set(str(data.get("speed", 90)))
        v["height"].set(str(data.get("height", 80)))
        v["bubble"].set(BUBBLES.get(data.get("bubble"), BUBBLES["manga"]))
        v["can_disguise"].set(bool(data.get("can_disguise")))
        v["icon_label"].set(data.get("icon_label", "не_вирус.txt"))
        v["p_work"].set(", ".join(data.get("particles", {}).get("work", [])))
        v["p_laugh"].set(", ".join(data.get("particles", {}).get("laugh", [])))
        names = SP.anim_names(cid, self.ed.chars, self.ed.rels)
        for code, (wv, av, box) in self.act_vars.items():
            wv.set(f"{float(data['actions'].get(code, 0)):g}")
            av.set(data.get("anims", {}).get(code, catalog.ACTIONS[code][1]))
            box.configure(values=names)
        for row in self.rel_rows:
            row[0].destroy()
        self.rel_rows = []
        for r in data.get("relations", []):
            self.add_rel(r)
        self.saver.paused = False

    def add_rel(self, rel=None):
        others = [c for c in store.list_ids() if c != self.ed.key]
        if not others:
            self.ed.say("Сначала создай ещё одного персонажа.", WARN)
            return
        frame = ttk.Frame(self.rel_box, style="Panel.TFrame")
        frame.pack(fill="x", pady=2)
        kind = tk.StringVar(value=catalog.RELATIONS.get((rel or {}).get("type"), catalog.RELATIONS["chats"]))
        target = tk.StringVar(value=self.ed.name_of((rel or {}).get("target", others[0])))
        weight = tk.StringVar(value=f"{float((rel or {}).get('weight', 1)):g}")
        ttk.Combobox(frame, textvariable=kind, values=list(catalog.RELATIONS.values()), state="readonly",
                     width=14).pack(side="left")
        ttk.Combobox(frame, textvariable=target, values=[self.ed.name_of(c) for c in others], state="readonly",
                     width=16).pack(side="left", padx=4)
        ttk.Label(frame, text="как часто:", style="Muted.TLabel").pack(side="left", padx=(6, 2))
        ttk.Spinbox(frame, from_=0.1, to=5, increment=0.1, textvariable=weight, width=5).pack(side="left")
        row = (frame, kind, target, weight, others)
        ttk.Button(frame, text="✕", width=3, style="Small.TButton",
                   command=lambda: (frame.destroy(), self.rel_rows.remove(row), self.saver())).pack(side="right")
        for v in (kind, target, weight):
            v.trace_add("write", self.saver)
        self.rel_rows.append(row)
        if rel is None:
            self.saver()

    def pick_color(self):
        color = colorchooser.askcolor(self.vars["color"].get(), parent=self.root)[1]
        if color:
            self.vars["color"].set(color)

    def save(self):
        cid = self.ed.key
        if not cid or cid == EFFECTS_KEY or not os.path.isdir(store.char_dir(cid)):
            return False
        data = store.load_char(cid)
        v = self.vars
        name = v["name"].get().strip() or cid
        data["name"] = name
        data["drawing"] = inv(BODY_NAMES, v["drawing"].get()) or "simple"
        color = v["color"].get().strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            data["color"] = color
            self.color_btn.config(bg=color, activebackground=color)
        for key, lo, hi in (("speed", 20, 300), ("height", 40, 200)):
            try:
                data[key] = max(lo, min(hi, float(v[key].get())))
            except ValueError:
                pass
        data["bubble"] = inv(BUBBLES, v["bubble"].get()) or "manga"
        data["can_disguise"] = bool(v["can_disguise"].get())
        data["icon_label"] = v["icon_label"].get().strip() or "не_вирус.txt"
        split = lambda s: [p.strip() for p in s.split(",") if p.strip()]
        data["particles"] = {"work": split(v["p_work"].get()), "laugh": split(v["p_laugh"].get())}
        anims = {}
        for code, (wv, av, _) in self.act_vars.items():
            try:
                data["actions"][code] = max(0.0, float(wv.get().replace(",", ".")))
            except ValueError:
                pass
            if av.get().strip() and av.get().strip() != catalog.ACTIONS[code][1]:
                anims[code] = av.get().strip()
        data["anims"] = anims
        rels = []
        names = {self.ed.name_of(c): c for c in store.list_ids()}
        for _, kind, target, weight, _ in self.rel_rows:
            t = names.get(target.get())
            k = inv(catalog.RELATIONS, kind.get())
            if t and k and t != cid:
                try:
                    wt = max(0.1, float(weight.get().replace(",", ".")))
                except ValueError:
                    wt = 1.0
                rels.append({"type": k, "target": t, "weight": wt})
        data["relations"] = rels
        store.save_char(cid, data)
        if name != self.ed.chars.get(cid, {}).get("name"):
            self.ed.reload_data()
            self.ed.refresh_char_bar()
        else:
            self.ed.reload_data()

    def delete_char(self):
        cid = self.ed.key
        if not messagebox.askyesno("Удалить персонажа?",
                                   f"«{self.ed.name_of(cid)}» со всеми анимациями уйдёт в папку data/_корзина "
                                   f"(оттуда можно вернуть). События с ним удалятся. Удалить?"):
            return
        self.saver.job and self.root.after_cancel(self.saver.job)
        self.saver.job = None
        store.delete_char(cid)
        ids = store.list_ids()
        self.ed.select_char(ids[0] if ids else EFFECTS_KEY)
        self.ed.say("Персонаж убран в корзину.", OK)


class LinesTab:
    def __init__(self, ed, parent):
        self.ed = ed
        self.root = ed.root
        self.frame = ttk.Frame(parent)
        self.saver = Saver(self.root, self.save, ed.say)
        self.cat = None
        self.rows = []
        body = ttk.Frame(self.frame, padding=(0, 8, 0, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body, style="Panel.TFrame", padding=10)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        ttk.Label(left, text="Когда говорит", style="Head.TLabel").pack(anchor="w")
        self.cat_list = ed.listbox(left, width=42, height=30)
        self.cat_list.pack(fill="both", expand=True, pady=(6, 0))
        self.cat_list.bind("<<ListboxSelect>>", self.on_select)
        right = ttk.Frame(body, style="Panel.TFrame", padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        self.title = ttk.Label(right, text="", style="Head.TLabel")
        self.title.pack(anchor="w")
        ttk.Label(right, text="Каждая фраза с новой строки — скажет случайную. Пусто — промолчит.\n"
                              "Фраза капсом рисуется взрывом-криком, с «...» в начале — шёпотом.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(0, 6))
        self.text = ed.textbox(right, height=20)
        self.text.pack(fill="both", expand=True)
        self.text.bind("<<Modified>>", self.on_modified)

    def load(self):
        self.saver.flush()
        self.data = store.load_char(self.ed.key)
        lines = self.data.get("lines", {})
        self.cat_list.delete(0, "end")
        self.rows = []
        for group, items in catalog.LINE_GROUPS:
            self.cat_list.insert("end", f"━━ {group} ━━")
            self.cat_list.itemconfig("end", fg=MUTED)
            self.rows.append(None)
            for code, label in items:
                n = len([t for t in lines.get(code, []) if t.strip()])
                self.cat_list.insert("end", f"   {label}" + (f"  ({n})" if n else ""))
                self.rows.append(code)
        first = self.cat if self.cat is not None and self.cat in self.rows else self.rows[1]
        self.select(first)

    def select(self, code):
        i = self.rows.index(code)
        self.cat_list.selection_clear(0, "end")
        self.cat_list.selection_set(i)
        self.cat_list.see(i)
        self.cat = code
        self.title.config(text=f"{self.data.get('name', self.ed.key)}: {catalog.LINE_LABELS[code]}")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(self.data.get("lines", {}).get(code, [])))
        self.text.edit_modified(False)

    def on_select(self, _e=None):
        sel = self.cat_list.curselection()
        if not sel:
            return
        code = self.rows[sel[0]]
        if code is None:
            self.select(self.cat)
            return
        if code != self.cat:
            self.saver.flush()
            self.select(code)

    def on_modified(self, _e=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.saver()

    def save(self):
        cid = self.ed.key
        if not self.cat or not os.path.isdir(store.char_dir(cid)):
            return False
        data = store.load_char(cid)
        data.setdefault("lines", {})[self.cat] = [t.strip() for t in self.text.get("1.0", "end").splitlines() if t.strip()]
        store.save_char(cid, data)
        self.data = data
        i = self.rows.index(self.cat)
        n = len(data["lines"][self.cat])
        self.cat_list.delete(i)
        self.cat_list.insert(i, f"   {catalog.LINE_LABELS[self.cat]}" + (f"  ({n})" if n else ""))
        self.cat_list.selection_set(i)


class EventsTab:
    def __init__(self, ed, parent):
        self.ed = ed
        self.root = ed.root
        self.frame = ttk.Frame(parent)
        self.saver = Saver(self.root, self.save, ed.say)
        self.events = []
        self.cur = None
        self.loading = False
        self.build()

    def build(self):
        ed = self.ed
        body = ttk.Frame(self.frame, padding=(0, 8, 0, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Panel.TFrame", padding=10)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        ttk.Label(left, text="События", style="Head.TLabel").pack(anchor="w")
        ttk.Label(left, text="Сценки: кто что говорит и делает", style="Muted.TLabel").pack(anchor="w")
        self.only_mine = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Только с выбранным персонажем", variable=self.only_mine,
                        command=lambda: self.load(keep=True)).pack(anchor="w", pady=4)
        self.ev_list = ed.listbox(left, width=40, height=24)
        self.ev_list.pack(fill="both", expand=True)
        self.ev_list.bind("<<ListboxSelect>>", self.on_select)
        row = ttk.Frame(left, style="Panel.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="+ Новое событие", style="Accent.TButton", command=self.new_event).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Копия", command=self.dup_event).pack(side="left", padx=4)
        ttk.Button(row, text="Удалить", command=self.delete_event).pack(side="left")

        right = ttk.Frame(body, style="Panel.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        self.form = right
        self.v = {k: tk.StringVar() for k in ("name", "hook", "distance", "freq", "time", "cooldown")}
        r = 0
        for label, key, values in (("Название:", "name", None), ("Когда:", "hook", list(catalog.HOOKS.values())),
                                   ("Расстояние:", "distance", list(catalog.DISTANCES.values())),
                                   ("Как часто (для «иногда»/«далеко»):", "freq", [x[0] for x in SP.FREQ.values()]),
                                   ("Время суток:", "time", [x[0] for x in SP.TIMES.values()]),
                                   ("Не повторять чаще, чем раз в (сек):", "cooldown", None)):
            ttk.Label(right, text=label, style="Panel.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            if values:
                w = ttk.Combobox(right, textvariable=self.v[key], values=values, state="readonly")
            elif key == "cooldown":
                w = ttk.Spinbox(right, from_=0, to=3600, increment=10, textvariable=self.v[key], width=8)
            else:
                w = ttk.Entry(right, textvariable=self.v[key])
            w.grid(row=r, column=1, sticky="ew" if key != "cooldown" else "w", pady=3)
            self.v[key].trace_add("write", self.changed)
            r += 1
        self.hint = ttk.Label(right, text="", style="Muted.TLabel", wraplength=640, justify="left")
        self.hint.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0, 6))
        r += 1

        ttk.Label(right, text="Участники (первый — главный)", style="Head.TLabel").grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 2))
        r += 1
        prow = ttk.Frame(right, style="Panel.TFrame")
        prow.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.who_list = ed.listbox(prow, width=28, height=4)
        self.who_list.pack(side="left")
        pbtn = ttk.Frame(prow, style="Panel.TFrame")
        pbtn.pack(side="left", padx=8, anchor="n")
        self.add_who_var = tk.StringVar()
        self.add_who_box = ttk.Combobox(pbtn, textvariable=self.add_who_var, state="readonly", width=18)
        self.add_who_box.pack(anchor="w")
        row = ttk.Frame(pbtn, style="Panel.TFrame")
        row.pack(anchor="w", pady=4)
        ttk.Button(row, text="+ Добавить", style="Small.TButton", command=self.add_who).pack(side="left")
        ttk.Button(row, text="↑", width=3, style="Small.TButton", command=lambda: self.move_who(-1)).pack(side="left", padx=2)
        ttk.Button(row, text="Убрать", style="Small.TButton", command=self.remove_who).pack(side="left")
        r += 1

        ttk.Label(right, text="Шаги (по очереди)", style="Head.TLabel").grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 2))
        r += 1
        self.step_list = ed.listbox(right, height=9)
        self.step_list.grid(row=r, column=0, columnspan=2, sticky="nsew")
        self.step_list.bind("<<ListboxSelect>>", self.on_step_select)
        right.rowconfigure(r, weight=1)
        r += 1
        srow = ttk.Frame(right, style="Panel.TFrame")
        srow.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(srow, text="Кто:", style="Panel.TLabel").pack(side="left")
        self.step_who = tk.StringVar()
        self.step_who_box = ttk.Combobox(srow, textvariable=self.step_who, state="readonly", width=14)
        self.step_who_box.pack(side="left", padx=(4, 10))
        self.step_who.trace_add("write", lambda *a: self.refresh_step_anims())
        ttk.Label(srow, text="Анимация:", style="Panel.TLabel").pack(side="left")
        self.step_anim = tk.StringVar()
        self.step_anim_box = ttk.Combobox(srow, textvariable=self.step_anim, width=16)
        self.step_anim_box.pack(side="left", padx=4)
        r += 1
        frow = ttk.Frame(right, style="Panel.TFrame")
        frow.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(frow, text="Фраза:", style="Panel.TLabel").pack(side="left")
        self.step_say = tk.StringVar()
        ttk.Entry(frow, textvariable=self.step_say).pack(side="left", fill="x", expand=True, padx=4)
        r += 1
        brow = ttk.Frame(right, style="Panel.TFrame")
        brow.grid(row=r, column=0, columnspan=2, sticky="ew")
        ttk.Button(brow, text="+ Добавить шаг", style="Accent.TButton", command=self.add_step).pack(side="left")
        ttk.Button(brow, text="Изменить выбранный", command=self.update_step).pack(side="left", padx=4)
        ttk.Button(brow, text="↑", width=3, command=lambda: self.move_step(-1)).pack(side="left")
        ttk.Button(brow, text="↓", width=3, command=lambda: self.move_step(1)).pack(side="left", padx=2)
        ttk.Button(brow, text="Удалить шаг", command=self.delete_step).pack(side="left")
        ttk.Button(brow, text="▶ Показать на рабочем столе", style="Accent.TButton",
                   command=self.show).pack(side="right")

    def visible_events(self):
        if self.only_mine.get() and self.ed.key not in (None, EFFECTS_KEY):
            return [e for e in self.events if self.ed.key in e.get("who", [])]
        return list(self.events)

    def load(self, keep=False):
        self.saver.flush()
        self.events = store.load_events()
        cur_id = self.cur.get("id") if keep and self.cur else None
        self.refresh_list(select_id=cur_id)

    def label(self, e):
        who = ", ".join(self.ed.name_of(c) for c in e.get("who", []))
        dist = {"near": " · рядом", "far": " · далеко"}.get(e.get("distance"), "")
        hook = catalog.HOOKS.get(e.get("hook"), e.get("hook", ""))
        return f" {e.get('name') or e.get('id')}  —  {hook.split(' (')[0]}{dist}  [{who}]"

    def refresh_list(self, select_id=None):
        self.shown = self.visible_events()
        self.ev_list.delete(0, "end")
        for e in self.shown:
            self.ev_list.insert("end", self.label(e))
        ids = [e.get("id") for e in self.shown]
        if select_id in ids:
            i = ids.index(select_id)
        elif self.shown:
            i = 0
        else:
            self.cur = None
            self.set_form_state(False)
            return
        self.ev_list.selection_clear(0, "end")
        self.ev_list.selection_set(i)
        self.ev_list.see(i)
        self.select(self.shown[i])

    def set_form_state(self, on):
        for w in self.form.winfo_children():
            self._state(w, on)

    def _state(self, w, on):
        if isinstance(w, (ttk.Combobox, ttk.Entry, ttk.Spinbox, ttk.Button)):
            w.state(["!disabled"] if on else ["disabled"])
        for c in w.winfo_children():
            self._state(c, on)

    def on_select(self, _e=None):
        sel = self.ev_list.curselection()
        if sel and self.shown[sel[0]] is not self.cur:
            self.saver.flush()
            self.select(self.shown[sel[0]])

    def select(self, e):
        self.cur = e
        self.loading = True
        self.set_form_state(True)
        self.v["name"].set(e.get("name", ""))
        self.v["hook"].set(catalog.HOOKS.get(e.get("hook"), catalog.HOOKS["random"]))
        self.v["distance"].set(catalog.DISTANCES.get(e.get("distance"), catalog.DISTANCES["any"]))
        self.v["freq"].set(SP.FREQ.get(e.get("freq"), SP.FREQ["sometimes"])[0])
        self.v["time"].set(SP.TIMES.get(e.get("time"), SP.TIMES["any"])[0])
        self.v["cooldown"].set(str(e.get("cooldown", 30)))
        self.refresh_who()
        self.refresh_steps()
        self.update_hint()
        self.loading = False

    def update_hint(self):
        hook = inv(catalog.HOOKS, self.v["hook"].get()) or "random"
        dist = inv(catalog.DISTANCES, self.v["distance"].get()) or "any"
        tips = {
            "near": "Если участники далеко — сначала подойдут друг к другу, потом заговорят.",
            "far": "Играет, только когда участники далеко: кричат друг другу через экран. "
                   "Для встроенных моментов (пристаёт, болтают, защита…) сначала играет «далеко», потом они сходятся и играет «рядом».",
            "any": "Играет там, где стоят, без подхода.",
        }
        roles = {
            "pester": "Первый — кто пристаёт, второй — к кому.", "talk": "Первый и второй — кто болтает.",
            "defend": "Первый — защитник, второй — охотник, третий — добыча.",
            "break_fight": "Первый — защитник, второй — охотник, третий — добыча.",
            "prey_wins": "Первый — добыча, второй — охотник.", "hunter_wins": "Первый — охотник, второй — добыча.",
            "after_hide": "Первый — кто прятался, второй — защитник.",
            "click": "Тыкаешь в первого участника — играет это событие.",
            "meet": "Срабатывает, когда участники подошли друг к другу.",
        }
        self.hint.config(text=" ".join(t for t in (roles.get(hook, ""), tips[dist]) if t))

    def refresh_who(self):
        e = self.cur
        self.who_list.delete(0, "end")
        for c in e.get("who", []):
            self.who_list.insert("end", f" {self.ed.name_of(c)}")
        others = [c for c in store.list_ids() if c not in e.get("who", [])]
        self.add_who_box.configure(values=[self.ed.name_of(c) for c in others])
        self.add_who_var.set(self.ed.name_of(others[0]) if others else "")
        names = [self.ed.name_of(c) for c in e.get("who", [])]
        self.step_who_box.configure(values=names)
        if self.step_who.get() not in names:
            self.step_who.set(names[0] if names else "")

    def id_by_name(self, name):
        return next((c for c in store.list_ids() if self.ed.name_of(c) == name), None)

    def add_who(self):
        cid = self.id_by_name(self.add_who_var.get())
        if cid and cid not in self.cur.setdefault("who", []):
            self.cur["who"].append(cid)
            self.refresh_who()
            self.changed()

    def move_who(self, d):
        sel = self.who_list.curselection()
        who = self.cur.get("who", [])
        if sel and 0 <= sel[0] + d < len(who):
            i = sel[0]
            who[i], who[i + d] = who[i + d], who[i]
            self.refresh_who()
            self.who_list.selection_set(i + d)
            self.changed()

    def remove_who(self):
        sel = self.who_list.curselection()
        if sel:
            cid = self.cur["who"].pop(sel[0])
            self.cur["steps"] = [s for s in self.cur.get("steps", []) if s.get("who") != cid]
            self.refresh_who()
            self.refresh_steps()
            self.changed()

    def refresh_steps(self, select=None):
        self.step_list.delete(0, "end")
        for s in self.cur.get("steps", []):
            anim = f"  [{s['anim']}]" if s.get("anim") else ""
            say = f"«{s['say']}»" if s.get("say") else "(молча)"
            self.step_list.insert("end", f" {self.ed.name_of(s.get('who'))}: {say}{anim}")
        if select is not None and self.cur.get("steps"):
            select = max(0, min(select, len(self.cur["steps"]) - 1))
            self.step_list.selection_set(select)
            self.step_list.see(select)

    def refresh_step_anims(self):
        cid = self.id_by_name(self.step_who.get())
        names = SP.anim_names(cid, self.ed.chars, self.ed.rels) if cid else []
        self.step_anim_box.configure(values=[""] + [n for n in names if n] + [p for p in POSES if p and p not in names])

    def on_step_select(self, _e=None):
        sel = self.step_list.curselection()
        if sel:
            s = self.cur["steps"][sel[0]]
            self.step_who.set(self.ed.name_of(s.get("who")))
            self.step_say.set(s.get("say", ""))
            self.step_anim.set(s.get("anim", ""))

    def current_step(self):
        cid = self.id_by_name(self.step_who.get())
        if not cid:
            self.ed.say("Сначала добавь участников.", WARN)
            return None
        if not self.step_say.get().strip() and not self.step_anim.get().strip():
            self.ed.say("Нужна фраза или анимация.", WARN)
            return None
        return {"who": cid, "say": self.step_say.get().strip(), "anim": self.step_anim.get().strip()}

    def add_step(self):
        s = self.current_step()
        if s:
            self.cur.setdefault("steps", []).append(s)
            self.step_say.set("")
            self.step_anim.set("")
            self.refresh_steps(select=len(self.cur["steps"]) - 1)
            self.changed()

    def update_step(self):
        sel = self.step_list.curselection()
        s = self.current_step()
        if sel and s:
            self.cur["steps"][sel[0]] = s
            self.refresh_steps(select=sel[0])
            self.changed()

    def move_step(self, d):
        sel = self.step_list.curselection()
        steps = self.cur.get("steps", [])
        if sel and 0 <= sel[0] + d < len(steps):
            i = sel[0]
            steps[i], steps[i + d] = steps[i + d], steps[i]
            self.refresh_steps(select=i + d)
            self.changed()

    def delete_step(self):
        sel = self.step_list.curselection()
        if sel:
            self.cur["steps"].pop(sel[0])
            self.refresh_steps(select=sel[0])
            self.changed()

    def new_event(self):
        self.saver.flush()
        self.events = store.load_events()
        who = [self.ed.key] if self.ed.key not in (None, EFFECTS_KEY) else []
        e = {"id": store.new_event_id(self.events), "name": "Новое событие", "hook": "random", "who": who,
             "distance": "near", "freq": "sometimes", "time": "any", "cooldown": 60, "steps": []}
        self.events.append(e)
        store.save_events(self.events)
        self.refresh_list(select_id=e["id"])
        self.ed.say("Событие создано: выбери «Когда», добавь участников и шаги.", OK)

    def dup_event(self):
        if not self.cur:
            return
        self.saver.flush()
        self.events = store.load_events()
        e = dict(self.cur, steps=[dict(s) for s in self.cur.get("steps", [])], who=list(self.cur.get("who", [])))
        e["id"] = store.new_event_id(self.events)
        e["name"] = (self.cur.get("name") or "") + " (копия)"
        self.events.append(e)
        store.save_events(self.events)
        self.refresh_list(select_id=e["id"])

    def delete_event(self):
        if not self.cur or not messagebox.askyesno("Удалить событие?", f"«{self.cur.get('name')}» удалить?"):
            return
        self.saver.job and self.root.after_cancel(self.saver.job)
        self.saver.job = None
        self.events = [e for e in store.load_events() if e.get("id") != self.cur.get("id")]
        store.save_events(self.events)
        self.cur = None
        self.refresh_list()

    def changed(self, *_):
        if not self.loading and self.cur:
            self.update_hint()
            self.saver()

    def save(self):
        if not self.cur:
            return False
        e = self.cur
        e["name"] = self.v["name"].get().strip() or e.get("id")
        e["hook"] = inv(catalog.HOOKS, self.v["hook"].get()) or "random"
        e["distance"] = inv(catalog.DISTANCES, self.v["distance"].get()) or "any"
        e["freq"] = inv(SP.FREQ, self.v["freq"].get(), lambda x: x[0]) or "sometimes"
        e["time"] = inv(SP.TIMES, self.v["time"].get(), lambda x: x[0]) or "any"
        try:
            e["cooldown"] = max(0, int(float(self.v["cooldown"].get())))
        except ValueError:
            pass
        events = store.load_events()
        ids = [x.get("id") for x in events]
        if e.get("id") in ids:
            events[ids.index(e["id"])] = e
        else:
            events.append(e)
        store.save_events(events)
        self.events = events
        sel = self.ev_list.curselection()
        if sel:
            self.ev_list.delete(sel[0])
            self.ev_list.insert(sel[0], self.label(e))
            self.ev_list.selection_set(sel[0])
            self.shown[sel[0]] = e

    def show(self):
        self.saver.flush()
        if not self.cur or not self.cur.get("steps"):
            self.ed.say("Добавь хотя бы один шаг.", WARN)
            return
        self.ed.play("event", self.cur["id"])


class BuildDialog:
    def __init__(self, ed):
        self.ed = ed
        ed.flush_all()
        self.win = win = tk.Toplevel(ed.root)
        win.title("Собрать пакет для друга")
        win.configure(bg=PANEL)
        win.geometry("620x560")
        win.transient(ed.root)
        f = ttk.Frame(win, style="Panel.TFrame", padding=16)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Пакет для друга", style="Head.TLabel").pack(anchor="w")
        ttk.Label(f, text="Соберёт готовую программу: Desktop Pets.exe и редактор, Python у друга не нужен.\n"
                          "Друг сможет менять, добавлять и удалять персонажей, реплики и события сам.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(2, 10))
        ttk.Label(f, text="Каких персонажей положить (можно никого — будет пустой конструктор):",
                  style="Panel.TLabel").pack(anchor="w")
        self.picks = {}
        for cid in store.list_ids():
            v = tk.BooleanVar(value=True)
            ttk.Checkbutton(f, text=ed.name_of(cid), variable=v).pack(anchor="w")
            self.picks[cid] = v
        row = ttk.Frame(f, style="Panel.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Название:", style="Panel.TLabel").pack(side="left")
        self.name = tk.StringVar(value="Desktop Pets")
        ttk.Entry(row, textvariable=self.name).pack(side="left", fill="x", expand=True, padx=6)
        self.btn = ttk.Button(f, text="Собрать", style="Accent.TButton", command=self.start)
        self.btn.pack(anchor="w", pady=10)
        self.log = ed.textbox(f, height=12)
        self.log.pack(fill="both", expand=True)

    def write(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    def start(self):
        chars = [c for c, v in self.picks.items() if v.get()]
        name = re.sub(r'[\\/:*?"<>|]', "", self.name.get()).strip() or "Персонажи"
        self.btn.state(["disabled"])
        self.write("Собираю… это займёт 1–3 минуты.\n")
        cmd = [sys.executable, os.path.join(paths.BASE, "build.py"), "--name", name, "--chars", ",".join(chars)]

        def run():
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", cwd=paths.BASE,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                     env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                result = None
                for line in p.stdout:
                    if line.startswith("ГОТОВО:"):
                        result = line.split(":", 1)[1].strip()
                    self.win.after(0, self.write, line)
                p.wait()
                self.win.after(0, self.done, p.returncode, result)
            except Exception as e:
                self.win.after(0, self.write, f"Ошибка: {e}\n")
                self.win.after(0, self.done, 1, None)

        threading.Thread(target=run, daemon=True).start()

    def done(self, code, result):
        self.btn.state(["!disabled"])
        if code == 0 and result:
            self.write(f"\nГотово! Архив: {result}\n")
            os.startfile(os.path.dirname(result))
        else:
            self.write("\nНе получилось собрать — подробности выше.\n")


if __name__ == "__main__":
    Editor().root.mainloop()
