const $ = (s) => document.querySelector(s);
const app = $("#app");
const esc = (s = "") => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const date = (d) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
let token = store.get("token");
let user = store.get("user");

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && token) setSession(null, null);
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 2500);
}
function setSession(t, u) {
  token = t; user = u; store.set("token", t); store.set("user", u);
  document.querySelectorAll(".auth-only").forEach((el) => (el.hidden = !user));
  document.querySelectorAll(".guest-only").forEach((el) => (el.hidden = !!user));
  $("#userName").textContent = user?.username || "";
}
const tagsHtml = (tags) => tags.length ? `<div class="tags">${tags.map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}</div>` : "";

// ---------- pages ----------
async function homePage(mine = false) {
  app.innerHTML = `
    <section class="hero">
      <h1>${mine ? "My posts" : "Stories, ideas and notes."}</h1>
      <p>${mine ? "Everything you've published. Edit or delete any time." : "Read what the community is writing — or share your own."}</p>
      <input type="search" id="search" placeholder="Search posts by title, text or tag..." />
    </section>
    <div id="list"><p class="empty">Loading…</p></div>`;
  const load = async () => {
    const q = $("#search").value.trim();
    const params = new URLSearchParams({ ...(q && { q }), ...(mine && { author: user.username }) });
    const posts = await api(`/api/posts?${params}`);
    $("#list").innerHTML = posts.length ? posts.map((p) => `
      <article class="post-item">
        <div class="meta"><strong>@${esc(p.author.username)}</strong><span>${date(p.created_at)}</span><span>💬 ${p.comment_count}</span></div>
        <h2><a href="#/post/${p.id}">${esc(p.title)}</a></h2>
        <p>${esc(p.excerpt)}</p>
        ${tagsHtml(p.tags)}
      </article>`).join("")
      : `<p class="empty">${mine ? `You haven't written anything yet. <a class="link" href="#/new">Write your first post →</a>` : "No posts found."}</p>`;
  };
  let timer;
  $("#search").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 250); });
  await load();
}

async function postPage(id) {
  const p = await api(`/api/posts/${id}`);
  const isOwner = user && user.id === p.author.id;
  const edited = new Date(p.updated_at) - new Date(p.created_at) > 60000;
  app.innerHTML = `
    <article class="article">
      <a class="back" href="#/">← All posts</a>
      <h1>${esc(p.title)}</h1>
      <div class="meta"><strong>@${esc(p.author.username)}</strong><span>${date(p.created_at)}${edited ? " · edited" : ""}</span></div>
      ${tagsHtml(p.tags)}
      ${isOwner ? `<div class="owner-actions"><a class="btn small" href="#/edit/${p.id}">Edit</a><button class="btn small danger" id="deletePost">Delete</button></div>` : ""}
      <div class="content">${esc(p.content)}</div>
    </article>
    <section class="comments">
      <h3>Comments (${p.comments.length})</h3>
      ${user ? `<form class="comment-form" id="commentForm"><textarea name="body" rows="3" maxlength="2000" required placeholder="Share your thoughts..."></textarea><button class="btn btn-primary">Post comment</button></form>`
             : `<div class="login-note"><button class="link" data-auth="login">Log in</button> or <button class="link" data-auth="register">sign up</button> to join the discussion.</div>`}
      <div>${p.comments.map((c) => `
        <div class="comment">
          <div class="meta"><strong>@${esc(c.author.username)}</strong><span>${date(c.created_at)}</span>
            ${user && (user.id === c.author.id || isOwner) ? `<button class="link" style="margin-left:auto;font-size:.82rem" data-del-comment="${c.id}">Delete</button>` : ""}</div>
          <p>${esc(c.body)}</p>
        </div>`).join("") || `<p class="muted">No comments yet. Be the first!</p>`}</div>
    </section>`;

  $("#deletePost")?.addEventListener("click", async () => {
    if (!confirm("Delete this post and its comments?")) return;
    try { await api(`/api/posts/${id}`, { method: "DELETE" }); toast("Post deleted"); location.hash = "#/mine"; }
    catch (e) { toast(e.message); }
  });
  $("#commentForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api(`/api/posts/${id}/comments`, { method: "POST", body: JSON.stringify({ body: e.target.body.value }) }); toast("Comment added"); postPage(id); }
    catch (err) { toast(err.message); }
  });
  app.querySelectorAll("[data-del-comment]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("Delete this comment?")) return;
    try { await api(`/api/comments/${b.dataset.delComment}`, { method: "DELETE" }); toast("Comment deleted"); postPage(id); }
    catch (e) { toast(e.message); }
  }));
}

