import os
import secrets
import sqlite3
from datetime import date, datetime, timezone, timedelta
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from utils.invitations import (
    build_invitation_body,
    build_invitation_subject,
    send_invitation_email,
    send_invitation_email_api,
)
from utils.matching import rank_advisors

_ISTANBUL_TZ = timezone(timedelta(hours=3))


def istanbul_now():
    return datetime.now(_ISTANBUL_TZ).strftime("%Y-%m-%d %H:%M:%S")


app = Flask(__name__)
app.config.from_object("config")


def format_date_with_day(date_str):
    """Jinja2 filter: '2026-05-16' -> 'Saturday, 2026-05-16'"""
    if not date_str:
        return date_str
    try:
        dt = datetime.strptime(str(date_str).strip()[:10], "%Y-%m-%d")
        return dt.strftime("%A, %Y-%m-%d")
    except (ValueError, TypeError):
        return date_str


app.jinja_env.filters["day_date"] = format_date_with_day


def get_db_connection():
    db_path = app.config["DATABASE"]
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            "Database file is missing. Run `python database/init_db.py` first."
        )

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def login_required(route_func):
    @wraps(route_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return route_func(*args, **kwargs)

    return wrapped


def admin_required(route_func):
    @wraps(route_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        if session.get("user_role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return route_func(*args, **kwargs)

    return wrapped


def render_public_template(template_name, **context):
    context.setdefault("force_public_nav", True)
    return render_template(template_name, **context)


@app.context_processor
def inject_auth_user():
    auth_user = None
    if session.get("user_id"):
        auth_user = {
            "id": session.get("user_id"),
            "name": session.get("user_name"),
            "role": session.get("user_role"),
        }
    return {"auth_user": auth_user}


@app.errorhandler(404)
def page_not_found(_error):
    return render_template("errors/404.html", force_public_nav=True), 404


def parse_advisor_form(form):
    return {
        "title": form.get("title", "").strip(),
        "full_name": form.get("full_name", "").strip(),
        "department": form.get("department", "").strip(),
        "expertise_keywords": form.get("expertise_keywords", "").strip(),
        "recent_seminar_topics": form.get("recent_seminar_topics", "").strip(),
        "email": form.get("email", "").strip().lower(),
    }


def validate_advisor_form(connection, advisor_data, current_advisor_id=None):
    errors = []

    if not advisor_data["full_name"]:
        errors.append("Advisor name is required.")
    if not advisor_data["department"]:
        errors.append("Department is required.")
    if not advisor_data["expertise_keywords"]:
        errors.append("Expertise keywords are required.")
    if not advisor_data["email"]:
        errors.append("Email is required.")
    elif "@" not in advisor_data["email"] or "." not in advisor_data["email"].split("@")[
        -1
    ]:
        errors.append("Please enter a valid email address.")

    if advisor_data["email"]:
        duplicate = connection.execute(
            """
            SELECT id FROM advisors
            WHERE lower(email) = lower(?)
            LIMIT 1
            """,
            (advisor_data["email"],),
        ).fetchone()
        if duplicate and duplicate["id"] != current_advisor_id:
            errors.append("An advisor with this email already exists.")

    return errors


EVENT_STATUS_OPTIONS = {"draft", "open", "closed"}
EVENT_STATUS_LABELS = {
    "draft": "Draft",
    "open": "Open",
    "closed": "Closed",
}
INVITATION_STATUS_META = {
    "pending": {
        "label": "Awaiting Response",
        "meaning": "Awaiting advisor response",
        "badge": "warning",
        "is_pending": True,
    },
    "accepted": {
        "label": "Confirmed",
        "meaning": "Confirmed speaker/advisor",
        "badge": "success",
        "is_pending": False,
    },
    "declined": {
        "label": "Declined",
        "meaning": "Not participating",
        "badge": "secondary",
        "is_pending": False,
    },
    "cancelled": {
        "label": "Cancelled",
        "meaning": "Withdrawn by admin",
        "badge": "dark",
        "is_pending": False,
    },
}


def get_event_status_label(status):
    if not status:
        return "Unknown"
    return EVENT_STATUS_LABELS.get(status, status.replace("_", " ").title())


def get_invitation_status_meta(status):
    return INVITATION_STATUS_META.get(
        status,
        {
            "label": status.title() if status else "Unknown",
            "meaning": "Status unavailable",
            "badge": "secondary",
            "is_pending": False,
        },
    )


def parse_event_form(form):
    return {
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "topic": form.get("topic", "").strip(),
        "event_date": form.get("event_date", "").strip(),
        "start_time": form.get("start_time", "").strip(),
        "end_time": form.get("end_time", "").strip(),
        "location": form.get("location", "").strip(),
        "capacity": form.get("capacity", "").strip(),
        "registration_deadline": form.get("registration_deadline", "").strip(),
        "status": form.get("status", "").strip(),
    }


def validate_event_form(event_data):
    errors = []

    required_fields = [
        ("title", "Title is required."),
        ("topic", "Topic is required."),
        ("event_date", "Event date is required."),
        ("start_time", "Start time is required."),
        ("end_time", "End time is required."),
        ("location", "Location is required."),
        ("capacity", "Capacity is required."),
        ("status", "Status is required."),
    ]

    for field_name, message in required_fields:
        if not event_data[field_name]:
            errors.append(message)

    capacity_value = None
    if event_data["capacity"]:
        try:
            capacity_value = int(event_data["capacity"])
            if capacity_value <= 0:
                errors.append("Capacity must be a positive integer.")
        except ValueError:
            errors.append("Capacity must be a positive integer.")

    if event_data["status"] and event_data["status"] not in EVENT_STATUS_OPTIONS:
        errors.append("Status must be one of: draft, open, closed.")

    if event_data["event_date"]:
        try:
            datetime.strptime(event_data["event_date"], "%Y-%m-%d")
        except ValueError:
            errors.append("Event date must be a valid date (YYYY-MM-DD).")

    if event_data["registration_deadline"]:
        try:
            datetime.strptime(event_data["registration_deadline"], "%Y-%m-%d")
        except ValueError:
            errors.append("Registration deadline must be a valid date (YYYY-MM-DD).")

    if event_data["start_time"] and event_data["end_time"]:
        try:
            start_time = datetime.strptime(event_data["start_time"], "%H:%M")
            end_time = datetime.strptime(event_data["end_time"], "%H:%M")
            if end_time <= start_time:
                errors.append("End time must be later than start time.")
        except ValueError:
            errors.append("Start time and end time must be valid (HH:MM).")

    return errors, capacity_value


def generate_unique_invitation_token(connection):
    while True:
        token = secrets.token_urlsafe(18)
        exists = connection.execute(
            "SELECT 1 FROM invitations WHERE token = ? LIMIT 1", (token,)
        ).fetchone()
        if not exists:
            return token


def parse_positive_int(raw_value):
    try:
        value = int(raw_value)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def build_invitation_response_url(token):
    base_url = (app.config.get("BASE_URL") or request.url_root).rstrip("/")
    return f"{base_url}{url_for('invite_response', token=token)}"


def load_invitation_by_id(connection, invitation_id):
    return connection.execute(
        """
        SELECT
            i.id,
            i.token,
            i.status,
            i.response_note,
            i.sent_at,
            i.responded_at,
            i.created_at,
            e.id AS event_id,
            e.title AS event_title,
            e.topic AS event_topic,
            e.event_date,
            e.start_time,
            e.end_time,
            e.location,
            a.id AS advisor_id,
            a.full_name AS advisor_name,
            a.email AS advisor_email
        FROM invitations i
        JOIN events e ON e.id = i.event_id
        JOIN advisors a ON a.id = i.advisor_id
        WHERE i.id = ?
        LIMIT 1
        """,
        (invitation_id,),
    ).fetchone()


def parse_registration_form(form):
    return {
        "student_name": form.get("student_name", "").strip(),
        "student_id": form.get("student_id", "").strip(),
        "email": form.get("email", "").strip().lower(),
    }


def validate_registration_form(registration_data):
    errors = []
    if not registration_data["student_name"]:
        errors.append("Student name is required.")
    if not registration_data["student_id"]:
        errors.append("Student ID is required.")
    if not registration_data["email"]:
        errors.append("Email is required.")
    elif "@" not in registration_data["email"] or "." not in registration_data["email"].split("@")[
        -1
    ]:
        errors.append("Please enter a valid email address.")
    return errors


def registration_deadline_passed(registration_deadline):
    if not registration_deadline:
        return False
    try:
        deadline_date = datetime.strptime(registration_deadline, "%Y-%m-%d").date()
    except ValueError:
        return False
    return date.today() > deadline_date


def get_accepted_invitation_count(connection, event_id):
    row = connection.execute(
        """
        SELECT COUNT(*) AS accepted_count
        FROM invitations
        WHERE event_id = ? AND status = 'accepted'
        """,
        (event_id,),
    ).fetchone()
    return int(row["accepted_count"] if row else 0)


def get_event_invitation_summary(connection, event_id):
    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END), 0) AS accepted_count,
            COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
            COALESCE(SUM(CASE WHEN status = 'declined' THEN 1 ELSE 0 END), 0) AS declined_count
        FROM invitations
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()
    accepted = int(row["accepted_count"] if row else 0)
    pending = int(row["pending_count"] if row else 0)
    declined = int(row["declined_count"] if row else 0)
    return {
        "accepted_count": accepted,
        "pending_count": pending,
        "declined_count": declined,
        "public_ready": accepted >= 1,
    }


def get_public_events_with_counts(connection):
    return connection.execute(
        """
        SELECT
            e.id,
            e.title,
            e.description,
            e.topic,
            e.event_date,
            e.start_time,
            e.end_time,
            e.location,
            e.capacity,
            e.registration_deadline,
            e.status,
            (
                SELECT COUNT(*)
                FROM registrations r
                WHERE r.event_id = e.id AND r.state = 'active'
            ) AS active_registrations
        FROM events e
        WHERE e.status IN ('open', 'closed')
        ORDER BY e.event_date ASC, e.start_time ASC, e.id ASC
        """
    ).fetchall()


def get_public_event_with_count(connection, event_id):
    return connection.execute(
        """
        SELECT
            e.id,
            e.title,
            e.description,
            e.topic,
            e.event_date,
            e.start_time,
            e.end_time,
            e.location,
            e.capacity,
            e.registration_deadline,
            e.status,
            (
                SELECT COUNT(*)
                FROM registrations r
                WHERE r.event_id = e.id AND r.state = 'active'
            ) AS active_registrations
        FROM events e
        WHERE e.id = ?
          AND e.status IN ('open', 'closed')
        LIMIT 1
        """,
        (event_id,),
    ).fetchone()


def calculate_registration_summary(event_row):
    active_count = int(event_row["active_registrations"])
    remaining = max(int(event_row["capacity"]) - active_count, 0)
    closed_by_deadline = registration_deadline_passed(event_row["registration_deadline"])
    is_full = remaining <= 0
    closed_by_status = event_row["status"] == "closed"
    is_open = (not is_full) and (not closed_by_deadline) and (not closed_by_status)

    if closed_by_status:
        status_text = "Closed"
    elif closed_by_deadline:
        status_text = "Registration Closed"
    elif is_full:
        status_text = "Full"
    else:
        status_text = "Open"

    return {
        "active_registrations": active_count,
        "remaining_seats": remaining,
        "registration_open": is_open,
        "registration_status_text": status_text,
        "closed_by_deadline": closed_by_deadline,
        "closed_by_status": closed_by_status,
        "is_full": is_full,
    }


@app.route("/")
def home():
    return render_public_template("public/home.html")


@app.route("/events/public")
def public_events():
    events = []
    connection = None
    try:
        connection = get_db_connection()
        rows = get_public_events_with_counts(connection)
        for row in rows:
            event = dict(row)
            event.update(calculate_registration_summary(row))
            events.append(event)
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
    except sqlite3.Error:
        flash("Could not load public events.", "danger")
    finally:
        if connection:
            connection.close()

    return render_public_template("public/public_events.html", events=events)


@app.route("/events/public/<int:event_id>")
def public_event_detail(event_id):
    connection = None
    try:
        connection = get_db_connection()
        row = get_public_event_with_count(connection, event_id)
        if not row:
            abort(404)

        event = dict(row)
        event.update(calculate_registration_summary(row))
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("public_events"))
    except sqlite3.Error:
        flash("Could not load event details.", "danger")
        return redirect(url_for("public_events"))
    finally:
        if connection:
            connection.close()

    return render_public_template("public/public_event_detail.html", event=event)


