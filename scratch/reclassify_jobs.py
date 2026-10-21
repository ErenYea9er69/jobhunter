import json
from jh import db

def main():
    db.init_db()
    with db.session() as c:
        rows = c.execute("SELECT job_key, title, job_type, job_json FROM search_jobs").fetchall()
        print(f"Total jobs in DB: {len(rows)}")
        before_counts = {}
        for r in rows:
            jt = r["job_type"] or "Unknown"
            before_counts[jt] = before_counts.get(jt, 0) + 1
        print("Before reclassification counts:", before_counts)

        updated = 0
        for r in rows:
            raw_data = {}
            if r["job_json"]:
                try:
                    raw_data = json.loads(r["job_json"])
                except Exception:
                    pass
            raw_data["title"] = r["title"]
            raw_data["job_type"] = r["job_type"]
            c_meta = db.classify_job(raw_data)
            new_jt = c_meta["job_type"]
            raw_data["job_type"] = new_jt
            raw_data["category"] = c_meta["category"]
            raw_data["seniority"] = c_meta["seniority"]
            raw_data["work_mode"] = c_meta["work_mode"]
            raw_data["country"] = c_meta["country"]
            c.execute("UPDATE search_jobs SET job_type=?, job_json=? WHERE job_key=?", (new_jt, json.dumps(raw_data), r["job_key"]))
            if new_jt != r["job_type"]:
                updated += 1
        print(f"Updated {updated} jobs.")

        after_rows = c.execute("SELECT job_type FROM search_jobs").fetchall()
        after_counts = {}
        for r in after_rows:
            jt = r["job_type"] or "Unknown"
            after_counts[jt] = after_counts.get(jt, 0) + 1
        print("After reclassification counts:", after_counts)

if __name__ == "__main__":
    main()
