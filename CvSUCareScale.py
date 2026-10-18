import base64
import csv
import io
import math
import os
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

# ---------------------------------------------------------------- settings
W, H = 1120, 630                                   # window size (16:9)
FOLDER = os.path.dirname(os.path.abspath(__file__))
SPLASH_FILE = os.path.join(FOLDER, "splash.png")
SAVE_FILE = os.path.join(FOLDER, "bmi_records.csv")      # list of all patients
RECEIPT_DIR = os.path.join(FOLDER, "BMI_Receipts")       # receipt pictures

FONT = "Segoe UI"                                  # clean, easy-to-read font
DARK = "#2b1d0e"                                   # text / borders
GREEN = "#1f7a35"                                  # section headings
CARD = "#f7f1e3"                                   # cream card color
FIELD = "#ffffff"                                  # input box color

# Area of the PROCEED button on the splash image (x1, y1, x2, y2)
# (taken from the 1920x1080 design and scaled to the 1120x630 window)
PROCEED_AREA = (456, 482, 664, 540)

CATEGORY_COLORS = {
    "UNDERWEIGHT": "#c47a00",
    "NORMAL WEIGHT": "#1f7a35",
    "OVERWEIGHT": "#c47a00",
    "OBESE": "#b3261e",
}


def get_category(bmi):
    """WHO BMI categories. Change the cut-offs here if your clinic uses others."""
    if bmi < 18.5:
        return "UNDERWEIGHT"
    elif bmi < 25:
        return "NORMAL WEIGHT"
    elif bmi < 30:
        return "OVERWEIGHT"
    return "OBESE"


def name_error(text):
    """Returns the reason the name is invalid, or None if it is fine."""
    text = text.strip()
    if not text:
        return "Name is required."
    if (not any(ch.isalpha() for ch in text)
            or not all(ch.isalpha() or ch in " .'-" for ch in text)):
        return "Letters only, no numbers/symbols."
    return None


def age_error(text):
    text = text.strip()
    if not text:
        return "Age is required."
    if text.startswith("-") and text[1:].isdigit():
        return "Age cannot be negative."
    if not text.isdigit():
        return "Use a whole number, like 20."
    if int(text) == 0:
        return "Age cannot be zero."
    return None


def number_check(text, label, example):
    """Returns (value, None) if fine, or (None, reason) if invalid."""
    text = text.strip()
    if not text:
        return None, f"{label} is required."
    try:
        value = float(text)
    except ValueError:
        return None, f"Use a number, like {example}."
    if not math.isfinite(value):
        return None, f"Use a number, like {example}."
    if value < 0:
        return None, f"{label} cannot be negative."
    if value == 0:
        return None, f"{label} cannot be zero."
    return value, None


# ----------------------------------------------------------------- helpers
def draw_background(canvas):
    """Brown-to-tan gradient."""
    top, bottom = (120, 82, 42), (192, 158, 112)
    for y in range(H):
        t = y / H
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        canvas.create_line(0, y, W, y, fill=f"#{r:02x}{g:02x}{b:02x}")


def make_button(canvas, text, x, y, w, h, command, size=16):
    """White button with a black shadow, centered at (x, y)."""
    canvas.create_rectangle(x - w // 2 + 5, y - h // 2 + 5,
                            x + w // 2 + 5, y + h // 2 + 5,
                            fill="black", outline="black")
    btn = tk.Button(canvas, text=text, font=(FONT, size, "bold"), fg=DARK,
                    bg="white", activebackground="#e8e8e8", relief="flat",
                    bd=0, cursor="hand2", command=command)
    canvas.create_window(x, y, window=btn, width=w, height=h)
    return btn


def make_entry(canvas, x1, x2, y, h=46):
    """Input box spanning x1..x2, vertically centered at y."""
    entry = tk.Entry(canvas, font=(FONT, 17), justify="center", bg=FIELD,
                     fg=DARK, relief="flat", highlightthickness=3,
                     highlightbackground=DARK, highlightcolor=GREEN)
    canvas.create_window((x1 + x2) // 2, y, window=entry,
                         width=x2 - x1, height=h)
    return entry


# ------------------------------------------------------- receipt (photo) tools
def ensure_pillow(parent=None):
    """Receipt pictures need the free 'Pillow' library. Offer to install it."""
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        pass
    if not messagebox.askyesno(
            "One-time setup",
            "To make the receipt picture, the program needs a free add-on "
            "called Pillow.\n\nInstall it now? (needs internet, takes a few seconds)",
            parent=parent):
        return False
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "pillow"],
                       check=True)
        import PIL  # noqa: F401
        return True
    except Exception:
        messagebox.showerror(
            "Install failed",
            "Pillow could not be installed.\nPlease check your internet "
            "connection and try again.", parent=parent)
        return False