@app.route("/register/<int:event_id>", methods=["GET", "POST"])
def register_form(event_id):
    registration = {"student_name": "", "student_id": "", "email": ""}
    connection = None

    try:
        connection = get_db_connection()
        row = get_public_event_with_count(connection, event_id)
        if not row:
            flash("Event not found or not available for public registration.", "danger")
            return redirect(url_for("public_events"))

        event = dict(row)
        event.update(calculate_registration_summary(row))

        if request.method == "POST":
            registration = parse_registration_form(request.form)
            errors = validate_registration_form(registration)

            if not event["registration_open"]:
                if event["is_full"]:
                    errors.append("This event is full.")
                elif event["closed_by_deadline"]:
                    errors.append("Registration is closed for this event.")
                else:
                    errors.append("Registration is not open for this event.")

            if registration["student_id"]:
                duplicate = connection.execute(
                    """
                    SELECT id, state FROM registrations
                    WHERE event_id = ? AND student_id = ?
                    LIMIT 1
                    """,
                    (event_id, registration["student_id"]),
                ).fetchone()
                if duplicate:
                    if duplicate["state"] == "active":
                        errors.append(
                            "An active registration already exists for this student ID in this event."
                        )
                    else:
                        errors.append(
                            "A registration already exists for this student ID in this event."
                        )

            current_active_count = connection.execute(
                """
                SELECT COUNT(*) FROM registrations
                WHERE event_id = ? AND state = 'active'
                """,
                (event_id,),
            ).fetchone()[0]
            if int(current_active_count) >= int(event["capacity"]) and "This event is full." not in errors:
                errors.append("This event is full.")

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_public_template(
                    "public/register_form.html",
                    event=event,
                    registration=registration,
                )

            connection.execute(
                """
                INSERT INTO registrations (event_id, student_name, student_id, email, state, registered_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (
                    event_id,
                    registration["student_name"],
                    registration["student_id"],
                    registration["email"],
                    istanbul_now(),
                ),
            )
            connection.commit()
            flash("Registration submitted successfully.", "success")

            # Send confirmation email to the student
            formatted_date = format_date_with_day(event.get("event_date", ""))
            confirmation_subject = f"Registration Confirmed: {event['title']}"
            confirmation_body = (
                f"Dear {registration['student_name']},\n\n"
                f"Your registration has been confirmed for the following event:\n\n"
                f"  Event   : {event['title']}\n"
                f"  Topic   : {event.get('topic', '')}\n"
                f"  Date    : {formatted_date}\n"
                f"  Time    : {event['start_time']} - {event['end_time']}\n"
                f"  Location: {event['location']}\n"
            )
            if event.get("description"):
                confirmation_body += f"\n  About   : {event['description']}\n"
            confirmation_body += (
                f"\nStudent ID: {registration['student_id']}\n\n"
                f"We look forward to seeing you there.\n\n"
                f"Regards,\nBAU Seminar & Summit Management Team"
            )

            delivery_mode = app.config.get("INVITATION_DELIVERY_MODE", "local").lower()
            if delivery_mode == "smtp":
                send_invitation_email(
                    app.config, registration["email"],
                    confirmation_subject, confirmation_body
                )
            elif delivery_mode == "api":
                send_invitation_email_api(
                    app.config, registration["email"],
                    confirmation_subject, confirmation_body
                )

            return redirect(url_for("public_event_detail", event_id=event_id))

        return render_public_template(
            "public/register_form.html",
            event=event,
            registration=registration,
        )
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("public_events"))
    except sqlite3.IntegrityError:
        flash(
            "A registration for this student ID already exists for this event.",
            "danger",
        )
        return redirect(url_for("register_form", event_id=event_id))
    except sqlite3.Error:
        flash("Could not submit registration. Please try again.", "danger")
        return redirect(url_for("public_events"))
    finally:
        if connection:
            connection.close()


@app.route("/invite/respond/<token>", methods=["GET", "POST"])
def invite_response(token):
    connection = None
    try:
        connection = get_db_connection()
        invitation = connection.execute(
            """
            SELECT
                i.id,
                i.token,
                i.status,
                i.response_note,
                i.sent_at,
                i.responded_at,
                i.created_at,
                e.id AS event_id,
                e.title AS event_title,
                e.topic AS event_topic,
                e.event_date,
                e.start_time,
                e.end_time,
                e.location,
                a.id AS advisor_id,
                a.full_name AS advisor_name,
                a.email AS advisor_email
            FROM invitations i
            JOIN events e ON e.id = i.event_id
            JOIN advisors a ON a.id = i.advisor_id
            WHERE i.token = ?
            LIMIT 1
            """,
            (token,),
        ).fetchone()

        if not invitation:
            flash("Invitation not found.", "danger")
            return (
                render_template(
                    "public/invite_response.html",
                    invitation=None,
                    invalid_token=True,
                    force_public_nav=True,
                ),
                404,
            )
        status_meta = get_invitation_status_meta(invitation["status"])

        if request.method == "POST":
            if invitation["status"] == "cancelled":
                flash("This invitation has been cancelled by the admin.", "warning")
                return redirect(url_for("invite_response", token=token))

            action = request.form.get("action", "").strip().lower()
            response_note = request.form.get("response_note", "").strip()

            if action not in {"accept", "decline"}:
                flash("Please choose Accept or Decline.", "danger")
                return render_public_template(
                    "public/invite_response.html",
                    invitation=invitation,
                    status_meta=status_meta,
                )

            new_status = "accepted" if action == "accept" else "declined"
            if new_status == invitation["status"]:
                flash(f"Your response is already '{status_meta['label']}'.", "info")
                return redirect(url_for("invite_response", token=token))

            connection.execute(
                """
                UPDATE invitations
                SET status = ?, response_note = ?, responded_at = ?
                WHERE id = ? AND status != 'cancelled'
                """,
                (new_status, response_note or None, istanbul_now(), invitation["id"]),
            )
            connection.commit()

            flash("Invitation response submitted successfully.", "success")
            return redirect(url_for("invite_response", token=token))

        return render_public_template(
            "public/invite_response.html",
            invitation=invitation,
            status_meta=status_meta,
        )
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return (
            render_template(
                "public/invite_response.html",
                invitation=None,
                invalid_token=True,
                force_public_nav=True,
            ),
            500,
        )
    except sqlite3.Error:
        flash("Could not load invitation response page.", "danger")
        return (
            render_template(
                "public/invite_response.html",
                invitation=None,
                invalid_token=True,
                force_public_nav=True,
            ),
            500,
        )
    finally:
        if connection:
            connection.close()


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter email and password.", "warning")
            return render_template("auth/login.html", email=email)

        connection = None
        try:
            connection = get_db_connection()
            user = connection.execute(
                """
                SELECT id, full_name, email, password_hash, role, is_active, must_change_password
                FROM users
                WHERE email = ?
                LIMIT 1
                """,
                (email,),
            ).fetchone()
        except FileNotFoundError:
            flash(
                "Database not found. Initialize it first with `python database/init_db.py`.",
                "danger",
            )
            return render_template("auth/login.html", email=email)
        except sqlite3.Error:
            flash(
                "Authentication database is not ready. Run `python database/init_db.py`.",
                "danger",
            )
            return render_template("auth/login.html", email=email)
        finally:
            if connection:
                connection.close()

        if (
            user
            and user["is_active"] == 1
            and check_password_hash(user["password_hash"], password)
        ):
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["user_role"] = user["role"]
            if user["must_change_password"] == 1:
                flash("You logged in with a temporary password. Please set a new password to continue.", "warning")
                return redirect(url_for("change_password"))
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")
        return render_template("auth/login.html", email=email)

    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not new_password or not confirm_password:
            flash("Please fill in both password fields.", "warning")
            return render_template("auth/change_password.html")

        if len(new_password) < 8:
            flash("Password must be at least 8 characters long.", "warning")
            return render_template("auth/change_password.html")

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/change_password.html")

        connection = None
        try:
            connection = get_db_connection()
            connection.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (generate_password_hash(new_password), session["user_id"]),
            )
            connection.commit()
            flash("Your password has been updated successfully.", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.Error:
            flash("Could not update password. Please try again.", "danger")
            return render_template("auth/change_password.html")
        finally:
            if connection:
                connection.close()

    return render_template("auth/change_password.html")


@app.route("/dashboard")
@login_required
def dashboard():
    stats = {
        "total_events": 0,
        "public_events": 0,
        "pending_invitations": 0,
        "registrations": 0,
    }

    connection = None
    try:
        connection = get_db_connection()
        stats["total_events"] = connection.execute(
            "SELECT COUNT(*) FROM events"
        ).fetchone()[0]
        stats["public_events"] = connection.execute(
            "SELECT COUNT(*) FROM events WHERE status IN ('open', 'closed')"
        ).fetchone()[0]
        stats["pending_invitations"] = connection.execute(
            "SELECT COUNT(*) FROM invitations WHERE status = 'pending'"
        ).fetchone()[0]
        stats["registrations"] = connection.execute(
            "SELECT COUNT(*) FROM registrations WHERE state = 'active'"
        ).fetchone()[0]
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
    except sqlite3.Error:
        flash("Could not load dashboard statistics.", "danger")
    finally:
        if connection:
            connection.close()

    return render_template("admin/dashboard.html", stats=stats)


@app.route("/advisors")
@admin_required
def advisors_list():
    advisors = []
    departments = []
    selected_department = request.args.get("department", "").strip()
    connection = None
    try:
        connection = get_db_connection()
        departments = [
            r["department"]
            for r in connection.execute(
                "SELECT DISTINCT department FROM advisors ORDER BY department ASC"
            ).fetchall()
        ]
        if selected_department and selected_department in departments:
            advisors = connection.execute(
                """
                SELECT id, full_name, department, expertise_keywords, email, created_at
                FROM advisors
                WHERE department = ?
                ORDER BY full_name ASC, id ASC
                """,
                (selected_department,),
            ).fetchall()
        else:
            selected_department = ""
            advisors = connection.execute(
                """
                SELECT id, full_name, department, expertise_keywords, email, created_at
                FROM advisors
                ORDER BY department ASC, full_name ASC, id ASC
                """
            ).fetchall()
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
    except sqlite3.Error:
        flash("Could not load advisors from database.", "danger")
    finally:
        if connection:
            connection.close()

    return render_template(
        "admin/advisors_list.html",
        advisors=advisors,
        departments=departments,
        selected_department=selected_department,
    )


@app.route("/advisors/new", methods=["GET", "POST"])
@admin_required
def advisor_new():
    advisor = {
        "title": "",
        "full_name": "",
        "department": "",
        "expertise_keywords": "",
        "recent_seminar_topics": "",
        "email": "",
    }

    if request.method == "POST":
        advisor = parse_advisor_form(request.form)
        connection = None
        try:
            connection = get_db_connection()
            errors = validate_advisor_form(connection, advisor)

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("admin/advisor_form.html", mode="Create", advisor=advisor)

            connection.execute(
                """
                INSERT INTO advisors (title, full_name, department, expertise_keywords,
                                     recent_seminar_topics, email, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    advisor["title"],
                    advisor["full_name"],
                    advisor["department"],
                    advisor["expertise_keywords"],
                    advisor["recent_seminar_topics"],
                    advisor["email"],
                    istanbul_now(),
                ),
            )
            connection.commit()
            flash("Advisor created successfully.", "success")
            return redirect(url_for("advisors_list"))
        except FileNotFoundError:
            flash(
                "Database not found. Initialize it first with `python database/init_db.py`.",
                "danger",
            )
        except sqlite3.IntegrityError:
            flash("An advisor with this email already exists.", "danger")
        except sqlite3.Error:
            flash("Could not save advisor. Please try again.", "danger")
        finally:
            if connection:
                connection.close()

    return render_template("admin/advisor_form.html", mode="Create", advisor=advisor)


