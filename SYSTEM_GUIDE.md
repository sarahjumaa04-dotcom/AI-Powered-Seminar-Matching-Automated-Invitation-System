# BAU Seminar & Summit Management System — User Guide

## What Is This System?

This is a **web-based event management system** built for Bahçeşehir University (BAU). It allows the university to:

- Create and manage seminars, summits, and academic events
- Find the best professors for each event using **AI-powered semantic matching with category-aware ranking**
- Send and track speaker invitations to professors
- Allow students to browse public events and reserve seats

The system runs locally on your computer at `http://127.0.0.1:5000` and uses a local SQLite database with **50 real BAU professors** pre-loaded from the provided Excel file.

---

## Who Has Access?

There are **4 types of users** in the system:

| User Type | How They Access | Login Required? |
|-----------|----------------|-----------------|
| **Admin** | Login at `/login` | Yes |
| **Organizer** | Login at `/login` | Yes |
| **Professor (Advisor)** | Via invitation token link | No |
| **Student (Public)** | Public pages, no login | No |

### Default Login Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@bau.edu.tr` | `admin123` |
| Organizer | `organizer@bau.edu.tr` | `organizer123` |

---

## What Can Each User Do?

### 1. Admin — Full Control

The admin has **complete access** to every feature in the system. This is the primary management role.

| Feature | What Admin Can Do |
|---------|-------------------|
| **Events** | Create, edit, delete any event. Set status (Draft/Open/Closed), capacity, registration deadline |
| **Professors** | View all 50 professors, add new ones, edit their details, remove them |
| **AI Matching** | Enter a seminar topic → system ranks all 50 professors by relevance using AI (0–100% per professor) |
| **Single Invitation** | Pick one event + one professor → create an invitation with a unique token link |
| **Bulk Invitation** | Select an event → filter professors by department → "Select All" or pick individually → send invitations to multiple professors at once with a personalized message |
| **Invitation Management** | View all invitations. **Cancel** an invitation (withdraws it). **Reset** a cancelled/declined/accepted invitation back to pending |
| **Registrations** | View which students have registered for each event |
| **Forgot Password** | Reset their own password via the forgot password page |
| **Dashboard** | See stats: total events, public events, pending invitations, registrations |

### 2. Organizer — Events Only

The organizer has **limited access**. They can only work with events.

| Feature | What Organizer Can Do |
|---------|----------------------|
| **Events** | Create new events, edit their own events |
| **Registrations** | View which students have registered for events |
| **Dashboard** | See event-related stats only |

| Feature | What Organizer CANNOT Do |
|---------|--------------------------|
| Professors / Advisors | ❌ Cannot view, add, edit, or remove professors |
| AI Matching | ❌ Cannot access the matching page |
| Invitations | ❌ Cannot create, send, cancel, or manage any invitations |
| Delete Events | ❌ Cannot delete events (admin only) |

> The organizer's navigation bar only shows "Home", "Public Events", and "Management → Dashboard / Events". All restricted pages are hidden AND protected — even if they type the URL directly, they'll be redirected to the dashboard with an "Admin access required" message.

### 3. Professor (Advisor) — Invitation Response Only

Professors **do not have login accounts**. They interact with the system only through **invitation links**.

**How it works:**

1. Admin creates an invitation for a professor
2. The system generates a unique token URL like:
   `http://127.0.0.1:5000/invite/abc123xyz`
3. This link is shared with the professor (copied manually in local mode, or sent via email in SMTP mode)
4. The professor opens the link and sees:
   - Event details (title, topic, date with day name, time, location)
   - Their name and the current invitation status
5. The professor can:
   - **Accept** the invitation
   - **Decline** the invitation
   - **Change their mind** — if they accepted, they can later decline (and vice versa)
   - Add an optional **response note** for the organizer
6. If the admin **cancels** the invitation, the professor sees "This invitation has been cancelled by the admin" and cannot respond anymore

### 4. Student (Public) — Browse and Register

Students access the system **without any login**. They use the public-facing pages.

**What students can do:**

