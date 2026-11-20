"""
Inkwell Blog - Backend (Flask + SQLAlchemy)

- User registration, login and token authentication (hashed passwords, signed bearer tokens)
- Create, edit, delete blog posts (only the author can change a post)
- Comment section: logged-in users comment; comment author or post author can delete
- RESTful JSON API, PostgreSQL / MySQL via DATABASE_URL, SQLite fallback for local dev
"""
import hashlib
import os
import re
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, abort, g, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Use the psycopg2 driver (in requirements.txt) for plain postgres URLs from Neon / Heroku
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg2://" + url[len(prefix):]
        return url
    folder = "/tmp" if os.environ.get("VERCEL") else BASE_DIR
    return f"sqlite:///{os.path.join(folder, 'blog.db')}"


app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="/static")
def secret_key() -> str:
    """SECRET_KEY env var if set; otherwise derived from the private DATABASE_URL so every deployment is unique."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    if os.environ.get("DATABASE_URL"):
        return hashlib.sha256(("%s:%s" % (__name__, os.environ["DATABASE_URL"])).encode()).hexdigest()
    return "dev-secret-change-me"  # local development only


app.config["SECRET_KEY"] = secret_key()
app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
CORS(app)
db = SQLAlchemy(app)
serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="auth-token")


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt and dt.tzinfo is None else (dt.isoformat() if dt else None)


# ---------------------------------------------------------------- models
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.String(200), default="")
    created_at = db.Column(db.DateTime, default=now)

    def public(self):
        return {"id": self.id, "username": self.username, "bio": self.bio}

    def private(self):
        return {**self.public(), "email": self.email}


class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(200), default="")
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)
    author = db.relationship("User")
    comments = db.relationship("Comment", backref="post", cascade="all, delete-orphan", order_by="Comment.id")

    def to_dict(self, full=False):
        data = {
            "id": self.id, "title": self.title, "author": self.author.public(),
            "tags": [t.strip() for t in (self.tags or "").split(",") if t.strip()],
            "excerpt": re.sub(r"\s+", " ", self.content)[:180] + ("…" if len(self.content) > 180 else ""),
            "comment_count": len(self.comments),
            "created_at": iso(self.created_at), "updated_at": iso(self.updated_at),
        }
        if full:
            data["content"] = self.content
            data["comments"] = [c.to_dict() for c in self.comments]
        return data


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=now)
    author = db.relationship("User")

    def to_dict(self):
        return {"id": self.id, "post_id": self.post_id, "body": self.body,
                "author": self.author.public(), "created_at": iso(self.created_at)}


# ---------------------------------------------------------------- auth helpers
def make_token(user):
    return serializer.dumps({"uid": user.id})


def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        data = serializer.loads(header[7:], max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return db.session.get(User, data.get("uid"))


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if not g.user:
            abort(401, description="Please log in")
        return fn(*args, **kwargs)
    return wrapper


def body():
    return request.get_json(silent=True) or {}


def text(data, key, max_len, required=True):
    value = str(data.get(key) or "").strip()
    if required and not value:
        abort(400, description=f"{key} is required")
    if len(value) > max_len:
        abort(400, description=f"{key} must be at most {max_len} characters")
    return value


# ---------------------------------------------------------------- setup
WELCOME = """Welcome to Inkwell, a simple blogging platform.

Create an account, write your own posts, edit or delete them any time, and join the conversation in the comments below each post.

