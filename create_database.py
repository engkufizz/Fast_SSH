import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "ne_database.db") 
TXT_FILE = os.path.join(BASE_DIR, "List.txt")

def build_database():
    """Reads List.txt and populates a new SQLite database."""
    if not os.path.exists(TXT_FILE):
        print(f"Error: '{TXT_FILE}' not found. Cannot build database.")
        return

    # Delete old database if it exists to ensure a fresh build
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"Removed old database '{DB_FILE}'.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create table
    cursor.execute('''
        CREATE TABLE network_elements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            ip TEXT NOT NULL
        )
    ''')
    # Create an index on the name column for faster searching
    cursor.execute('CREATE INDEX idx_name ON network_elements (name)')

    # Read the text file and insert data
    count = 0
    with open(TXT_FILE, 'r', encoding='utf-8') as f:
        next(f, None)  # Skip header line if present
        for line in f:
            if ',' in line:
                name, ip = [item.strip() for item in line.split(',', 1)]
                if not name or not ip:
                    continue
                try:
                    cursor.execute("INSERT INTO network_elements (name, ip) VALUES (?, ?)", (name, ip))
                    count += 1
                except sqlite3.IntegrityError:
                    print(f"Warning: Duplicate NE name '{name}' found. Skipping.")

    conn.commit()
    conn.close()
    print(f"Successfully created '{DB_FILE}' with {count} entries.")

if __name__ == "__main__":
    build_database()
