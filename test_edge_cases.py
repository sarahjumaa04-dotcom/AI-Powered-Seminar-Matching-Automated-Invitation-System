import os
import sqlite3
import tempfile
import sys
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.getcwd())
from app import app
import utils.invitations as invitations_mod


def _setup_db(seed_advisor=True):
    tmpdir = tempfile.TemporaryDirectory()
    test_db = os.path.join(tmpdir.name, "test_app.db")
    with open("database/schema.sql", "r") as f:
        schema = f.read()
    conn = sqlite3.connect(test_db)
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO users (full_name,email,password_hash,role,is_active) VALUES (?,?,?,?,?)",
        ("System Admin", "admin@bau.edu.tr", generate_password_hash("admin123"), "admin", 1),
    )
    conn.execute(
        "INSERT INTO users (full_name,email,password_hash,role,is_active) VALUES (?,?,?,?,?)",
        ("Event Organizer", "organizer@bau.edu.tr", generate_password_hash("organizer123"), "organizer", 1),
    )
    if seed_advisor:
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

    app.config["TESTING"] = True
    app.config["DATABASE"] = test_db
    app.config["SECRET_KEY"] = "test-secret"
    app.config["INVITATION_DELIVERY_MODE"] = "local"
    client = app.test_client()
    return client, tmpdir


def test_capacity_and_duplicate_registration():
    client, tmpdir = _setup_db()

    # login and create event
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)
    client.post(
        "/events/new",
        data={
            "title": "Capacity Event",
            "description": "Capacity test",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "1",
            "registration_deadline": "2026-06-20",
            "status": "open",
        },
        follow_redirects=True,
    )

    # add advisor and create+accept invitation so event is public
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute(
        "INSERT INTO advisors (title, full_name, department, expertise_keywords, recent_seminar_topics, all_topics_corpus, email) VALUES (?,?,?,?,?,?,?)",
        ("Prof.", "Advisor A", "CS", "AI", "AI", "AI", "a@example.com"),
    )
    conn.commit()
    advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("a@example.com",)).fetchone()[0]
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("Capacity Event",)).fetchone()[0]
    conn.execute("INSERT INTO invitations (event_id, advisor_id, token, status, sent_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)", (event_id, advisor_id, 'tok1', 'accepted'))
    conn.commit()
    conn.close()

    # first registration should succeed
    r1 = client.post(f"/register/{event_id}", data={"student_name": "Alice", "student_id": "S1", "email": "alice@example.com"}, follow_redirects=True)
    assert b"Registration submitted successfully" in r1.data

    # second registration should be blocked because capacity=1
    r2 = client.post(f"/register/{event_id}", data={"student_name": "Bob", "student_id": "S2", "email": "bob@example.com"}, follow_redirects=True)
    assert b"This event is full." in r2.data


def test_duplicate_student_id_registration():
    client, tmpdir = _setup_db()

    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)
    client.post(
        "/events/new",
        data={
            "title": "Dup Event",
            "description": "Dup test",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "10",
            "registration_deadline": "2026-06-20",
            "status": "open",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute(
        "INSERT INTO advisors (title, full_name, department, expertise_keywords, recent_seminar_topics, all_topics_corpus, email) VALUES (?,?,?,?,?,?,?)",
        ("Prof.", "Advisor B", "CS", "AI", "AI", "AI", "b@example.com"),
    )
    conn.commit()
    advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("b@example.com",)).fetchone()[0]
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("Dup Event",)).fetchone()[0]
    conn.execute("INSERT INTO invitations (event_id, advisor_id, token, status, sent_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)", (event_id, advisor_id, 'tok2', 'accepted'))
    conn.commit()
    conn.close()

    # first registration
    r1 = client.post(f"/register/{event_id}", data={"student_name": "Carol", "student_id": "S42", "email": "carol@example.com"}, follow_redirects=True)
    assert b"Registration submitted successfully" in r1.data

    # duplicate registration with same student_id should be blocked
    r2 = client.post(f"/register/{event_id}", data={"student_name": "Carol Dup", "student_id": "S42", "email": "carol2@example.com"}, follow_redirects=True)
    assert b"An active registration already exists for this student ID" in r2.data