@app.route("/advisors/<int:advisor_id>/edit", methods=["GET", "POST"])
@admin_required
def advisor_edit(advisor_id):
    connection = None
    try:
        connection = get_db_connection()
        existing_advisor = connection.execute(
            """
            SELECT id, title, full_name, department, expertise_keywords,
                   recent_seminar_topics, email
            FROM advisors
            WHERE id = ?
            LIMIT 1
            """,
            (advisor_id,),
        ).fetchone()

        if not existing_advisor:
            abort(404)

        if request.method == "POST":
            advisor_data = parse_advisor_form(request.form)
            advisor_data["id"] = advisor_id
            errors = validate_advisor_form(connection, advisor_data, advisor_id)

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template(
                    "admin/advisor_form.html",
                    mode="Edit",
                    advisor=advisor_data,
                )

            connection.execute(
                """
                UPDATE advisors
                SET title = ?, full_name = ?, department = ?,
                    expertise_keywords = ?, recent_seminar_topics = ?, email = ?
                WHERE id = ?
                """,
                (
                    advisor_data["title"],
                    advisor_data["full_name"],
                    advisor_data["department"],
                    advisor_data["expertise_keywords"],
                    advisor_data["recent_seminar_topics"],
                    advisor_data["email"],
                    advisor_id,
                ),
            )
            connection.commit()
            flash("Advisor updated successfully.", "success")
            return redirect(url_for("advisors_list"))

        return render_template("admin/advisor_form.html", mode="Edit", advisor=existing_advisor)
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("advisors_list"))
    except sqlite3.IntegrityError:
        flash("An advisor with this email already exists.", "danger")
        return redirect(url_for("advisor_edit", advisor_id=advisor_id))
    except sqlite3.Error:
        flash("Could not load advisor details.", "danger")
        return redirect(url_for("advisors_list"))
    finally:
        if connection:
            connection.close()


