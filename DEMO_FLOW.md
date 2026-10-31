# Demo Flow

Use this short sequence during presentation.

1. Initialize database
- Run: `python database/init_db.py`

2. Start the app
- Run: `python app.py`
- Open: `http://127.0.0.1:5000`

3. Login as admin
- Go to `/login`
- Use `admin@local / admin123`

4. Manage advisors
- Open `/advisors`
- Create a new advisor
- Edit an existing advisor

5. Run advisor matching
- Open `/advisors/match`
- Enter topic + optional description
- The matching engine now uses category-aware AI ranking, so software, mechanical, biomedical, civil, mathematics, and physics queries favor advisors in the matching field
- Show ranked advisor results with higher scores for truly relevant professors and lower scores for unrelated profiles

6. Create and edit event
- Open `/events`
- Create a new event
- Open event detail
- Edit event fields

7. Create invitation
- Open `/invitations/new`
- Select event and advisor
- Submit invitation

8. Preview and send invitation
- Open `/invitations`
- Click `Preview`
- Use `Send/Resend` (local mode default)

9. Respond through public token link
- Open invitation response URL from invitations list
- Accept or decline invitation

10. View public events
- Open `/events/public`
- Open a public event detail page

11. Register as student
- Open `/register/<event_id>` from event detail
- Submit student reservation form

12. Review registrations in admin side
- Login if needed
- Open `/events/<id>/registrations`
- Show registration rows and seat counts
