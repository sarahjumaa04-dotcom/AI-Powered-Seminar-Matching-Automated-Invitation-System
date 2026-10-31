import os
import sqlite3
import tempfile
import sys
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.getcwd())
from app import app


def test_smoke():
    """Basic end-to-end smoke test for the main app flows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "test_app.db")
        with open("database/schema.sql", "r") as f:
            schema = f.read()
        conn = sqlite3.connect(test_db)
        conn.executescript(schema)
        # seed users and one advisor
        conn.execute(
            "INSERT INTO users (full_name,email,password_hash,role,is_active) VALUES (?,?,?,?,?)",
            ("System Admin", "admin@bau.edu.tr", generate_password_hash("admin123"), "admin", 1),
        )
        conn.execute(
            "INSERT INTO users (full_name,email,password_hash,role,is_active) VALUES (?,?,?,?,?)",
            ("Event Organizer", "organizer@bau.edu.tr", generate_password_hash("organizer123"), "organizer", 1),
        )
        conn.execute(
            "INSERT INTO advisors (title, full_name, department, expertise_keywords, recent_seminar_topics, all_topics_corpus, email) VALUES (?,?,?,?,?,?,?)",
            (
                "Prof.",
                "Prof. Test Advisor",
                "Computer Science",
                "AI; machine learning; data science",
                "AI applications|Machine learning",
                "AI applications|Machine learning|Data mining",
                "advisor1@example.com",
            ),
        )
        conn.commit()
        conn.close()

        # configure app to use the temp DB
        app.config["TESTING"] = True
        app.config["DATABASE"] = test_db
        app.config["SECRET_KEY"] = "test-secret"
        app.config["INVITATION_DELIVERY_MODE"] = "local"

        client = app.test_client()

        # smoke steps
        r = client.get("/")
        assert r.status_code == 200

        r = client.get("/login")
        assert r.status_code == 200

        r = client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)
        assert r.status_code == 200
        assert b"Dashboard" in r.data

        # create an event
        r = client.post(
            "/events/new",
            data={
                "title": "Test Event",
                "description": "A test event.",
                "topic": "AI in Education",
                "event_date": "2026-06-15",
                "start_time": "10:00",
                "end_time": "12:00",
                "location": "Test Hall",
                "capacity": "10",
                "registration_deadline": "2026-06-12",
                "status": "open",
            },
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b"Event created successfully" in r.data

        # read event id
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("Test Event",)).fetchone()["id"]
        advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("advisor1@example.com",)).fetchone()["id"]
        conn.close()

        # run matching
        r = client.post("/advisors/match", data={"topic": "AI in Education", "description": "Seminar on AI applications"}, follow_redirects=True)
        assert r.status_code == 200

        # create invitation
        r = client.post("/invitations/new", data={"event_id": str(event_id), "advisor_id": str(advisor_id)}, follow_redirects=True)
        assert r.status_code == 200
        assert b"Invitation created successfully" in r.data

        # find invitation token
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        inv = conn.execute("SELECT id, token FROM invitations WHERE event_id = ? AND advisor_id = ? LIMIT 1", (event_id, advisor_id)).fetchone()
        conn.close()
        assert inv is not None
        token = inv["token"]

        # preview and respond
        r = client.get(f"/invitations/{inv['id']}/preview")
        assert r.status_code == 200

        r = client.get(f"/invite/respond/{token}")
        assert r.status_code == 200

        r = client.post(f"/invite/respond/{token}", data={"action": "accept", "response_note": "Looking forward"}, follow_redirects=True)
        assert r.status_code == 200
        assert b"Invitation response submitted successfully" in r.data

        # public events and registration
        r = client.get("/events/public")
        assert r.status_code == 200

        r = client.get(f"/events/public/{event_id}")
        assert r.status_code == 200

        r = client.post(f"/register/{event_id}", data={"student_name": "Jane Doe", "student_id": "S123456", "email": "jane.doe@example.com"}, follow_redirects=True)
        assert r.status_code == 200
        assert b"Registration submitted successfully" in r.data

        # registrations list (admin)
        r = client.get(f"/events/{event_id}/registrations")
        assert r.status_code == 200
        assert b"Jane Doe" in r.data

        # forgot password
        r = client.get("/forgot-password")
        assert r.status_code == 200
        r = client.post("/forgot-password", data={"email": "admin@bau.edu.tr"}, follow_redirects=True)
        assert r.status_code == 200
        assert b"Password has been reset" in r.data


if __name__ == "__main__":
    try:
        test_smoke()
        print("SMOKE TEST PASSED")
        sys.exit(0)
    except AssertionError as e:
        print("SMOKE TEST FAILED", e)
        sys.exit(2)