@app.route("/advisors/<int:advisor_id>/delete", methods=["POST"])
@admin_required
def advisor_delete(advisor_id):
    connection = None
    try:
        connection = get_db_connection()
        advisor = connection.execute(
            "SELECT id, full_name FROM advisors WHERE id = ? LIMIT 1",
            (advisor_id,),
        ).fetchone()
        if not advisor:
            abort(404)

        connection.execute("DELETE FROM advisors WHERE id = ?", (advisor_id,))
        connection.commit()
        flash("Advisor removed successfully.", "success")
        return redirect(url_for("advisors_list"))
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("advisors_list"))
    except sqlite3.Error:
        flash("Could not remove advisor. Please try again.", "danger")
        return redirect(url_for("advisors_list"))
    finally:
        if connection:
            connection.close()


@app.route("/advisors/match", methods=["GET", "POST"])
@admin_required
def advisor_match():
    ranked_advisors = None
    hidden_count = 0
    advisors = []
    events = []
    selected_event = None

    connection = None
    try:
        connection = get_db_connection()
        advisors = connection.execute(
            """
            SELECT id, title, full_name, department, expertise_keywords,
                   recent_seminar_topics, all_topics_corpus, email
            FROM advisors
            ORDER BY full_name ASC, id ASC
            """
        ).fetchall()
        events = connection.execute(
            """
            SELECT id, title, topic, description, event_date, start_time, end_time, location
            FROM events
            ORDER BY event_date DESC, id DESC
            """
        ).fetchall()
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
    except sqlite3.Error:
        flash("Could not load data from database.", "danger")
    finally:
        if connection:
            connection.close()

    if request.method == "POST":
        event_id = parse_positive_int(request.form.get("event_id"))
        if not event_id:
            flash("Please select an event.", "danger")
        else:
            selected_event = next((e for e in events if e["id"] == event_id), None)
            if not selected_event:
                flash("Selected event not found.", "danger")
            elif not advisors:
                flash("No advisors found in database. Add advisors first.", "warning")
            else:
                topic = selected_event["topic"] or selected_event["title"]
                description = selected_event["description"] or ""
                all_ranked = rank_advisors(topic, description, advisors)
                ranked_advisors = [a for a in all_ranked if a["score"] >= 20]
                hidden_count = len(all_ranked) - len(ranked_advisors)

    return render_template(
        "admin/advisor_match.html",
        events=events,
        selected_event=selected_event,
        ranked_advisors=ranked_advisors,
        advisors_count=len(advisors),
        hidden_count=hidden_count,
    )


