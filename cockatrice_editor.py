#!/usr/bin/env python3
"""
Cockatrice Card Editor
Three-panel GUI editor for Cockatrice v4 XML card databases.
Requires Python 3.9+  |  Pillow is optional (enables JPG card images)
"""

import os
import uuid
import copy
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import xml.etree.ElementTree as ET

# ── Persistent config ─────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "cockatrice_editor_config.json"
)

# Optional Pillow for JPG support
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#0d0d11"
PANEL     = "#14141c"
PANEL2    = "#1a1a24"
BORDER    = "#28283a"
GOLD      = "#c9a84c"
GOLD_DIM  = "#6b5820"
GOLD_LT   = "#e8c96a"
TEXT      = "#e4dccf"
TEXT_DIM  = "#706860"
TEXT_MID  = "#a89880"
INPUT_BG  = "#1c1c28"
SEL_BG    = "#2a2010"
SEL_FG    = GOLD_LT
SUCCESS   = "#5cb87a"
ERROR     = "#d95f5f"
WARN      = "#c49a3c"

F_BODY  = ("Georgia", 10)
F_MONO  = ("Courier", 10)
F_SMALL = ("Courier", 9)
F_H1    = ("Georgia", 15, "bold")
F_H2    = ("Georgia", 10, "bold")
F_LABEL = ("Courier", 9, "bold")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

LAYOUTS   = ["normal", "split", "transform", "flip", "double-faced", "leveler",
             "saga", "planar", "scheme", "vanguard", "meld", "token", "emblem"]
SIDES     = ["front", "back"]
MAINTYPES = ["", "Creature", "Instant", "Sorcery", "Enchantment", "Artifact",
             "Land", "Planeswalker", "Battle", "Token"]
RARITIES  = ["common", "uncommon", "rare", "mythic", "special", "bonus", "land"]
TABLEROWS = [
    ("0", "0 — Lands"),
    ("1", "1 — Non-creature permanents"),
    ("2", "2 — Creatures"),
    ("3", "3 — Non-permanents (Instants / Sorceries)"),
]
FORMATS   = ["standard", "commander", "modern", "pauper", "legacy", "vintage", "pioneer"]


# ── XML helpers ───────────────────────────────────────────────────────────────

def load_xml(path: str):
    """Return (tree, root) or raise."""
    ET.register_namespace("", "")
    tree = ET.parse(path)
    return tree, tree.getroot()


def get_text(parent, tag, default=""):
    el = parent.find(tag)
    return (el.text or "").strip() if el is not None else default


def set_text(parent, tag, value, after_tag=None):
    """Set or remove a child element. If value is falsy, removes the tag."""
    el = parent.find(tag)
    if value:
        if el is None:
            el = ET.SubElement(parent, tag)
            if after_tag:
                _move_after(parent, el, after_tag)
        el.text = value
    else:
        if el is not None:
            parent.remove(el)


def _move_after(parent, el, after_tag):
    """Move el to appear directly after the first occurrence of after_tag."""
    children = list(parent)
    ref = parent.find(after_tag)
    if ref is None:
        return
    idx = children.index(ref)
    parent.remove(el)
    parent.insert(idx + 1, el)


def ensure_prop(card_el):
    prop = card_el.find("prop")
    if prop is None:
        prop = ET.SubElement(card_el, "prop")
    return prop


def card_names_from_root(root):
    """Return list of card name strings from the XML root."""
    names = []
    for card in root.findall("cards/card"):
        name_el = card.find("name")
        if name_el is not None and name_el.text:
            names.append(name_el.text.strip())
    return names


def find_card_el(root, name):
    for card in root.findall("cards/card"):
        n = card.find("name")
        if n is not None and (n.text or "").strip() == name:
            return card
    return None


def indent_xml(root, space="  ", level=0):
    """Pretty-print in-place (Python < 3.9 fallback)."""
    try:
        ET.indent(root, space=space)
    except AttributeError:
        _indent_fallback(root, space, level)


