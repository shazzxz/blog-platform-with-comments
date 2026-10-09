# Submission Checklist

- [x] User registration, login and authentication
- [x] Create, edit and delete blog posts (author-only changes)
- [x] Comment section on individual stories
- [x] RESTful Flask API
- [x] Persistent SQLite database
- [x] Responsive frontend
- [x] Search and category filtering

## Manual demo

1. Register User A and publish a story.
2. Edit and delete a story as its author.
3. Add a comment while signed in.
4. Register User B and confirm they can read/comment but cannot edit/delete User A's content.
5. Restart the backend and verify the content persists.

Run automated tests with `python -m unittest discover -s tests -v`.
