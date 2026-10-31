# Features

## Authentication
- Session-based login/logout for `admin` and `organizer`
- Protected admin routes with login guard
- Public routes remain accessible without login

## Advisor Management
- Advisor list from database
- Create advisor with server-side validation
- Edit advisor with duplicate email protection

## Advisor Matching
- Topic-required matching form
- Optional short description
- Category-aware AI ranking using department, expertise, recent topics, and semantic similarity
- Supports field-sensitive matching for software, mechanical, biomedical, civil, mathematics, physics, and related domains
- Ranked result display with stronger separation between relevant advisors and unrelated profiles

## Event Management
- Event list from database
- Create event with required field validation
- Event detail view
- Edit event with updated timestamp handling
- Status and visibility constrained to locked values

## Invitation Workflow
- Invitation list with event/advisor/status data
- Create invitation by selecting event + advisor
- Duplicate event+advisor invitation prevention
- Public token response page (`accept` / `decline`)
- One-time response behavior with `responded_at` update

## Invitation Preview and Sending
- Authenticated preview page with subject/body/response link
- Local send/resend simulation (default)
- Optional basic SMTP send attempt when configured
- `sent_at` updated on successful send/share

## Student Registration
- Public event list from database (`visibility='public'`, `status='public'`, and at least one accepted invitation)
- Public event detail with seat and registration status
- Student reservation form (no student login)
- Duplicate registration and over-capacity prevention
- Registration deadline enforcement

## Validation and Error Handling
- Server-side validation on forms
- Consistent flash messages
- Clean handling for missing resources (404)
- Simple empty-state messages across list pages