1. **Browse Public Events** — Only events marked as "public" with at least one confirmed (accepted) speaker appear here
2. **View Event Details** — See the event topic, date (with day name), time, location, capacity, remaining seats
3. **Reserve a Seat** — Fill in their name, student ID, and email to register for an event
   - Registration is blocked if: the event is full, the deadline has passed, or registration is closed

---

## How Does the System Work? (End-to-End Flow)

Here is the typical workflow from start to finish:

### Step 1: Admin Creates an Event

```
Dashboard → Events → Create Event
```

Admin fills in:
- Title (e.g., "AI in Education Summit")
- Topic (e.g., "Artificial Intelligence in Education")
- Description (optional context)
- Date and Time (day name shown automatically, e.g., "Monday, 2026-06-15")
- Location (e.g., "BAU Main Auditorium")
- Capacity (e.g., 120 seats)
- Registration Deadline (optional)
- Status: **Draft** (default — not visible to students yet)

### Step 2: Admin Uses AI Matching to Find Professors

```
Dashboard → AI Matching
```

Admin enters the seminar topic (e.g., "Artificial Intelligence and machine learning") and optionally a description for better accuracy.

The system uses a transformer-based AI model (`all-MiniLM-L6-v2`) and category-aware ranking to:
1. Convert the seminar topic into a mathematical vector (embedding)
2. Convert each professor's full expertise profile into a vector (keywords + recent conference topics + all past conference topics + department)
3. Detect the most likely academic category for the seminar (software, mechanical, biomedical, civil, mathematics, physics, etc.)
4. Calculate **cosine similarity** between the seminar and each professor
5. Apply a **category relevance boost** for professors in the detected field
6. Apply a **penalty** to professors whose expertise is not in the detected category
7. Return a **ranked list** with:
   - **Score** (0–100% per professor, independently calculated)
   - **Score Label** (Excellent Match / Strong Match / Moderate Match / Weak Match / Low Relevance)
   - **Why Matched** — Human-readable explanation:
     - "Recent topic: Neural Networks in Image Recognition"
     - "Keyword overlap: machine learning, NLP, AI"
     - "Department: Artificial Intelligence Engineering"

> **Important:** The first time you run AI Matching after starting the app, it takes ~15-30 seconds because the AI model needs to download (~80MB, happens once). After that, matching runs in a few seconds.

### Step 3: Admin Sends Invitations

**Option A — Single Invitation:**
```
Invitations → Single Invite → Select Event → Select Professor → Create
```

**Option B — Bulk Invitation (recommended):**
```
Invitations → Bulk Invite → Select Event → Select professors by department → Add personalized message → Create
```

In bulk mode:
- Professors are grouped by department
- Each department has a "Select All" checkbox
- There's a global "Select All" checkbox
- The admin can write a personalized message template using placeholders:
  - `{name}` → replaced with each professor's name
  - `{event_title}` → replaced with the event title
  - Example: `"Dear {name}, we are pleased to invite you to {event_title}..."`
- Duplicate invitations are automatically skipped

### Step 4: Admin Shares Invitation Links

After creating invitations, the admin goes to:
```
Invitations → Preview (eye icon) → Copy the Response Link
```

In **local mode** (default): The admin manually copies the response URL and shares it with the professor (e.g., via email, WhatsApp, etc.)

In **SMTP mode** (optional): The system can send the invitation via email automatically if SMTP is configured in `config.py`.

### Step 5: Professors Respond

Professors open their unique link and accept or decline. The admin can see the status change in real-time on the Invitations page.

### Step 6: Admin Opens Event for Students

When the admin is ready, they simply change the status:
```
Events → Edit Event → Status: Open
```

Now the event appears on the **Public Events** page for students.

### Step 7: Students Register

Students visit the homepage, click "View Public Events", choose an event, and fill in the registration form. The system tracks remaining seats automatically.

### Step 8: Admin Monitors Everything

The admin can:
- View all registrations per event
- Cancel/reset invitations if needed
- Close registration by changing event status to "Closed"

---

## Feature Details

### AI Matching — Score Interpretation