def find_font(size, bold=False):
    from PIL import ImageFont
    if bold:
        names = ["arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "Arial Bold.ttf"]
    else:
        names = ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf",
                 "/System/Library/Fonts/Supplemental/Arial.ttf", "Arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def make_receipt_image(path, info):
    """Draw the BMI receipt as a PNG picture (ready to print)."""
    from PIL import Image, ImageDraw

    RW, RH = 800, 1180
    ink = (43, 29, 14)
    green = (31, 122, 53)
    gold = (214, 165, 0)
    gray = (110, 100, 90)

    img = Image.new("RGB", (RW, RH), "white")
    d = ImageDraw.Draw(img)

    def width(text, font):
        return d.textlength(text, font=font)

    def center(y, text, font, fill):
        d.text(((RW - width(text, font)) / 2, y), text, font=font, fill=fill)

    def fit(text, max_w, size, bold):
        font = find_font(size, bold)
        while size > 14 and width(text, font) > max_w:
            size -= 2
            font = find_font(size, bold)
        return font

    def dashed(y):
        x = 60
        while x < RW - 60:
            d.line((x, y, x + 14, y), fill=ink, width=3)
            x += 24

    # border
    d.rectangle((15, 15, RW - 15, RH - 15), outline=ink, width=4)
    d.rectangle((26, 26, RW - 26, RH - 26), outline=green, width=2)

    # header
    center(55, "CAVITE STATE UNIVERSITY", find_font(34, True), green)
    center(102, "CARMONA CAMPUS CLINIC", find_font(30, True), green)
    f_big = find_font(92, True)
    w1, w2 = width("CARE", f_big), width("SCALE", f_big)
    x0 = (RW - (w1 + w2)) / 2
    d.text((x0, 150), "CARE", font=f_big, fill=green)
    d.text((x0 + w1, 150), "SCALE", font=f_big, fill=gold)
    center(268, "CULTIVATING HEALTH. BALANCING WELL-BEING.",
           find_font(20, True), green)
    dashed(318)

    # title + date
    center(338, "BMI RECEIPT", find_font(46, True), ink)
    center(402, info["when"].strftime("%B %d, %Y  -  %I:%M %p"),
           find_font(24), gray)

    # details
    rows = [("NAME:", info["name"]), ("AGE:", info["age"]),
            ("WEIGHT:", info["weight"] + " kg"),
            ("HEIGHT:", info["height"] + " cm")]
    y = 465
    f_label = find_font(28, True)
    for label, value in rows:
        d.text((70, y), label, font=f_label, fill=ink)
        f_val = fit(value, 480, 28, False)
        d.text((RW - 70 - width(value, f_val), y), value, font=f_val, fill=ink)
        y += 62
    d.line((60, 715, RW - 60, 715), fill=ink, width=3)

    # result
    center(735, "YOUR BMI", find_font(30, True), gray)
    center(775, f"{info['bmi']}", find_font(130, True), ink)

    colors = {"UNDERWEIGHT": (196, 122, 0), "NORMAL WEIGHT": (31, 122, 53),
              "OVERWEIGHT": (196, 122, 0), "OBESE": (179, 38, 30)}
    cat = info["category"]
    f_cat = find_font(40, True)
    cw = width(cat, f_cat) + 80
    d.rounded_rectangle(((RW - cw) / 2, 935, (RW + cw) / 2, 1005),
                        radius=35, fill=colors[cat])
    center(945, cat, f_cat, "white")

    # BMI scale bar (10 to 40)
    bx1, bx2, by1, by2 = 70, RW - 70, 1050, 1072

    def pos(v):
        v = min(max(v, 10), 40)
        return bx1 + (v - 10) / 30 * (bx2 - bx1)

    for lo, hi, col in [(10, 18.5, (196, 122, 0)), (18.5, 25, (31, 122, 53)),
                        (25, 30, (196, 122, 0)), (30, 40, (179, 38, 30))]:
        d.rectangle((pos(lo), by1, pos(hi), by2), fill=col)
    mx = pos(info["bmi"])
    d.polygon([(mx, by1 - 4), (mx - 12, by1 - 24), (mx + 12, by1 - 24)], fill=ink)
    f_small = find_font(18)
    for v in (18.5, 25, 30):
        t = str(v)
        d.text((pos(v) - width(t, f_small) / 2, by2 + 6), t, font=f_small, fill=gray)

    # footer
    center(1118, "Computer-generated receipt. Thank you!", find_font(20), gray)

    img.save(path, "PNG", dpi=(200, 200))


def print_receipt(path):
    """Send the receipt picture to the printer (falls back to opening it)."""
    try:
        if sys.platform.startswith("win"):
            try:
                os.startfile(path, "print")
            except OSError:
                os.startfile(path)         # open it, then print from the viewer
        elif sys.platform == "darwin":
            subprocess.run(["lpr", path], check=True)
        else:
            subprocess.run(["lp", path], check=True)
    except Exception as error:
        messagebox.showerror("Could not print",
                             f"Could not start printing.\n\n{error}\n\n"
                             f"You can open the picture and print it yourself:\n{path}")


def show_receipt_window(parent, path):
    """Shows the saved receipt picture with PRINT and DONE buttons."""
    from PIL import Image
    img = Image.open(path)
    scale = 0.5
    small = img.resize((int(img.width * scale), int(img.height * scale)),
                       Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "PNG")
    photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))

    top = tk.Toplevel(parent)
    top.title("Receipt Saved")
    top.resizable(False, False)
    top.transient(parent)
    top.configure(bg="#f7f1e3")

    bar = tk.Frame(top, bg="#f7f1e3")
    bar.pack(pady=8)
    tk.Button(bar, text="PRINT RECEIPT", font=(FONT, 13, "bold"), width=16,
              bg=GREEN, fg="white", activebackground="#17602a",
              activeforeground="white", cursor="hand2",
              command=lambda: print_receipt(path)).pack(side="left", padx=8)
    tk.Button(bar, text="DONE", font=(FONT, 13, "bold"), width=12,
              bg="white", fg=DARK, cursor="hand2",
              command=top.destroy).pack(side="left", padx=8)

    label = tk.Label(top, image=photo, bd=2, relief="solid")
    label.image = photo                     # keep a reference
    label.pack(padx=12, pady=(0, 12))

    top.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - top.winfo_width()) // 2
    top.geometry(f"+{max(x, 0)}+10")
    top.grab_set()
    parent.wait_window(top)


