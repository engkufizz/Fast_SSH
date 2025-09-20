# NE Search, Copy & SSH Login Tool

This project provides a **GUI tool** for searching network elements from a database, copying SSH commands, and launching SSH sessions via **PuTTY** or **Plink** (with session logging).
It is designed to help network engineers quickly find and connect to devices by name or IP.

---

## Features

* 🔎 **Search** network elements stored in an SQLite database.
* 👤 **Configurable SSH username** (auto-detected, or manually set and saved).
* 📋 **One-click copy**: copies `ssh <username>@<ip>` to clipboard.
* 💻 **One-click login**: launches PuTTY or Plink with automatic session logging.
* 🗂️ **Log management**: session logs saved in a `logs` folder with timestamped filenames.
* 💾 **SQLite database backend** built from a plain text file (`List.txt`).

---

## Project Structure

```
├── Fast_SSH.py         # Main GUI application
├── create_database.py  # Script to build SQLite database from List.txt
├── List.txt            # Input file (device list: name,ip)
├── ne_database.db      # SQLite database (generated)
├── app.ico             # Optional app icon (for Windows taskbar)
```

---

## Requirements

* **Python 3.8+**

* Modules:

  * `customtkinter`
  * `tkinter` (built-in)
  * `sqlite3` (built-in)

* **Windows users**:

  * PuTTY (`putty.exe`) or Plink (`plink.exe`) must be installed or available in PATH.

---

## Setup

1. **Clone or copy the repository** to your local machine.
   (Make sure `Fast_SSH.py`, `create_database.py`, and `List.txt` are in the same folder.)

2. **Install dependencies**:

   ```bash
   pip install customtkinter
   ```

3. **Prepare your device list** (`List.txt`):
   The file should contain device names and IPs in this format:

   ```
   Name,IP
   Router1,192.168.1.1
   Switch1,192.168.1.2
   ...
   ```

4. **Build the database**:

   ```bash
   python create_database.py
   ```

   This generates `ne_database.db`.

5. **Run the tool**:

   ```bash
   python Fast_SSH.py
   ```

---

## Usage

* **Search**: Type part of a device name and press `Enter`.
* **Copy**: Copies the SSH command (`ssh username@ip`) to clipboard.
* **Login**: Launches PuTTY/Plink directly into the device, with session logs saved automatically.
* **Change SSH username**: Enter a new username in the GUI → click **Apply**.
* **Reset username**: Click **Set to Default** (auto-detects OS username or previously saved config).

---

## Logs

* Logs are stored in:

  * `logs/` folder next to the application (if writable), or
  * `%LOCALAPPDATA%/NESearchTool/logs` on Windows.

Each log file is named as:

```
ssh_<deviceName>_<ip>_<timestamp>.log
```

---

## License

MIT License – free to use, modify, and distribute.

