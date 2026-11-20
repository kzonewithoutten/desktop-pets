import ctypes
import math
import os
import random
import sys
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
import winreg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog
import desktop_icons
import fonts
import paths
import sprites as SP
import store
from sprites import SpriteSet

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

KEY = "#000001"
GRAVITY = 2200
BEAM = 240
INK, PAPER = "#111111", "#ffffff"
DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "#32768", "NotifyIconOverflowWindow"}
S = 1.0


def pick(seq):
    return random.choice(seq)


def sign(v):
    return 1 if v >= 0 else -1


def weighted(options):
    options = [(w, f) for w, f in options if w > 0]
    if not options:
        return None
    r = random.uniform(0, sum(w for w, _ in options))
    for w, f in options:
        r -= w
        if r <= 0:
            return f
    return options[-1][1]


def shade(color, k):
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return color
    f = lambda v: max(0, min(255, int(v * k if k < 1 else v + (255 - v) * (k - 1))))
    return f"#{f(r):02x}{f(g):02x}{f(b):02x}"


def work_area(root):
    try:
        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
        r = RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)
        return r.l, r.t, r.r, r.b
    except Exception:
        return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 40


class Character:
    height = None
    width = None
    OUT = "#1a1a1a"
    SITTING = ("code", "read", "sleep")

    def __init__(self, world, cid, data, x):
        self.w = world
        self.cid = self.key = cid
        self.apply(data)
        self.x, self.y = x, world.ground
        self.vx = self.vy = 0.0
        self.facing = random.choice((-1, 1))
        self.pose = "stand"
        self.action = None
        self.busy = False
        self.scene = None
        self.held = False
        self.climbing = False
        self.drop_check = False
        self.hide_mode = None
        self.alert = False
        self.caged = False
        self.scanning = False
        self.label = None
        self.progress = None
        self.checked = set()
        self.hide_cd = 0
        self.glitch_until = 0
        self.hunger = random.uniform(5, 35)
        self.energy = random.uniform(60, 100)
        self.bubble = None
        self.bubble_until = 0
        self.t0 = random.uniform(0, 100)
        self._ox = self._oy = 0
        self._rot = None
        self.sprites = None
        self._anim = None
        self._shown_pose, self._pose_t0 = None, 0
        self.custom_cd = {}
        self._vi, self._vi_anim, self._vi_t0 = 0, None, 0
        self._last_vi = {}
        self._lock_variant = False
        self.reacted = {}
        self.platform = None
        self.ignore_platforms_until = 0
        self.bump_cd = 0
        self.seen_through = self.fooled = False

    def apply(self, data):
        self.data = data
        self.name = data.get("name", self.cid)
        self.color = data.get("color", "#7c6cff")
        self.speed = float(data.get("speed", 90) or 90)
        self.h = type(self).height or float(data.get("height", 80) or 80)
        self.wd = type(self).width or self.h * 0.42

    def line(self, cat):
        options = [t for t in self.data.get("lines", {}).get(cat, []) if t.strip()]
        return pick(options) if options else None

    def say_line(self, cat, dur=None):
        text = self.line(cat)
        return self.say(text, dur) if text else 0

    def anim_for(self, action):
        return self.data.get("anims", {}).get(action) or catalog.ACTIONS[action][1]

    @property
    def floor(self):
        return self.platform[1] if self.platform else self.w.ground

    @property
    def airborne(self):
        return not self.climbing and (self.y < self.floor - 0.5 or self.vy < 0)

    @property
    def free(self):
        return not self.busy and not self.held and not self.airborne

    def say(self, text, dur=None):
        d = dur or (1.3 + 0.05 * len(text))
        self.bubble = text
        self.bubble_until = self.w.now + d + 0.5
        return d

    def set_action(self, gen):
        old, self.action = self.action, gen
        if old is not None and old is not gen:
            old.close()

    def glitch(self, sec):
        self.glitch_until = max(self.glitch_until, self.w.now + sec)

    def needs(self, dt):
        self.hunger = min(100, self.hunger + 0.22 * dt)
        if self.pose == self.anim_for("sleep"):
            self.energy = min(100, self.energy + 5 * dt)
        else:
            self.energy = max(0, self.energy - (1.3 if self.pose.startswith("sport") else 0.12) * dt)

    def update(self):
        w, dt = self.w, self.w.dt
        self.needs(dt)
        if self.held:
            return
        if self.platform and not self.climbing and not self.platform[0] - 6 <= self.x <= self.platform[2] + 6:
            self.platform = None
            self.ignore_platforms_until = w.now + 0.5
        if self.airborne:
            prev = self.y
            self.vy += GRAVITY * S * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            lo, hi = w.left + 20 * S, w.right - 20 * S
            if self.x < lo or self.x > hi:
                self.x = min(max(self.x, lo), hi)
                self.vx = -self.vx * 0.5
            hit = w.icon_collision(self, prev) if w.now >= self.ignore_platforms_until else None
            if hit and hit[0] == "land":
                impact = self.vy
                self.platform = hit[1]
                self.y, self.vx, self.vy = hit[1][1], 0.0, 0.0
                self.on_land(impact, icon=True)
            elif hit and hit[0] == "bump" and w.now > self.bump_cd:
                self.bump_cd = w.now + 1
                self.on_bump()
            elif self.y >= w.ground:
                impact = self.vy
                self.platform = None
                self.y, self.vx, self.vy = w.ground, 0.0, 0.0
                self.on_land(impact)
            return
        self.step()

    def step(self):
        if self.action is None and not self.busy:
            self.pose = "stand"
            self.action = self.choose()
        gen = self.action
        if gen is None:
            return
        try:
            next(gen)
        except StopIteration:
            if self.action is gen:
                self.action = None

    def on_land(self, impact, icon=False):
        if impact > 1400 * S:
            self.say_line("land")
        dropped, started = self.drop_check, False
        if self.drop_check:
            self.drop_check = False
            started = self.w.check_drop(self)
        if started or self.busy:
            return
        name = None
        if icon:
            name = (impact > 900 * S and self.situ("icon_bump")) or self.situ("icon_sit")
        if not name and dropped:
            name = self.situ("drop")
        if name:
            self.set_action(self.play_custom(name))

    def on_bump(self):
        if not self.busy:
            name = self.situ("icon_bump")
            if name:
                self.set_action(self.play_custom(name))

    def choose(self):
        w = self.w
        opts = []
        for code, weight in self.data.get("actions", {}).items():
            fn = getattr(self, "act_" + code, None)
            if not fn or not weight or weight <= 0:
                continue
            if code == "sleep":
                weight *= max(0.0, (70 - self.energy) / 12)
            elif code == "eat":
                weight *= max(0.0, (self.hunger - 40) / 10)
            elif code == "sport" and self.energy < 30:
                weight *= 0.1
            opts.append((weight, fn))
        for kind, other, weight in w.relations_of(self):
            if other.free and kind == "pesters":
                opts.append((weight, lambda o=other: self.start_scene(scene_pester, [self, o])))
            elif other.free and kind == "chats":
                opts.append((weight, lambda o=other: self.start_scene(scene_talk, [self, o])))
        fn = weighted(opts + self.custom_options()) or self.act_look_around
        return fn()

    def start_scene(self, fn, chars):
        self.w.director.request(fn, chars)
        yield from self.wait(0.3)

    def area_ok(self, info):
        w = self.w
        try:
            ax0, ay0, ax1, ay1 = (float(v) for v in info.get("area", (0, 0, 1, 1)))
        except (TypeError, ValueError):
            return True
        sx = (self.x - w.left) / max(1, w.right - w.left)
        sy = self.y / max(1, w.ground)
        surface = info.get("surface", "any")
        if surface == "floor" and self.platform:
            return False
        if surface == "icon" and not self.platform:
            return False
        return ax0 - 0.01 <= sx <= ax1 + 0.01 and ay0 - 0.01 <= sy <= ay1 + 0.01

    def customs(self, *triggers, anywhere=False):
        customs = self.sprites.customs if self.sprites is not None else {}
        hour = time.localtime().tm_hour
        return [(n, i) for n, i in customs.items()
                if i.get("trigger") in triggers and self.w.now >= self.custom_cd.get(n, 0)
                and SP.time_ok(i.get("time", "any"), hour) and (anywhere or self.area_ok(i))]

    def situ(self, code):
        options = self.customs(code)
        return pick(options)[0] if options else None

    def anim_name(self):
        pose = self._shown_pose or self.pose
        if self.sprites is not None and pose in self.sprites.customs:
            return pose
        if self.hide_mode:
            return self.hide_mode
        return "idle" if pose == "stand" else pose

    def custom_options(self):
        out = []
        if not self.platform and self.w.platforms:
            for name, info in self.customs("icon_sit", anywhere=True):
                wt = SP.FREQ.get(info.get("freq"), SP.FREQ["sometimes"])[1] * 0.6
                out.append((wt, lambda n=name: self.go_to_icon(n)))
        for name, info in self.customs("random", "hungry", "tired"):
            wt = SP.FREQ.get(info.get("freq"), SP.FREQ["sometimes"])[1]
            trig = info.get("trigger")
            if trig == "hungry":
                if self.hunger < 55:
                    continue
                wt *= 2
            elif trig == "tired":
                if self.energy > 35:
                    continue
                wt *= 2
            out.append((wt, lambda n=name: self.play_custom(n)))
        return out

    def anim_duration(self, name):
        anim = self.sprites.anims.get(name) if self.sprites is not None else None
        return anim.duration(0) if anim else 1.5

    def play_custom(self, name, quiet=False, repeat=None):
        anim = self.sprites.anims.get(name) if self.sprites is not None else None
        if anim is None:
            return
        info = self.sprites.customs.get(name, {})
        if info.get("say") and not quiet:
            self.say(pick(info["say"]))
        try:
            repeat = max(1, int(repeat or info.get("repeat", 2)))
            speed = float(info.get("move", 0)) * S
        except (TypeError, ValueError):
            repeat, speed = 2, 0
        vi = anim.next_variant(self._last_vi.get(id(anim), -1))
        self._last_vi[id(anim)] = vi
        self._vi, self._vi_anim, self._vi_t0 = vi, anim, self.w.now
        self.pose = self._shown_pose = name
        self._pose_t0 = self.w.now
        end = self.w.now + max(1.0, anim.duration(vi) * repeat)
        self._lock_variant = True
        try:
            while self.w.now < end:
                self.pose = name
                if speed:
                    nx = self.x + self.facing * speed * self.w.dt
                    if nx != self.w.clamp_x(nx):
                        self.facing = -self.facing
                    else:
                        self.x = nx
                yield
        finally:
            self._lock_variant = False
        self.pose = "stand"
        self.custom_cd[name] = self.w.now + 20
        trig = info.get("trigger")
        if trig == "hungry":
            self.hunger = max(0, self.hunger - 60)
        elif trig == "tired":
            self.energy = min(100, self.energy + 50)

    def go_to_icon(self, name):
        plats = sorted(self.w.platforms, key=lambda p: -p[1])[:4]
        if not plats:
            return
        x0, top, x1, _ = random.choice(plats)
        yield from self.walk_to((x0 + x1) / 2)
        if self.platform or self.airborne or abs(self.x - (x0 + x1) / 2) > 10 * S:
            return
        h = max(10.0, self.y - top) + 30 * S
        self.vy, self.vx = -math.sqrt(2 * GRAVITY * S * h), 0.0
        self.y -= 1
        yield

    def puppet(self):
        while True:
            yield

    def wait(self, sec, pose=None):
        end = self.w.now + sec
        while self.w.now < end:
            if pose:
                self.pose = pose
            yield

    def walk_to(self, tx, speed=None, pose="walk"):
        tx = self.w.clamp_x(tx)
        sp = (speed or self.speed) * S
        while abs(self.x - tx) > 2:
            d = sign(tx - self.x)
            self.facing, self.pose = d, pose
            self.x += d * min(sp * self.w.dt, abs(tx - self.x))
            yield
        self.pose = "stand"

    def act_wander(self):
        yield from self.walk_to(self.x + random.uniform(-350, 350) * S)
        if random.random() < 0.35:
            self.say_line("idle")
        yield from self.wait(random.uniform(1, 3))

    def act_look_around(self):
        for _ in range(random.randint(1, 3)):
            yield from self.wait(random.uniform(1.5, 3))
            self.facing = -self.facing

    def act_talk_user(self):
        yield from self.wait(max(2.0, self.say_line("user") + 1))

    def act_sleep(self):
        self.say_line("sleep")
        yield from self.wait(1.5)
        end = self.w.now + 25
        while self.w.now < end and self.energy < 98:
            self.pose = self.anim_for("sleep")
            yield
        self.pose = "stand"
        self.say_line("wake")
        yield from self.wait(2)

    def act_eat(self):
        self.say_line("eat")
        yield from self.wait(6, pose=self.anim_for("eat"))
        self.hunger = 0

    def act_sport(self):
        self.say_line("sport_start")
        poses = ["sport_jacks", "sport_squat"]
        if self.data.get("anims", {}).get("sport"):
            poses = [self.data["anims"]["sport"]]
        for kind in random.sample(poses, k=random.choice([1, len(poses)])):
            yield from self.wait(random.uniform(5, 8), pose=kind)
        self.pose = "stand"
        self.say_line("sport_end")
        yield from self.wait(2)

    def act_laugh(self):
        self.say_line("laugh")
        texts = self.data.get("particles", {}).get("laugh") or []
        end = self.w.now + 3.5
        while self.w.now < end:
            self.pose = self.anim_for("laugh")
            if texts and random.random() < 0.08:
                self.w.add_particle(self.x + random.uniform(-25, 25) * S, self.y - self.top() * 0.95, pick(texts),
                                    self.color, size=random.randint(9, 14), life=1.2)
            yield
        self.pose = "stand"

    def act_work(self):
        w = self.w
        texts = self.data.get("particles", {}).get("work") or []
        end, next_line = w.now + random.uniform(12, 22), w.now + random.uniform(3, 7)
        while w.now < end:
            self.pose = self.anim_for("work")
            if texts and random.random() < w.dt * 1.2:
                hx, hy = self.x + 24 * S * self.facing, self.y - self.top() * 0.35
                w.add_particle(hx, hy, pick(texts), "#7fd8ff", size=8, font="Consolas", life=2.2)
            if w.now > next_line:
                next_line = w.now + random.uniform(7, 12)
                self.say_line("work")
            yield
        self.energy = max(0, self.energy - 6)

    def act_read(self):
        self.say_line("read")
        yield from self.wait(random.uniform(10, 16), pose=self.anim_for("read"))

    def act_update(self):
        w = self.w
        self.say_line("update")
        start, dur = w.now, 7
        try:
            while w.now - start < dur:
                self.pose = self.anim_for("update") if self.anim_for("update") != "idle" else "stand"
                self.progress = (w.now - start) / dur
                yield
        finally:
            self.progress = None
        self.say_line("update_done")
        yield from self.wait(2)

    def act_patrol(self):
        w = self.w
        self.say_line("scan_start")
        self.scanning, self.checked = True, set()
        try:
            legs = [w.right, w.left] if self.x < (w.left + w.right) / 2 else [w.left, w.right]
            legs = [w.clamp_x(v) for v in legs]
            total = abs(legs[0] - self.x) + abs(legs[1] - legs[0]) + 1
            done = 0.0
            for tx in legs:
                while abs(self.x - tx) > 2:
                    d = sign(tx - self.x)
                    step = min(self.speed * S * w.dt, abs(tx - self.x))
                    self.facing, self.pose = d, self.anim_for("patrol")
                    self.x += d * step
                    done += step
                    self.label = f"Сканирование... {min(99, int(done / total * 100))}%"
                    res, prey = w.beam_check(self)
                    if res == "hit":
                        w.director.request(scene_chase, [self, prey])
                        yield from self.wait(1)
                    elif res == "fooled":
                        name = self.situ(f"hunter_fooled:{prey.cid}")
                        if name:
                            yield from self.play_custom(name)
                    yield
            self.label = None
            self.pose = "stand"
            self.say_line("scan_clean")
            yield from self.wait(2)
        finally:
            self.scanning, self.label = False, None

    def act_escape(self):
        yield from weighted([(1.3, self.cursor_hunt), (1, self.bang), (1, self.climb)])()

    def cursor_hunt(self):
        w = self.w
        self.say_line("cursor")
        end, last_jump = w.now + 9, 0
        while w.now < end:
            px, py = w.pointer()
            dx = px - self.x
            if abs(dx) > 25 * S:
                self.facing, self.pose = sign(dx), "run"
                self.x = w.clamp_x(self.x + sign(dx) * 190 * S * w.dt)
            else:
                self.pose = "stand"
            if abs(dx) < 80 * S and self.y - 450 * S < py < self.y and w.now - last_jump > 1.3:
                last_jump = w.now
                h = min(max(self.y - py, 60 * S), 450 * S)
                self.vy = -math.sqrt(2 * GRAVITY * S * h)
                self.vx = dx * 2
                self.say_line("jump_cursor")
            yield
        self.pose = "stand"
        self.say_line("cursor_fail")
        yield from self.wait(2)

    def go_to_edge(self):
        w = self.w
        side = -1 if self.x < (w.left + w.right) / 2 else 1
        yield from self.walk_to(w.left if side < 0 else w.right, speed=170, pose="run")
        self.facing = side

    def bang(self):
        w = self.w
        yield from self.go_to_edge()
        self.say_line("bang")
        end, next_crack, said = w.now + 5.5, w.now + 0.4, False
        while w.now < end:
            self.pose = "bang"
            if w.now > next_crack:
                next_crack = w.now + random.uniform(0.6, 1.2)
                w.add_crack(self.x + 20 * S * self.facing, self.y - self.top() * random.uniform(0.6, 0.8))
            if not said and end - w.now < 2.5:
                said = True
                self.say_line("bang")
            yield
        self.pose = "stand"

    def climb(self):
        w = self.w
        yield from self.go_to_edge()
        self.say_line("climb")
        self.climbing = True
        try:
            top = self.y - random.uniform(0.3, 0.6) * w.ground
            while self.y > top:
                self.pose = "climb"
                self.y -= 75 * S * w.dt
                yield
            self.say_line("climb_top")
            yield from self.wait(2.2, pose="climb")
        finally:
            self.climbing = False
        self.say_line("fall")
        yield

    def self_hide(self, hunter):
        w = self.w
        mode = "icon" if random.random() < 0.75 else "flat"
        self.fooled = False
        self.say_line("hide_" + mode)
        yield from self.wait(0.5)
        self.hide_mode, self.pose = mode, "stand"
        start = w.now
        try:
            while w.now - start < 15:
                if w.now - start > 3 and not hunter.scanning:
                    break
                yield
        finally:
            self.hide_mode = None
        name = self.situ(f"prey_fooled:{hunter.cid}") if self.fooled else None
        self.fooled = False
        if name:
            yield from self.play_custom(name)
        else:
            self.say_line("unhide")
            yield from self.wait(2)

    def react_then_hide(self, hunter, protector):
        name = self.situ(f"prey_near:{hunter.cid}")
        if name:
            yield from self.play_custom(name)
        if protector is not None and protector.free:
            self.w.director.request(lambda sc, w: scene_hide_behind(sc, w, self, protector, hunter), [self, protector])
            yield from self.wait(0.5)
        elif self.data.get("can_disguise"):
            yield from self.self_hide(hunter)

    def P(self, dx, dy):
        if self._rot is not None:
            c, s = self._rot
            dx, dy = dx * c - dy * s, dx * s + dy * c
        dx += self._ox
        dy += self._oy
        return self.x + dx * S * self.facing, self.y - dy * S

    def pts(self, seq):
        out = []
        for dx, dy in seq:
            out.extend(self.P(dx, dy))
        return out

    def poly(self, seq, fill, outline=None, w=2, smooth=False):
        self.w.cv.create_polygon(self.pts(seq), fill=fill, outline=self.OUT if outline is None else outline,
                                 width=w * S, smooth=smooth, joinstyle=tk.ROUND)

    def line_(self, seq, fill, w=2, **kw):
        self.w.cv.create_line(self.pts(seq), fill=fill, width=max(1, w * S), capstyle=tk.ROUND,
                              joinstyle=tk.ROUND, **kw)

    def circle(self, cx, cy, r, fill, outline=None, w=2, ry=None):
        x, y = self.P(cx, cy)
        ry = r if ry is None else ry
        self.w.cv.create_oval(x - r * S, y - ry * S, x + r * S, y + ry * S, fill=fill,
                              outline=self.OUT if outline is None else outline, width=w * S if outline != "" else 0)

    def text(self, dx, dy, s, fill, size=10, font="Segoe UI", bold=True):
        x, y = self.P(dx, dy)
        self.w.cv.create_text(x, y, text=s, fill=fill, font=(font, size, "bold" if bold else "normal"))

    def zzz(self, dx, dy, t):
        for k in range(3):
            ph = (t * 0.6 + k / 3) % 1
            self._rot = None
            self.text(dx + ph * 14, dy + ph * 26, "z", "#9db7ff", size=int(8 + ph * 7))

    def render(self):
        self._ox = self._oy = 0
        self._rot = None
        if self.held:
            pose = "held"
        elif self.airborne:
            pose = "fall"
        else:
            pose = self.pose
        if pose != self._shown_pose:
            self._shown_pose, self._pose_t0 = pose, self.w.now
        t = self.w.now + self.t0
        self._anim = None
        if pose == "incloud":
            return
        if self.sprites is not None:
            if pose in self.sprites.customs:
                name = pose
            else:
                name = self.hide_mode or ("idle" if pose == "stand" else pose)
            if self.sprites or name in self.sprites.anims:
                self._anim = self.sprites.get(name, self.alert)
        anim = self._anim
        if anim:
            now = self.w.now
            if self._vi_anim is not anim or self._pose_t0 == now:
                if not (self._lock_variant and self._vi_anim is anim):
                    self._vi = anim.next_variant(self._last_vi.get(id(anim), -1))
                    self._last_vi[id(anim)] = self._vi
                self._vi_anim, self._vi_t0 = anim, now
            elif not self._lock_variant and len(anim.variants) > 1 and now - self._vi_t0 >= anim.duration(self._vi):
                self._vi = anim.next_variant(self._vi)
                self._last_vi[id(anim)] = self._vi
                self._vi_t0 = now
            img = anim.frame(now - self._vi_t0, self.facing, self._vi)
            self.w.cv.create_image(self.x, self.y, image=img, anchor="s")
        elif self.hide_mode == "icon":
            self.draw_icon(t)
        elif self.hide_mode == "flat":
            self.draw_flat(t)
        else:
            self.draw(pose, t)
        self._rot = None
        self._ox = self._oy = 0
        self.overlays(pose, t)

    def draw(self, pose, t):
        pass

    def overlays(self, pose, t):
        cv = self.w.cv
        if self.caged:
            self.draw_cage()
        if pose == self.anim_for("patrol") and self.scanning or pose == "scan":
            top = self.top()
            ex, ey = self.x + self.half() * 0.5 * self.facing, self.y - top * 0.65
            tx1, ty1 = self.x + BEAM * S * self.facing, self.y - top * 1.25
            tx2, ty2 = self.x + BEAM * S * self.facing, self.y
            cv.create_line(ex, ey, tx1, ty1, fill="#5cf2ff", width=1, dash=(4, 4))
            cv.create_line(ex, ey, tx2, ty2, fill="#5cf2ff", width=1, dash=(4, 4))
            ph = (math.sin(t * 3) + 1) / 2
            cv.create_line(ex, ey, tx1, ty1 + (ty2 - ty1) * ph, fill="#5cf2ff", width=2 * S)
        if self.progress is not None:
            x0, y0 = self.x - 26 * S, self.y - self.top() - 12 * S
            cv.create_rectangle(x0, y0, x0 + 52 * S, y0 + 7 * S, fill="#0d1b2a", outline="#5cf2ff", width=1)
            cv.create_rectangle(x0 + 1.5 * S, y0 + 1.5 * S, x0 + (1.5 + 49 * self.progress) * S, y0 + 5.5 * S,
                                fill=self.color, width=0)

    def draw_icon(self, t):
        self.poly([(-12, 48), (5, 48), (12, 41), (12, 14), (-12, 14)], "#ffffff", outline="#6b7280", w=1.5)
        self.line_([(5, 48), (5, 41), (12, 41)], "#6b7280", w=1.5)
        for k in range(4):
            self.line_([(-8, 36 - k * 5), (8, 36 - k * 5)], "#c4c8d0", w=1.5)
        if (t % 5) < 0.6:
            self.circle(-3, 30, 1.4, self.color, outline="")
            self.circle(3, 30, 1.4, self.color, outline="")
        self.w.boxed_text(self.x, self.y - 5 * S, self.data.get("icon_label") or "файл.txt", "#ffffff", "#1f3a68",
                          ("Segoe UI", 8))

    def draw_flat(self, t):
        for i, c in enumerate((shade(self.color, 1.3), self.color, shade(self.color, 0.55))):
            self.poly([(-24, 4.5 - i * 1.5), (24, 4.5 - i * 1.5), (24, 3 - i * 1.5), (-24, 3 - i * 1.5)], c, outline="")
        if (t % 3) < 0.4:
            self.circle(8, 6, 1, "#ff2a6d", outline="")
            self.circle(11, 6, 1, "#ff2a6d", outline="")

    def draw_cage(self):
        cv, x, y = self.w.cv, self.x, self.y
        half = self.half() + 6
        x0, x1, top = x - half, x + half, y - self.top() - 12 * S
        for k in range(7):
            bx = x0 + (x1 - x0) * k / 6
            cv.create_line(bx, top, bx, y, fill="#5cf2ff", width=2 * S)
        cv.create_line(x0, top, x1, top, fill="#5cf2ff", width=3 * S)
        cv.create_line(x0, y, x1, y, fill="#5cf2ff", width=3 * S)
        self.w.boxed_text(x, top - 8 * S, "КАРАНТИН", "#0d1b2a", "#5cf2ff", ("Consolas", 8, "bold"))

    def cur_box(self):
        if not self._anim:
            return None
        x0, top, x1 = self._anim.bbox_of(self._vi)
        if self.facing < 0:
            x0, x1 = -x1, -x0
        return x0, top, x1

    def top(self):
        b = self.cur_box()
        return b[1] if b else self.h * S

    def half(self):
        b = self.cur_box()
        return max(-b[0], b[2]) if b else self.wd / 2 * S

    def hitbox(self):
        if self.hide_mode == "behind":
            return None
        b = self.cur_box()
        if b:
            return self.x + b[0] - 4, self.y - b[1] - 4, self.x + b[2] + 4, self.y + 4
        if self.hide_mode in ("icon", "flat"):
            return self.x - 20 * S, self.y - 50 * S, self.x + 20 * S, self.y + 4
        hw = self.wd / 2 * S + 6
        if self.pose in ("sleep", "knocked") and not self.held and not self.airborne:
            return self.x - 46 * S, self.y - 34 * S, self.x + 46 * S, self.y + 4
        return self.x - hw, self.y - self.h * S - 6, self.x + hw, self.y + 4


