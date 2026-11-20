import os
import struct
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icons")

COLORS = {"V": "#a66bff", "P": "#ff3d8b",
          "D": "#2c1a45", "O": "#1b1424", "W": "#ffffff", "K": "#2a2531"}

EDITOR = [
    "KKKKKKKKKKKKKKKK",
    "KWKKWKKWKKWKKWKK",
    "KKKKKKKKKKKKKKKK",
    "KPPPPPPPPPPPPPPK",
    "KPPPPWPPPPPPPPPK",
    "KPPPPWWPPPPPPPPK",
    "KPPPPWWWPPPPPPPK",
    "KPPPPWWWWPPPPPPK",
    "KPPPPWWWWPPPPPPK",
    "KPPPPWWWPPPPPPPK",
    "KPPPPWWPPPPPPPPK",
    "KPPPPWPPPPPPPPPK",
    "KPPPPPPPPPPPPPPK",
    "KKKKKKKKKKKKKKKK",
    "KWKKWKKWKKWKKWKK",
    "KKKKKKKKKKKKKKKK",
]


PETS = [
    "................",
    ".....VVVVVV.....",
    "...VVVVVVVVVV...",
    "..VVVVVVVVVVVV..",
    "..VVWWVVVVWWVV..",
    ".VVVWOVVVVWOVVV.",
    ".VVVWOVVVVWOVVV.",
    ".VVVVVVVVVVVVVV.",
    ".VVVVVVPPVVVVVV.",
    ".VVVVVVVVVVVVVV.",
    "..VVVVVVVVVVVV..",
    "..VVVVVVVVVVVV..",
    "...VVVVVVVVVV...",
    "....VV....VV....",
    "....DD....DD....",
    "................",
]


def make(grid, name):
    img = tk.PhotoImage(width=16, height=16)
    img.blank()
    for y, row in enumerate(grid):
        for x, ch in enumerate(row.ljust(16, ".")[:16]):
            if ch in COLORS:
                img.put(COLORS[ch], to=(x, y))
    big = tk.PhotoImage()
    big.tk.call(big, "copy", img, "-zoom", 16)
    png = os.path.join(OUT, name + ".png")
    big.write(png, format="png")
    data = open(png, "rb").read()
    header = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(data), 22)
    with open(os.path.join(OUT, name + ".ico"), "wb") as f:
        f.write(header + data)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    root = tk.Tk()
    make(EDITOR, "editor")
    make(PETS, "pets")
    root.destroy()
    print("ok")