# ------------------------------------------------------------ splash screen
class SplashScreen(tk.Frame):
    """Front page = the logo image. Click PROCEED to continue."""

    def __init__(self, app):
        super().__init__(app, width=W, height=H)
        self.app = app
        c = self.c = tk.Canvas(self, width=W, height=H, highlightthickness=0)
        c.pack()

        try:
            self.image = tk.PhotoImage(file=SPLASH_FILE)
            c.create_image(0, 0, image=self.image, anchor="nw")
        except tk.TclError:
            # splash.png missing: plain background + a real button
            draw_background(c)
            make_button(c, "PROCEED", W // 2, 480, 205, 55,
                        lambda: app.show("bmi"))
            return

        # The PROCEED button is already drawn in the image,
        # so we only make that area clickable.
        c.bind("<Button-1>", self.on_click)
        c.bind("<Motion>", self.on_move)

    def inside_button(self, event):
        x1, y1, x2, y2 = PROCEED_AREA
        return x1 <= event.x <= x2 and y1 <= event.y <= y2

    def on_click(self, event):
        if self.inside_button(event):
            self.app.show("bmi")

    def on_move(self, event):
        self.c.config(cursor="hand2" if self.inside_button(event) else "")


# ------------------------------------------------------------------ tutorial
# Each step: title, explanation, and the areas (x1, y1, x2, y2) of the BMI
# screen to highlight with a yellow frame while that step is shown.
TUTORIAL_STEPS = [
    {"title": "Welcome to CareScale!",
     "text": "This program calculates your BMI (Body Mass Index) and makes a "
             "printable receipt.\n\nOn the first screen, click PROCEED to start. "
             "This short guide will show you how to use the next screen.",
     "boxes": []},
    {"title": "Step 1: User Information",
     "text": "Type your NAME and AGE.\n\n- Name: letters only (no numbers or symbols)\n"
             "- Age: a whole number, like 20",
     "boxes": [(90, 108, 1030, 168)]},
    {"title": "Step 2: Measurements",
     "text": "Type your WEIGHT in kilograms (kg) and your HEIGHT in centimeters (cm).\n\n"
             "Example: weight 65, height 170.\nUse positive numbers only.",
     "boxes": [(90, 226, 1030, 300)]},
    {"title": "Step 3: Calculate",
     "text": "Click CALCULATE BMI.\n\nYour BMI number and your category "
             "(Underweight, Normal Weight, Overweight or Obese) will appear "
             "at the bottom.",
     "boxes": [(405, 338, 715, 404), (90, 444, 1030, 512)]},
    {"title": "If you see INVALID INPUT",
     "text": "Something was typed wrongly. The wrong boxes turn red and a short "
             "red message under each one tells you why.\n\nFix the red boxes and "
             "click CALCULATE BMI again.",
     "boxes": [(90, 108, 1030, 168), (90, 226, 1030, 300)]},
    {"title": "Step 4: Save and Print",
     "text": "Click SAVE AND EXIT to save your record. A receipt picture will "
             "appear. Click PRINT RECEIPT to print it, then DONE.\n\n"
             "The program then goes back to the start screen. "
             "Click PREVIOUS if you want to go back without saving.",
     "boxes": [(285, 520, 865, 582)]},
]


