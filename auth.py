"""
Authentication handlers: login, logout, register.
"""

import hashlib
import logging
import secrets

import tornado.web

from app.database import get_db
from app.handlers.base import BaseHandler

logger = logging.getLogger(__name__)


def _hash_password(password: str, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}${h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
        return secrets.compare_digest(stored, _hash_password(password, salt))
    except Exception:
        return False


class LoginHandler(BaseHandler):
    def get(self):
        if self.current_user:
            self.redirect("/")
            return
        self.render("login.html", error="", title="Login")

    def post(self):
        username = self.get_argument("username", "").strip()
        password = self.get_argument("password", "")

        db = get_db()
        row = db.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()

        if row and _verify_password(password, row["password_hash"]):
            self.set_secure_cookie("user_id", str(row["id"]), expires_days=1)
            self.redirect(self.get_argument("next", "/"))
        else:
            self.render("login.html", error="Invalid username or password.", title="Login")


class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user_id")
        self.redirect("/login")


class RegisterHandler(BaseHandler):
    """Admin-only: create a new user account."""

    def get(self):
        if not self.current_user or not self.current_user.get("is_admin"):
            raise tornado.web.HTTPError(403)
        self.render("register.html", error="", title="Register")

    def post(self):
        if not self.current_user or not self.current_user.get("is_admin"):
            raise tornado.web.HTTPError(403)

        username = self.get_argument("username", "").strip()
        password = self.get_argument("password", "")
        email = self.get_argument("email", "").strip()

        if not username or not password:
            self.render("register.html", error="Username and password required.", title="Register")
            return

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (?,?,?)",
                (username, _hash_password(password), email),
            )
            db.commit()
            self.redirect("/")
        except Exception:
            self.render("register.html", error="Username already exists.", title="Register")
