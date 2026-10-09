"""Flask REST API for Fieldnotes."""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import jwt
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("JWT_SECRET", "change-this-local-development-secret"),
        DATABASE=os.getenv("BLOG_DB", str(BASE_DIR / "blog.db")),
        TOKEN_TTL_HOURS=int(os.getenv("TOKEN_TTL_HOURS", "12")),
        MAX_CONTENT_LENGTH=1_000_000,
    )
    if test_config:
        app.config.update(test_config)

    origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}})

    def connect_db():
        db_path = app.config["DATABASE"]
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def get_db():
        if "db" not in g:
            g.db = connect_db()
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def init_db():
        conn = connect_db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    excerpt TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Journal',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id);
                CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(created_at);
                CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id, created_at);
            """)
            conn.commit()
        finally:
            conn.close()

    def user_dict(row):
        return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}

    def issue_token(user):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user["id"]),
            "email": user["email"],
            "iat": now,
            "exp": now + timedelta(hours=app.config["TOKEN_TTL_HOURS"]),
        }
        return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

    def auth_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify({"error": "Please sign in to continue."}), 401
            try:
                payload = jwt.decode(header[7:].strip(), app.config["SECRET_KEY"], algorithms=["HS256"])
                user_id = int(payload["sub"])
            except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
                return jsonify({"error": "Your session has expired. Please sign in again."}), 401
            row = get_db().execute(
                "SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                return jsonify({"error": "Account not found. Please sign in again."}), 401
            g.current_user = user_dict(row)
            return fn(*args, **kwargs)
        return wrapper

    def post_dict(row, include_body=False):
        result = dict(row)
        result["comment_count"] = get_db().execute(
            "SELECT COUNT(*) FROM comments WHERE post_id = ?", (result["id"],)
        ).fetchone()[0]
        if not include_body:
            result.pop("body", None)
        return result

    def get_post_row(post_id):
        return get_db().execute("""
            SELECT p.id, p.author_id, p.title, p.excerpt, p.body, p.category,
                   p.created_at, p.updated_at, u.name AS author_name
            FROM posts p JOIN users u ON u.id = p.author_id
            WHERE p.id = ?
        """, (post_id,)).fetchone()

    @app.get("/api/health")
    def health():
        try:
            get_db().execute("SELECT 1").fetchone()
            return jsonify({"status": "ok", "database": "connected"})
        except sqlite3.Error:
            app.logger.exception("Database health check failed")
            return jsonify({"status": "error", "database": "unavailable"}), 503

    @app.post("/api/auth/register")
    def register():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not 2 <= len(name) <= 80:
            return jsonify({"error": "Name must be between 2 and 80 characters."}), 400
        if not EMAIL_RE.match(email):
            return jsonify({"error": "Enter a valid email address."}), 400
        if len(password) < 8 or len(password) > 128:
            return jsonify({"error": "Password must be at least 8 characters long."}), 400
        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), utc_now()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return jsonify({"error": "An account with that email already exists."}), 409
        row = conn.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        user = user_dict(row)
        return jsonify({"user": user, "token": issue_token(user)}), 201

    @app.post("/api/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return jsonify({"error": "Email or password is incorrect."}), 401
        user = user_dict(row)
        return jsonify({"user": user, "token": issue_token(user)})

    @app.get("/api/auth/me")
    @auth_required
    def me():
        return jsonify({"user": g.current_user})

    @app.get("/api/posts")
    def list_posts():
        search = str(request.args.get("search", "")).strip()
        category = str(request.args.get("category", "")).strip()
        sql = """
            SELECT p.id, p.author_id, p.title, p.excerpt, p.body, p.category,
                   p.created_at, p.updated_at, u.name AS author_name
            FROM posts p JOIN users u ON u.id = p.author_id WHERE 1 = 1
        """
        params = []
        if search:
            sql += " AND (LOWER(p.title) LIKE LOWER(?) OR LOWER(p.excerpt) LIKE LOWER(?) OR LOWER(p.body) LIKE LOWER(?))"
            term = "%" + search + "%"
            params.extend([term, term, term])
        if category and category.lower() != "all":
            sql += " AND p.category = ?"
            params.append(category)
        sql += " ORDER BY p.created_at DESC, p.id DESC"
        rows = get_db().execute(sql, params).fetchall()
        return jsonify({"posts": [post_dict(row) for row in rows]})

    @app.get("/api/posts/<int:post_id>")
    def get_post(post_id):
        row = get_post_row(post_id)
        if row is None:
            return jsonify({"error": "Story not found."}), 404
        return jsonify({"post": post_dict(row, include_body=True)})

    @app.post("/api/posts")
    @auth_required
    def create_post():
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        body = str(data.get("body", "")).strip()
        excerpt = str(data.get("excerpt", "")).strip()
        category = str(data.get("category", "Journal")).strip() or "Journal"
        if not 4 <= len(title) <= 140:
            return jsonify({"error": "Title must be between 4 and 140 characters."}), 400
        if not 30 <= len(body) <= 30000:
            return jsonify({"error": "Story text must be between 30 and 30,000 characters."}), 400
        if len(excerpt) > 240 or len(category) > 40:
            return jsonify({"error": "Introduction is limited to 240 characters and category to 40."}), 400
        now = utc_now()
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO posts (author_id, title, excerpt, body, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (g.current_user["id"], title, excerpt, body, category, now, now),
        )
        conn.commit()
        return jsonify({"post": post_dict(get_post_row(cur.lastrowid), include_body=True)}), 201

    @app.patch("/api/posts/<int:post_id>")
    @auth_required
    def update_post(post_id):
        existing = get_post_row(post_id)
        if existing is None:
            return jsonify({"error": "Story not found."}), 404
        if existing["author_id"] != g.current_user["id"]:
            return jsonify({"error": "You can only edit your own stories."}), 403
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", existing["title"])).strip()
        body = str(data.get("body", existing["body"])).strip()
        excerpt = str(data.get("excerpt", existing["excerpt"])).strip()
        category = str(data.get("category", existing["category"])).strip() or "Journal"
        if not 4 <= len(title) <= 140 or not 30 <= len(body) <= 30000:
            return jsonify({"error": "Title must be 4–140 characters and story text 30–30,000 characters."}), 400
        if len(excerpt) > 240 or len(category) > 40:
            return jsonify({"error": "Introduction is limited to 240 characters and category to 40."}), 400
        conn = get_db()
        conn.execute(
            "UPDATE posts SET title = ?, excerpt = ?, body = ?, category = ?, updated_at = ? WHERE id = ?",
            (title, excerpt, body, category, utc_now(), post_id),
        )
        conn.commit()
        return jsonify({"post": post_dict(get_post_row(post_id), include_body=True)})

    @app.delete("/api/posts/<int:post_id>")
    @auth_required
    def delete_post(post_id):
        row = get_post_row(post_id)
        if row is None:
            return jsonify({"error": "Story not found."}), 404
        if row["author_id"] != g.current_user["id"]:
            return jsonify({"error": "You can only delete your own stories."}), 403
        get_db().execute("DELETE FROM posts WHERE id = ?", (post_id,))
        get_db().commit()
        return jsonify({"ok": True, "id": post_id})

    @app.get("/api/posts/<int:post_id>/comments")
    def list_comments(post_id):
        if get_post_row(post_id) is None:
            return jsonify({"error": "Story not found."}), 404
        rows = get_db().execute("""
            SELECT c.id, c.post_id, c.author_id, c.body, c.created_at,
                   u.name AS author_name
            FROM comments c JOIN users u ON u.id = c.author_id
            WHERE c.post_id = ? ORDER BY c.created_at ASC, c.id ASC
        """, (post_id,)).fetchall()
        return jsonify({"comments": [dict(row) for row in rows]})

    @app.post("/api/posts/<int:post_id>/comments")
    @auth_required
    def create_comment(post_id):
        if get_post_row(post_id) is None:
            return jsonify({"error": "Story not found."}), 404
        data = request.get_json(silent=True) or {}
        body = str(data.get("body", "")).strip()
        if not 2 <= len(body) <= 2000:
            return jsonify({"error": "Comment must be between 2 and 2,000 characters."}), 400
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO comments (post_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
            (post_id, g.current_user["id"], body, utc_now()),
        )
        conn.commit()
        row = conn.execute("""
            SELECT c.id, c.post_id, c.author_id, c.body, c.created_at,
                   u.name AS author_name
            FROM comments c JOIN users u ON u.id = c.author_id WHERE c.id = ?
        """, (cur.lastrowid,)).fetchone()
        return jsonify({"comment": dict(row)}), 201

    @app.delete("/api/comments/<int:comment_id>")
    @auth_required
    def delete_comment(comment_id):
        row = get_db().execute("SELECT id, author_id FROM comments WHERE id = ?", (comment_id,)).fetchone()
        if row is None:
            return jsonify({"error": "Comment not found."}), 404
        if row["author_id"] != g.current_user["id"]:
            return jsonify({"error": "You can only delete your own comments."}), 403
        get_db().execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        get_db().commit()
        return jsonify({"ok": True, "id": comment_id})

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Route not found."}), 404
        return jsonify({"error": "Page not found."}), 404


    # Initialize this app instance's database too (important for tests and custom DB paths).
    with app.app_context():
        conn = get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                excerpt TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Journal',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id);
            CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(created_at);
            CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id, created_at);
        """)
        conn.commit()

    return app


app = create_app()
with app.app_context():
    # Creating tables is safe to repeat and keeps the first local run simple.
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, author_id INTEGER NOT NULL, title TEXT NOT NULL,
            excerpt TEXT NOT NULL DEFAULT '', body TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Journal',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL, author_id INTEGER NOT NULL,
            body TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id);
        CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(created_at);
        CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id, created_at);
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