def test_invitation_cancel_and_reset():
    client, tmpdir = _setup_db()
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)

    # prepare event and advisor
    client.post(
        "/events/new",
        data={
            "title": "InvChange",
            "description": "Inv test",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "10",
            "registration_deadline": "2026-06-20",
            "status": "open",
        },
        follow_redirects=True,
    )
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute(
        "INSERT INTO advisors (title, full_name, department, expertise_keywords, recent_seminar_topics, all_topics_corpus, email) VALUES (?,?,?,?,?,?,?)",
        ("Prof.", "Advisor C", "CS", "AI", "AI", "AI", "c@example.com"),
    )
    conn.commit()
    advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("c@example.com",)).fetchone()[0]
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("InvChange",)).fetchone()[0]
    # create invitation
    conn.execute("INSERT INTO invitations (event_id, advisor_id, token, status) VALUES (?,?,?,?)", (event_id, advisor_id, 'tok3', 'pending'))
    conn.commit()
    inv = conn.execute("SELECT id FROM invitations WHERE token = ? LIMIT 1", ('tok3',)).fetchone()
    inv_id = inv[0]
    conn.close()

    # cancel
    r1 = client.post(f"/invitations/{inv_id}/update-status", data={"action": "cancel"}, follow_redirects=True)
    assert b"Invitation cancelled" in r1.data

    # reset
    r2 = client.post(f"/invitations/{inv_id}/update-status", data={"action": "reset"}, follow_redirects=True)
    assert b"Invitation reset to pending" in r2.data


def test_invitation_send_smtp_monkeypatch(monkeypatch):
    client, tmpdir = _setup_db()
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)

    client.post(
        "/events/new",
        data={
            "title": "SMTPEvent",
            "description": "SMTP test",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "10",
            "registration_deadline": "2026-06-20",
            "status": "open",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute(
        "INSERT INTO advisors (title, full_name, department, expertise_keywords, recent_seminar_topics, all_topics_corpus, email) VALUES (?,?,?,?,?,?,?)",
        ("Prof.", "Advisor D", "CS", "AI", "AI", "AI", "d@example.com"),
    )
    conn.commit()
    advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("d@example.com",)).fetchone()[0]
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("SMTPEvent",)).fetchone()[0]
    conn.execute("INSERT INTO invitations (event_id, advisor_id, token, status) VALUES (?,?,?,?)", (event_id, advisor_id, 'tok4', 'pending'))
    conn.commit()
    inv = conn.execute("SELECT id FROM invitations WHERE token = ? LIMIT 1", ('tok4',)).fetchone()
    inv_id = inv[0]
    conn.close()

    # monkeypatch SMTP send to always succeed
    def fake_send(cfg, to_email, subject, body):
        return True, "sent"

    # the app imported send_invitation_email at module import time; patch the app module symbol
    import sys
    app_mod = sys.modules.get('app')
    monkeypatch.setattr(app_mod, 'send_invitation_email', fake_send)
    app.config['INVITATION_DELIVERY_MODE'] = 'smtp'

    r = client.post(f"/invitations/{inv_id}/send", data={}, follow_redirects=True)
    # verify sent_at was updated in DB (SMTP branch should mark sent_at)
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT sent_at FROM invitations WHERE id = ? LIMIT 1", (inv_id,)).fetchone()
    conn.close()
    assert row is not None and row["sent_at"] is not None


def test_invitation_send_api_monkeypatch(monkeypatch):
    client, tmpdir = _setup_db()
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)

    client.post(
        "/events/new",
        data={
            "title": "APIEvent",
            "description": "API test",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "10",
            "registration_deadline": "2026-06-20",
            "status": "open",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute(
        "INSERT INTO advisors (title, full_name, department, expertise_keywords, recent_seminar_topics, all_topics_corpus, email) VALUES (?,?,?,?,?,?,?)",
        ("Prof.", "Advisor E", "CS", "AI", "AI", "AI", "e@example.com"),
    )
    conn.commit()
    advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("e@example.com",)).fetchone()[0]
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("APIEvent",)).fetchone()[0]
    conn.execute("INSERT INTO invitations (event_id, advisor_id, token, status) VALUES (?,?,?,?)", (event_id, advisor_id, 'tok_api', 'pending'))
    conn.commit()
    inv = conn.execute("SELECT id FROM invitations WHERE token = ? LIMIT 1", ('tok_api',)).fetchone()
    inv_id = inv[0]
    conn.close()

    def fake_send(cfg, to_email, subject, body):
        return True, "sent"

    import sys
    app_mod = sys.modules.get('app')
    monkeypatch.setattr(app_mod, 'send_invitation_email_api', fake_send)
    app.config['INVITATION_DELIVERY_MODE'] = 'api'

    r = client.post(f"/invitations/{inv_id}/send", data={}, follow_redirects=True)
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT sent_at FROM invitations WHERE id = ? LIMIT 1", (inv_id,)).fetchone()
    conn.close()
    assert row is not None and row["sent_at"] is not None