@app.route("/events")
@login_required
def events_list():
    events = []
    connection = None
    try:
        connection = get_db_connection()
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                topic,
                event_date,
                start_time,
                end_time,
                location,
                status,
                created_at
            FROM events
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        for row in rows:
            event = dict(row)
            event["status_label"] = get_event_status_label(event["status"])
            events.append(event)
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
    except sqlite3.Error:
        flash("Could not load events from database.", "danger")
    finally:
        if connection:
            connection.close()

    return render_template("admin/events_list.html", events=events)


@app.route("/events/new", methods=["GET", "POST"])
@login_required
def event_new():
    event = {
        "title": "",
        "description": "",
        "topic": "",
        "event_date": "",
        "start_time": "",
        "end_time": "",
        "location": "",
        "capacity": "",
        "registration_deadline": "",
        "status": "draft",
    }

    if request.method == "POST":
        event = parse_event_form(request.form)
        errors, capacity_value = validate_event_form(event)

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("admin/event_form.html", mode="Create", event=event)

        connection = None
        try:
            connection = get_db_connection()
            connection.execute(
                """
                INSERT INTO events (
                    title,
                    description,
                    topic,
                    event_date,
                    start_time,
                    end_time,
                    location,
                    capacity,
                    registration_deadline,
                    status,
                    created_by_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["title"],
                    event["description"] or None,
                    event["topic"],
                    event["event_date"],
                    event["start_time"],
                    event["end_time"],
                    event["location"],
                    capacity_value,
                    event["registration_deadline"] or None,
                    event["status"],
                    session["user_id"],
                    istanbul_now(),
                    istanbul_now(),
                ),
            )
            connection.commit()
            flash("Event created successfully.", "success")
            return redirect(url_for("events_list"))
        except FileNotFoundError:
            flash(
                "Database not found. Initialize it first with `python database/init_db.py`.",
                "danger",
            )
        except sqlite3.Error:
            flash("Could not save event. Please try again.", "danger")
        finally:
            if connection:
                connection.close()

    return render_template("admin/event_form.html", mode="Create", event=event)


@app.route("/events/<int:event_id>")
@login_required
def event_detail(event_id):
    connection = None
    try:
        connection = get_db_connection()
        event = connection.execute(
            """
            SELECT
                id,
                title,
                description,
                topic,
                event_date,
                start_time,
                end_time,
                location,
                capacity,
                registration_deadline,
                status,
                created_by_user_id,
                created_at,
                updated_at
            FROM events
            WHERE id = ?
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()

        if not event:
            abort(404)

        event = dict(event)
        event["status_label"] = get_event_status_label(event["status"])

        invitation_summary = get_event_invitation_summary(connection, event_id)

        return render_template(
            "admin/event_detail.html",
            event=event,
            invitation_summary=invitation_summary,
        )
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("events_list"))
    except sqlite3.Error:
        flash("Could not load event details.", "danger")
        return redirect(url_for("events_list"))
    finally:
        if connection:
            connection.close()