class SimpleBody(Character):

    def draw(self, pose, t):
        k = self.h / 80
        col, dark, light = self.color, shade(self.color, 0.55), shade(self.color, 1.35)
        self.OUT = shade(self.color, 0.3)
        cx_, cy_, rx, ry = 0, 34 * k, 18 * k, 26 * k
        swing, base = 0.0, 0.0
        hands = [(-20 * k, 28 * k), (20 * k, 28 * k)]
        face = "calm"
        if pose in ("walk", "run", "scan"):
            sp = 15 if pose == "run" else 10
            swing = math.sin(t * sp) * (8 if pose == "run" else 5) * k
            base = abs(math.sin(t * sp)) * 1.5
        elif pose == "held":
            swing = math.sin(t * 3) * 4 * k
            hands, face = [(-14 * k, 62 * k), (14 * k, 62 * k)], "scared"
        elif pose == "fall":
            hands, face = [(-22 * k, 58 * k), (22 * k, 58 * k)], "scared"
        elif pose == "sport_jacks":
            o = (math.sin(t * 8) + 1) / 2
            base = o * 6
            hands = [(-20 * k - 4 * o, 28 * k + 30 * o * k), (20 * k + 4 * o, 28 * k + 30 * o * k)]
            face = "strain"
        elif pose == "sport_squat":
            d = (math.sin(t * 4) + 1) / 2 * 8 * k
            cy_, ry = cy_ - d * 0.6, ry - d * 0.4
            hands, face = [(16 * k, 34 * k - d), (20 * k, 34 * k - d)], "strain"
        elif pose == "laugh":
            self._ox = math.sin(t * 45) * 1.2
            hands, face = [(-14 * k, 40 * k), (20 * k, 56 * k)], "laugh"
        elif pose in ("eat", "tea"):
            chew = (t % 1.6) < 0.8
            hands, face = [(-20 * k, 28 * k), (10 * k, (48 if chew else 40) * k)], "chew" if chew else "calm"
        elif pose in ("sleep", "knocked"):
            cy_, rx, ry = 13 * k, 28 * k, 13 * k
            hands, face = [(-22 * k, 6 * k), (22 * k, 6 * k)], "closed" if pose == "sleep" else "x"
        elif pose == "behind":
            cy_, ry = 22 * k, 18 * k
            hands, face = [(6 * k, 34 * k), (9 * k, 34 * k)], "scared"
        elif pose in ("code", "read"):
            cy_, ry = 26 * k, 22 * k
            hands = [(16 * k, 18 * k), (20 * k, 18 * k)] if pose == "code" else [(14 * k, 34 * k), (18 * k, 34 * k)]
        elif pose == "defend":
            hands, face = [(-30 * k, 44 * k), (30 * k, 44 * k)], "stern"
        elif pose == "facepalm":
            hands, face = [(-20 * k, 28 * k), (8 * k, 46 * k)], "closed"
        elif pose == "whistle":
            hands, face = [(-6 * k, 22 * k), (-3 * k, 22 * k)], "whistle"
        elif pose == "bang":
            hit = max(0.0, math.sin(t * 10))
            hands, face = [(24 * k + 5 * hit, 42 * k), (20 * k, 34 * k)], "strain"
        elif pose == "climb":
            a = math.sin(t * 6) * 5
            hands, face = [(8 * k, 64 * k + a), (12 * k, 64 * k - a)], "strain"

        self._oy = base
        if pose not in ("sleep", "knocked"):
            for hx, s in ((-7 * k, swing), (7 * k, -swing)):
                self.line_([(hx, cy_ - ry * 0.7), (hx + s, 2)], dark, w=4)
                self.circle(hx + s + 2, 1.8, 3.5, dark, ry=2, w=1)
        if pose == "code":
            self.poly([(10 * k, 0), (32 * k, 0), (32 * k, 3), (10 * k, 3)], "#9aa3ad", w=1)
            self.poly([(29 * k, 3), (32 * k, 3), (26 * k, 22 * k), (23 * k, 22 * k)], "#4b5563", w=1)
        self.circle(cx_, cy_, rx, col, ry=ry)
        self.circle(cx_ + 3 * k, cy_ - ry * 0.25, rx * 0.55, light, outline="", ry=ry * 0.5)
        for sx, (hx, hy) in zip((-rx * 0.8, rx * 0.8), hands):
            self.line_([(sx, cy_ + ry * 0.1), (hx, hy)], dark, w=3.5)
            self.circle(hx, hy, 2.6, light, w=1)
        if pose in ("eat", "tea"):
            self.circle(hands[1][0] + 3, hands[1][1], 4, "#ffd166" if pose == "eat" else "#ffffff", w=1)
        if pose == "read":
            self.poly([(10 * k, 28 * k), (22 * k, 28 * k), (22 * k, 40 * k), (10 * k, 40 * k)], "#ffffff", w=1)
        ey = cy_ + ry * 0.35
        ex = (3 * k, 10 * k) if pose not in ("sleep", "knocked") else (14 * k, 20 * k)
        for x in ex:
            if face in ("closed",) or (t % 4.5) < 0.12:
                self.line_([(x - 2, ey), (x + 2, ey)], self.OUT, w=1.5)
            elif face == "x":
                self.line_([(x - 2, ey - 2), (x + 2, ey + 2)], self.OUT, w=1.5)
                self.line_([(x - 2, ey + 2), (x + 2, ey - 2)], self.OUT, w=1.5)
            elif face == "scared":
                self.circle(x, ey, 2.4, "#ffffff", w=1)
                self.circle(x, ey, 0.9, self.OUT, outline="")
            else:
                self.circle(x, ey + (1 if face == "whistle" else 0), 1.6, self.OUT, outline="", ry=2.2)
        mx, my = (ex[0] + ex[1]) / 2, ey - 7 * k
        if face == "laugh":
            self.circle(mx, my, 3.2, "#3a0010", ry=2.6, w=1)
        elif face in ("chew", "scared", "strain", "whistle"):
            self.circle(mx, my, 1.6, "#3a0010", ry=1.2, w=1)
        elif face == "stern":
            self.line_([(mx - 3, my), (mx + 3, my)], self.OUT, w=1.4)
        else:
            self.line_([(mx - 3, my + 0.5), (mx, my - 0.6), (mx + 3, my + 0.5)], self.OUT, w=1.4)
        if pose == "sleep":
            self.zzz(24 * k, 30 * k, t)
        if pose == "whistle":
            for j in range(2):
                ph = (t * 0.7 + j * 0.5) % 1
                self.text(14 * k + ph * 12, ey + ph * 20, "♪", col, size=int(9 + ph * 4))


