"""Print cookie counts for a Zesje host without exposing cookie values."""
import sqlite3
import sys
import time

db, host = sys.argv[1:]
con = sqlite3.connect(db)
try:
    rows = con.execute('SELECT expires_utc, substr(encrypted_value,1,3) FROM cookies WHERE host_key IN (?, ?)', (host, '.' + host)).fetchall()
    now = int((time.time() + 11644473600) * 1000000)
    print(f'Zesje host cookies: {len(rows)}; nonexpired or session: {sum(not expiry or expiry > now for expiry, _ in rows)}; encryption versions: {sorted({bytes(version).decode("ascii", "replace") for _, version in rows})}')
finally:
    con.close()
