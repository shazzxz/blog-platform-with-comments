# Fieldnotes — Blog Platform with Comments

A full-stack blog application with registration/login, author-managed posts, comments, REST API endpoints and persistent storage.

## Stack

- React + Vite frontend
- Flask REST API
- SQLite for local development (no Docker/database server needed)
- JWT authentication and password hashing

## Run on Windows

1. Install Python 3.11+ and Node.js 20+.
2. Run `setup.bat` from the project root.
3. Run `run_backend.bat` in one terminal.
4. Run `run_frontend.bat` in a second terminal.
5. Open http://localhost:5173.

The backend health endpoint is http://localhost:5000/api/health. Copy `.env.example` to `.env` if setup has not done so. Change `JWT_SECRET` for any environment beyond a quick local demo.

## Main features

- Register, log in and maintain an authenticated session
- Browse, search and filter stories
- Create, edit and delete your own posts
- Read stories and add comments while signed in
- Delete your own comments
- Enforce author ownership in the API
- Keep posts and comments in a local SQLite database

## Tests

After `setup.bat`, run `python -m unittest discover -s tests -v` from the repository root.

See `SUBMISSION_CHECKLIST.md` for the requirements mapping and manual review sequence. No hosting is required by the task brief.