BODIES = {"simple": SimpleBody}
BODY_NAMES = {"simple": "Простой кругляш (своего цвета)"}
try:
    import my_characters
    BODIES.update(my_characters.make(Character, globals()))
    BODY_NAMES.update(my_characters.NAMES)
except ImportError:
    pass


class Scene:
    def __init__(self, world):
        self.w = world
        self.chars = []

    def lock(self, c):
        if c.busy and c.scene is not self:
            return False
        if c not in self.chars:
            c.busy, c.scene = True, self
            self.chars.append(c)
            if c.pose in ("walk", "run", "scan"):
                c.pose = "stand"
            c.set_action(c.puppet())
        return True

    def release(self):
        for c in self.chars:
            if c.scene is self:
                c.busy, c.scene = False, None
                c.alert = c.caged = False
                if c.hide_mode == "behind":
                    c.hide_mode = None
                c.set_action(None)

    def wait(self, sec):
        end = self.w.now + sec
        while self.w.now < end:
            yield

    def say(self, c, text, pose=None):
        if pose:
            c.pose = pose
        if text:
            yield from self.wait(c.say(text))

    def do(self, c, gen):
        c.set_action(gen)
        while c.action is gen:
            yield

    def beats(self, *pairs):
        gens = []
        for c, code in pairs:
            name = c.situ(code)
            if name:
                gen = c.play_custom(name)
                c.set_action(gen)
                gens.append((c, gen))
        while any(c.action is g for c, g in gens):
            yield

    def gather(self, chars, timeout=12):
        if len(chars) < 2:
            return
        anchor = next((c for c in chars if c.held or c.airborne), chars[0])
        others = [c for c in chars if c is not anchor]
        for i, c in enumerate(others):
            side = sign(c.x - anchor.x) if abs(c.x - anchor.x) > 1 else (1 if i % 2 else -1)
            target = anchor.x + side * (48 + 40 * (i // 2)) * S
            if abs(c.x - target) > 30 * S and not c.held:
                c.set_action(c.walk_to(target))
        end = self.w.now + timeout
        while self.w.now < end and any(c.action is not None and c.pose == "walk" for c in others):
            yield
        for c in chars:
            c.set_action(c.puppet())
            if c.pose == "walk":
                c.pose = "stand"
        cx = sum(c.x for c in chars) / len(chars)
        for c in chars:
            if c.pose not in c.SITTING and abs(c.x - cx) > 2:
                c.facing = sign(cx - c.x)

    @staticmethod
    def face(a, b):
        a.facing = sign(b.x - a.x)


def spread(chars):
    xs = [c.x for c in chars]
    return max(xs) - min(xs) if xs else 0


def distance_state(chars):
    return "near" if spread(chars) <= catalog.NEAR_DIST * S else "far"


def run_event(sc, w, ev, chars):
    by_id = {c.cid: c for c in chars}
    w.event_cd[ev.get("id")] = w.now + float(ev.get("cooldown", 30) or 0)
    for step in ev.get("steps", []):
        c = by_id.get(step.get("who"))
        if c is None or not sc.lock(c):
            continue
        anim = (step.get("anim") or "").strip()
        text = (step.get("say") or "").strip()
        gen = None
        if anim:
            if c.sprites is not None and anim in c.sprites.anims:
                gen = c.play_custom(anim, quiet=True, repeat=1 if text else None)
                c.set_action(gen)
            else:
                c.pose = anim
        if text:
            yield from sc.wait(c.say(text))
        elif gen is not None:
            while c.action is gen:
                yield
        elif anim:
            yield from sc.wait(1.5)
        if gen is not None and c.action is gen:
            c.set_action(c.puppet())
    for c in chars:
        if c.scene is sc and c.pose not in c.SITTING:
            c.pose = "stand"


def run_hook(sc, w, hook, chars, gather=False):
    played = False
    if distance_state(chars) == "far":
        ev = w.pick_event(hook, chars, "far")
        if ev:
            yield from run_event(sc, w, ev, chars)
            played = True
        if gather:
            yield from sc.gather(chars)
    ev = w.pick_event(hook, chars, distance_state(chars))
    if ev:
        yield from run_event(sc, w, ev, chars)
        played = True
    return played


def scene_event(sc, w, ev, chars):
    if ev.get("distance") == "near" and distance_state(chars) == "far":
        yield from sc.gather(chars)
    yield from run_event(sc, w, ev, chars)


def scene_intro(sc, w):
    yield from sc.wait(0.5)
    yield from run_hook(sc, w, "intro", sc.chars, gather=True)


def scene_meal(sc, w):
    yield from run_hook(sc, w, "meal", sc.chars, gather=True)
    yield from sc.wait(1)
    for c in sc.chars:
        c.hunger = 0


def scene_pester(sc, w):
    a, b = sc.chars[:2]
    if distance_state([a, b]) == "far":
        ev = w.pick_event("pester", [a, b], "far")
        if ev:
            yield from run_event(sc, w, ev, [a, b])
    side = -1 if a.x < b.x else 1
    yield from sc.do(a, a.walk_to(b.x + side * 36 * S))
    sc.face(a, b)
    if b.pose not in b.SITTING:
        sc.face(b, a)
    a.pose = a.situ(f"pester_doing:{b.cid}") or a.pose
    b.pose = b.situ(f"pestered:{a.cid}") or b.pose
    ev = w.pick_event("pester", [a, b], "near")
    if ev:
        yield from run_event(sc, w, ev, [a, b])
    yield from sc.wait(0.5)


def scene_talk(sc, w):
    a, b = sc.chars[:2]
    if distance_state([a, b]) == "far":
        ev = w.pick_event("talk", [a, b], "far")
        if ev:
            yield from run_event(sc, w, ev, [a, b])
    if abs(a.x - b.x) > 70 * S:
        yield from sc.do(a, a.walk_to(b.x + sign(a.x - b.x) * 55 * S))
    sc.face(a, b)
    sc.face(b, a)
    a.pose = a.situ(f"chat:{b.cid}") or a.pose
    b.pose = b.situ(f"chat:{a.cid}") or b.pose
    ev = w.pick_event("talk", [a, b], "near")
    if ev:
        yield from run_event(sc, w, ev, [a, b])


def scene_hide_behind(sc, w, prey, guard, hunter):
    if random.random() < 0.5 and prey.line("hide_ask"):
        prey.say_line("hide_ask")
    else:
        guard.say_line("hide_call")
    guard.pose = "stand"
    yield from sc.do(prey, prey.walk_to(guard.x - guard.facing * 9 * S, speed=230, pose="run"))
    if prey.held or guard.held:
        return
    yield from sc.wait(guard.say_line("hide_accept"))
    prey.hide_mode = "behind"
    prey.pose = prey.situ(f"protected_hidden:{guard.cid}") or "stand"
    guard.pose = guard.situ(f"protect_hide:{prey.cid}") or "whistle"
    start, asked, answered = w.now, None, False
    while w.now - start < 16:
        if prey.hide_mode != "behind" or prey.held:
            break
        prey.x, prey.y, prey.facing = guard.x - guard.facing * 9 * S, guard.y, guard.facing
        if asked is None and hunter.scanning and abs(hunter.x - guard.x) < 150 * S:
            asked = w.now
            hunter.say_line("hair_question")
        if asked is not None and not answered and w.now - asked > 2.4:
            answered = True
            guard.say_line("hair_reply")
        if w.now - start > 4 and not hunter.scanning and (asked is None or answered):
            break
        yield
    prey.hide_mode, prey.pose, guard.pose = None, "stand", "stand"
    yield from sc.wait(1)
    yield from sc.do(prey, prey.walk_to(guard.x - guard.facing * 45 * S))
    sc.face(prey, guard)
    sc.face(guard, prey)
    yield from run_hook(sc, w, "after_hide", [prey, guard])


def defend(sc, w, guard, hunter, prey):
    trio = [guard, hunter, prey]
    if abs(guard.x - prey.x) > catalog.NEAR_DIST * S:
        ev = w.pick_event("defend", trio, "far")
        if ev:
            yield from run_event(sc, w, ev, trio)
    yield from sc.do(guard, guard.walk_to((prey.x + hunter.x) / 2, speed=240, pose="run"))
    sc.face(guard, hunter)
    sc.face(prey, guard)
    sc.face(hunter, guard)
    guard.pose = guard.situ(f"protect_defend:{prey.cid}") or "defend"
    prey.pose = prey.situ(f"protected_defended:{guard.cid}") or "stand"
    hunter.pose = hunter.situ(f"hunter_blocked:{prey.cid}") or "stand"
    ev = w.pick_event("defend", trio, "near")
    if ev:
        yield from run_event(sc, w, ev, trio)
    hunter.alert = False
    yield from sc.do(hunter, hunter.walk_to(hunter.x + sign(hunter.x - prey.x) * 300 * S))


def run_toward(c, tx, speed, pose, w):
    dx = tx - c.x
    c.facing, c.pose = sign(dx), pose
    c.x = w.clamp_x(c.x + sign(dx) * min(speed * S * w.dt, abs(dx)))


def icon_trick(sc, w, hunter, prey, hunter_run):
    prey.say_line("hide_icon")
    prey.hide_mode, prey.pose = "icon", "stand"
    while abs(hunter.x - prey.x) > 60 * S:
        if prey.held or prey.hide_mode != "icon":
            prey.hide_mode = None
            return "broken"
        if not hunter.held and not hunter.airborne:
            run_toward(hunter, prey.x, 220, hunter_run, w)
        yield
    hunter.pose = "stand"
    yield from sc.wait(1.2)
    if random.random() < 0.55:
        hunter.say_line("fooled_icon")
        yield from sc.beats((hunter, f"hunter_fooled:{prey.cid}"))
        yield from sc.wait(max(0.0, hunter.bubble_until - 0.6 - w.now))
        hunter.alert = False
        yield from sc.do(hunter, hunter.walk_to(hunter.x + sign(hunter.x - prey.x) * 320 * S))
        prey.hide_mode = None
        yield from sc.beats((prey, f"prey_fooled:{hunter.cid}"))
        if not prey.situ(f"prey_fooled:{hunter.cid}"):
            yield from sc.wait(prey.say_line("unhide"))
        return "fooled"
    hunter.say_line("seen_icon")
    prey.hide_mode = None
    yield from sc.beats((prey, f"prey_caught:{hunter.cid}"))
    yield from sc.wait(0.6)
    return "caught"


def scene_chase(sc, w):
    hunter, prey = sc.chars[:2]
    guards = w.protectors_of(prey)
    while hunter.bubble_until - 0.6 > w.now:
        yield
    caught, prey.seen_through = prey.seen_through, False
    prey.hide_mode = None
    hunter.alert = True
    sc.face(hunter, prey)
    sc.face(prey, hunter)
    hunter.say_line("alert")
    yield from sc.beats((hunter, f"hunter_noticed:{prey.cid}"),
                        (prey, f"prey_caught:{hunter.cid}" if caught else f"prey_noticed:{hunter.cid}"))
    yield from sc.wait(max(0.0, hunter.bubble_until - 0.6 - w.now))

    for g in guards:
        if abs(g.x - prey.x) < 220 * S and g.free and sc.lock(g):
            yield from defend(sc, w, g, hunter, prey)
            return

    yield from sc.wait(prey.say_line("flee"))
    prey_run = prey.situ(f"prey_chased:{hunter.cid}") or "run"
    hunter_run = hunter.situ(f"hunter_chase:{prey.cid}") or "run"
    end, jumped, tried_icon = w.now + 10, 0, not prey.data.get("can_disguise")
    ground = lambda c: not c.held and not c.airborne
    while True:
        if w.now > end:
            hunter.pose = prey.pose = "stand"
            hunter.say_line("lost")
            yield from sc.beats((hunter, f"hunter_lost:{prey.cid}"))
            yield from sc.wait(max(0.0, hunter.bubble_until - 0.6 - w.now))
            prey.pose = prey.anim_for("laugh")
            yield from sc.wait(prey.say_line("laugh") or 1.5)
            return
        for g in guards:
            if abs(prey.x - g.x) < 90 * S and ground(prey) and g.free and sc.lock(g):
                yield from defend(sc, w, g, hunter, prey)
                return
        gap = abs(prey.x - hunter.x)
        if not tried_icon and gap > 220 * S and ground(prey) and random.random() < w.dt * 1.2:
            tried_icon = True
            result = yield from icon_trick(sc, w, hunter, prey, hunter_run)
            if result == "fooled":
                return
            end = max(end, w.now + 5)
            continue
        d = sign(prey.x - hunter.x)
        if ground(prey):
            nx = prey.x + d * 230 * S * w.dt
            if nx != w.clamp_x(nx):
                if w.now - jumped > 1.2:
                    jumped = w.now
                    prey.platform = None
                    prey.vy, prey.vx = -950 * S, -d * 430 * S
                    prey.say_line("jump")
            else:
                prey.x, prey.facing, prey.pose = nx, d, prey_run
        if ground(hunter):
            run_toward(hunter, prey.x, 250, hunter_run, w)
        if gap < 40 * S and abs(prey.y - hunter.y) < 30 * S and ground(prey) and ground(hunter):
            break
        yield

    mx = (prey.x + hunter.x) / 2
    prey.pose = hunter.pose = "incloud"
    w.add_cloud(mx, 3.2, (prey.color, hunter.color))
    yield from sc.wait(3.2)
    side = random.choice((-1, 1))
    prey.x, hunter.x = w.clamp_x(mx - side * 32 * S), w.clamp_x(mx + side * 32 * S)
    prey.pose = hunter.pose = "stand"
    sc.face(prey, hunter)
    sc.face(hunter, prey)

    guard = next((g for g in guards if g.free), None)
    if guard and random.random() < 0.55 and sc.lock(guard):
        guard.say_line("stop")
        yield from sc.do(guard, guard.walk_to(mx, speed=260, pose="run"))
        sc.face(guard, hunter)
        guard.pose = guard.situ(f"protect_defend:{prey.cid}") or "defend"
        hunter.pose = hunter.situ(f"hunter_blocked:{prey.cid}") or "stand"
        yield from run_hook(sc, w, "break_fight", [guard, hunter, prey])
        guard.pose = "stand"
    elif random.random() < 0.5:
        hunter.pose = "knocked"
        hunter.alert = False
        yield from run_hook(sc, w, "prey_wins", [prey, hunter])
        yield from sc.wait(1.5)
        hunter.pose = "stand"
        yield from sc.wait(hunter.say_line("reboot"))
    else:
        prey.caged = True
        yield from run_hook(sc, w, "hunter_wins", [hunter, prey])
        yield from sc.wait(1)
        prey.pose = prey.anim_for("laugh")
        prey.glitch(1.5)
        yield from sc.wait(prey.say_line("break_out") or 1.5)
        prey.caged = False
        for _ in range(10):
            w.add_particle(prey.x + random.uniform(-25, 25) * S, prey.y - random.uniform(0.1, 1) * prey.top(),
                           random.choice("▪▫■"), "#5cf2ff", size=9, life=1)
    hunter.alert = False
    yield from sc.do(hunter, hunter.walk_to(hunter.x + sign(hunter.x - prey.x) * 250 * S))


class Director:
    def __init__(self, world):
        self.w = world
        self.scenes = []
        self.pending = []

    def request(self, fn, chars, force=False):
        self.pending.append((fn, list(chars), force))

    def cancel(self, chars):
        for item in list(self.scenes):
            if any(c in item[0].chars for c in chars):
                self.scenes.remove(item)
                item[1].close()

    def _run(self, sc, fn):
        try:
            yield from fn(sc, self.w)
        finally:
            sc.release()

    def process(self):
        pending, self.pending = self.pending, []
        for fn, chars, force in pending:
            chars = [c for c in chars if c in self.w.chars]
            if not chars or any(c.held for c in chars):
                continue
            if any(c.busy for c in chars):
                if not force:
                    continue
                self.cancel(chars)
            sc = Scene(self.w)
            for c in chars:
                sc.lock(c)
            self.scenes.append((sc, self._run(sc, fn)))
        for item in list(self.scenes):
            try:
                next(item[1])
            except StopIteration:
                self.scenes.remove(item)
            except Exception:
                traceback.print_exc()
                if item in self.scenes:
                    self.scenes.remove(item)


class World:
    def __init__(self):
        global S
        self.settings = store.load_settings()
        own_fonts = fonts.load()
        self.root = root = tk.Tk()
        root.title("Desktop Pets")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", KEY)
        root.config(bg=KEY)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        l, t, r, b = work_area(root)
        h = b if b < sh else sh - 1
        root.geometry(f"{sw}x{h}+0+0")
        S = max(1.0, root.winfo_fpixels("1i") / 96) * float(self.settings.get("size", 1.15) or 1.15)
        self.left, self.right = l, r
        self.ground = h - 4 * S
        self.cv = tk.Canvas(root, width=sw, height=h, bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self.now = self.last = time.monotonic()
        self.fps = max(10, min(60, int(self.settings.get("fps", 30) or 30)))
        self.dt = 1 / self.fps
        self.particles, self.cracks, self.clouds = [], [], []
        self.director = Director(self)
        self.chars, self.by_key, self.events, self.rels = [], {}, [], []
        self.event_cd, self.event_near = {}, {}
        self.next_react = 0
        self.drag = None
        self.fight_sprites = None
        self.platforms = []
        self.visible = True
        self._bubble_cache = {}
        self._measure = {}
        families = set(tkfont.families(root))
        have = lambda *names: next((n for n in names if n and n in families), "Segoe UI")
        self.font_main = have(own_fonts["main"], "Comic Sans MS", "Ink Free")
        self.font_shout = have(own_fonts["shout"], own_fonts["main"], "Comic Sans MS", "Impact")
        self.load_data()

        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="Покормить всех", command=self.feed)
        self.menu.add_command(label="Запустить проверку (охотники)", command=self.force_scan)
        self.act_menu = tk.Menu(self.menu, tearoff=0, postcommand=self.fill_act_menu)
        self.menu.add_cascade(label="Действия", menu=self.act_menu)
        self.anim_menu = tk.Menu(self.menu, tearoff=0, postcommand=self.fill_anim_menu)
        self.menu.add_cascade(label="Свои анимации", menu=self.anim_menu)
        self.event_menu = tk.Menu(self.menu, tearoff=0, postcommand=self.fill_event_menu)
        self.menu.add_cascade(label="События", menu=self.event_menu)
        self.menu.add_separator()
        self.desktop_only_var = tk.BooleanVar(value=bool(self.settings.get("desktop_only", True)))
        self.menu.add_checkbutton(label="Только на рабочем столе (прятаться, когда открыта программа)",
                                  variable=self.desktop_only_var, command=self.toggle_desktop_only)
        self.autostart_var = tk.BooleanVar(value=self.autostart_enabled())
        self.menu.add_checkbutton(label="Запускаться вместе с Windows", variable=self.autostart_var,
                                  command=self.toggle_autostart)
        self.menu.add_command(label="Перезагрузить всё из data", command=self.reload_all)
        self.menu.add_command(label="Выход", command=root.destroy)

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Button-3>", self.on_menu)

        if self.settings.get("intro", True):
            root.after(1500, lambda: self.director.request(scene_intro, self.chars))
        root.after(3000, self.keep_on_top)
        root.after(2000, self.watch_data)
        root.after(500, self.watch_play_file)
        root.after(200, self.refresh_icons)
        root.after(300, self.watch_foreground)
        self.tick()

    def load_data(self):
        self.data_sig = self.pending_sig = SP.signature()
        chars = store.load_all()
        width = self.right - self.left
        keep = []
        for i, (cid, data) in enumerate(chars.items()):
            old = self.by_key.get(cid)
            body = BODIES.get(data.get("drawing"), SimpleBody)
            if old is not None and type(old) is body:
                old.apply(data)
                keep.append(old)
                continue
            x = old.x if old else self.left + width * (0.2 + 0.65 * (i + 0.5) / max(1, len(chars)))
            c = body(self, cid, data, x)
            if old is not None:
                self.director.cancel([old])
                c.y, c.facing = old.y, old.facing
            keep.append(c)
        gone = [c for c in self.chars if c not in keep]
        if gone:
            self.director.cancel(gone)
        self.chars = keep
        self.by_key = {c.cid: c for c in self.chars}
        self.events = store.load_events()
        self.rels = []
        for c in self.chars:
            for r in c.data.get("relations", []):
                other = self.by_key.get(r.get("target"))
                if other is not None and other is not c and r.get("type") in catalog.RELATIONS:
                    self.rels.append((c, r["type"], other, float(r.get("weight", 1) or 1)))
        errors = []
        for c in self.chars:
            c.sprites = SpriteSet(c.cid)
            errors += c.sprites.errors
        self.fight_sprites = SpriteSet("fight", os.path.join(paths.EFFECTS, "fight"))
        errors += self.fight_sprites.errors
        for e in errors:
            print("Не загрузилось:", e, file=sys.stderr)
        return errors

    def reload_all(self):
        errors = self.load_data()
        if self.chars:
            msg = f"Подгрузил: персонажей {len(self.chars)}, событий {len(self.events)}."
            if errors:
                msg += f" Не открылось файлов: {len(errors)} (подробности в crash.log)."
            self.chars[0].say(msg, dur=5)

    def frame_count(self):
        sets = [c.sprites for c in self.chars] + [self.fight_sprites]
        return sum(a.total_frames() for s in sets if s is not None for a in s.anims.values())

    def watch_data(self):
        try:
            sig = SP.signature()
            if sig != self.data_sig:
                if sig == self.pending_sig:
                    before = self.frame_count()
                    self.load_data()
                    if self.frame_count() != before and self.chars:
                        pick(self.chars).say("О, новые рисунки.", dur=2.5)
                else:
                    self.pending_sig = sig
        except Exception:
            traceback.print_exc()
        finally:
            self.root.after(2000, self.watch_data)

    def watch_play_file(self):
        try:
            if os.path.exists(paths.PLAY_FILE):
                with open(paths.PLAY_FILE, encoding="utf-8") as f:
                    kind, _, rest = f.read().strip().partition("\n")
                os.remove(paths.PLAY_FILE)
                if self.data_sig != SP.signature():
                    self.load_data()
                kind = kind.strip()
                if kind == "event":
                    ev = next((e for e in self.events if e.get("id") == rest.strip()), None)
                    if ev:
                        self.start_event(ev, force=True)
                elif kind == "fight":
                    self.add_cloud((self.left + self.right) / 2, 3)
                elif kind in self.by_key:
                    self.play_now(self.by_key[kind], rest.strip())
        except Exception:
            traceback.print_exc()
        finally:
            self.root.after(500, self.watch_play_file)

    def relations_of(self, c):
        return [(kind, b, wt) for a, kind, b, wt in self.rels if a is c]

    def hunters_of(self, c):
        return [a for a, kind, b, _ in self.rels if kind == "hunts" and b is c]

    def preys_of(self, c):
        return [b for a, kind, b, _ in self.rels if kind == "hunts" and a is c]

    def protectors_of(self, c):
        return [a for a, kind, b, _ in self.rels if kind == "protects" and b is c]

    def related(self, a, b, kind):
        return any(x is a and k == kind and y is b for x, k, y, _ in self.rels)

    def pick_event(self, hook, chars, state):
        ids = {c.cid for c in chars}
        hour = time.localtime().tm_hour
        options = [e for e in self.events
                   if e.get("hook") == hook and e.get("who") and set(e["who"]) <= ids
                   and e.get("distance", "any") in ("any", state)
                   and SP.time_ok(e.get("time", "any"), hour)]
        return pick(options) if options else None

    def event_chars(self, ev):
        chars = [self.by_key.get(cid) for cid in ev.get("who", [])]
        return None if not chars or None in chars else chars

    def start_event(self, ev, force=False):
        chars = self.event_chars(ev)
        if chars:
            self.director.request(lambda sc, w: scene_event(sc, w, ev, chars), chars, force=force)
            return True
        return False

    def auto_events(self):
        hour = time.localtime().tm_hour
        for ev in self.events:
            hook = ev.get("hook")
            if hook not in ("random", "meet", "apart") or self.now < self.event_cd.get(ev.get("id"), 0):
                continue
            chars = self.event_chars(ev)
            if not chars or not SP.time_ok(ev.get("time", "any"), hour):
                continue
            state = distance_state(chars)
            was_near, self.event_near[ev.get("id")] = self.event_near.get(ev.get("id")), state == "near"
            if not all(c.free and not c.hide_mode for c in chars):
                continue
            freq = SP.FREQ.get(ev.get("freq"), SP.FREQ["sometimes"])[1]
            if hook == "meet":
                ok = state == "near" and was_near is False and random.random() < 0.6 * min(1.0, freq)
            elif hook == "apart":
                ok = state == "far" and random.random() < 0.006 * freq
            else:
                ok = ev.get("distance", "any") in ("any", "near", state) and random.random() < 0.003 * freq
            if ok:
                self.event_cd[ev.get("id")] = self.now + float(ev.get("cooldown", 30) or 0)
                self.start_event(ev)

    def clamp_x(self, x):
        return min(max(x, self.left + 30 * S), self.right - 30 * S)

    def pointer(self):
        return self.root.winfo_pointerxy()

    def add_particle(self, x, y, text, color, size=10, font="Segoe UI", life=2.0):
        self.particles.append(dict(x=x, y=y, text=text, color=color, size=size, font=font,
                                   until=self.now + life, vx=random.uniform(-10, 10) * S, vy=-35 * S))

    def add_crack(self, x, y):
        self.cracks.append(dict(x=x, y=y, until=self.now + 7, seed=random.random()))

    def add_cloud(self, x, dur, colors=("#ffe3d3", "#2fa86b")):
        self.clouds.append(dict(x=x, until=self.now + dur, seed=random.random(), colors=colors))

    def boxed_text(self, x, y, text, fg, bg, font):
        tid = self.cv.create_text(x, y, text=text, fill=fg, font=font, anchor="s")
        x0, y0, x1, y1 = self.cv.bbox(tid)
        rid = self.cv.create_rectangle(x0 - 3, y0 - 1, x1 + 3, y1 + 1, fill=bg, width=0)
        self.cv.tag_raise(tid, rid)

    def protected(self, prey):
        if prey.hide_mode == "behind":
            return True
        for g in self.protectors_of(prey):
            guard = {"defend", "whistle"}
            if g.sprites is not None:
                guard |= set(g.sprites.with_trigger("protect_defend") + g.sprites.with_trigger("protect_hide"))
            if abs(g.x - prey.x) < 110 * S and g.pose in guard:
                return True
        return False

    def beam_check(self, hunter):
        for prey in self.preys_of(hunter):
            if prey.busy or prey.held or prey.airborne or self.protected(prey):
                continue
            dx = (prey.x - hunter.x) * hunter.facing
            if not 0 < dx < BEAM * S or abs(prey.y - hunter.y) > 140 * S:
                continue
            mode = prey.hide_mode
            if mode is None:
                return "hit", prey
            key = (prey.cid, mode)
            if key in hunter.checked:
                continue
            hunter.checked.add(key)
            if random.random() < {"icon": 0.3, "flat": 0.4}.get(mode, 0.1):
                hunter.say_line("seen_" + mode)
                prey.seen_through = True
                return "hit", prey
            hunter.say_line("fooled_" + mode)
            prey.fooled = True
            return "fooled", prey
        return None, None

    def refresh_icons(self):
        try:
            rects = desktop_icons.icon_rects() if self.visible else None
        except Exception:
            rects = []
        if rects is not None:
            plats = []
            for l, t, r, b in rects:
                cx, half = (l + r) / 2, min(r - l, b - t) * 0.38
                plats.append((cx - half, t + (b - t) * 0.12, cx + half, (l, t, r, b)))
            self.platforms = plats
            by_rect = {p[3]: p for p in plats}
            for c in self.chars:
                if c.platform:
                    c.platform = by_rect.get(c.platform[3])
        self.root.after(3000, self.refresh_icons)

    def icon_collision(self, c, prev_y):
        for p in self.platforms:
            x0, top, x1, (l, t, r, b) = p
            if c.vy > 0 and x0 - 6 <= c.x <= x1 + 6 and prev_y <= top <= c.y:
                return "land", p
            if abs(c.vx) > 250 * S and l <= c.x <= r and t <= c.y - c.top() * 0.5 <= b:
                c.x = l - 2 if c.vx > 0 else r + 2
                c.vx = -c.vx * 0.35
                return "bump", p
        return None

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    RUN_NAME = "DesktopPets_" + os.path.basename(paths.BASE)

    def autostart_enabled(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                winreg.QueryValueEx(k, self.RUN_NAME)
            return True
        except OSError:
            return False

    def say_any(self, text, dur=3):
        if self.chars:
            self.chars[0].say(text, dur=dur)

    def toggle_autostart(self):
        on = self.autostart_var.get()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if on:
                    if paths.FROZEN:
                        cmd = f'"{sys.executable}"'
                    else:
                        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                        cmd = f'"{exe if os.path.exists(exe) else sys.executable}" "{os.path.abspath(__file__)}"'
                    winreg.SetValueEx(k, self.RUN_NAME, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(k, self.RUN_NAME)
                    except OSError:
                        pass
            self.say_any("Теперь буду запускаться вместе с Windows." if on else "Ок, автозапуск выключен.")
        except OSError as e:
            self.autostart_var.set(self.autostart_enabled())
            self.say_any(f"Не получилось поменять автозапуск: {e}", 4)

    def check_drop(self, c):
        near = [o for o in self.chars
                if o is not c and not o.held and o.hide_mode != "behind" and abs(o.x - c.x) < 130 * S]
        for o in near:
            for hunter, prey in ((c, o), (o, c)):
                if self.related(hunter, prey, "hunts"):
                    self.director.request(scene_chase, [hunter, prey], force=True)
                    return True
        ids = {c.cid} | {o.cid for o in near}
        options = [e for e in self.events if e.get("hook") == "drop" and c.cid in e.get("who", [])
                   and set(e["who"]) <= ids]
        if options:
            return self.start_event(pick(options), force=True)
        for o in near:
            for a, b in ((c, o), (o, c)):
                if self.related(a, b, "pesters"):
                    self.director.request(scene_pester, [a, b], force=True)
                    return True
            for a, b in ((c, o), (o, c)):
                if self.related(a, b, "chats"):
                    self.director.request(scene_talk, [a, b], force=True)
                    return True
        return False

    def feed(self):
        self.director.request(scene_meal, self.chars, force=True)

    def force_scan(self):
        for c in self.chars:
            if self.preys_of(c) or c.data.get("actions", {}).get("patrol"):
                self.force(c, c.act_patrol)

    def force(self, c, fn):
        if c.held:
            return
        self.director.cancel([c])
        c.pose = "stand"
        c.set_action(fn())

    def play_now(self, c, name):
        if c.held:
            return
        self.director.cancel([c])
        c.hide_mode = None
        c.pose = "stand"
        c.custom_cd.pop(name, None)
        if c.sprites is not None and name in c.sprites.anims:
            c.set_action(c.play_custom(name))
        else:
            c.set_action(c.wait(2.5, pose=name))

    def fill_act_menu(self):
        m = self.act_menu
        m.delete(0, "end")
        for c in self.chars:
            acts = [(code, wt) for code, wt in c.data.get("actions", {}).items() if wt and code in catalog.ACTIONS]
            if not acts:
                continue
            m.add_command(label=c.name, state="disabled")
            for code, _ in acts:
                m.add_command(label="    " + catalog.ACTIONS[code][0],
                              command=lambda c=c, code=code: self.force(c, getattr(c, "act_" + code)))
        if not self.chars:
            m.add_command(label="(персонажей нет — добавь в редакторе)", state="disabled")

    def fill_anim_menu(self):
        m = self.anim_menu
        m.delete(0, "end")
        empty = True
        for c in self.chars:
            names = sorted(c.sprites.customs) if c.sprites is not None else []
            if not names:
                continue
            empty = False
            m.add_command(label=c.name, state="disabled")
            for n in names:
                m.add_command(label="    " + n, command=lambda c=c, n=n: self.play_now(c, n))
        if empty:
            m.add_command(label="(пока нет — добавь в редакторе)", state="disabled")

    def fill_event_menu(self):
        m = self.event_menu
        m.delete(0, "end")
        menu_events = [e for e in self.events if e.get("hook") == "menu" and self.event_chars(e)]
        for e in menu_events:
            m.add_command(label=e.get("name") or e.get("id"), command=lambda e=e: self.start_event(e, force=True))
        if not menu_events:
            m.add_command(label="(нет событий «Только вручную» — добавь в редакторе)", state="disabled")

    def on_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def hit(self, x, y):
        for c in reversed(self.chars):
            hb = c.hitbox()
            if hb and hb[0] <= x <= hb[2] and hb[1] <= y <= hb[3]:
                return c
        return None

    def on_press(self, e):
        c = self.hit(e.x, e.y)
        self.drag = None
        if c:
            self.drag = dict(c=c, ox=c.x - e.x, oy=c.y - e.y, sx=e.x, sy=e.y, moved=False,
                             hist=[(time.monotonic(), e.x, e.y)])

    def pick_up(self, c):
        c.held, c.vx, c.vy = True, 0.0, 0.0
        c.platform = None
        if not c.busy:
            c.set_action(None)
            c.pose = "stand"
        if c.hide_mode in ("icon", "flat") and not c.busy:
            c.hide_mode = None
        for a, kind, prey, _ in self.rels:
            if a is c and kind == "protects" and prey.hide_mode == "behind":
                prey.hide_mode = None
                prey.say_line("exposed")
        c.say_line("held")

    def on_motion(self, e):
        d = self.drag
        if not d:
            return
        c = d["c"]
        if not d["moved"] and abs(e.x - d["sx"]) + abs(e.y - d["sy"]) > 6:
            d["moved"] = True
            self.pick_up(c)
        if d["moved"]:
            c.x = self.clamp_x(e.x + d["ox"])
            c.y = min(self.ground, e.y + d["oy"])
            d["hist"] = (d["hist"] + [(time.monotonic(), e.x, e.y)])[-8:]

    def on_release(self, e):
        d, self.drag = self.drag, None
        if not d:
            return
        c = d["c"]
        if not d["moved"]:
            clicks = [ev for ev in self.events if ev.get("hook") == "click" and (ev.get("who") or [None])[0] == c.cid
                      and self.event_chars(ev) and self.now >= self.event_cd.get(ev.get("id"), 0)]
            if clicks and c.free and random.random() < 0.7:
                self.start_event(pick(clicks), force=True)
                return
            options = c.customs("click") if c.free and c.hide_mode is None else []
            if options and random.random() < 0.7:
                name, info = pick(options)
                if not info.get("say"):
                    c.say_line("poke")
                c.set_action(c.play_custom(name))
                return
            c.say_line("poke")
            if c.free and c.pose not in ("sleep", "code", "read", "knocked") and c.hide_mode is None:
                c.vy = -380 * S
            return
        c.held = False
        now = time.monotonic()
        t1, x1, y1 = d["hist"][-1]
        old = [h for h in d["hist"] if t1 - h[0] >= 0.04] or d["hist"][:1]
        t0, x0, y0 = old[-1]
        if t1 > t0 and now - t1 < 0.1:
            vx, vy = (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)
            sp = math.hypot(vx, vy)
            lim = 2600 * S
            if sp > lim:
                vx, vy = vx * lim / sp, vy * lim / sp
            c.vx, c.vy = vx, vy
        c.drop_check = True
        if not c.airborne:
            c.y, c.vy = self.ground, 0.0
            c.on_land(0)

    def keep_on_top(self):
        try:
            if self.visible:
                self.root.attributes("-topmost", True)
                self.root.lift()
        finally:
            self.root.after(3000, self.keep_on_top)

    def desktop_active(self):
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        fg = user32.GetForegroundWindow()
        if not fg:
            return True
        fg = user32.GetAncestor(fg, 2) or fg
        mine = user32.GetAncestor(ctypes.c_void_p(self.root.winfo_id()), 2)
        if fg == mine:
            return True
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ctypes.c_void_p(fg), name, 256)
        return name.value in DESKTOP_CLASSES

    def set_visible(self, show):
        if show == self.visible:
            return
        self.visible = show
        if show:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
        else:
            if self.drag:
                self.drag["c"].held = False
                self.drag = None
            self.root.withdraw()

    def watch_foreground(self):
        try:
            self.set_visible(not self.desktop_only_var.get() or self.desktop_active())
        except Exception:
            traceback.print_exc()
        finally:
            self.root.after(300, self.watch_foreground)

    def toggle_desktop_only(self):
        settings = store.load_settings()
        settings["desktop_only"] = self.desktop_only_var.get()
        store.save_settings(settings)
        self.say_any("Буду показываться только на рабочем столе." if settings["desktop_only"]
                     else "Ок, буду поверх всех окон.")

    def reactions(self):
        if self.now < self.next_react:
            return
        self.next_react = self.now + 0.5
        self.near_customs()
        self.react_customs()
        self.auto_events()
        for hunter, kind, prey, _ in self.rels:
            if kind != "hunts":
                continue
            if not (hunter.scanning and prey.hide_mode is None and prey.free and self.now > prey.hide_cd):
                continue
            guards = [g for g in self.protectors_of(prey) if g.free]
            if not guards and not prey.data.get("can_disguise"):
                continue
            dx = prey.x - hunter.x
            if abs(dx) < 480 * S and dx * hunter.facing > 0:
                prey.hide_cd = self.now + 3
                if random.random() < 0.55:
                    prey.hide_cd = self.now + 10
                    guard = guards[0] if guards and (random.random() < 0.5 or not prey.data.get("can_disguise")) else None
                    prey.set_action(prey.react_then_hide(hunter, guard))

    def near_customs(self):
        for c in self.chars:
            customs = c.sprites.customs if c.sprites is not None else {}
            if not customs or not c.free or c.hide_mode or c.pose in customs:
                continue
            for o in self.chars:
                if o is c or o.hide_mode == "behind":
                    continue
                near = abs(o.x - c.x) <= 160 * S and abs(o.y - c.y) <= 120 * S
                if near:
                    options, chance = c.customs(f"near:{o.cid}", "near:any"), 0.1
                elif abs(o.x - c.x) > catalog.NEAR_DIST * S * 1.5:
                    options, chance = c.customs(f"far:{o.cid}"), 0.02
                else:
                    continue
                if options and random.random() < chance:
                    c.facing = sign(o.x - c.x)
                    c.set_action(c.play_custom(pick(options)[0]))
                    break

    def react_customs(self):
        for c in self.chars:
            if c.sprites is None or not c.sprites.customs or not c.free or c.hide_mode:
                continue
            for o in self.chars:
                if o is c or self.now - o._pose_t0 > 0.8:
                    continue
                name = o.anim_name()
                if c.reacted.get(o.cid) == (name, o._pose_t0):
                    continue
                c.reacted[o.cid] = (name, o._pose_t0)
                options = c.customs(f"react:{o.cid}:{name}")
                if options and random.random() < 0.75:
                    c.facing = sign(o.x - c.x)
                    c.set_action(c.play_custom(pick(options)[0]))
                    break

    def tick(self):
        try:
            t = time.monotonic()
            self.dt = min(0.05, t - self.last)
            self.last = self.now = t
            for c in self.chars:
                c.update()
            self.reactions()
            self.director.process()
            for p in self.particles:
                p["x"] += p["vx"] * self.dt
                p["y"] += p["vy"] * self.dt
            self.particles = [p for p in self.particles if p["until"] > t]
            self.cracks = [c for c in self.cracks if c["until"] > t]
            self.clouds = [c for c in self.clouds if c["until"] > t]
            self.draw()
        except Exception:
            traceback.print_exc()
        self.root.after(int(1000 / self.fps) if self.visible else 100, self.tick)

    def draw(self):
        cv = self.cv
        cv.delete("dyn")
        if not self.visible:
            if self._bubble_cache:
                cv.delete("bub")
                self._bubble_cache.clear()
            return
        for cr in self.cracks:
            rnd = random.Random(cr["seed"])
            for _ in range(6):
                pts = [cr["x"], cr["y"]]
                ang = rnd.uniform(0, math.tau)
                x, y = cr["x"], cr["y"]
                for _ in range(3):
                    ang += rnd.uniform(-0.6, 0.6)
                    ln = rnd.uniform(8, 18) * S
                    x, y = x + math.cos(ang) * ln, y + math.sin(ang) * ln
                    pts += [x, y]
                cv.create_line(pts, fill="#e8f4ff", width=1.6 * S)
        for c in self.chars:
            c.render()
        for cl in self.clouds:
            self.draw_cloud(cl)
        for p in self.particles:
            cv.create_text(p["x"], p["y"], text=p["text"], fill=p["color"], font=(p["font"], p["size"], "bold"))
        for c in self.chars:
            if c.label and not (c.bubble and self.now < c.bubble_until):
                hb = c.hitbox()
                if hb:
                    self.boxed_text(c.x, hb[1] - 4 * S, c.label, "#5cf2ff", "#0d1b2a", ("Consolas", 8))
        cv.addtag_all("dyn")
        cv.dtag("bub", "dyn")
        self.draw_bubbles()

    def draw_cloud(self, cl):
        cv, x, y = self.cv, cl["x"], self.ground
        cy = y - 40 * S
        anim = self.fight_sprites.anims.get("cloud") if self.fight_sprites else None
        if anim:
            cv.create_image(x, y, image=anim.frame(self.now, 1), anchor="s")
            return self.draw_fight_words(cl, x, cy)
        for i in range(8):
            ang = i / 8 * math.tau + self.now * 3
            cv.create_oval(x + math.cos(ang) * 30 * S - 22 * S, cy + math.sin(ang) * 18 * S - 20 * S,
                           x + math.cos(ang) * 30 * S + 22 * S, cy + math.sin(ang) * 18 * S + 20 * S,
                           fill="#e9e9e9", outline="#9a9a9a", width=1.5 * S)
        cv.create_oval(x - 34 * S, cy - 26 * S, x + 34 * S, cy + 26 * S, fill="#f4f4f4", width=0)
        a, b = cl.get("colors", ("#ffe3d3", "#2fa86b"))
        for k in range(4):
            ang = random.uniform(0, math.tau)
            ln = random.uniform(40, 56) * S
            ex, ey = x + math.cos(ang) * ln, cy + math.sin(ang) * ln * 0.7
            color = (a, b, shade(a, 0.7), shade(b, 0.7))[k]
            cv.create_line(x + math.cos(ang) * 28 * S, cy + math.sin(ang) * 18 * S, ex, ey, fill=color, width=4 * S,
                           capstyle=tk.ROUND)
            cv.create_oval(ex - 3 * S, ey - 3 * S, ex + 3 * S, ey + 3 * S, fill=color, width=0)
        self.draw_fight_words(cl, x, cy)

    def draw_fight_words(self, cl, x, cy):
        cv = self.cv
        rnd = random.Random(int(self.now * 4) + cl["seed"])
        for _ in range(2):
            word = rnd.choice(["БАМ!", "ПОЖ!", "ДЫЩ!", "ХРЯСЬ!", "КУСЬ!", "0xDEAD!", "БДЫЩ!"])
            wx, wy = x + rnd.uniform(-60, 60) * S, cy + rnd.uniform(-60, -20) * S
            cv.create_text(wx + 2, wy + 2, text=word, fill="#222222", font=("Impact", 14))
            cv.create_text(wx, wy, text=word, fill="#ffd23f", font=("Impact", 14))

    def bubble_kind(self, c, text):
        if c.data.get("bubble") == "robot":
            return "robot"
        t = text.strip()
        letters = [ch for ch in t if ch.isalpha()]
        if t.startswith(("...", "…", "*", "(", "Тсс", "тсс")) or c.pose == c.anim_for("sleep"):
            return "whisper"
        if len(letters) > 2 and sum(ch.isupper() for ch in letters) / len(letters) > 0.6:
            return "shout"
        return "speech"

    def text_size(self, text, font, wrap):
        key = (text, font, wrap)
        if key not in self._measure:
            tid = self.cv.create_text(0, 0, text=text, font=font, width=wrap, justify="center")
            x0, y0, x1, y1 = self.cv.bbox(tid)
            self.cv.delete(tid)
            if len(self._measure) > 400:
                self._measure.clear()
            self._measure[key] = (x1 - x0, y1 - y0)
        return self._measure[key]

    def draw_bubbles(self):
        cv = self.cv
        placed, alive = [], set()
        for c in self.chars:
            if not (c.bubble and self.now < c.bubble_until):
                continue
            text = c.bubble
            kind = self.bubble_kind(c, text)
            if self.settings.get("caps", True):
                text = text.upper()
            font = {"speech": (self.font_main, 10, "bold"), "shout": (self.font_shout, 12, "bold"),
                    "whisper": (self.font_main, 9, "normal"), "robot": ("Consolas", 10, "bold")}[kind]
            wrap = int((150 if kind != "robot" else 190) * S)
            tw, th = self.text_size(text, font, wrap)
            hb = c.hitbox() or (c.x - 10, c.y - c.h * S, c.x + 10, c.y)
            tipx, tipy = c.x, hb[1] - 2 * S
            k = {"speech": (1.25, 1.4), "shout": (1.45, 1.75), "whisper": (1.25, 1.4), "robot": (1.0, 1.0)}[kind]
            pad = (11 if kind == "robot" else 9) * S
            rx, ry = tw / 2 * k[0] + pad, th / 2 * k[1] + pad
            cx = min(max(tipx, self.left + rx + 4), self.right - rx - 4)
            cy = max(tipy - 16 * S - ry, ry + 4)
            moved = True
            while moved:
                moved = False
                for bx0, by0, bx1, by1 in placed:
                    if cx - rx < bx1 and cx + rx > bx0 and cy - ry < by1 and cy + ry > by0:
                        cy = by0 - 6 - ry
                        moved = True
            placed.append((cx - rx, cy - ry, cx + rx, cy + ry))
            key = (text, kind, round(cx), round(cy), round(tipx), round(tipy))
            alive.add(c.cid)
            cached = self._bubble_cache.get(c.cid)
            if cached and cached[0] == key:
                continue
            tag = f"bub_{c.cid}"
            cv.delete(tag)
            before = set(cv.find_all())
            sw = 2.4 * S
            {"speech": self.bubble_speech, "shout": self.bubble_shout,
             "whisper": self.bubble_whisper, "robot": self.bubble_robot}[kind](cx, cy, rx, ry, tipx, tipy, sw, text)
            cv.create_text(cx, cy, text=text, fill="#0b2a3a" if kind == "robot" else INK, font=font,
                           width=wrap, justify="center")
            for item in set(cv.find_all()) - before:
                cv.addtag_withtag(tag, item)
                cv.addtag_withtag("bub", item)
            self._bubble_cache[c.cid] = (key, tag)
        for cid in list(self._bubble_cache):
            if cid not in alive:
                cv.delete(self._bubble_cache.pop(cid)[1])
        cv.tag_raise("bub")

    @staticmethod
    def tail(cx, cy, rx, ry, tipx, tipy, width, curve=0.22):
        ang = math.atan2(tipy - cy, tipx - cx)
        bx, by = cx + math.cos(ang) * rx * 0.62, cy + math.sin(ang) * ry * 0.62
        px, py = -math.sin(ang), math.cos(ang)
        lx, ly = bx + px * width, by + py * width
        qx, qy = bx - px * width, by - py * width
        length = math.hypot(tipx - bx, tipy - by)
        ox, oy = px * length * curve, py * length * curve
        ml = (lx + (tipx - lx) * 0.55 + ox, ly + (tipy - ly) * 0.55 + oy)
        mr = (qx + (tipx - qx) * 0.6 + ox * 0.7, qy + (tipy - qy) * 0.6 + oy * 0.7)
        return [lx, ly, *ml, tipx, tipy, tipx, tipy, tipx, tipy, *mr, qx, qy]

    def bubble_speech(self, cx, cy, rx, ry, tipx, tipy, sw, _text):
        cv = self.cv
        t = self.tail(cx, cy, rx, ry, tipx, tipy, min(rx, ry) * 0.3)
        cv.create_polygon(t, fill=PAPER, outline=INK, width=sw * 2, smooth=True)
        cv.create_oval(cx - rx, cy - ry, cx + rx, cy + ry, fill=PAPER, outline=INK, width=sw)
        cv.create_polygon(t, fill=PAPER, outline="", smooth=True)

    def bubble_shout(self, cx, cy, rx, ry, tipx, tipy, sw, text):
        rnd = random.Random(text)
        n = 16 + int(rx / (30 * S))
        pts = []
        for i in range(2 * n):
            a = i / (2 * n) * math.tau
            r = (1.0 + rnd.uniform(0.08, 0.22)) if i % 2 == 0 else rnd.uniform(0.82, 0.9)
            pts.append([cx + math.cos(a) * rx * r, cy + math.sin(a) * ry * r])
        ang = math.atan2(tipy - cy, tipx - cx)
        best = min(range(0, 2 * n, 2), key=lambda i: abs((i / (2 * n) * math.tau - ang + math.pi) % math.tau - math.pi))
        pts[best] = [tipx, tipy]
        self.cv.create_polygon([v for p in pts for v in p], fill=PAPER, outline=INK, width=sw, joinstyle=tk.MITER)

    def dashed(self, pts, width, dash=7.0, gap=5.0):
        acc, on = 0.0, True
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            seg = math.hypot(x1 - x0, y1 - y0)
            pos = 0.0
            while pos < seg:
                step = min((dash if on else gap) * S - acc, seg - pos)
                a, b = pos / seg, (pos + step) / seg
                if on:
                    self.cv.create_line(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b,
                                        y0 + (y1 - y0) * b, fill=INK, width=width, capstyle=tk.ROUND)
                pos += step
                acc += step
                if acc >= (dash if on else gap) * S - 1e-6:
                    acc, on = 0.0, not on

    def bubble_whisper(self, cx, cy, rx, ry, tipx, tipy, sw, _text):
        cv = self.cv
        ang = math.atan2(tipy - cy, tipx - cx)
        w = min(rx, ry) * 0.22
        bx, by = cx + math.cos(ang) * rx * 0.92, cy + math.sin(ang) * ry * 0.92
        px, py = -math.sin(ang), math.cos(ang)
        tail = [bx + px * w, by + py * w, tipx, tipy, bx - px * w, by - py * w]
        cv.create_polygon(tail, fill=PAPER, outline="")
        cv.create_oval(cx - rx, cy - ry, cx + rx, cy + ry, fill=PAPER, outline="")
        n = 72
        a0 = ang + math.atan2(w, rx)
        span = math.tau - 2 * math.atan2(w, rx)
        ring = [(cx + math.cos(a0 + span * i / n) * rx, cy + math.sin(a0 + span * i / n) * ry) for i in range(n + 1)]
        self.dashed(ring, sw * 0.8)
        self.dashed([(tail[0], tail[1]), (tipx, tipy), (tail[4], tail[5])], sw * 0.8, dash=5, gap=4)

    def bubble_robot(self, cx, cy, rx, ry, tipx, tipy, sw, _text):
        cv = self.cv
        cut = 7 * S
        x0, y0, x1, y1 = cx - rx, cy - ry, cx + rx, cy + ry
        bx = min(max(tipx, x0 + 14 * S), x1 - 14 * S)
        t = [bx - 7 * S, y1 - sw, tipx, tipy, bx + 7 * S, y1 - sw]
        cv.create_polygon(t, fill="#eefcff", outline=INK, width=sw * 2)
        cv.create_polygon(x0 + cut, y0, x1 - cut, y0, x1, y0 + cut, x1, y1 - cut, x1 - cut, y1,
                          x0 + cut, y1, x0, y1 - cut, x0, y0 + cut, fill="#eefcff", outline=INK, width=sw)
        cv.create_polygon(t, fill="#eefcff", outline="")
        cv.create_line(x0 + cut, y0 + 4 * S, x1 - cut, y0 + 4 * S, fill="#5cc8e0", width=1)


def main():
    if sys.stderr is None or sys.stdout is None:
        log = open(paths.LOG, "a", encoding="utf-8")
        sys.stderr = sys.stdout = log
    World().root.mainloop()


if __name__ == "__main__":
    main()