| Score Range | Label | Meaning |
|------------|-------|---------|
| 90–100% | Excellent Match | Professor's expertise highly aligns with the seminar topic and detected academic field |
| 70–89% | Strong Match | Good alignment, professor has relevant experience in the detected category |
| 50–69% | Moderate Match | Some overlap, professor has partially related work |
| 20–49% | Weak Match | Minimal overlap, limited relevance |
| 0–19% | Low Relevance | Very little or no connection found or outside the detected category |

> The matching uses **semantic understanding**, not just keyword overlap. For example, searching "machine learning" will match professors whose expertise mentions "neural networks", "deep learning", or "pattern recognition" even if they never used the exact phrase "machine learning".
> 
> It also uses **category-aware ranking**, so a software-related query will prefer software/AI professors and deprioritize unrelated departments more strongly.

### Invitation Statuses

| Status | Who Sets It | Meaning |
|--------|------------|---------|
| **Pending** | System (on creation) | Waiting for the professor to respond |
| **Accepted** | Professor | Professor confirmed participation |
| **Declined** | Professor | Professor is not participating |
| **Cancelled** | Admin | Admin withdrew the invitation |

**Status transitions allowed:**
- Professor: `pending → accepted`, `pending → declined`, `accepted → declined`, `declined → accepted`
- Admin: Any status → `cancelled`, Any status → `pending` (reset)
- If cancelled by admin, professor **cannot** respond anymore

### Forgot Password

1. Click "Forgot Password?" on the login page
2. Enter your registered email (e.g., `admin@bau.edu.tr`)
3. System generates a new random secure password
4. **In local/demo mode**: The new password is displayed on screen with a "Demo Mode" badge
5. **In SMTP mode**: The new password would be sent to the email address
6. Use the new password to log in

### Day Names on Dates

All dates throughout the system show the day name:
- "Saturday, 2026-06-15" instead of just "2026-06-15"
- The event creation form also shows a live day name preview when you pick a date

---

## Database — The 50 Professors

The system comes pre-loaded with **50 real Bahçeşehir University professors** from the provided Excel file. For each professor, the database stores:

| Field | Description | Example |
|-------|-------------|---------|
| Title | Academic title | "Prof. Dr.", "Assoc. Prof.", "Assist Prof." |
| Full Name | Professor's name | "Prof. Dr. Ahmet Arif ERGİN" |
| Department | BAU department | "Artificial Intelligence Engineering" |
| Email | University email | "arif.ergin@bau.edu.tr" |
| Expertise Keywords | Aggregated from all conferences | "Computational Electromagnetics; Scattering; Numerical Methods; ..." |
| Recent Academic Topics | Last 5 conference/seminar topics (by date) | "Electromagnetic scattering computation \| Antenna transient analysis \| ..." |
| All Topics Corpus | Full history of conference topics | Used by AI matching for deep analysis |

The professors span **17 departments** including: Computer Engineering, AI Engineering, Software Engineering, Industrial Engineering, Physics, Mathematics, Biomedical Engineering, and more.

---

## Current Limitations

These are things the system does **not** do (yet) or where behavior is limited:

### Authentication & Security
- **No email verification** — User accounts are created manually in the database
- **No password complexity requirements** — Any password is accepted
- **Session-based auth only** — No JWT, no OAuth, no 2FA
- **Forgot password in local mode shows the password on screen** — In a production system, this would only be sent via email

### Invitation Delivery
- **Local mode (default)**: Invitations are NOT automatically emailed. The admin must manually copy and share the invitation link with each professor
- **SMTP mode**: Basic SMTP support is available but requires manual configuration in `config.py`. No retry, no queue, no delivery tracking
- **No notification system** — Professors are not notified when their invitation status changes

### AI Matching
- **First-time model download** — The AI model (~80MB) downloads from HuggingFace the first time you use matching. Requires internet connection for this one-time download
- **No GPU acceleration** — The model runs on CPU, which is sufficient for 50 professors but may be slow for thousands
- **Scores are relative, not absolute** — A 100% match doesn't guarantee the professor is the perfect speaker; it means their expertise profile has the highest semantic similarity to the query
- **English-focused model** — The AI model (`all-MiniLM-L6-v2`) is optimized for English text. Turkish content in professor profiles may have slightly reduced matching accuracy

