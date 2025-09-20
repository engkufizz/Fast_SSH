import customtkinter as ctk
import subprocess
import datetime
import os
import sys
import sqlite3
import shutil
from tkinter import messagebox as tkmsg
import threading
import time
import tempfile
import getpass
import json

# ------------- Configuration -------------

# Auto-detect SSH username, but allow override via SSH_USERNAME env var
def detect_ssh_username():
    # Highest priority: explicit environment variable
    env = os.getenv("SSH_USERNAME")
    if env:
        return env.strip()

    # Common environment variables used by OSes
    for var in ("USER", "USERNAME", "LOGNAME"):
        v = os.getenv(var)
        if v:
            return v.strip()

    # Fallbacks
    try:
        u = getpass.getuser()
        if u:
            return u.strip()
    except Exception:
        pass

    try:
        u = os.getlogin()
        if u:
            return u.strip()
    except Exception:
        pass

    # None if detection fails; we'll prompt when needed
    return None

def _user_roaming_dir():
    if sys.platform == "win32":
        return os.getenv("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.expanduser("~")

# Prefer this directory for PuTTY/plink (user-agnostic; no hard-coded usernames)
PREFERRED_PUTTY_DIRS = [
    os.path.join(_user_roaming_dir(), "putty"),
]

# ------------- Path helpers for frozen/non-frozen -------------

def is_frozen():
    return getattr(sys, "frozen", False)

def resource_path(*relative):
    """
    Path helper for read-only bundled assets.
    When frozen (onefile), PyInstaller extracts files to sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *relative)

def app_dir():
    """
    Directory of the running executable when frozen, else the script directory.
    """
    return os.path.dirname(sys.executable) if is_frozen() else os.path.dirname(os.path.abspath(__file__))

def user_data_dir():
    """
    User-writable data directory for logs and any runtime files.
    """
    root = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "NESearchTool")

def ensure_log_dir():
    """
    Try to use a 'logs' folder beside the app. If not writable, fall back to user data,
    then finally to a temp folder. Returns a usable directory path.
    """
    candidates = [
        os.path.join(app_dir(), "logs"),
        os.path.join(user_data_dir(), "logs"),
        os.path.join(tempfile.gettempdir(), "NESearchTool", "logs"),
    ]
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            testfile = os.path.join(d, ".__writetest.tmp")
            with open(testfile, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(testfile)
            return d
        except Exception:
            continue
    # Last resort
    d = os.path.join(tempfile.gettempdir(), "NESearchTool", "logs")
    os.makedirs(d, exist_ok=True)
    return d

BASE_DIR = app_dir()
DB_FILE = resource_path("ne_database.db")  # Ensure this file is added when packaging
LOG_DIR = ensure_log_dir()
CONFIG_FILE = os.path.join(user_data_dir(), "settings.json")

def load_username_from_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            u = data.get("ssh_username")
            if u:
                return str(u).strip()
    except Exception:
        pass
    return None

def save_username_to_config(username):
    try:
        os.makedirs(user_data_dir(), exist_ok=True)
        data = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        data["ssh_username"] = username
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        # Non-fatal if save fails
        pass

# ------------- Utilities -------------

def _sanitize_filename_part(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-", ".", "@") else "_" for c in s)

def _existing(path: str) -> bool:
    try:
        return bool(path and os.path.exists(path))
    except Exception:
        return False

def _find_exe_in_dir(basenames, directory):
    if not directory:
        return None
    for b in basenames:
        p = os.path.join(directory, b)
        if _existing(p):
            return p
    return None

def _find_putty():
    # 1) User-preferred directories first
    for pref in PREFERRED_PUTTY_DIRS:
        p = _find_exe_in_dir(["putty.exe", "putty"], pref)
        if p:
            return p
    # 2) PATH
    for b in ["putty.exe", "putty"]:
        w = shutil.which(b)
        if _existing(w):
            return w
    # 3) Common installs and local dirs
    common_dirs = [
        r"C:\Program Files\PuTTY",
        r"C:\Program Files (x86)\PuTTY",
        BASE_DIR,
        os.path.join(os.path.expanduser("~"), "Desktop"),
    ]
    for d in common_dirs:
        p = _find_exe_in_dir(["putty.exe", "putty"], d)
        if p:
            return p
    return None

def _find_plink():
    # 1) User-preferred directories
    for pref in PREFERRED_PUTTY_DIRS:
        p = _find_exe_in_dir(["plink.exe", "plink"], pref)
        if p:
            return p
    # 2) PATH
    for b in ["plink.exe", "plink"]:
        w = shutil.which(b)
        if _existing(w):
            return w
    # 3) Common installs and local dirs
    for d in [r"C:\Program Files\PuTTY", r"C:\Program Files (x86)\PuTTY", BASE_DIR]:
        p = _find_exe_in_dir(["plink.exe", "plink"], d)
        if p:
            return p
    return None

def _show_startup_error(title, msg):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(title, msg)
        r.destroy()
    except Exception:
        try:
            print(f"{title}: {msg}")
        except Exception:
            pass

# ------------- App -------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NE Search, Copy & Login Tool (DB Mode)")
        self.geometry("600x500")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # Detected SSH username (can be None; we will prompt when first needed)
        self.ssh_username = detect_ssh_username()
        # If a saved username exists, prefer it over detection
        _saved = load_username_from_config()
        if _saved:
            self.ssh_username = _saved

        # Apply window/taskbar icon (ensure app.ico is available)
        self._apply_app_icon()

        # Ensure logs dir exists
        os.makedirs(LOG_DIR, exist_ok=True)

        # Top controls
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=(10, 0))

        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(top, textvariable=self.search_var, placeholder_text="Type search term and press Enter...")
        search_entry.pack(side="left", padx=(0, 8), pady=8, fill="x", expand=True)
        search_entry.focus()
        search_entry.bind("<Return>", self._perform_search)

        logs_btn = ctk.CTkButton(top, text="Open Logs Folder", width=140, command=self._open_logs_folder)
        logs_btn.pack(side="right", pady=8)

        # Username panel
        userframe = ctk.CTkFrame(self)
        userframe.pack(fill="x", padx=10, pady=(8, 0))

        ctk.CTkLabel(userframe, text="SSH Username:").pack(side="left", padx=(10, 6), pady=8)
        self.username_var = ctk.StringVar(value=self.ssh_username or "")
        uname_entry = ctk.CTkEntry(userframe, textvariable=self.username_var, width=220, placeholder_text="e.g. admin")
        uname_entry.pack(side="left", padx=(0, 10), pady=8)

        apply_btn = ctk.CTkButton(userframe, text="Apply", width=80, command=self._apply_username)
        apply_btn.pack(side="left", padx=(0, 6), pady=8)

        reset_btn = ctk.CTkButton(userframe, text="Set to Default", width=110, command=self._reset_username_to_detected)
        reset_btn.pack(side="left", padx=(0, 6), pady=8)

        # Results
        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="Results")
        self.scrollable_frame.pack(pady=10, padx=10, fill="both", expand=True)

    def _apply_app_icon(self):
        """
        Applies the app icon so that the titlebar and taskbar show the same icon on Windows.
        Ensure there is an 'app.ico' file accessible via resource_path.
        """
        try:
            ico_path = resource_path("app.ico")
            if sys.platform == "win32" and os.path.exists(ico_path):
                # On Windows, .ico is required for taskbar
                self.iconbitmap(ico_path)
        except Exception:
            # Silently ignore if icon not found or not supported on platform
            pass

    def _open_logs_folder(self):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", LOG_DIR])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", LOG_DIR])
            else:
                subprocess.Popen(["xdg-open", LOG_DIR])
        except Exception as e:
            tkmsg.showerror("Error", f"Failed to open logs folder:\n{e}")

    def _perform_search(self, event=None):
        search_term = self.search_var.get().strip()
        if not search_term:
            self._update_results_ui([])
            return
        try:
            db_path = DB_FILE
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            query = "SELECT name, ip FROM network_elements WHERE name LIKE ? ORDER BY name LIMIT 100"
            results = cursor.execute(query, ('%' + search_term + '%',)).fetchall()
            conn.close()
            self._update_results_ui(results)
        except Exception as e:
            tkmsg.showerror("Database error", f"Failed to query database:\n{e}")

    def _update_results_ui(self, results):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        if not results:
            ctk.CTkLabel(self.scrollable_frame, text="No results").pack(pady=10)
            return

        for name, ip in results:
            row = ctk.CTkFrame(self.scrollable_frame)
            row.pack(fill="x", pady=4, padx=4)
            label_text = f"{name} ({ip})"
            ctk.CTkLabel(row, text=label_text, anchor="w").pack(side="left", expand=True, fill="x", padx=10)
            login_button = ctk.CTkButton(
                row, text="Login", width=80, fg_color="#28a745", hover_color="#218838",
                command=lambda n=name, i=ip: self._login_and_log_session(n, i)
            )
            login_button.pack(side="right", padx=(0, 5), pady=5)
            copy_button = ctk.CTkButton(
                row, text="Copy", width=80,
                command=lambda ip_addr=ip: self._copy_to_clipboard(ip_addr)
            )
            copy_button.pack(side="right", padx=5, pady=5)

    def _apply_username(self):
        u = (self.username_var.get() or "").strip()
        if not u:
            tkmsg.showerror("Invalid username", "Please enter a valid SSH username.")
            return
        self.ssh_username = u
        save_username_to_config(u)
        try:
            tkmsg.showinfo("Username updated", f"SSH username set to: {u}")
        except Exception:
            pass

    def _reset_username_to_detected(self):
        detected = detect_ssh_username() or ""
        self.username_var.set(detected)
        self.ssh_username = detected
        if detected:
            save_username_to_config(detected)
            try:
                tkmsg.showinfo("Username reset", f"SSH username reset to default: {detected}")
            except Exception:
                pass
        else:
            try:
                tkmsg.showwarning("No username detected", "Could not auto-detect a default username. Please enter one manually.")
            except Exception:
                pass

    def _ensure_username(self):
        """
        Ensure we have a usable SSH username. Prefer the panel's current value.
        If empty, try saved/detected; else prompt once.
        """
        # 1) Prefer entry value
        entry_val = (self.username_var.get() or "").strip() if hasattr(self, "username_var") else ""
        if entry_val:
            self.ssh_username = entry_val
            save_username_to_config(entry_val)
            return entry_val

        # 2) Fall back to stored/detected value
        if self.ssh_username:
            return self.ssh_username

        # 3) Prompt user
        try:
            dialog = ctk.CTkInputDialog(title="SSH Username", text="Enter SSH username:")
            username = dialog.get_input()
            if username:
                username = username.strip()
                self.ssh_username = username
                try:
                    self.username_var.set(username)
                except Exception:
                    pass
                save_username_to_config(username)
        except Exception:
            pass
        if not self.ssh_username:
            tkmsg.showerror("Username required", "No SSH username detected or provided.")
        return self.ssh_username

    def _copy_to_clipboard(self, ip_address):
        username = self._ensure_username()
        if not username:
            return
        command = f"ssh {username}@{ip_address}"
        self.clipboard_clear()
        self.clipboard_append(command)
        try:
            self.after(0, lambda: tkmsg.showinfo("Copied", f"Copied to clipboard:\n{command}"))
        except Exception:
            pass

    def _login_and_log_session(self, name, ip):
        if sys.platform != "win32":
            tkmsg.showerror("Unsupported OS", "This feature requires Windows.")
            return

        username = self._ensure_username()
        if not username:
            return

        try:
            safe_name = _sanitize_filename_part(name)
            safe_ip = _sanitize_filename_part(ip)
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
            os.makedirs(LOG_DIR, exist_ok=True)
            log_filename = os.path.join(LOG_DIR, f"ssh_{safe_name}_{safe_ip}_{timestamp}.log")

            putty = _find_putty()
            plink = _find_plink()

            if putty:
                # IMPORTANT: Put all options before the host for reliability
                args = [
                    putty,
                    "-ssh",
                    "-l", username,
                    "-sessionlog", log_filename,
                    "-logappend",
                    ip,
                ]
                subprocess.Popen(args)
                threading.Thread(target=self._warn_if_log_stays_empty, args=(log_filename,), daemon=True).start()
                return

            if plink:
                # IMPORTANT: With plink, all options MUST be before the host
                args = [
                    plink,
                    "-ssh",
                    "-t",
                    "-sessionlog", log_filename,
                    "-logappend",
                    f"{username}@{ip}",
                ]
                # CREATE_NEW_CONSOLE is Windows-only; platform already checked above
                subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
                threading.Thread(target=self._warn_if_log_stays_empty, args=(log_filename,), daemon=True).start()
                return

            tkmsg.showerror(
                "No SSH client found",
                "Could not find putty.exe or plink.exe.\n\n"
                f"Looked in: {', '.join([d for d in PREFERRED_PUTTY_DIRS if d])} and PATH."
            )
        except Exception as e:
            tkmsg.showerror("Error", f"An error occurred:\n{e}")

    def _warn_if_log_stays_empty(self, path):
        try:
            time.sleep(8)
            # Some PuTTY versions create the file only after login; check existence or zero size
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                tkmsg.showwarning(
                    "Log not created",
                    "The log file was not created or is still empty.\n\n"
                    "Possible causes:\n"
                    "- You closed the session before login.\n"
                    "- Your PuTTY/plink is too old to support command-line session logging.\n"
                    "Please update to the latest PuTTY (0.76 or newer) or install KiTTY."
                )
        except Exception:
            pass

# ------------- Entry point -------------

if __name__ == "__main__":
    try:
        # Ensure user data directories exist
        os.makedirs(LOG_DIR, exist_ok=True)

        # Windows: set AppUserModelID for correct taskbar grouping + icon
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NESearchTool.1.0")
            except Exception:
                pass

        # Check database exists where expected
        if not os.path.exists(DB_FILE):
            _show_startup_error(
                "Database not found",
                f"Could not find the database at:\n{DB_FILE}\n\n"
                "When packaging, include 'ne_database.db' as an Additional File:\n"
                "  - Source: path to ne_database.db\n"
                "  - Destination: ."
            )
            sys.exit(1)

        app = App()
        app.mainloop()
    except Exception as e:
        _show_startup_error("Fatal error", f"{e}")
        raise