@app.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def event_edit(event_id):
    connection = None
    try:
        connection = get_db_connection()
        existing_event = connection.execute(
            """
            SELECT
                id,
                title,
                description,
                topic,
                event_date,
                start_time,
                end_time,
                location,
                capacity,
                registration_deadline,
                status
            FROM events
            WHERE id = ?
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()

        if not existing_event:
            abort(404)

        if request.method == "POST":
            event_data = parse_event_form(request.form)
            errors, capacity_value = validate_event_form(event_data)

            if errors:
                for error in errors:
                    flash(error, "danger")
                event_data["id"] = event_id
                return render_template(
                    "admin/event_form.html",
                    mode="Edit",
                    event=event_data,
                )

            connection.execute(
                """
                UPDATE events
                SET
                    title = ?,
                    description = ?,
                    topic = ?,
                    event_date = ?,
                    start_time = ?,
                    end_time = ?,
                    location = ?,
                    capacity = ?,
                    registration_deadline = ?,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    event_data["title"],
                    event_data["description"] or None,
                    event_data["topic"],
                    event_data["event_date"],
                    event_data["start_time"],
                    event_data["end_time"],
                    event_data["location"],
                    capacity_value,
                    event_data["registration_deadline"] or None,
                    event_data["status"],
                    istanbul_now(),
                    event_id,
                ),
            )
            connection.commit()
            flash("Event updated successfully.", "success")
            return redirect(url_for("event_detail", event_id=event_id))

        return render_template("admin/event_form.html", mode="Edit", event=existing_event)
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("events_list"))
    except sqlite3.Error:
        flash("Could not load event for editing.", "danger")
        return redirect(url_for("events_list"))
    finally:
        if connection:
            connection.close()


@app.route("/events/<int:event_id>/delete", methods=["POST"])
@admin_required
def event_delete(event_id):
    connection = None
    try:
        connection = get_db_connection()
        event = connection.execute(
            "SELECT id, title, status FROM events WHERE id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        if not event:
            abort(404)

        connection.execute("DELETE FROM events WHERE id = ?", (event_id,))
        connection.commit()
        flash("Event removed successfully.", "success")
        return redirect(url_for("events_list"))
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("events_list"))
    except sqlite3.Error:
        flash("Could not remove event. Please try again.", "danger")
        return redirect(url_for("events_list"))
    finally:
        if connection:
            connection.close()


@app.route("/invitations")
@admin_required
def invitations_list():
    invitations = []
    connection = None
    try:
        connection = get_db_connection()
        rows = connection.execute(
            """
            SELECT
                i.id,
                i.token,
                i.status,
                i.created_at,
                i.sent_at,
                i.responded_at,
                e.id AS event_id,
                e.title AS event_title,
                e.event_date,
                a.id AS advisor_id,
                a.full_name AS advisor_name,
                a.email AS advisor_email
            FROM invitations i
            JOIN events e ON e.id = i.event_id
            JOIN advisors a ON a.id = i.advisor_id
            ORDER BY i.created_at DESC, i.id DESC
            """
        ).fetchall()
        for row in rows:
            invitation = dict(row)
            invitation.update(get_invitation_status_meta(invitation["status"]))
            invitations.append(invitation)
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
    except sqlite3.Error:
        flash("Could not load invitations from database.", "danger")
    finally:
        if connection:
            connection.close()

    return render_template(
        "admin/invitations_list.html",
        invitations=invitations,
        base_url=(app.config.get("BASE_URL") or request.url_root).rstrip("/"),
        delivery_mode=app.config.get("INVITATION_DELIVERY_MODE", "local"),
    )