class TutorialWindow(tk.Toplevel):
    """Small step-by-step guide. You can move it around the screen."""

    def __init__(self, screen):
        super().__init__(screen.app)
        self.screen = screen
        self.step = 0
        self.frames = []                      # yellow highlight frames on the canvas
        self.title("How to use CareScale")
        self.resizable(False, False)
        self.transient(screen.app)
        self.configure(bg=CARD)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.counter = tk.Label(self, bg=CARD, fg="#5a4630", font=(FONT, 10, "bold"))
        self.counter.pack(anchor="e", padx=16, pady=(10, 0))
        self.title_label = tk.Label(self, bg=CARD, fg=GREEN, font=(FONT, 16, "bold"),
                                    anchor="w", justify="left")
        self.title_label.pack(fill="x", padx=16)
        self.text_label = tk.Label(self, bg=CARD, fg=DARK, font=(FONT, 12),
                                   anchor="nw", justify="left", wraplength=400,
                                   width=44, height=9)
        self.text_label.pack(fill="x", padx=16, pady=(6, 6))

        bar = tk.Frame(self, bg=CARD)
        bar.pack(pady=(0, 12))
        self.back_btn = tk.Button(bar, text="< BACK", width=10, font=(FONT, 11, "bold"),
                                  cursor="hand2", command=self.back)
        self.back_btn.pack(side="left", padx=6)
        self.next_btn = tk.Button(bar, text="NEXT >", width=10, bg=GREEN, fg="white",
                                  activebackground="#17602a", activeforeground="white",
                                  font=(FONT, 11, "bold"), cursor="hand2",
                                  command=self.next)
        self.next_btn.pack(side="left", padx=6)

        self.place_window()
        self.show_step()

    def place_window(self):
        self.update_idletasks()
        app = self.screen.app
        tw, th = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        right_edge = app.winfo_rootx() + app.winfo_width()
        if sw - right_edge >= tw + 10:                 # room beside the app
            x, y = right_edge + 10, app.winfo_rooty()
        else:                                          # otherwise bottom-right corner
            x, y = sw - tw - 20, sh - th - 80
        self.geometry(f"+{x}+{max(y, 0)}")

    def clear_frames(self):
        for item in self.frames:
            self.screen.c.delete(item)
        self.frames = []

    def show_step(self):
        step = TUTORIAL_STEPS[self.step]
        total = len(TUTORIAL_STEPS)
        self.counter.config(text=f"{self.step + 1} of {total}")
        self.title_label.config(text=step["title"])
        self.text_label.config(text=step["text"])
        self.back_btn.config(state="normal" if self.step > 0 else "disabled")
        self.next_btn.config(text="FINISH" if self.step == total - 1 else "NEXT >")

        self.clear_frames()
        for x1, y1, x2, y2 in step["boxes"]:
            self.frames.append(self.screen.c.create_rectangle(
                x1, y1, x2, y2, outline="#ffb300", width=5))

    def next(self):
        if self.step >= len(TUTORIAL_STEPS) - 1:
            self.close()
        else:
            self.step += 1
            self.show_step()

    def back(self):
        if self.step > 0:
            self.step -= 1
            self.show_step()

    def close(self):
        self.clear_frames()
        self.destroy()


