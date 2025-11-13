import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from pathlib import Path
import json
import sys
import os
import winsound

# ----- Defaults -----
DEFAULT_SET_MINUTES = 30
DEFAULT_PING_VALUE = 5
DEFAULT_PING_UNIT = "Minutes"  # Off | Seconds | Minutes

PERSIST_PATH = Path.home() / "AppData/Local/ThirtyTimer"
PERSIST_FILE = PERSIST_PATH / "state.json"

def fmt(seconds: int) -> str:
    if seconds < 0: seconds = 0
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

class ThirtyTimer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Thirty Timer")
        self.geometry("340x210+100+100")  # starting size; user can resize
        self.minsize(220, 150)            # small but usable
        self.resizable(True, True)
        self.attributes("-topmost", True)
        self.configure(bg="#F3F3F3")

        # state
        self.set_minutes = DEFAULT_SET_MINUTES
        self.target_seconds = self.set_minutes * 60
        self.remaining = self.target_seconds
        self.running = False
        self.sets_done = 0
        self.after_id = None

        self.ping_value = DEFAULT_PING_VALUE
        self.ping_unit = DEFAULT_PING_UNIT  # Off | Seconds | Minutes
        self.ping_interval_seconds = self._calc_ping_interval_seconds()

        # Fonts that auto-scale
        self.font_timer = tkfont.Font(family="Segoe UI", size=28, weight="bold")
        self.font_info  = tkfont.Font(family="Segoe UI", size=9)
        self.font_count = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        self._load_state()
        self._build_ui()
        self._update_settings_controls_from_state()
        self._update_display()

        # keyboard shortcuts
        self.bind("<space>", lambda e: self.toggle())
        self.bind("<KeyPress-r>", lambda e: self.reset())
        # auto-scale on resize
        self.bind("<Configure>", self._on_resize)

    # ---------- UI ----------
    def _build_ui(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        # grid stretch
        for c in range(4):
            outer.columnconfigure(c, weight=1)

        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            pass
        style.configure("Timer.TLabel", font=self.font_timer)
        style.configure("Info.TLabel", font=self.font_info)
        style.configure("Count.TLabel", font=self.font_count)

        # Time display
        self.time_lbl = ttk.Label(outer, text="00:00:00", style="Timer.TLabel")
        self.time_lbl.grid(row=0, column=0, columnspan=4, pady=(0, 8), sticky="w")

        # Controls
        self.start_btn = ttk.Button(outer, text="▶ Start", command=self.toggle)
        self.start_btn.grid(row=1, column=0, padx=(0,6), sticky="ew")

        self.reset_btn = ttk.Button(outer, text="⟲ Reset", command=self.reset)
        self.reset_btn.grid(row=1, column=1, padx=(6,6), sticky="ew")

        self.minus_btn = ttk.Button(outer, text="−", width=3, command=self.minus_set)
        self.minus_btn.grid(row=1, column=2, sticky="ew")

        self.plus_btn = ttk.Button(outer, text="+", width=3, command=self.plus_set)
        self.plus_btn.grid(row=1, column=3, sticky="ew")

        # Sets row + Reset Sets
        self.count_lbl = ttk.Label(outer, text=self._count_text(), style="Count.TLabel")
        self.count_lbl.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6,8))
        self.reset_sets_btn = ttk.Button(outer, text="Reset Sets", command=self.reset_sets_to_zero)
        self.reset_sets_btn.grid(row=2, column=3, sticky="e", pady=(6,8))

        # Settings row
        # Set length
        ttk.Label(outer, text="Set length:", style="Info.TLabel").grid(row=3, column=0, sticky="w")
        self.set_len_spin = tk.Spinbox(
            outer, from_=1, to=999, width=5, justify="right", repeatdelay=300, repeatinterval=60
        )
        self.set_len_spin.grid(row=3, column=1, sticky="w", padx=(6,12))
        ttk.Label(outer, text="min", style="Info.TLabel").grid(row=3, column=1, sticky="e")

        # Ping every
        ttk.Label(outer, text="Ping every:", style="Info.TLabel").grid(row=4, column=0, sticky="w", pady=(4,0))
        self.ping_value_spin = tk.Spinbox(
            outer, from_=1, to=3600, width=5, justify="right", repeatdelay=300, repeatinterval=60
        )
        self.ping_value_spin.grid(row=4, column=1, sticky="w", padx=(6,6), pady=(4,0))
        self.ping_unit_combo = ttk.Combobox(
            outer, values=["Off", "Seconds", "Minutes"], state="readonly", width=9
        )
        self.ping_unit_combo.grid(row=4, column=2, sticky="w", pady=(4,0))

        self.apply_btn = ttk.Button(outer, text="Apply", command=self.apply_settings)
        self.apply_btn.grid(row=4, column=3, sticky="e", pady=(4,0))

        tip = ttk.Label(
            outer,
            text="(Space = Start/Pause, R = Reset)  •  Apply saves & resets to new set length",
            style="Info.TLabel", foreground="#666", wraplength=9999
        )
        tip.grid(row=5, column=0, columnspan=4, pady=(8,0), sticky="w")

    def _count_text(self):
        return f"Sets done: {self.sets_done}"

    def _update_settings_controls_from_state(self):
        self.set_len_spin.delete(0, "end"); self.set_len_spin.insert(0, str(self.set_minutes))
        self.ping_value_spin.delete(0, "end"); self.ping_value_spin.insert(0, str(self.ping_value))
        self.ping_unit_combo.set(self.ping_unit)

    # ---------- Timer logic ----------
    def toggle(self):
        if self.running: self.pause()
        else: self.start()

    def start(self):
        # If timer is at 0, start a fresh set instead of completing instantly
        if self.remaining <= 0:
            self.remaining = self.target_seconds
            self._update_display()

        if self.running:
            return
        self.running = True
        self.start_btn.config(text="⏸ Pause")
        self._tick()

    def pause(self):
        self.running = False
        self.start_btn.config(text="▶ Start")
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

    def reset(self):
        self.pause()
        self.remaining = self.target_seconds
        self._update_display()

    def _tick(self):
        if not self.running:
            return

        # Only decrement if we're above zero
        if self.remaining > 0:
            self.remaining -= 1
        self._update_display()

        # Awareness ping (plays ting.wav)
        if self.ping_interval_seconds and self.ping_interval_seconds > 0:
            elapsed = self.target_seconds - self.remaining
            if elapsed > 0 and elapsed % self.ping_interval_seconds == 0:
                self._beep_ok()

        # Handle completion
        if self.remaining <= 0:
            self.remaining = 0
            self._update_display()
            self._on_complete()
        else:
            self.after_id = self.after(1000, self._tick)


    def _on_complete(self):
        self.pause()
        self.sets_done += 1
        self.count_lbl.config(text=self._count_text())
        self.remaining = 0
        self._update_display()
        self._save_state()
        self._beep_exclaim()

        if messagebox.askyesno("Set complete!", "Nice! Start the next set?"):
            self.remaining = self.target_seconds
            self.start()

    def _update_display(self):
        self.time_lbl.config(text=fmt(self.remaining))

    # ---------- Set adjust buttons ----------
    def plus_set(self):
        self.sets_done += 1
        self.count_lbl.config(text=self._count_text())
        self._save_state()

    def minus_set(self):
        if self.sets_done > 0:
            self.sets_done -= 1
            self.count_lbl.config(text=self._count_text())
            self._save_state()

    def reset_sets_to_zero(self):
        if messagebox.askyesno("Reset sets", "Reset 'Sets done' to 0?"):
            self.sets_done = 0
            self.count_lbl.config(text=self._count_text())
            self._save_state()

    # ---------- Settings handling ----------
    def _calc_ping_interval_seconds(self):
        if self.ping_unit == "Off": return None
        if self.ping_unit == "Seconds": return max(1, int(self.ping_value))
        if self.ping_unit == "Minutes": return max(1, int(self.ping_value)) * 60
        return None

    def apply_settings(self):
        try:
            new_set_minutes = max(1, int(self.set_len_spin.get()))
        except Exception:
            new_set_minutes = self.set_minutes

        try:
            new_ping_value = max(1, int(self.ping_value_spin.get()))
        except Exception:
            new_ping_value = self.ping_value

        new_ping_unit = self.ping_unit_combo.get() or "Off"
        if new_ping_unit not in ("Off", "Seconds", "Minutes"):
            new_ping_unit = "Off"

        self.set_minutes = new_set_minutes
        self.ping_value = new_ping_value
        self.ping_unit = new_ping_unit
        self.ping_interval_seconds = self._calc_ping_interval_seconds()

        self.target_seconds = self.set_minutes * 60
        self.reset()
        self._save_state()

    # ---------- Persistence ----------
    def _load_state(self):
        try:
            if PERSIST_FILE.exists():
                data = json.loads(PERSIST_FILE.read_text(encoding="utf-8"))
                self.sets_done = int(data.get("sets_done", 0))
                self.set_minutes = int(data.get("set_minutes", DEFAULT_SET_MINUTES))
                self.ping_value = int(data.get("ping_value", DEFAULT_PING_VALUE))
                self.ping_unit = str(data.get("ping_unit", DEFAULT_PING_UNIT))
                self.target_seconds = self.set_minutes * 60
                self.ping_interval_seconds = self._calc_ping_interval_seconds()
                self.remaining = self.target_seconds
        except Exception:
            self.sets_done = self.sets_done or 0

    def _save_state(self):
        try:
            PERSIST_PATH.mkdir(parents=True, exist_ok=True)
            payload = {
                "sets_done": self.sets_done,
                "set_minutes": self.set_minutes,
                "ping_value": self.ping_value,
                "ping_unit": self.ping_unit,
            }
            PERSIST_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    # ---------- Sounds ----------
    def _beep_ok(self):
        try:
            sound_file = os.path.join(os.path.dirname(__file__), "ding.wav")
            if os.path.exists(sound_file):
                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    def _beep_exclaim(self):
        try:
            sound_file = os.path.join(os.path.dirname(__file__), "ting.wav")
            if os.path.exists(sound_file):
                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    # ---------- Resizing / Auto font scale ----------
    def _on_resize(self, event):
        # Scale fonts roughly with width; clamp to sensible ranges
        try:
            w = max(self.winfo_width(), 220)
            timer_size = max(16, min(48, int(w / 9)))
            info_size  = max(8,  min(12, int(w / 35)))
            count_size = max(9,  min(14, int(w / 25)))
            self.font_timer.configure(size=timer_size)
            self.font_info.configure(size=info_size)
            self.font_count.configure(size=count_size)
        except Exception:
            pass

    def destroy(self):
        self._save_state()
        super().destroy()

if __name__ == "__main__":
    if sys.platform.startswith("win"):
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)  # crisp text
        except Exception:
            pass
    app = ThirtyTimer()
    app.mainloop()