def _indent_fallback(elem, space, level):
    i = "\n" + level * space
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + space
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            _indent_fallback(child, space, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


# ── Styled widget factories ───────────────────────────────────────────────────

def mk_label(parent, text, font=F_BODY, fg=TEXT_DIM, bg=PANEL2, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)


def mk_entry(parent, textvariable=None, width=28, bg=PANEL2):
    return tk.Entry(
        parent, textvariable=textvariable, width=width,
        font=F_MONO, bg=INPUT_BG, fg=TEXT, insertbackground=GOLD,
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=GOLD,
    )


def mk_combo(parent, values, textvariable=None, width=20):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Dark.TCombobox",
        fieldbackground=INPUT_BG, background=INPUT_BG, foreground=TEXT,
        selectbackground=SEL_BG, selectforeground=SEL_FG,
        bordercolor=BORDER, arrowcolor=GOLD,
        lightcolor=BORDER, darkcolor=BORDER,
    )
    style.map("Dark.TCombobox",
        fieldbackground=[("readonly", INPUT_BG)],
        foreground=[("readonly", TEXT)],
        background=[("readonly", INPUT_BG)],
        selectbackground=[("readonly", SEL_BG)],
        selectforeground=[("readonly", SEL_FG)],
    )
    cb = ttk.Combobox(parent, values=values, textvariable=textvariable,
                      width=width, style="Dark.TCombobox", font=F_MONO)
    cb["state"] = "readonly"
    # Style the dropdown popup listbox via the option database
    parent.option_add("*TCombobox*Listbox.background",        INPUT_BG)
    parent.option_add("*TCombobox*Listbox.foreground",        TEXT)
    parent.option_add("*TCombobox*Listbox.selectBackground",  SEL_BG)
    parent.option_add("*TCombobox*Listbox.selectForeground",  SEL_FG)
    parent.option_add("*TCombobox*Listbox.font",              "Courier 10")
    return cb


def mk_button(parent, text, command, bg=GOLD, fg=BG, padx=12, pady=5):
    return tk.Button(
        parent, text=text, command=command,
        font=F_H2, fg=fg, bg=bg,
        activebackground=GOLD_DIM, activeforeground=TEXT,
        relief="flat", bd=0, padx=padx, pady=pady, cursor="hand2",
    )


def mk_small_button(parent, text, command):
    return tk.Button(
        parent, text=text, command=command,
        font=F_SMALL, fg=GOLD, bg=PANEL,
        activebackground=BORDER, activeforeground=GOLD_LT,
        relief="flat", bd=0, padx=6, pady=3, cursor="hand2",
        highlightthickness=1, highlightbackground=GOLD_DIM,
    )


def mk_check(parent, text, variable, bg=PANEL2):
    return tk.Checkbutton(
        parent, text=text, variable=variable,
        font=F_BODY, fg=TEXT, bg=bg,
        selectcolor=INPUT_BG, activebackground=bg,
        activeforeground=GOLD, relief="flat", bd=0,
    )


def sep(parent, bg=BORDER, pady=6):
    f = tk.Frame(parent, height=1, bg=bg)
    f.pack(fill="x", pady=pady)
    return f


def section_header(parent, text, bg=PANEL2):
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=(10, 4))
    tk.Label(row, text=text, font=F_LABEL, fg=GOLD, bg=bg).pack(side="left")
    tk.Frame(row, height=1, bg=GOLD_DIM).pack(
        side="left", fill="x", expand=True, padx=(8, 0), pady=5)
    return row


# ── Main App ──────────────────────────────────────────────────────────────────

class CardEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cockatrice Card Editor")
        self.configure(bg=BG)
        self.minsize(1100, 700)

        # Style the ttk Combobox dropdown listbox globally — must be set
        # before any Combobox is created; ttk style system can't reach this.
        self.option_add("*TCombobox*Listbox.background",       INPUT_BG)
        self.option_add("*TCombobox*Listbox.foreground",       TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", SEL_BG)
        self.option_add("*TCombobox*Listbox.selectForeground", SEL_FG)
        self.option_add("*TCombobox*Listbox.font",             "Courier 10")

        self.xml_paths        = []
        self.xml_trees        = {}
        self.active_xml       = None
        self.active_card      = None
        self.image_dir        = None
        self._img_ref         = None
        self._img_current_path = None
        self._dirty           = False

        self._build_ui()
        self._center()
        self._load_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Title bar
        bar = tk.Frame(self, bg=PANEL, pady=10)
        bar.pack(fill="x")
        tk.Frame(bar, width=4, bg=GOLD).pack(side="left", fill="y")
        tk.Label(bar, text="⬡  Cockatrice Card Editor",
                 font=F_H1, fg=TEXT, bg=PANEL, padx=14).pack(side="left")
        self._status_var = tk.StringVar(value="No file loaded")
        tk.Label(bar, textvariable=self._status_var,
                 font=F_SMALL, fg=TEXT_DIM, bg=PANEL, padx=10).pack(side="right")

        tk.Frame(self, height=1, bg=BORDER).pack(fill="x")

        # Three-pane area
        paned = tk.PanedWindow(self, orient="horizontal", bg=BORDER,
                               sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        self._build_xml_panel(paned)
        self._build_card_panel(paned)
        self._build_editor_panel(paned)

    # ── Panel 1: XML list ─────────────────────────────────────────────────────
    def _build_xml_panel(self, paned):
        frame = tk.Frame(paned, bg=PANEL, width=220, padx=8, pady=8)
        paned.add(frame, minsize=160)

        mk_label(frame, "XML DATABASES", font=F_LABEL, fg=GOLD, bg=PANEL).pack(anchor="w")
        tk.Frame(frame, height=1, bg=GOLD_DIM).pack(fill="x", pady=4)

        lb_frame = tk.Frame(frame, bg=BORDER, highlightthickness=0)
        lb_frame.pack(fill="both", expand=True, pady=(0, 6))
        self.xml_lb = tk.Listbox(
            lb_frame, font=F_SMALL, bg=INPUT_BG, fg=TEXT,
            selectbackground=SEL_BG, selectforeground=SEL_FG,
            relief="flat", bd=0, activestyle="none",
            highlightthickness=0,
        )
        sb = tk.Scrollbar(lb_frame, orient="vertical", command=self.xml_lb.yview,
                          bg=PANEL, troughcolor=INPUT_BG, width=8)
        self.xml_lb.config(yscrollcommand=sb.set)
        self.xml_lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.xml_lb.bind("<<ListboxSelect>>", self._on_xml_select)

        btn_row = tk.Frame(frame, bg=PANEL)
        btn_row.pack(fill="x")
        mk_small_button(btn_row, "+ Add XML", self._add_xml).pack(side="left", padx=(0, 4))
        mk_small_button(btn_row, "− Remove",  self._remove_xml).pack(side="left")

    # ── Panel 2: Card list ────────────────────────────────────────────────────
    def _build_card_panel(self, paned):
        frame = tk.Frame(paned, bg=PANEL, width=220, padx=8, pady=8)
        paned.add(frame, minsize=160)

        mk_label(frame, "CARDS", font=F_LABEL, fg=GOLD, bg=PANEL).pack(anchor="w")
        tk.Frame(frame, height=1, bg=GOLD_DIM).pack(fill="x", pady=4)

        # Search
        sv = tk.StringVar()
        sv.trace_add("write", lambda *_: self._filter_cards(sv.get()))
        search = mk_entry(frame, textvariable=sv, width=24, bg=PANEL)
        search.pack(fill="x", pady=(0, 4), ipady=4)

        # Proper placeholder — insert hint text, clear on focus, restore on blur
        PLACEHOLDER = "Search cards…"
        search.insert(0, PLACEHOLDER)
        search.config(fg=TEXT_DIM)

        def _on_focus_in(e):
            if search.get() == PLACEHOLDER:
                search.delete(0, "end")
                search.config(fg=TEXT)

        def _on_focus_out(e):
            if not search.get():
                search.insert(0, PLACEHOLDER)
                search.config(fg=TEXT_DIM)

        search.bind("<FocusIn>",  _on_focus_in)
        search.bind("<FocusOut>", _on_focus_out)

        # Don't trigger filter on the placeholder text itself
        def _on_trace(*_):
            val = sv.get()
            if val != PLACEHOLDER:
                self._filter_cards(val)
        sv.trace_add("write", lambda *_: None)  # remove the earlier trace
        # Re-bind directly on keyrelease instead — more reliable
        search.bind("<KeyRelease>", lambda e: self._filter_cards(
            "" if search.get() == PLACEHOLDER else search.get()
        ))

        lb_frame = tk.Frame(frame, bg=BORDER)
        lb_frame.pack(fill="both", expand=True)
        self.card_lb = tk.Listbox(
            lb_frame, font=F_SMALL, bg=INPUT_BG, fg=TEXT,
            selectbackground=SEL_BG, selectforeground=SEL_FG,
            relief="flat", bd=0, activestyle="none", highlightthickness=0,
        )
        sb2 = tk.Scrollbar(lb_frame, orient="vertical", command=self.card_lb.yview,
                           bg=PANEL, troughcolor=INPUT_BG, width=8)
        self.card_lb.config(yscrollcommand=sb2.set)
        self.card_lb.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        self.card_lb.bind("<<ListboxSelect>>", self._on_card_select)

        self._card_count_var = tk.StringVar(value="0 cards")
        mk_label(frame, "", textvariable=self._card_count_var,
                 font=F_SMALL, fg=TEXT_DIM, bg=PANEL).pack(anchor="w", pady=(4, 0))

    # ── Panel 3: Editor ───────────────────────────────────────────────────────
    def _build_editor_panel(self, paned):
        outer = tk.Frame(paned, bg=PANEL2)
        paned.add(outer, minsize=500)

        # Save bar pinned to bottom of outer before the paned split
        tk.Frame(outer, height=1, bg=BORDER).pack(fill="x", side="bottom")
        bot = tk.Frame(outer, bg=PANEL, pady=8, padx=12)
        bot.pack(fill="x", side="bottom")
        mk_button(bot, "💾  Save Changes", self._save_card, pady=7).pack(side="right")
        self._save_status = tk.StringVar(value="")
        mk_label(bot, "", textvariable=self._save_status,
                 font=F_SMALL, fg=SUCCESS, bg=PANEL).pack(side="right", padx=10)

        # Inner PanedWindow — image col | form col, both resizable by dragging
        inner = tk.PanedWindow(
            outer, orient="horizontal",
            bg=GOLD_DIM, sashwidth=5, sashrelief="flat",
            sashpad=0, handlesize=0,
        )
        inner.pack(fill="both", expand=True)

        # ── Left: image column ────────────────────────────────────────────
        img_col = tk.Frame(inner, bg=PANEL)
        inner.add(img_col, minsize=180, width=310, stretch="never")

        # Top section: card name + set + folder picker (always visible)
        top_sec = tk.Frame(img_col, bg=PANEL)
        top_sec.pack(fill="x", padx=10, pady=(10, 0))

        self._card_title_var = tk.StringVar(value="Select a card")
        tk.Label(top_sec, textvariable=self._card_title_var,
                 font=("Georgia", 13, "bold"), fg=TEXT, bg=PANEL,
                 wraplength=275, justify="left").pack(anchor="w")

        self._card_set_var = tk.StringVar(value="")
        tk.Label(top_sec, textvariable=self._card_set_var,
                 font=F_SMALL, fg=TEXT_DIM, bg=PANEL).pack(anchor="w", pady=(1, 6))

        tk.Frame(top_sec, height=1, bg=BORDER).pack(fill="x", pady=(0, 6))

        mk_small_button(top_sec, "📁  Choose Image Folder",
                        self._choose_image_dir).pack(anchor="w")
        self._img_dir_var = tk.StringVar(value="No folder selected")
        tk.Label(top_sec, textvariable=self._img_dir_var,
                 font=F_SMALL, fg=TEXT_DIM, bg=PANEL,
                 wraplength=275, justify="left").pack(anchor="w", pady=(3, 0))

        tk.Frame(img_col, height=1, bg=BORDER).pack(fill="x", pady=8)

        # Image label — fills all remaining space, reloads on resize
        self._img_label = tk.Label(
            img_col, bg=INPUT_BG,
            text="No image", font=F_SMALL, fg=TEXT_DIM,
            relief="flat", bd=0,
        )
        self._img_label.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._img_w = 260
        self._img_h = 364
        self._img_current_path = None  # track last loaded image path

        def _on_img_col_resize(e):
            # Reload image at new dimensions whenever the column is resized
            if self._img_current_path and os.path.isfile(self._img_current_path):
                self.after(50, lambda: self._load_image(self._img_current_path))

        self._img_label.bind("<Configure>", _on_img_col_resize)

        # ── Right: scrollable form ────────────────────────────────────────
        form_col = tk.Frame(inner, bg=PANEL2)
        inner.add(form_col, minsize=380, stretch="always")

        canvas = tk.Canvas(form_col, bg=PANEL2, bd=0, highlightthickness=0)
        vsb = tk.Scrollbar(form_col, orient="vertical", command=canvas.yview,
                           bg=PANEL2, troughcolor=INPUT_BG, width=8)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._form = tk.Frame(canvas, bg=PANEL2, padx=14, pady=10)
        self._form_id = canvas.create_window((0, 0), window=self._form, anchor="nw")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_resize(e):
            canvas.itemconfig(self._form_id, width=e.width)

        self._form.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        self._build_form(self._form)

    def _build_form(self, f):
        bg = PANEL2

        def row(label, widget_builder, hint=""):
            r = tk.Frame(f, bg=bg)
            r.pack(fill="x", pady=2)
            mk_label(r, label, font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
            if hint:
                mk_label(r, hint, font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
            w = widget_builder(r)
            w.pack(fill="x", pady=(2, 0), ipady=3)
            return w

        def entry_row(label, hint=""):
            v = tk.StringVar()
            row(label, lambda p: mk_entry(p, textvariable=v), hint)
            return v

        # ── Identity ──────────────────────────────────────────────────────
        section_header(f, "IDENTITY")

        self.v_name     = entry_row("Card Name")
        self.v_picurl   = entry_row("Pic URL", "Full URL to card image")

        # ── Description ───────────────────────────────────────────────────
        section_header(f, "ORACLE TEXT")
        mk_label(f, "Card Description / Oracle Text", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        self.txt_desc = tk.Text(
            f, height=5, font=F_MONO, bg=INPUT_BG, fg=TEXT,
            insertbackground=GOLD, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=GOLD, wrap="word",
        )
        self.txt_desc.pack(fill="x", pady=(2, 0))

        # ── Card Type ─────────────────────────────────────────────────────
        section_header(f, "TYPE LINE")
        self.v_type     = entry_row("Full Type", 'e.g. Legendary Creature — Spirit Cleric')

        mk_label(f, "Main Type", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        self.v_maintype = tk.StringVar()
        cb_main = mk_combo(f, MAINTYPES, textvariable=self.v_maintype, width=26)
        cb_main["state"] = "normal"
        cb_main.pack(anchor="w", pady=(2, 0))
        cb_main.bind("<<ComboboxSelected>>", self._auto_tablerow)

        mk_label(f, "Layout", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w", pady=(6, 0))
        self.v_layout = tk.StringVar()
        mk_combo(f, LAYOUTS, textvariable=self.v_layout, width=26).pack(anchor="w", pady=(2, 0))

        mk_label(f, "Side", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w", pady=(6, 0))
        self.v_side = tk.StringVar()
        mk_combo(f, SIDES, textvariable=self.v_side, width=14).pack(anchor="w", pady=(2, 0))

        # ── Mana ──────────────────────────────────────────────────────────
        section_header(f, "MANA")

        two = tk.Frame(f, bg=bg)
        two.pack(fill="x", pady=2)

        left_m = tk.Frame(two, bg=bg)
        left_m.pack(side="left", fill="x", expand=True, padx=(0, 8))
        mk_label(left_m, "Mana Cost", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        mk_label(left_m, "e.g. 2WU", font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_manacost = tk.StringVar()
        mk_entry(left_m, textvariable=self.v_manacost, width=14).pack(anchor="w", ipady=3, pady=(2,0))

        right_m = tk.Frame(two, bg=bg)
        right_m.pack(side="left", fill="x", expand=True)
        mk_label(right_m, "Mana Value (CMC)", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        mk_label(right_m, "e.g. 3", font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_cmc = tk.StringVar()
        mk_entry(right_m, textvariable=self.v_cmc, width=8).pack(anchor="w", ipady=3, pady=(2,0))

        two2 = tk.Frame(f, bg=bg)
        two2.pack(fill="x", pady=2)
        lc = tk.Frame(two2, bg=bg)
        lc.pack(side="left", fill="x", expand=True, padx=(0, 8))
        mk_label(lc, "Colors", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        mk_label(lc, "e.g. WU or R", font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_colors = tk.StringVar()
        mk_entry(lc, textvariable=self.v_colors, width=14).pack(anchor="w", ipady=3, pady=(2,0))

        rc = tk.Frame(two2, bg=bg)
        rc.pack(side="left", fill="x", expand=True)
        mk_label(rc, "Color Identity", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        mk_label(rc, "e.g. WU", font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_coloridentity = tk.StringVar()
        mk_entry(rc, textvariable=self.v_coloridentity, width=14).pack(anchor="w", ipady=3, pady=(2,0))

        # ── Stats ─────────────────────────────────────────────────────────
        section_header(f, "STATS")
        two3 = tk.Frame(f, bg=bg)
        two3.pack(fill="x", pady=2)
        lp = tk.Frame(two3, bg=bg)
        lp.pack(side="left", fill="x", expand=True, padx=(0, 8))
        mk_label(lp, "Power / Toughness", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        mk_label(lp, "e.g. 3/4  (omit if not a creature)", font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_pt = tk.StringVar()
        mk_entry(lp, textvariable=self.v_pt, width=10).pack(anchor="w", ipady=3, pady=(2,0))

        rp = tk.Frame(two3, bg=bg)
        rp.pack(side="left", fill="x", expand=True)
        mk_label(rp, "Loyalty", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        mk_label(rp, "Starting loyalty (planeswalkers)", font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_loyalty = tk.StringVar()
        mk_entry(rp, textvariable=self.v_loyalty, width=8).pack(anchor="w", ipady=3, pady=(2,0))

        # ── Set info ──────────────────────────────────────────────────────
        section_header(f, "SET INFO")
        two4 = tk.Frame(f, bg=bg)
        two4.pack(fill="x", pady=2)
        ls = tk.Frame(two4, bg=bg)
        ls.pack(side="left", fill="x", expand=True, padx=(0, 8))
        mk_label(ls, "Rarity", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        self.v_rarity = tk.StringVar()
        mk_combo(ls, RARITIES, textvariable=self.v_rarity, width=14).pack(anchor="w", pady=(2,0))

        rs = tk.Frame(two4, bg=bg)
        rs.pack(side="left", fill="x", expand=True)
        mk_label(rs, "Collector Number", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        self.v_num = tk.StringVar()
        mk_entry(rs, textvariable=self.v_num, width=10).pack(anchor="w", ipady=3, pady=(2,0))

        # ── Tablerow ──────────────────────────────────────────────────────
        section_header(f, "TABLE ROW")
        mk_label(f, "Table Row", font=F_LABEL, fg=GOLD_LT, bg=bg).pack(anchor="w")
        mk_label(f, "Determines which row the card appears in during a game",
                 font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_tablerow = tk.StringVar()
        mk_combo(f, [t[1] for t in TABLEROWS], textvariable=self.v_tablerow,
                 width=40).pack(anchor="w", pady=(2,0))

        # ── Flags ─────────────────────────────────────────────────────────
        section_header(f, "FLAGS")
        flag_frame = tk.Frame(f, bg=bg)
        flag_frame.pack(fill="x", pady=4)

        self.v_token = tk.IntVar()
        mk_check(flag_frame, "Token  (can't be in a deck; created by other cards)",
                 self.v_token, bg=bg).pack(anchor="w", pady=2)

        self.v_cipt = tk.IntVar()
        mk_check(flag_frame, "Enters the battlefield tapped  (cipt)",
                 self.v_cipt, bg=bg).pack(anchor="w", pady=2)

        self.v_upsidedown = tk.IntVar()
        mk_check(flag_frame, "Show image upside-down  (flip cards)",
                 self.v_upsidedown, bg=bg).pack(anchor="w", pady=2)

        # ── Relations ─────────────────────────────────────────────────────
        section_header(f, "RELATIONS")
        self.v_related = entry_row("Related Cards",
                                   "Comma-separated — cards this card can create/transform into")
        self.v_rev_related = entry_row("Reverse-Related Cards",
                                       "Comma-separated — cards that can create this card")

        # ── Formats ───────────────────────────────────────────────────────
        section_header(f, "LEGALITY")
        mk_label(f, "Mark as 'legal' in selected formats:",
                 font=F_SMALL, fg=TEXT_DIM, bg=bg).pack(anchor="w")
        self.v_formats = {}
        fmt_frame = tk.Frame(f, bg=bg)
        fmt_frame.pack(fill="x", pady=4)
        for i, fmt in enumerate(FORMATS):
            v = tk.IntVar()
            self.v_formats[fmt] = v
            col = i % 4
            row_n = i // 4
            cb = mk_check(fmt_frame, fmt.capitalize(), v, bg=bg)
            cb.grid(row=row_n, column=col, sticky="w", padx=8, pady=2)

        tk.Frame(f, height=20, bg=bg).pack()

    # ── XML Panel actions ─────────────────────────────────────────────────────
    def _add_xml(self):
        path = filedialog.askopenfilename(
            title="Open Cockatrice XML",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
        )
        if not path or path in self.xml_paths:
            return
        try:
            tree, root = load_xml(path)
            self.xml_trees[path] = (tree, root)
            self.xml_paths.append(path)
            self.xml_lb.insert("end", os.path.basename(path))
            self._status("Loaded: " + os.path.basename(path))
            self._save_config()
        except Exception as e:
            messagebox.showerror("Parse error", str(e))

    def _remove_xml(self):
        sel = self.xml_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        path = self.xml_paths[idx]
        self.xml_paths.pop(idx)
        del self.xml_trees[path]
        self.xml_lb.delete(idx)
        if self.active_xml == path:
            self.active_xml = None
            self.active_card = None
            self.card_lb.delete(0, "end")
            self._clear_form()
        self._save_config()

    def _on_xml_select(self, _event=None):
        sel = self.xml_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        self.active_xml = self.xml_paths[idx]
        _, root = self.xml_trees[self.active_xml]
        names = card_names_from_root(root)
        self._populate_card_list(names)
        self._status(f"{os.path.basename(self.active_xml)}  —  {len(names)} cards")

    # ── Card Panel actions ────────────────────────────────────────────────────
    def _populate_card_list(self, names):
        self.card_lb.delete(0, "end")
        for n in names:
            self.card_lb.insert("end", n)
        self._card_count_var.set(f"{len(names)} card{'s' if len(names)!=1 else ''}")

    def _filter_cards(self, query):
        if not self.active_xml:
            return
        _, root = self.xml_trees[self.active_xml]
        all_names = card_names_from_root(root)
        filtered = [n for n in all_names if query.lower() in n.lower()] if query else all_names
        self._populate_card_list(filtered)

    def _on_card_select(self, _event=None):
        sel = self.card_lb.curselection()
        if not sel or not self.active_xml:
            return
        name = self.card_lb.get(sel[0])
        self.active_card = name
        _, root = self.xml_trees[self.active_xml]
        card_el = find_card_el(root, name)
        if card_el is not None:
            self._load_card(card_el)

    # ── Form population ───────────────────────────────────────────────────────
    def _clear_form(self):
        for v in [self.v_name, self.v_picurl, self.v_type, self.v_maintype,
                  self.v_layout, self.v_side, self.v_manacost, self.v_cmc,
                  self.v_colors, self.v_coloridentity, self.v_pt, self.v_loyalty,
                  self.v_rarity, self.v_num, self.v_tablerow, self.v_related,
                  self.v_rev_related]:
            v.set("")
        self.txt_desc.delete("1.0", "end")
        self.v_token.set(0)
        self.v_cipt.set(0)
        self.v_upsidedown.set(0)
        for fv in self.v_formats.values():
            fv.set(0)
        self._card_title_var.set("Select a card")
        self._card_set_var.set("")
        self._img_label.config(image="", text="No image")

    def _load_card(self, card_el):
        self._clear_form()

        name = get_text(card_el, "name")
        self.v_name.set(name)
        self._card_title_var.set(name)

        self.txt_desc.insert("1.0", get_text(card_el, "text"))

        prop = card_el.find("prop") or ET.Element("prop")
        self.v_layout.set(get_text(prop, "layout", "normal"))
        self.v_side.set(get_text(prop, "side", "front"))
        self.v_type.set(get_text(prop, "type"))
        self.v_maintype.set(get_text(prop, "maintype"))
        self.v_manacost.set(get_text(prop, "manacost"))
        self.v_cmc.set(get_text(prop, "cmc"))
        self.v_colors.set(get_text(prop, "colors"))
        self.v_coloridentity.set(get_text(prop, "coloridentity"))
        self.v_pt.set(get_text(prop, "pt"))
        self.v_loyalty.set(get_text(prop, "loyalty"))

        for fmt in FORMATS:
            self.v_formats[fmt].set(1 if prop.find(f"format-{fmt}") is not None else 0)

        # Set attributes
        set_el = card_el.find("set")
        if set_el is not None:
            self.v_rarity.set(set_el.get("rarity", "common"))
            self.v_num.set(set_el.get("num", ""))
            self.v_picurl.set(set_el.get("picurl", ""))
            self._card_set_var.set(f"Set: {set_el.text or ''}")

        # Tablerow
        tr = get_text(card_el, "tablerow", "2")
        for val, label in TABLEROWS:
            if val == tr:
                self.v_tablerow.set(label)
                break

        # Flags
        self.v_token.set(1 if get_text(card_el, "token") == "1" else 0)
        self.v_cipt.set(1 if get_text(card_el, "cipt") == "1" else 0)
        self.v_upsidedown.set(1 if get_text(card_el, "upsidedown") == "1" else 0)

        # Relations
        related     = [r.text or "" for r in card_el.findall("related")]
        rev_related = [r.text or "" for r in card_el.findall("reverse-related")]
        self.v_related.set(", ".join(related))
        self.v_rev_related.set(", ".join(rev_related))

        # Image
        self._show_card_image(name)

    # ── Save ──────────────────────────────────────────────────────────────────
    def _save_card(self):
        if not self.active_xml or not self.active_card:
            self._save_status.set("No card selected.")
            return

        tree, root = self.xml_trees[self.active_xml]
        card_el = find_card_el(root, self.active_card)
        if card_el is None:
            self._save_status.set("Card not found in XML.")
            return

        # Name
        name_el = card_el.find("name")
        if name_el is not None:
            name_el.text = self.v_name.get().strip()

        # Text / description
        text_el = card_el.find("text")
        if text_el is None:
            text_el = ET.SubElement(card_el, "text")
        text_el.text = self.txt_desc.get("1.0", "end-1c")

        # Prop
        prop = ensure_prop(card_el)
        for tag, val in [
            ("layout",        self.v_layout.get()),
            ("side",          self.v_side.get()),
            ("type",          self.v_type.get().strip()),
            ("maintype",      self.v_maintype.get().strip()),
            ("manacost",      self.v_manacost.get().strip()),
            ("cmc",           self.v_cmc.get().strip()),
            ("colors",        self.v_colors.get().strip()),
            ("coloridentity", self.v_coloridentity.get().strip()),
            ("pt",            self.v_pt.get().strip()),
            ("loyalty",       self.v_loyalty.get().strip()),
        ]:
            set_text(prop, tag, val)

        # Formats
        for fmt in FORMATS:
            tag = f"format-{fmt}"
            set_text(prop, tag, "legal" if self.v_formats[fmt].get() else "")

        # Set element
        set_el = card_el.find("set")
        if set_el is None:
            set_el = ET.SubElement(card_el, "set")
            if not set_el.get("uuid"):
                set_el.set("uuid", str(uuid.uuid4()))
        set_el.set("rarity", self.v_rarity.get() or "common")
        set_el.set("num",    self.v_num.get().strip())
        set_el.set("picurl", self.v_picurl.get().strip())

        # Tablerow
        tr_label = self.v_tablerow.get()
        tr_val = "2"
        for val, label in TABLEROWS:
            if label == tr_label:
                tr_val = val
                break
        tr_el = card_el.find("tablerow")
        if tr_el is None:
            tr_el = ET.SubElement(card_el, "tablerow")
        tr_el.text = tr_val

        # CIPT (after tablerow)
        set_text(card_el, "cipt", "1" if self.v_cipt.get() else "")

        # Upsidedown (after cipt)
        set_text(card_el, "upsidedown", "1" if self.v_upsidedown.get() else "")

        # Token
        set_text(card_el, "token", "1" if self.v_token.get() else "")

        # Related / reverse-related — rebuild
        for existing in card_el.findall("related"):
            card_el.remove(existing)
        for existing in card_el.findall("reverse-related"):
            card_el.remove(existing)
        for name in [n.strip() for n in self.v_related.get().split(",") if n.strip()]:
            el = ET.SubElement(card_el, "related")
            el.text = name
        for name in [n.strip() for n in self.v_rev_related.get().split(",") if n.strip()]:
            el = ET.SubElement(card_el, "reverse-related")
            el.text = name

        # Write XML
        try:
            indent_xml(root)
            tree.write(self.active_xml, encoding="UTF-8", xml_declaration=True)
            self._save_status.set(f"✓  Saved  —  {os.path.basename(self.active_xml)}")
            self.active_card = self.v_name.get().strip()
            self._card_title_var.set(self.active_card)
            # Refresh card list
            _, root2 = self.xml_trees[self.active_xml]
            self._populate_card_list(card_names_from_root(root2))
        except Exception as e:
            self._save_status.set(f"✗  Error: {e}")

    # ── Image ─────────────────────────────────────────────────────────────────
    def _choose_image_dir(self):
        d = filedialog.askdirectory(title="Select folder containing card images")
        if d:
            self.image_dir = d
            self._img_dir_var.set(os.path.basename(d))
            if self.active_card:
                self._show_card_image(self.active_card)
            self._save_config()

    # ── Persistence ───────────────────────────────────────────────────────────
    def _save_config(self):
        try:
            data = {
                "xml_paths": self.xml_paths,
                "image_dir": self.image_dir or "",
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        # Restore image folder
        img_dir = data.get("image_dir", "")
        if img_dir and os.path.isdir(img_dir):
            self.image_dir = img_dir
            self._img_dir_var.set(os.path.basename(img_dir))

        # Restore XML files in order
        for path in data.get("xml_paths", []):
            if os.path.isfile(path) and path not in self.xml_paths:
                try:
                    tree, root = load_xml(path)
                    self.xml_trees[path] = (tree, root)
                    self.xml_paths.append(path)
                    self.xml_lb.insert("end", os.path.basename(path))
                except Exception:
                    pass

        if self.xml_paths:
            self._status(f"Restored {len(self.xml_paths)} XML file(s)")

    def _on_close(self):
        self._save_config()
        self.destroy()

    def _show_card_image(self, card_name):
        self._img_label.config(image="", text="No image")
        self._img_ref = None
        if not self.image_dir or not card_name:
            return
        for ext in IMAGE_EXT:
            path = os.path.join(self.image_dir, card_name + ext)
            if os.path.isfile(path):
                self._load_image(path)
                return

    def _load_image(self, path):
        self._img_current_path = path
        try:
            self._img_label.update_idletasks()
            w = max(self._img_label.winfo_width(),  60)
            h = max(self._img_label.winfo_height(), 60)
            if HAS_PIL:
                img = Image.open(path)
                img.thumbnail((w, h), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            else:
                photo = tk.PhotoImage(file=path)
                pw, ph = photo.width(), photo.height()
                if pw > w or ph > h:
                    scale = max(pw // w, ph // h, 1)
                    photo = photo.subsample(scale)
            self._img_ref = photo
            self._img_label.config(image=photo, text="")
        except Exception:
            self._img_label.config(image="", text="(image error)")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _auto_tablerow(self, _event=None):
        mt = self.v_maintype.get().lower()
        mapping = {
            "creature": "2 — Creatures",
            "land":     "0 — Lands",
            "instant":  "3 — Non-permanents (Instants / Sorceries)",
            "sorcery":  "3 — Non-permanents (Instants / Sorceries)",
        }
        for key, val in mapping.items():
            if key in mt:
                self.v_tablerow.set(val)
                return
        self.v_tablerow.set("1 — Non-creature permanents")

    def _status(self, msg):
        self._status_var.set(msg)

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = min(1300, sw - 60)
        h  = min(820,  sh - 60)
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


if __name__ == "__main__":
    app = CardEditor()
    app.mainloop()
