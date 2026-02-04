import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from pathlib import Path
import json
import sys
import os
import winsound
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# ----- Defaults -----
DEFAULT_SET_MINUTES = 30
DEFAULT_PING_VALUE = 5
DEFAULT_PING_UNIT = "Minutes"  # Off | Seconds | Minutes
DEFAULT_VOLUME = 50  # 0-100

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

        # MUCH smaller minimum size
        self.geometry("300x170+100+100")
        self.minsize(150, 110)

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
        self.ping_unit = DEFAULT_PING_UNIT
        self.ping_interval_seconds = self._calc_ping_interval_seconds()
        self.volume = DEFAULT_VOLUME

        # Initialize pygame mixer if available
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
            except:
                pass

        # Fonts scale dynamically
        self.font_timer = tkfont.Font(family="Segoe UI", size=24, weight="bold")
        self.font_info  = tkfont.Font(family="Segoe UI", size=8)
        self.font_count = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        self._load_state()
        self._build_ui()
        self._update_settings_controls_from_state()
        self._update_display()

        # keyboard shortcuts
        self.bind("<space>", lambda e: self.toggle())
        self.bind("<KeyPress-r>", lambda e: self.reset())
        self.bind("<Configure>", self._on_resize)

        # drag state
        self._drag_start_x = 0
        self._drag_start_y = 0


    # ---------- Drag ----------
    def _start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag(self, event):
        x = self.winfo_x() + event.x - self._drag_start_x
        y = self.winfo_y() + event.y - self._drag_start_y
        self.geometry(f"+{x}+{y}")


    # ---------- UI ----------
    def _build_ui(self):

        outer = ttk.Frame(self, padding=6)
        outer.pack(fill="both", expand=True)
        outer.pack_propagate(False)

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
        style.configure("Drag.TLabel", font=self.font_info, foreground="#999", cursor="fleur")

        # Time display
        self.time_lbl = ttk.Label(outer, text="00:00:00", style="Timer.TLabel")
        self.time_lbl.grid(row=0, column=0, columnspan=4, pady=(0, 4), sticky="ew")

        # Drag handle (overlaid on top-left corner)
        self.drag_lbl = ttk.Label(outer, text="⋮⋮", style="Drag.TLabel")
        self.drag_lbl.place(x=0, y=0)
        self.drag_lbl.bind("<Button-1>", self._start_drag)
        self.drag_lbl.bind("<B1-Motion>", self._on_drag)

        # Buttons row
        self.start_btn = ttk.Button(outer, text="▶", command=self.toggle)
        self.start_btn.grid(row=1, column=0, sticky="ew", padx=2)

        self.reset_btn = ttk.Button(outer, text="⟲", command=self.reset)
        self.reset_btn.grid(row=1, column=1, sticky="ew", padx=2)

        self.minus_btn = ttk.Button(outer, text="−", command=self.minus_set)
        self.minus_btn.grid(row=1, column=2, sticky="ew", padx=2)

        self.plus_btn = ttk.Button(outer, text="+", command=self.plus_set)
        self.plus_btn.grid(row=1, column=3, sticky="ew", padx=2)

        # Sets row
        self.count_lbl = ttk.Label(outer, text=self._count_text(), style="Count.TLabel")
        self.count_lbl.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 4))

        self.reset_sets_btn = ttk.Button(outer, text="0", width=2, command=self.reset_sets_to_zero)
        self.reset_sets_btn.grid(row=2, column=3, sticky="e")

        # Settings row
        ttk.Label(outer, text="Set:", style="Info.TLabel").grid(row=3, column=0, sticky="w")
        self.set_len_spin = tk.Spinbox(outer, from_=1, to=999, width=3, justify="right")
        self.set_len_spin.grid(row=3, column=1, sticky="w")

        ttk.Label(outer, text="min", style="Info.TLabel").grid(row=3, column=1, sticky="e")

        ttk.Label(outer, text="Ping:", style="Info.TLabel").grid(row=4, column=0, sticky="w", pady=(4, 0))
        self.ping_value_spin = tk.Spinbox(outer, from_=1, to=3600, width=3, justify="right")
        self.ping_value_spin.grid(row=4, column=1, sticky="w", pady=(4, 0))

        self.ping_unit_combo = ttk.Combobox(outer, values=["Off", "Seconds", "Minutes"],
                                            state="readonly", width=8)
        self.ping_unit_combo.grid(row=4, column=2, sticky="w", pady=(4, 0))

        self.apply_btn = ttk.Button(outer, text="Apply", command=self.apply_settings)
        self.apply_btn.grid(row=4, column=3, sticky="e", pady=(4, 0))

        # Volume control
        ttk.Label(outer, text="Vol:", style="Info.TLabel").grid(row=5, column=0, sticky="w", pady=(4, 0))
        self.volume_scale = ttk.Scale(outer, from_=0, to=100, orient="horizontal", command=self._on_volume_change)
        self.volume_scale.set(self.volume)
        self.volume_scale.grid(row=5, column=1, columnspan=2, sticky="ew", pady=(4, 0))

        self.volume_lbl = ttk.Label(outer, text=f"{int(self.volume)}%", style="Info.TLabel")
        self.volume_lbl.grid(row=5, column=3, sticky="w", pady=(4, 0))

        # Tip (WRAPS — no more fixed giant width)
        tip = ttk.Label(
            outer,
            text="Space=start/pause, R=reset",
            style="Info.TLabel",
            foreground="#666",
            wraplength=160
        )
        tip.grid(row=6, column=0, columnspan=4, pady=(4, 0), sticky="w")


    def _count_text(self):
        return f"Sets: {self.sets_done}"


    def _on_volume_change(self, value):
        self.volume = float(value)
        self.volume_lbl.config(text=f"{int(self.volume)}%")
        self._save_state()


    def _update_settings_controls_from_state(self):
        self.set_len_spin.delete(0, "end")
        self.set_len_spin.insert(0, str(self.set_minutes))

        self.ping_value_spin.delete(0, "end")
        self.ping_value_spin.insert(0, str(self.ping_value))

        self.ping_unit_combo.set(self.ping_unit)

        self.volume_scale.set(self.volume)
        self.volume_lbl.config(text=f"{int(self.volume)}%")


    # ---------- Timer logic ----------
    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def start(self):
        if self.remaining <= 0:
            self.remaining = self.target_seconds
            self._update_display()

        if self.running:
            return
        self.running = True
        self.start_btn.config(text="⏸")
        self._tick()

    def pause(self):
        self.running = False
        self.start_btn.config(text="▶")
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

        if self.remaining > 0:
            self.remaining -= 1

        self._update_display()

        # Ping
        if self.ping_interval_seconds and self.ping_interval_seconds > 0:
            elapsed = self.target_seconds - self.remaining
            if elapsed > 0 and elapsed % self.ping_interval_seconds == 0:
                self._beep_ok()

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

        if messagebox.askyesno("Set complete!", "Start next set?"):
            self.remaining = self.target_seconds
            self.start()

    def _update_display(self):
        self.time_lbl.config(text=fmt(self.remaining))

    # ---------- Set adjust ----------
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
        if messagebox.askyesno("Reset sets?", "Reset Sets to 0?"):
            self.sets_done = 0
            self.count_lbl.config(text=self._count_text())
            self._save_state()

    # ---------- Settings ----------
    def _calc_ping_interval_seconds(self):
        if self.ping_unit == "Off": return None
        if self.ping_unit == "Seconds": return max(1, int(self.ping_value))
        if self.ping_unit == "Minutes": return max(1, int(self.ping_value)) * 60
        return None

    def apply_settings(self):
        try: new_set_minutes = max(1, int(self.set_len_spin.get()))
        except: new_set_minutes = self.set_minutes

        try: new_ping_value = max(1, int(self.ping_value_spin.get()))
        except: new_ping_value = self.ping_value

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
                self.volume = float(data.get("volume", DEFAULT_VOLUME))
                self.target_seconds = self.set_minutes * 60
                self.ping_interval_seconds = self._calc_ping_interval_seconds()
                self.remaining = self.target_seconds
        except:
            pass

    def _save_state(self):
        try:
            PERSIST_PATH.mkdir(parents=True, exist_ok=True)
            payload = {
                "sets_done": self.sets_done,
                "set_minutes": self.set_minutes,
                "ping_value": self.ping_value,
                "ping_unit": self.ping_unit,
                "volume": self.volume,
            }
            PERSIST_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except:
            pass

    # ---------- Sounds ----------
    def _beep_ok(self):
        try:
            sound_file = os.path.join(os.path.dirname(__file__), "ding.wav")
            if os.path.exists(sound_file) and PYGAME_AVAILABLE:
                sound = pygame.mixer.Sound(sound_file)
                sound.set_volume(self.volume / 100.0)
                sound.play()
            elif os.path.exists(sound_file):
                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_OK)
        except:
            pass

    def _beep_exclaim(self):
        try:
            sound_file = os.path.join(os.path.dirname(__file__), "ting.wav")
            if os.path.exists(sound_file) and PYGAME_AVAILABLE:
                sound = pygame.mixer.Sound(sound_file)
                sound.set_volume(self.volume / 100.0)
                sound.play()
            elif os.path.exists(sound_file):
                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except:
            pass

    # ---------- Auto resize ----------
    def _on_resize(self, event):
        try:
            w = self.winfo_width()
            timer_size = max(12, min(40, int(w / 8)))
            info_size  = max(7,  min(11, int(w / 30)))
            count_size = max(8,  min(13, int(w / 22)))

            self.font_timer.configure(size=timer_size)
            self.font_info.configure(size=info_size)
            self.font_count.configure(size=count_size)
        except:
            pass

    def destroy(self):
        self._save_state()
        super().destroy()



if __name__ == "__main__":
    if sys.platform.startswith("win"):
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
    app = ThirtyTimer()
    app.mainloop()