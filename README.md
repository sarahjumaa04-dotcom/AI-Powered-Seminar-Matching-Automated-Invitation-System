# Seminar and Summit Management Capstone Prototype

## Overview
This project is a simple localhost web system for seminar/summit management. It is designed for capstone submission and focuses on core end-to-end flows with minimal complexity.

## Project Goal
Provide a clean, runnable Flask application where organizers can manage advisors/events/invitations and students can view public events and reserve seats.

## Tech Stack (Locked)
- Backend: Python
- Framework: Flask
- Templates: Jinja2
- Database: SQLite (`sqlite3`)
- Frontend: HTML, CSS, JavaScript
- Styling: Bootstrap 5 + minimal custom CSS
- Authentication: Flask session-based login
- Run mode: localhost only

## System Roles
- Admin (authenticated)
- Organizer (authenticated)
- Student/public user (no login)


## Setup and Run
1. Install Python 3.12+ and make sure `python3 --version` works in a new terminal.
2. Recreate the virtual environment if `.venv` points to an old Python install:
   - macOS/Linux: `rm -rf .venv`
   - Windows: `rmdir /s /q .venv`
   - `python3 -m venv .venv`
3. Activate the virtual environment.
   - macOS/Linux: `source .venv/bin/activate`
   - PowerShell: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
     then `.\.venv\Scripts\Activate.ps1`
   - Command Prompt: `.\.venv\Scripts\activate.bat`
4. Install dependencies:
   - `python -m pip install -r requirements.txt`
   - Note: `sentence-transformers`, `scikit-learn`, and `openpyxl` may take a few moments to install.
5. Initialize database:
   - `python database/init_db.py`
6. Run app:
   - `python app.py`
   - or macOS/Linux: `bash run.sh` or `./run.sh`
   - or Windows: `.\run.bat`
7. Open in browser:
   - `http://127.0.0.1:5000`

### Troubleshooting
- If `python3` is required, use `python3` instead of `python`.
- If PowerShell says running scripts is disabled, use the process-only command above or activate with `activate.bat`.
- If `.venv\Scripts\python.exe` reports the base Python cannot be found, reinstall Python and recreate `.venv`.

## RUN this
- macOS/Linux: `bash run.sh` or `./run.sh`
- Windows: `.\run.bat`

## Sample Login Credentials
- Admin: `admin@bau.edu.tr` / `admin123`
- Organizer: `organizer@bau.edu.tr` / `organizer123`

## Demo Order (Recommended)
1. Login (`/login`)
2. Add/edit advisors (`/advisors`)
3. Run advisor matching (`/advisors/match`)
4. Create/edit event (`/events`, `/events/new`)
5. Create invitation (`/invitations/new`)
6. Preview/send invitation (`/invitations` -> Preview -> Send/Resend for pending invitations)
7. Open token response link (`/invite/respond/<token>`)
8. View public events (`/events/public`)
9. Register as student (`/register/<event_id>`)
10. Review registrations (`/events/<event_id>/registrations`)

## Final Business Rules
- Invitation statuses:
  - `pending` = awaiting response
  - `accepted` = confirmed speaker/advisor
  - `declined` = not participating
  - `cancelled` = withdrawn by admin
- Event status values:
  - `draft` = draft event
  - `open` = event is visible and registrable
  - `closed` = event is visible but registration is closed
- Public event rule:
  - Public events are shown when `status` is `open` or `closed`.
  - There is no separate `visibility = public` or `status = public` state in this version.
- Matching rule:
  - Match score is based on expertise keyword overlap between seminar topic and advisor expertise (shown as percentage).
  - Simple phrase normalization is applied for close variants (for example, `cybersecurity` and `cyber security`).
- Invitation send rule:
  - Send/Resend is allowed only while invitation status is `pending`.
  - `accepted`, `declined`, and `cancelled` invitations are treated as final.

## Invitation Delivery Mode
Default mode is local and requires no external email service.

- Local mode (default):
  - `INVITATION_DELIVERY_MODE=local`
  - Send/Resend updates `sent_at` and supports manual link sharing.

- Optional SMTP mode (basic):
  - `INVITATION_DELIVERY_MODE=smtp`
  - Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`
  - Optional: `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`

- Optional API mode (Sendinblue):
  - `INVITATION_DELIVERY_MODE=api`
  - Set `EMAIL_PROVIDER=sendinblue`
  - Set `EMAIL_API_KEY` or `SENDINBLUE_API_KEY`
  - Set `EMAIL_FROM_EMAIL` or `SMTP_FROM_EMAIL`
  - Optional: `EMAIL_FROM_NAME` for the sender display name

Notes:
- This is intentionally basic SMTP and Sendinblue API support for prototype use.
- No queue/retry/tracking infrastructure is implemented.

## Demo Data Note
After this final logic cleanup, reinitialize the database for a clean demo dataset:
- `python database/init_db.py`

## Project Structure Summary
- `app.py` - Main Flask routes and logic
- `config.py` - App and delivery configuration
- `requirements.txt` - Minimal dependencies
- `database/schema.sql` - SQLite schema
- `database/init_db.py` - DB initialization and seed script
- `templates/` - Jinja templates (admin/public/auth/errors)
- `static/` - CSS/JS assets
- `utils/` - Small helper modules (matching, invitations)
- `docs/` - scope, phases, DB notes, and final submission docs