async function editorPage(id = null) {
  if (!user) { location.hash = "#/"; openAuth("login", "Please log in to write a post"); return; }
  const p = id ? await api(`/api/posts/${id}`) : { title: "", content: "", tags: [] };
  if (id && p.author.id !== user.id) { location.hash = `#/post/${id}`; return; }
  app.innerHTML = `
    <form class="editor" id="editor">
      <h1>${id ? "Edit post" : "Write a new post"}</h1>
      <input name="title" maxlength="150" required placeholder="Title" value="${esc(p.title)}" />
      <input name="tags" maxlength="200" placeholder="Tags, comma separated (e.g. travel, tech)" value="${esc(p.tags.join(", "))}" />
      <textarea name="content" required placeholder="Tell your story...">${esc(p.content)}</textarea>
      <p class="error" id="editorError"></p>
      <div class="row"><a class="btn" href="${id ? `#/post/${id}` : "#/"}">Cancel</a><button class="btn btn-primary">${id ? "Save changes" : "Publish"}</button></div>
    </form>`;
  $("#editor").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    try {
      const saved = await api(id ? `/api/posts/${id}` : "/api/posts", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
      toast(id ? "Post updated" : "Post published");
      location.hash = `#/post/${saved.id}`;
    } catch (err) { $("#editorError").textContent = err.message; }
  });
}

// ---------- router ----------
async function route() {
  const [, page, id] = location.hash.replace(/^#/, "").split("/");
  window.scrollTo(0, 0);
  try {
    if (page === "post" && id) await postPage(id);
    else if (page === "new") await editorPage();
    else if (page === "edit" && id) await editorPage(id);
    else if (page === "mine" && user) await homePage(true);
    else await homePage();
  } catch (e) {
    app.innerHTML = `<p class="empty">${esc(e.message)}. <a class="link" href="#/">Go home</a></p>`;
  }
}
window.addEventListener("hashchange", route);

// ---------- auth dialog ----------
let mode = "login";
function openAuth(m, msg = "") {
  mode = m;
  const reg = m === "register";
  $("#authTitle").textContent = reg ? "Create your account" : "Welcome back";
  $("#authSubmit").textContent = reg ? "Sign up" : "Login";
  $("#loginLabel").textContent = reg ? "Email" : "Username or email";
  $("#authForm").login.type = reg ? "email" : "text";
  $("#authSwitchText").textContent = reg ? "Already have an account?" : "New here?";
  $("#authSwitch").textContent = reg ? "Login" : "Create an account";
  document.querySelector(".register-only").hidden = !reg;
  $("#authForm").username.required = reg;
  $("#authError").textContent = msg;
  $("#authDialog").showModal();
}
document.addEventListener("click", (e) => {
  if (e.target.dataset.auth) openAuth(e.target.dataset.auth);
  if (e.target.matches("[data-close]")) e.target.closest("dialog").close();
});
$("#loginBtn").addEventListener("click", () => openAuth("login"));
$("#signupBtn").addEventListener("click", () => openAuth("register"));
$("#authSwitch").addEventListener("click", () => openAuth(mode === "login" ? "register" : "login"));
$("#authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const payload = mode === "register"
    ? { username: f.username.value, email: f.login.value, password: f.password.value }
    : { login: f.login.value, password: f.password.value };
  try {
    const res = await api(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify(payload) });
    setSession(res.token, res.user);
    f.reset();
    $("#authDialog").close();
    toast(`Welcome, @${res.user.username}!`);
    route();
  } catch (err) { $("#authError").textContent = err.message; }
});
$("#logoutBtn").addEventListener("click", () => { setSession(null, null); toast("Logged out"); location.hash = "#/"; route(); });

// ---------- init ----------
$("#year").textContent = new Date().getFullYear();
setSession(token, user);
if (token) api("/api/auth/me").then((u) => setSession(token, u)).catch(() => {});
route();