Everything you see here is served by a Flask REST API and stored in a SQL database."""


def init_db():
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            team = User(username="inkwell", email="team@inkwell.blog", bio="The Inkwell team",
                        password_hash=generate_password_hash(os.urandom(16).hex()))  # no usable password
            db.session.add(team)
            db.session.flush()
            db.session.add(Post(author_id=team.id, title="Welcome to Inkwell", content=WELCOME, tags="announcement, getting started"))
            db.session.commit()


# ---------------------------------------------------------------- frontend
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", database=db.engine.url.get_backend_name())


# ---------------------------------------------------------------- auth API
@app.post("/api/auth/register")
def register():
    data = body()
    username = text(data, "username", 30)
    email = text(data, "email", 120).lower()
    password = str(data.get("password") or "")
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        abort(400, description="Username: 3-30 letters, numbers or _")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        abort(400, description="Enter a valid email")
    if len(password) < 6:
        abort(400, description="Password must be at least 6 characters")
    if User.query.filter(db.func.lower(User.username) == username.lower()).first():
        abort(409, description="Username is taken")
    if User.query.filter_by(email=email).first():
        abort(409, description="Email is already registered")
    user = User(username=username, email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return jsonify(token=make_token(user), user=user.private()), 201


@app.post("/api/auth/login")
def login():
    data = body()
    ident = str(data.get("login") or data.get("email") or "").strip().lower()
    user = User.query.filter(db.or_(User.email == ident, db.func.lower(User.username) == ident)).first()
    if not user or not check_password_hash(user.password_hash, str(data.get("password") or "")):
        abort(401, description="Invalid username/email or password")
    return jsonify(token=make_token(user), user=user.private())


@app.get("/api/auth/me")
@login_required
def me():
    return jsonify(g.user.private())


@app.put("/api/auth/me")
@login_required
def update_me():
    g.user.bio = text(body(), "bio", 200, required=False)
    db.session.commit()
    return jsonify(g.user.private())


# ---------------------------------------------------------------- posts API
@app.get("/api/posts")
def list_posts():
    query = Post.query
    if q := request.args.get("q", "").strip():
        like = f"%{q}%"
        query = query.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like), Post.tags.ilike(like)))
    if author := request.args.get("author", "").strip():
        query = query.join(User).filter(User.username == author)
    return jsonify([p.to_dict() for p in query.order_by(Post.created_at.desc(), Post.id.desc()).all()])


@app.get("/api/posts/<int:pid>")
def get_post(pid):
    return jsonify(db.get_or_404(Post, pid).to_dict(full=True))


def post_fields(data):
    return {"title": text(data, "title", 150), "content": text(data, "content", 50000),
            "tags": text(data, "tags", 200, required=False)}


@app.post("/api/posts")
@login_required
def create_post():
    post = Post(author_id=g.user.id, **post_fields(body()))
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_dict(full=True)), 201


def own_post(pid):
    post = db.get_or_404(Post, pid)
    if post.author_id != g.user.id:
        abort(403, description="You can only change your own posts")
    return post


@app.put("/api/posts/<int:pid>")
@login_required
def update_post(pid):
    post = own_post(pid)
    for k, v in post_fields(body()).items():
        setattr(post, k, v)
    db.session.commit()
    return jsonify(post.to_dict(full=True))


@app.delete("/api/posts/<int:pid>")
@login_required
def delete_post(pid):
    db.session.delete(own_post(pid))
    db.session.commit()
    return jsonify(message="Post deleted", id=pid)


# ---------------------------------------------------------------- comments API
@app.get("/api/posts/<int:pid>/comments")
def list_comments(pid):
    return jsonify([c.to_dict() for c in db.get_or_404(Post, pid).comments])


@app.post("/api/posts/<int:pid>/comments")
@login_required
def add_comment(pid):
    post = db.get_or_404(Post, pid)
    comment = Comment(post_id=post.id, author_id=g.user.id, body=text(body(), "body", 2000))
    db.session.add(comment)
    db.session.commit()
    return jsonify(comment.to_dict()), 201


@app.delete("/api/comments/<int:cid>")
@login_required
def delete_comment(cid):
    comment = db.get_or_404(Comment, cid)
    if g.user.id not in (comment.author_id, comment.post.author_id):
        abort(403, description="You can only delete your own comments or comments on your posts")
    db.session.delete(comment)
    db.session.commit()
    return jsonify(message="Comment deleted", id=cid)


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
def handle_error(err):
    return jsonify(error=getattr(err, "description", str(err))), err.code


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