@app.route("/api/advisors/ranked")
@admin_required
def api_advisors_ranked():
    event_id = parse_positive_int(request.args.get("event_id"))
    if not event_id:
        return jsonify({"error": "event_id is required"}), 400

    connection = None
    try:
        connection = get_db_connection()
        event = connection.execute(
            "SELECT id, title, topic, description FROM events WHERE id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        if not event:
            return jsonify({"error": "Event not found"}), 404

        advisors = connection.execute(
            """SELECT id, title, full_name, department, expertise_keywords,
                      recent_seminar_topics, all_topics_corpus, email
               FROM advisors ORDER BY full_name ASC"""
        ).fetchall()

        ranked = rank_advisors(
            event["topic"] or event["title"],
            event["description"] or "",
            advisors,
        )
        return jsonify({"ranked": ranked})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        if connection:
            connection.close()


@app.route("/invitations/new", methods=["GET", "POST"])
@admin_required
def invitation_new():
    invitation_data = {"event_id": "", "advisor_id": ""}
    events = []
    advisors = []
    connection = None

    try:
        connection = get_db_connection()
        events = connection.execute(
            """
            SELECT id, title, event_date, start_time, end_time, location
            FROM events
            ORDER BY event_date DESC, id DESC
            """
        ).fetchall()
        advisors = connection.execute(
            """
            SELECT id, full_name, email, department
            FROM advisors
            ORDER BY full_name ASC, id ASC
            """
        ).fetchall()

        preselected_event_id = parse_positive_int(request.args.get("event_id"))
        if request.method == "GET" and preselected_event_id:
            invitation_data["event_id"] = str(preselected_event_id)

        if request.method == "POST":
            invitation_data["event_id"] = request.form.get("event_id", "").strip()
            invitation_data["advisor_id"] = request.form.get("advisor_id", "").strip()

            event_id = parse_positive_int(invitation_data["event_id"])
            advisor_id = parse_positive_int(invitation_data["advisor_id"])
            errors = []

            if not event_id:
                errors.append("Please select an event.")
            if not advisor_id:
                errors.append("Please select an advisor.")
            if not events:
                errors.append("No events found. Create an event first.")
            if not advisors:
                errors.append("No advisors found. Create an advisor first.")

            selected_event = None
            selected_advisor = None
            if event_id:
                selected_event = connection.execute(
                    "SELECT id FROM events WHERE id = ? LIMIT 1", (event_id,)
                ).fetchone()
                if not selected_event:
                    errors.append("Selected event does not exist.")
            if advisor_id:
                selected_advisor = connection.execute(
                    "SELECT id FROM advisors WHERE id = ? LIMIT 1", (advisor_id,)
                ).fetchone()
                if not selected_advisor:
                    errors.append("Selected advisor does not exist.")

            if event_id and advisor_id:
                duplicate = connection.execute(
                    """
                    SELECT id FROM invitations
                    WHERE event_id = ? AND advisor_id = ?
                    LIMIT 1
                    """,
                    (event_id, advisor_id),
                ).fetchone()
                if duplicate:
                    errors.append(
                        "An invitation for this event and advisor already exists."
                    )

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template(
                    "admin/invitation_form.html",
                    invitation=invitation_data,
                    events=events,
                    advisors=advisors,
                )

            token = generate_unique_invitation_token(connection)
            connection.execute(
                """
                INSERT INTO invitations (event_id, advisor_id, token, status, sent_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (event_id, advisor_id, token, istanbul_now()),
            )
            connection.commit()

            # Send the email immediately
            invitation = load_invitation_by_id(
                connection,
                connection.execute("SELECT last_insert_rowid()").fetchone()[0],
            )
            response_url = build_invitation_response_url(invitation["token"])
            subject = build_invitation_subject(invitation)
            body = build_invitation_body(invitation, response_url)
            delivery_mode = app.config.get("INVITATION_DELIVERY_MODE", "local").lower()

            if delivery_mode == "smtp":
                success, message = send_invitation_email(
                    app.config, invitation["advisor_email"], subject, body
                )
                flash(message, "success" if success else "danger")
            elif delivery_mode == "api":
                success, message = send_invitation_email_api(
                    app.config, invitation["advisor_email"], subject, body
                )
                flash(message, "success" if success else "danger")
            else:
                flash(
                    "Invitation created and ready to share locally. Response link is available.",
                    "success",
                )

            return redirect(url_for("invitations_list"))
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
    except sqlite3.IntegrityError:
        flash("An invitation for this event and advisor already exists.", "danger")
    except sqlite3.Error:
        flash("Could not create invitation. Please try again.", "danger")
    finally:
        if connection:
            connection.close()

    return render_template(
        "admin/invitation_form.html",
        invitation=invitation_data,
        events=events,
        advisors=advisors,
    )


@app.route("/invitations/<int:invitation_id>/preview")
@admin_required
def invitation_preview(invitation_id):
    connection = None
    try:
        connection = get_db_connection()
        invitation = load_invitation_by_id(connection, invitation_id)
        if not invitation:
            abort(404)

        response_url = build_invitation_response_url(invitation["token"])
        subject = build_invitation_subject(invitation)
        body = build_invitation_body(invitation, response_url)
        status_meta = get_invitation_status_meta(invitation["status"])

        return render_template(
            "admin/invitation_preview.html",
            invitation=invitation,
            response_url=response_url,
            subject=subject,
            body=body,
            status_meta=status_meta,
            delivery_mode=app.config.get("INVITATION_DELIVERY_MODE", "local"),
        )
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("invitations_list"))
    except sqlite3.Error:
        flash("Could not load invitation preview.", "danger")
        return redirect(url_for("invitations_list"))
    finally:
        if connection:
            connection.close()


@app.route("/invitations/<int:invitation_id>/send", methods=["POST"])
@admin_required
def invitation_send(invitation_id):
    connection = None
    try:
        connection = get_db_connection()
        invitation = load_invitation_by_id(connection, invitation_id)
        if not invitation:
            abort(404)

        if invitation["status"] != "pending":
            flash(
                "This invitation already has a final response and cannot be sent again.",
                "warning",
            )
            if request.form.get("next") == "preview":
                return redirect(url_for("invitation_preview", invitation_id=invitation_id))
            return redirect(url_for("invitations_list"))

        response_url = build_invitation_response_url(invitation["token"])
        subject = build_invitation_subject(invitation)
        body = build_invitation_body(invitation, response_url)
        delivery_mode = app.config.get("INVITATION_DELIVERY_MODE", "local").lower()
        was_sent = invitation["sent_at"] is not None

        if delivery_mode == "smtp":
            success, message = send_invitation_email(
                app.config, invitation["advisor_email"], subject, body
            )
            if not success:
                flash(message, "danger")
            else:
                connection.execute(
                    "UPDATE invitations SET sent_at = ? WHERE id = ?",
                    (istanbul_now(), invitation_id),
                )
                connection.commit()
                flash(
                    "Invitation re-sent successfully via SMTP."
                    if was_sent
                    else "Invitation sent successfully via SMTP.",
                    "success",
                )
        elif delivery_mode == "api":
            success, message = send_invitation_email_api(
                app.config, invitation["advisor_email"], subject, body
            )
            if not success:
                flash(message, "danger")
            else:
                connection.execute(
                    "UPDATE invitations SET sent_at = ? WHERE id = ?",
                    (istanbul_now(), invitation_id),
                )
                connection.commit()
                flash(
                    "Invitation re-sent successfully via API." if was_sent else "Invitation sent successfully via API.",
                    "success",
                )
        else:
            connection.execute(
                "UPDATE invitations SET sent_at = ? WHERE id = ?",
                (istanbul_now(), invitation_id),
            )
            connection.commit()
            flash(
                (
                    "Invitation re-shared locally. sent_at was updated and response link is available."
                    if was_sent
                    else "Invitation ready to share locally. sent_at was updated and response link is available."
                ),
                "success",
            )

        if request.form.get("next") == "preview":
            return redirect(url_for("invitation_preview", invitation_id=invitation_id))
        return redirect(url_for("invitations_list"))
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("invitations_list"))
    except sqlite3.Error:
        flash("Could not process invitation sending.", "danger")
        return redirect(url_for("invitations_list"))
    finally:
        if connection:
            connection.close()


@app.route("/events/<int:event_id>/registrations")
@login_required
def registrations_list(event_id):
    connection = None
    try:
        connection = get_db_connection()
        event = connection.execute(
            """
            SELECT id, title, topic, event_date, start_time, end_time, location, capacity
            FROM events
            WHERE id = ?
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if not event:
            abort(404)

        registrations = connection.execute(
            """
            SELECT id, student_name, student_id, email, state, registered_at
            FROM registrations
            WHERE event_id = ?
            ORDER BY registered_at DESC, id DESC
            """,
            (event_id,),
        ).fetchall()

        active_count = connection.execute(
            """
            SELECT COUNT(*) FROM registrations
            WHERE event_id = ? AND state = 'active'
            """,
            (event_id,),
        ).fetchone()[0]
        remaining_seats = max(int(event["capacity"]) - int(active_count), 0)

        return render_template(
            "admin/registrations_list.html",
            event=event,
            registrations=registrations,
            active_count=active_count,
            remaining_seats=remaining_seats,
        )
    except FileNotFoundError:
        flash(
            "Database not found. Initialize it first with `python database/init_db.py`.",
            "danger",
        )
        return redirect(url_for("events_list"))
    except sqlite3.Error:
        flash("Could not load registrations.", "danger")
        return redirect(url_for("events_list"))
    finally:
        if connection:
            connection.close()


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your email address.", "warning")
            return render_template("auth/forgot_password.html", email=email)

        connection = None
        try:
            connection = get_db_connection()
            user = connection.execute(
                "SELECT id, full_name, email FROM users WHERE email = ? LIMIT 1",
                (email,),
            ).fetchone()

            if not user:
                flash("No account found with that email address.", "danger")
                return render_template("auth/forgot_password.html", email=email)

            new_password = secrets.token_urlsafe(8)
            new_hash = generate_password_hash(new_password)
            connection.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                (new_hash, user["id"]),
            )
            connection.commit()

            delivery_mode = app.config.get("INVITATION_DELIVERY_MODE", "local").lower()
            if delivery_mode == "smtp":
                subject = "Your Password Has Been Reset"
                body = (
                    f"Hello {user['full_name']},\n\n"
                    f"Your password has been reset. Your new temporary password is:\n\n"
                    f"    {new_password}\n\n"
                    f"Please log in and change it as soon as possible.\n\n"
                    f"Regards,\nThe BAU Team"
                )
                send_invitation_email(app.config, user["email"], subject, body)
            elif delivery_mode == "api":
                subject = "Your Password Has Been Reset"
                body = (
                    f"Hello {user['full_name']},\n\n"
                    f"Your password has been reset. Your new temporary password is:\n\n"
                    f"    {new_password}\n\n"
                    f"Please log in and change it as soon as possible.\n\n"
                    f"Regards,\nThe BAU Team"
                )
                send_invitation_email_api(app.config, user["email"], subject, body)
            return render_template(
                "auth/forgot_password.html",
                email=email,
                success=True,
                new_password=new_password if delivery_mode == "local" else None,
                user_name=user["full_name"],
                delivery_mode=delivery_mode,
            )
        except (FileNotFoundError, sqlite3.Error):
            flash("Could not process password reset. Please try again.", "danger")
            return render_template("auth/forgot_password.html", email=email)
        finally:
            if connection:
                connection.close()

    return render_template("auth/forgot_password.html")


# ---------------------------------------------------------------------------
# Invitation Cancel / Reset (Admin)
# ---------------------------------------------------------------------------

@app.route("/invitations/<int:invitation_id>/update-status", methods=["POST"])
@admin_required
def invitation_update_status(invitation_id):
    action = request.form.get("action", "").strip().lower()
    if action not in {"cancel", "reset"}:
        flash("Invalid action.", "danger")
        return redirect(url_for("invitations_list"))

    connection = None
    try:
        connection = get_db_connection()
        invitation = connection.execute(
            "SELECT id, status FROM invitations WHERE id = ? LIMIT 1",
            (invitation_id,),
        ).fetchone()
        if not invitation:
            abort(404)

        if action == "cancel":
            connection.execute(
                "UPDATE invitations SET status = 'cancelled' WHERE id = ?",
                (invitation_id,),
            )
            connection.commit()
            flash("Invitation cancelled.", "success")
        elif action == "reset":
            connection.execute(
                """UPDATE invitations
                   SET status = 'pending', response_note = NULL, responded_at = NULL
                   WHERE id = ?""",
                (invitation_id,),
            )
            connection.commit()
            flash("Invitation reset to pending.", "success")
    except (FileNotFoundError, sqlite3.Error):
        flash("Could not update invitation status.", "danger")
    finally:
        if connection:
            connection.close()

    return redirect(url_for("invitations_list"))


# ---------------------------------------------------------------------------
# Bulk Invitation Creation (Admin)
# ---------------------------------------------------------------------------

@app.route("/invitations/bulk-create", methods=["GET", "POST"])
@admin_required
def invitation_bulk_create():
    events = []
    advisors = []
    departments = []
    connection = None

    try:
        connection = get_db_connection()
        events = connection.execute(
            """SELECT id, title, event_date, start_time, end_time, location
               FROM events ORDER BY event_date DESC, id DESC"""
        ).fetchall()
        advisors = connection.execute(
            """SELECT id, title, full_name, email, department
               FROM advisors ORDER BY department ASC, full_name ASC"""
        ).fetchall()
        dept_rows = connection.execute(
            "SELECT DISTINCT department FROM advisors ORDER BY department ASC"
        ).fetchall()
        departments = [r["department"] for r in dept_rows]

        if request.method == "POST":
            event_id = parse_positive_int(request.form.get("event_id"))
            advisor_ids = request.form.getlist("advisor_ids")
            personal_message = request.form.get("personal_message", "").strip()

            errors = []
            if not event_id:
                errors.append("Please select an event.")
            if not advisor_ids:
                errors.append("Please select at least one advisor.")

            if errors:
                for e in errors:
                    flash(e, "danger")
                return render_template(
                    "admin/invitation_bulk.html",
                    events=events, advisors=advisors, departments=departments,
                    selected_event_id=str(event_id or ""),
                    personal_message=personal_message,
                )

            created = 0
            skipped = 0
            for aid_str in advisor_ids:
                aid = parse_positive_int(aid_str)
                if not aid:
                    continue
                dup = connection.execute(
                    "SELECT id FROM invitations WHERE event_id=? AND advisor_id=? LIMIT 1",
                    (event_id, aid),
                ).fetchone()
                if dup:
                    skipped += 1
                    continue
                token = generate_unique_invitation_token(connection)
                connection.execute(
                    """INSERT INTO invitations
                       (event_id, advisor_id, token, status, personal_message, sent_at)
                       VALUES (?, ?, ?, 'pending', ?, ?)""",
                    (event_id, aid, token, personal_message or None, istanbul_now()),
                )
                created += 1

            connection.commit()
            msg = f"{created} invitation(s) created."
            if skipped:
                msg += f" {skipped} skipped (already exist)."
            flash(msg, "success")
            return redirect(url_for("invitations_list"))

    except (FileNotFoundError, sqlite3.Error):
        flash("Could not process bulk invitations.", "danger")
    finally:
        if connection:
            connection.close()

    return render_template(
        "admin/invitation_bulk.html",
        events=events, advisors=advisors, departments=departments,
        selected_event_id=request.args.get("event_id", ""),
        personal_message="",
    )


if __name__ == "__main__":
    app.run(debug=True)
