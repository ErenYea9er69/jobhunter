import sys
sys.path.insert(0, '.')
from jh import db

with db.session() as conn:
    conn.execute("DELETE FROM resume_profiles WHERE is_master = 0")
    conn.execute("UPDATE resume_profiles SET is_active=1, is_live=1 WHERE is_master=1")

profiles = db.list_resume_profiles()
print(f"Cleaned! Remaining profiles ({len(profiles)}): {[p['name'] for p in profiles]}")