### Events & Registration
- **No email confirmation for student registration** — Students register but don't receive a confirmation email
- **No duplicate student check across events** — A student can register for multiple events
- **No waitlist** — When an event is full, registration is simply blocked
- **No event categories or tags** — Events are only searchable by their title/topic

### User Management
- **No user registration page** — Admin and organizer accounts must be created via `init_db.py` or directly in the database
- **No user profile editing** — Users cannot change their own name or email through the UI
- **Only 2 roles** — Admin and Organizer. No student accounts, no professor accounts

### Data & Storage
- **SQLite database** — Single-file database, not suitable for concurrent multi-user production use
- **No backup system** — The database is a single file (`database/app.db`); losing it means losing all data
- **No file uploads** — Cannot attach documents, images, or files to events
- **No export** — Cannot export registrations, invitations, or reports to CSV/Excel

### UI/UX
- **No dark mode toggle** — The system uses a light theme with BAU colors only
- **No search/filter on professor list** — All 50 professors are shown in a single table
- **No pagination** — All records are shown on one page (adequate for 50 professors, but would be an issue at scale)
- **No calendar view for events** — Events are shown in a table list, not a calendar

### Deployment
- **Localhost only** — The system runs on `127.0.0.1:5000` on your local machine
- **Not production-ready** — Uses Flask's development server, not a production WSGI server
- **Single user at a time** — SQLite and Flask dev server are not designed for concurrent users

---

## Project File Structure

```
Project - V1/
├── app.py                          # Main Flask app (all routes and logic)
├── config.py                       # App configuration (DB path, SMTP settings)
├── requirements.txt                # Python dependencies
├── run.bat                         # One-click startup script
├── database/
│   ├── schema.sql                  # SQLite table definitions
│   ├── init_db.py                  # Database initialization + Excel import
│   └── app.db                      # SQLite database file (created on first run)
├── utils/
│   ├── matching.py                 # AI semantic matching engine
│   └── invitations.py              # Invitation email builder
├── static/
│   ├── css/styles.css              # BAU-branded stylesheet
│   └── js/main.js                  # Client-side JavaScript
├── templates/
│   ├── base.html                   # Base layout (navbar, footer, branding)
│   ├── auth/
│   │   ├── login.html              # Login page
│   │   └── forgot_password.html    # Password reset page
│   ├── admin/
│   │   ├── dashboard.html          # Admin/Organizer dashboard
│   │   ├── events_list.html        # Events list
│   │   ├── event_form.html         # Create/Edit event form
│   │   ├── event_detail.html       # Event details + invitation summary
│   │   ├── advisors_list.html      # Professors list
│   │   ├── advisor_form.html       # Create/Edit professor form
│   │   ├── advisor_match.html      # AI Matching page with results
│   │   ├── invitations_list.html   # All invitations with actions
│   │   ├── invitation_form.html    # Single invitation creation
│   │   ├── invitation_bulk.html    # Bulk invitation by department
│   │   ├── invitation_preview.html # Invitation preview + send
│   │   └── registrations_list.html # Student registrations per event
│   ├── public/
│   │   ├── home.html               # Homepage with BAU branding
│   │   ├── public_events.html      # Public event listing
│   │   ├── public_event_detail.html# Event details for students
│   │   ├── invite_response.html    # Professor invitation response page
│   │   └── register_form.html      # Student seat reservation
│   └── errors/
│       └── 404.html                # Not found page
└── Capstone II - DataBase - 50 Professors.xlsx  # Source professor data
```

---

## Quick Start

1. Double-click `run.bat` or run `.\run.bat` in terminal
2. Wait for dependencies to install (first time only, ~2-3 minutes)
3. Open `http://127.0.0.1:5000` in your browser
4. Login as admin: `admin@bau.edu.tr` / `admin123`
5. Explore the dashboard, professors, AI matching, and events

To reset the database to a clean state:
```
del database\app.db
.\run.bat
```