# --------------------------------------------------------------- BMI screen
class BMIScreen(tk.Frame):
    # column positions for a neat 2-column grid
    LABEL_L, ENTRY_L = 100, (275, 520)
    LABEL_R, ENTRY_R = 590, (765, 1010)

    def __init__(self, app):
        super().__init__(app, width=W, height=H)
        self.app = app
        self.last_result = None            # (bmi, category) after a valid calculation

        c = self.c = tk.Canvas(self, width=W, height=H, highlightthickness=0)
        c.pack()
        draw_background(c)

        # cream card with shadow
        c.create_rectangle(66, 46, 1066, 596, fill="black", outline="black")
        c.create_rectangle(60, 40, 1060, 590, fill=CARD, outline=DARK, width=3)

        # ---- section 1: patient information
        self.section(c, "USER INFORMATION", 82)
        self.label(c, "NAME:", self.LABEL_L, 135)
        self.name = make_entry(c, *self.ENTRY_L, 135)
        self.label(c, "AGE:", self.LABEL_R, 135)
        self.age = make_entry(c, *self.ENTRY_R, 135)

        # ---- section 2: measurements
        self.section(c, "MEASUREMENTS", 200)
        self.label(c, "WEIGHT (kg):", self.LABEL_L, 253)
        self.weight = make_entry(c, *self.ENTRY_L, 253)
        self.label(c, "HEIGHT (cm):", self.LABEL_R, 253)
        self.height = make_entry(c, *self.ENTRY_R, 253)

        self.entries = (self.name, self.age, self.weight, self.height)
        for entry in self.entries:
            entry.bind("<KeyRelease>", lambda e, en=entry: self.on_edit(en))

        # small red reason text under each box (shown only when invalid)
        self.reason_items = {}
        spots = [(self.name, 397, 163), (self.age, 887, 163),
                 (self.weight, 397, 281), (self.height, 887, 281)]
        for entry, x, y in spots:
            self.reason_items[entry] = c.create_text(
                x, y, text="", anchor="n", width=260, justify="center",
                font=(FONT, 11, "bold"), fill="#c00000", state="hidden")

        # error message (only shown when an input is invalid)
        self.error = c.create_text(560, 312, font=(FONT, 14, "bold"), fill="#c00000",
                                   text="", state="hidden")

        # calculate button
        make_button(c, "CALCULATE BMI", 560, 370, 280, 54, self.calculate)

        # dashed divider
        c.create_line(100, 424, 1020, 424, dash=(12, 8), width=3, fill=DARK)

        # ---- section 3: result
        self.label(c, "BMI RESULT:", self.LABEL_L, 478)
        c.create_rectangle(*self.box(self.ENTRY_L, 478), fill="white",
                           outline=DARK, width=3)
        self.result_text = c.create_text(sum(self.ENTRY_L) // 2, 478,
                                         text="", fill=DARK,
                                         font=(FONT, 22, "bold"))

        self.label(c, "CATEGORY:", self.LABEL_R, 478)
        c.create_rectangle(*self.box(self.ENTRY_R, 478), fill="white",
                           outline=DARK, width=3)
        self.category_text = c.create_text(sum(self.ENTRY_R) // 2, 478,
                                           text="---", fill=DARK,
                                           font=(FONT, 17, "bold"))

        # ---- bottom buttons
        make_button(c, "PREVIOUS", 400, 550, 210, 48, self.go_previous)
        make_button(c, "SAVE AND EXIT", 720, 550, 250, 48, self.save_and_exit)

        # mini tutorial button (top right of the card)
        self.tutorial = None
        make_button(c, " HOW TO USE ?", 940, 62, 170, 34, self.open_tutorial, size=12)

    # ----- drawing helpers
    @staticmethod
    def box(xs, y, h=52):
        return xs[0], y - h // 2, xs[1], y + h // 2

    def label(self, c, text, x, y):
        c.create_text(x, y, text=text, font=(FONT, 16, "bold"), fill=DARK, anchor="w")

    def section(self, c, text, y):
        c.create_text(100, y, text=text, font=(FONT, 14, "bold"), fill=GREEN, anchor="w")
        c.create_line(100, y + 17, 1020, y + 17, fill=GREEN, width=2)

    # ----- error display
    def show_error(self, message):
        self.c.itemconfig(self.error, text="INVALID INPUT - " + message, state="normal")

    def hide_error(self):
        self.c.itemconfig(self.error, state="hidden")

    def mark_invalid(self, entry, reason):
        """Red box + light red background + short reason underneath."""
        entry.config(bg="#ffd9d9", highlightbackground="#d00000",
                     highlightcolor="#d00000")
        self.c.itemconfig(self.reason_items[entry], text=reason, state="normal")

    def mark_normal(self, entry):
        entry.config(bg=FIELD, highlightbackground=DARK, highlightcolor=GREEN)
        self.c.itemconfig(self.reason_items[entry], state="hidden")

    def clear_marks(self):
        for entry in self.entries:
            self.mark_normal(entry)

    def on_edit(self, entry):
        """When the user types in a red box, it turns normal again."""
        self.mark_normal(entry)
        if not any(e.cget("highlightbackground") == "#d00000" for e in self.entries):
            self.hide_error()

    # ----- tutorial
    def open_tutorial(self):
        if self.tutorial is not None and self.tutorial.winfo_exists():
            self.tutorial.lift()
            return
        self.tutorial = TutorialWindow(self)

    def close_tutorial(self):
        if self.tutorial is not None and self.tutorial.winfo_exists():
            self.tutorial.close()
        self.tutorial = None

    def reset_result(self):
        self.last_result = None
        self.c.itemconfig(self.result_text, text="")
        self.c.itemconfig(self.category_text, text="---", fill=DARK)

    # ----- actions
    def calculate(self):
        self.hide_error()
        self.clear_marks()
        self.reset_result()

        weight, weight_msg = number_check(self.weight.get(), "Weight", 65)
        height, height_msg = number_check(self.height.get(), "Height", 170)
        checks = [
            ("NAME", self.name, name_error(self.name.get())),
            ("AGE", self.age, age_error(self.age.get())),
            ("WEIGHT", self.weight, weight_msg),
            ("HEIGHT", self.height, height_msg),
        ]
        wrong = [(label, entry, msg) for label, entry, msg in checks if msg]
        if wrong:
            for _, entry, msg in wrong:
                self.mark_invalid(entry, msg)
            wrong[0][1].focus_set()
            return self.show_error(", ".join(label for label, _, _ in wrong))

        bmi = weight / ((height / 100) ** 2)
        category = get_category(bmi)
        self.last_result = (round(bmi, 1), category)
        self.c.itemconfig(self.result_text, text=f"{bmi:.1f}")
        self.c.itemconfig(self.category_text, text=category,
                          fill=CATEGORY_COLORS[category])

    def clear_all(self):
        for entry in (self.name, self.age, self.weight, self.height):
            entry.delete(0, tk.END)
        self.clear_marks()
        self.hide_error()
        self.reset_result()

    def go_previous(self):
        self.close_tutorial()
        self.clear_all()
        self.app.show("splash")

    def save_and_exit(self):
        self.calculate()                    # makes sure the result is up to date
        if self.last_result is None:        # invalid input -> do not save
            return
        if not ensure_pillow(self):         # needed to draw the receipt picture
            return
        bmi, category = self.last_result
        now = datetime.now()
        info = {"when": now, "name": self.name.get().strip(),
                "age": self.age.get().strip(),
                "weight": self.weight.get().strip(),
                "height": self.height.get().strip(),
                "bmi": bmi, "category": category}

        try:
            # 1) receipt picture (one per patient)
            os.makedirs(RECEIPT_DIR, exist_ok=True)
            safe_name = re.sub(r"[^A-Za-z0-9]+", "_", info["name"]).strip("_")
            receipt_path = os.path.join(
                RECEIPT_DIR, f"{safe_name}_{now.strftime('%Y%m%d_%H%M%S')}.png")
            make_receipt_image(receipt_path, info)

            # 2) one-line record added to the main list
            new_file = not os.path.exists(SAVE_FILE)
            with open(SAVE_FILE, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(["Date/Time", "Name", "Age", "Weight (kg)",
                                     "Height (cm)", "BMI", "Category"])
                writer.writerow([now.strftime("%Y-%m-%d %H:%M:%S"), info["name"],
                                 info["age"], info["weight"], info["height"],
                                 bmi, category])
        except OSError as error:
            messagebox.showerror("Could not save",
                                 f"The record was not saved.\n\n{error}")
            return

        # show the receipt picture (print it if you want), then go back to start
        self.close_tutorial()
        show_receipt_window(self.app, receipt_path)
        self.clear_all()
        self.app.show("splash")


# ----------------------------------------------------------------- main app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CvSU CareScale - BMI Calculator")
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        self.screens = {"splash": SplashScreen(self), "bmi": BMIScreen(self)}
        self.show("splash")

    def show(self, name):
        for screen in self.screens.values():
            screen.pack_forget()
        self.screens[name].pack()


if __name__ == "__main__":
    App().mainloop()
