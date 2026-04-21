

import os
import sys
import psycopg

def main():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        for candidate in (".env", "../.env"):
            if os.path.exists(candidate):
                with open(candidate) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DATABASE_URL="):
                            db_url = line.split("=", 1)[1].strip()
                            break
            if db_url:
                break

    if not db_url:
        print("ERROR: DATABASE_URL not set and no .env found.")
        sys.exit(1)

    print(f"Connecting to database...")
    conn = psycopg.connect(db_url)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM itinerary_cache")
    itinerary_count = cur.fetchone()[0]
    print(f"itinerary_cache: {itinerary_count} rows found")

    if itinerary_count > 0:
        confirm = input(
            f"  Delete ALL {itinerary_count} itinerary_cache rows? "
            "They will be repopulated with coords on next trip. [y/N] "
        ).strip().lower()
        if confirm == "y":
            cur.execute("DELETE FROM itinerary_cache")
            print(f"  Deleted {cur.rowcount} itinerary_cache rows.")
        else:
            print("  Skipped itinerary_cache.")

    cur.execute("SELECT COUNT(*) FROM meal_cache WHERE lat IS NULL")
    meal_null_count = cur.fetchone()[0]
    print(f"meal_cache: {meal_null_count} rows with lat IS NULL")

    if meal_null_count > 0:
        confirm = input(
            f"  Delete {meal_null_count} meal_cache rows where lat IS NULL? [y/N] "
        ).strip().lower()
        if confirm == "y":
            cur.execute("DELETE FROM meal_cache WHERE lat IS NULL")
            print(f"  Deleted {cur.rowcount} meal_cache rows.")
        else:
            print("  Skipped meal_cache.")

    conn.commit()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