def test_invalid_event_capacity():
    client, tmpdir = _setup_db()
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)

    for invalid_capacity in ["0", "-5"]:
        r = client.post(
            "/events/new",
            data={
                "title": f"InvalidCapacity{invalid_capacity}",
                "description": "Capacity validation test",
                "topic": "Test",
                "event_date": "2026-06-15",
                "start_time": "10:00",
                "end_time": "12:00",
                "location": "Hall",
                "capacity": invalid_capacity,
                "registration_deadline": "2026-06-12",
                "status": "open",
            },
            follow_redirects=True,
        )
        assert b"Capacity must be a positive integer." in r.data


def test_duplicate_invitation_creation():
    client, tmpdir = _setup_db()
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)

    client.post(
        "/events/new",
        data={
            "title": "DupInvite Event",
            "description": "Duplicate invitation test",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "10",
            "registration_deadline": "2026-06-12",
            "status": "open",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(app.config["DATABASE"])
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("DupInvite Event",)).fetchone()[0]
    advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("advisor1@example.com",)).fetchone()[0]
    conn.close()

    r1 = client.post(
        "/invitations/new",
        data={"event_id": str(event_id), "advisor_id": str(advisor_id)},
        follow_redirects=True,
    )
    assert b"Invitation created successfully." in r1.data

    r2 = client.post(
        "/invitations/new",
        data={"event_id": str(event_id), "advisor_id": str(advisor_id)},
        follow_redirects=True,
    )
    assert b"An invitation for this event and advisor already exists." in r2.data

    conn = sqlite3.connect(app.config["DATABASE"])
    count = conn.execute(
        "SELECT COUNT(*) FROM invitations WHERE event_id = ? AND advisor_id = ?",
        (event_id, advisor_id),
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_registration_blocked_after_deadline():
    client, tmpdir = _setup_db()
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)

    client.post(
        "/events/new",
        data={
            "title": "DeadlineClosed Event",
            "description": "Registration deadline past",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "10",
            "registration_deadline": "2025-01-01",
            "status": "open",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute(
        "INSERT INTO invitations (event_id, advisor_id, token, status, sent_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
        (conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("DeadlineClosed Event",)).fetchone()[0],
         conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("advisor1@example.com",)).fetchone()[0],
         "tok-deadline",
         "accepted"),
    )
    conn.commit()
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("DeadlineClosed Event",)).fetchone()[0]
    conn.close()

    r = client.post(
        f"/register/{event_id}",
        data={"student_name": "Late Student", "student_id": "S999", "email": "late@example.com"},
        follow_redirects=True,
    )
    assert b"Registration is closed for this event." in r.data


def test_forgot_password_unknown_email():
    client, tmpdir = _setup_db()

    r = client.post(
        "/forgot-password",
        data={"email": "unknown@example.com"},
        follow_redirects=True,
    )
    assert b"No account found with that email address." in r.data


def test_invitation_send_for_non_pending_status():
    client, tmpdir = _setup_db()
    client.post("/login", data={"email": "admin@bau.edu.tr", "password": "admin123"}, follow_redirects=True)

    client.post(
        "/events/new",
        data={
            "title": "FinalizedInvitation Event",
            "description": "Send invite after response",
            "topic": "Test",
            "event_date": "2026-06-15",
            "start_time": "10:00",
            "end_time": "12:00",
            "location": "Hall",
            "capacity": "10",
            "registration_deadline": "2026-06-12",
            "status": "open",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute(
        "INSERT INTO advisors (title, full_name, department, expertise_keywords, recent_seminar_topics, all_topics_corpus, email) VALUES (?,?,?,?,?,?,?)",
        ("Prof.", "Advisor Final", "CS", "AI", "AI", "AI", "final@example.com"),
    )
    conn.commit()
    advisor_id = conn.execute("SELECT id FROM advisors WHERE email = ? LIMIT 1", ("final@example.com",)).fetchone()[0]
    event_id = conn.execute("SELECT id FROM events WHERE title = ? LIMIT 1", ("FinalizedInvitation Event",)).fetchone()[0]
    conn.execute(
        "INSERT INTO invitations (event_id, advisor_id, token, status) VALUES (?,?,?,?)",
        (event_id, advisor_id, "tok-final", "accepted"),
    )
    conn.commit()
    inv_id = conn.execute("SELECT id FROM invitations WHERE token = ? LIMIT 1", ("tok-final",)).fetchone()[0]
    conn.close()

    r = client.post(f"/invitations/{inv_id}/send", data={}, follow_redirects=True)
    assert b"This invitation already has a final response and cannot be sent again." in r.data
