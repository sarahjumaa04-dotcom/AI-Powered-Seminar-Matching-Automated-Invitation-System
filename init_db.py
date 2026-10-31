import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "app.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
EXCEL_PATH = PROJECT_DIR / "Capstone II - DataBase - 50 Professors.xlsx"


def table_count(connection: sqlite3.Connection, table_name: str) -> int:
    cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name}")
    return int(cursor.fetchone()[0])


def get_id_by_value(
    connection: sqlite3.Connection, table_name: str, key_column: str, key_value: str
):
    cursor = connection.execute(
        f"SELECT id FROM {table_name} WHERE {key_column} = ? LIMIT 1", (key_value,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def seed_users(connection: sqlite3.Connection) -> int:
    if table_count(connection, "users") > 0:
        return 0

    users = [
        (
            "System Admin",
            "admin@bau.edu.tr",
            generate_password_hash("admin123"),
            "admin",
            1,
        ),
        (
            "Event Organizer",
            "organizer@bau.edu.tr",
            generate_password_hash("organizer123"),
            "organizer",
            1,
        ),
    ]
    connection.executemany(
        """
        INSERT INTO users (full_name, email, password_hash, role, is_active)
        VALUES (?, ?, ?, ?, ?)
        """,
        users,
    )
    return len(users)


def _clean_name(raw_name: str) -> str:
    """Remove leading newlines/whitespace from professor names."""
    return re.sub(r"^\s+", "", raw_name).strip()


def _extract_title(full_name: str) -> tuple[str, str]:
    """Split academic title from full name.
    Returns (title, display_name). Title is e.g. 'Prof.' or 'Assist Prof.'
    """
    patterns = [
        r"^(Prof\.\s*Dr\.)\s+",
        r"^(Assoc\.\s*Prof\.)\s+",
        r"^(Assist\s*Prof\.)\s+",
        r"^(Prof\.)\s+",
    ]
    for pattern in patterns:
        match = re.match(pattern, full_name, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            rest = full_name[match.end():].strip()
            return title, rest
    return "", full_name


def _parse_conference_date(conf_text: str):
    """Try to extract a year from conference name & date text for sorting."""
    if not conf_text:
        return 0
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", conf_text)
    if years:
        return int(years[-1])
    return 0


def load_professors_from_excel() -> list[dict]:
    """Load all 50 professors from the Excel file, aggregating their data."""
    try:
        import openpyxl
    except ImportError:
        print("WARNING: openpyxl not installed. Cannot load Excel data.")
        return []

    if not EXCEL_PATH.exists():
        print(f"WARNING: Excel file not found at {EXCEL_PATH}")
        return []

    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]  # "50 Professors' DataBase"

    # Collect all rows per professor (by email as unique key)
    professor_data = defaultdict(lambda: {
        "name": "",
        "title": "",
        "department": "",
        "email": "",
        "keywords": set(),
        "topics": [],
        "conferences": [],
    })

    for row_idx in range(3, ws.max_row + 1):
        name_raw = ws.cell(row=row_idx, column=3).value
        if not name_raw:
            continue

        name_clean = _clean_name(str(name_raw))
        dept = str(ws.cell(row=row_idx, column=4).value or "").strip()
        conf = str(ws.cell(row=row_idx, column=5).value or "").strip()
        topic = str(ws.cell(row=row_idx, column=7).value or "").strip()
        keywords_raw = str(ws.cell(row=row_idx, column=8).value or "").strip()
        email = str(ws.cell(row=row_idx, column=9).value or "").strip().lower()

        if not email:
            continue

        prof = professor_data[email]
        prof["name"] = name_clean
        prof["department"] = dept
        prof["email"] = email

        # Parse keywords (semicolon-separated in Excel)
        if keywords_raw:
            for kw in re.split(r"[;,]", keywords_raw):
                kw = kw.strip()
                if kw:
                    prof["keywords"].add(kw)

        # Collect topics with conference date for sorting
        if topic:
            year = _parse_conference_date(conf)
            prof["topics"].append((year, topic))

        if conf:
            prof["conferences"].append(conf)

    wb.close()

    # Build final professor list
    professors = []
    for email, data in professor_data.items():
        title, display_name = _extract_title(data["name"])
        full_name_with_title = data["name"]

        # Sort topics by year (descending) and take last 5
        sorted_topics = sorted(data["topics"], key=lambda t: t[0], reverse=True)
        recent_5 = [t[1] for t in sorted_topics[:5]]

        # Build full topics corpus for AI matching
        all_topics = [t[1] for t in data["topics"]]

        # Clean up department (remove excessive whitespace)
        dept_clean = re.sub(r"\s{2,}", " ", data["department"]).strip()

        professors.append({
            "title": title,
            "full_name": full_name_with_title,
            "department": dept_clean,
            "email": email,
            "expertise_keywords": "; ".join(sorted(data["keywords"])),
            "recent_seminar_topics": " | ".join(recent_5) if recent_5 else "",
            "all_topics_corpus": " | ".join(all_topics) if all_topics else "",
        })

    # Sort by name for consistent ordering
    professors.sort(key=lambda p: p["full_name"].lower())
    return professors


def seed_advisors(connection: sqlite3.Connection) -> int:
    if table_count(connection, "advisors") > 0:
        return 0

    professors = load_professors_from_excel()
    if not professors:
        print("WARNING: No professors loaded from Excel. Using minimal seed data.")
        professors = [
            {
                "title": "Prof.",
                "full_name": "Prof. Dr. Ahmet Arif ERGİN",
                "department": "Electromagnetic Fields and Microwave Technique",
                "email": "arif.ergin@bau.edu.tr",
                "expertise_keywords": "Computational Electromagnetics; Scattering; Numerical Methods",
                "recent_seminar_topics": "",
                "all_topics_corpus": "",
            },
        ]

    connection.executemany(
        """
        INSERT INTO advisors (title, full_name, department, expertise_keywords,
                              recent_seminar_topics, all_topics_corpus, email)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                p["title"],
                p["full_name"],
                p["department"],
                p["expertise_keywords"],
                p["recent_seminar_topics"],
                p["all_topics_corpus"],
                p["email"],
            )
            for p in professors
        ],
    )
    return len(professors)


def seed_events(connection: sqlite3.Connection) -> int:
    if table_count(connection, "events") > 0:
        return 0

    admin_user_id = get_id_by_value(connection, "users", "email", "admin@bau.edu.tr")
    if not admin_user_id:
        return 0

    events = [
        (
            "AI in Education Summit",
            "Exploring the intersection of artificial intelligence and modern education methodologies.",
            "AI in Education",
            "2026-06-15",
            "10:00",
            "12:00",
            "BAU Main Auditorium",
            120,
            "2026-06-12",
            "draft",
            admin_user_id,
        ),
        (
            "Cybersecurity Workshop",
            "Workshop on information security threats and defense strategies for campus systems.",
            "Cybersecurity",
            "2026-07-10",
            "14:00",
            "16:00",
            "BAU Engineering Lab 2",
            60,
            "2026-07-05",
            "draft",
            admin_user_id,
        ),
    ]
    connection.executemany(
        """
        INSERT INTO events (
            title, description, topic, event_date, start_time, end_time, location,
            capacity, registration_deadline, status, created_by_user_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        events,
    )
    return len(events)


def initialize_database() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Delete existing DB for clean reinit
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing database: {DB_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(schema_sql)

        inserted = {
            "users": seed_users(connection),
            "advisors": seed_advisors(connection),
            "events": seed_events(connection),
        }
        connection.commit()
    finally:
        connection.close()

    print("Database initialization completed.")
    print(f"Database file: {DB_PATH}")
    print(
        "Seed summary: "
        + ", ".join([f"{table}={count}" for table, count in inserted.items()])
    )


if __name__ == "__main__":
    initialize_database()
