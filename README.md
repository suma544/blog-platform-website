# Inkwell — Blog Platform

A full-stack blogging website: users register and log in, write, edit and delete their own posts, and discuss them in a comment section. Everything runs on a Flask REST API backed by a SQL database.

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript single-page app (`static/`) |
| Backend | Python, Flask RESTful API (`app.py`) |
| Auth | Hashed passwords (Werkzeug) + signed bearer tokens (7-day expiry) |
| Database | PostgreSQL or MySQL via SQLAlchemy (`DATABASE_URL`), SQLite fallback for local dev |
| Deploy | Vercel (`vercel.json`) or Heroku (`Procfile`) |

## Features
- **Registration, login, authentication** — sign up with username + email, log in with either, token kept in the browser
- **Blog posts** — create, edit and delete your own posts, with title, body and tags; search across all posts; "My Posts" page
- **Comments** — logged-in users comment on any post; you can delete your own comments, and post authors can moderate comments on their posts
- Only the author can edit or delete a post (enforced by the API, not just the UI)

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

## Google Colab
Open `colab/Inkwell_Blog_Generator.ipynb` in Colab and choose **Runtime → Run all**.
It writes every project file, installs the packages, tests the APIs and downloads the folder as a zip.

## Database schema
`users` (id, username, email, password_hash, bio) · `posts` (id, author_id, title, content, tags, created_at, updated_at) · `comments` (id, post_id, author_id, body, created_at)

Set `DATABASE_URL` (see `.env.example`):
- PostgreSQL: `postgresql://user:pass@host:5432/blog`
- MySQL: `mysql+pymysql://user:pass@host:3306/blog` (add `PyMySQL` to requirements)

## REST API
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | — | `username`, `email`, `password` → token |
| POST | `/api/auth/login` | — | `login` (username or email), `password` → token |
| GET / PUT | `/api/auth/me` | ✓ | Current user / update bio |
| GET | `/api/posts?q=&author=` | — | List and search posts |
| GET | `/api/posts/<id>` | — | Post with comments |
| POST | `/api/posts` | ✓ | Create post (`title`, `content`, `tags`) |
| PUT | `/api/posts/<id>` | author | Edit post |
| DELETE | `/api/posts/<id>` | author | Delete post and its comments |
| GET | `/api/posts/<id>/comments` | — | List comments |
| POST | `/api/posts/<id>/comments` | ✓ | Add comment (`body`) |
| DELETE | `/api/comments/<id>` | comment or post author | Delete comment |

Send the token as `Authorization: Bearer <token>`.

## Deploy
**Vercel:** import the GitHub repo at vercel.com → add `DATABASE_URL` and `SECRET_KEY` env variables → Deploy.

**Heroku:**
```bash
heroku create
heroku addons:create heroku-postgresql:essential-0
heroku config:set SECRET_KEY=...
git push heroku main
```
