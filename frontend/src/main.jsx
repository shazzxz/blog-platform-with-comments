import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const api = async (path, options = {}, token = "") => {
  const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}) };
  if (token) headers.Authorization = "Bearer " + token;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
};
const prettyDate = value => new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const readingTime = body => Math.max(1, Math.ceil(String(body || "").trim().split(/\s+/).length / 200));

function App() {
  const [posts, setPosts] = useState([]);
  const [token, setToken] = useState(() => localStorage.getItem("fieldnotes_token") || "");
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ name: "", email: "", password: "" });
  const [authOpen, setAuthOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState("new");
  const [postForm, setPostForm] = useState({ title: "", excerpt: "", category: "Journal", body: "" });
  const [activePost, setActivePost] = useState(null);
  const [comments, setComments] = useState([]);
  const [commentText, setCommentText] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const loadPosts = async () => {
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      if (category !== "All") params.set("category", category);
      const data = await api("/api/posts?" + params.toString());
      setPosts(data.posts || []);
    } catch (error) { setNotice(error.message); }
  };
  const openPost = async id => {
    try {
      const [postData, commentData] = await Promise.all([
        api("/api/posts/" + id), api("/api/posts/" + id + "/comments")
      ]);
      setActivePost(postData.post);
      setComments(commentData.comments || []);
      setCommentText("");
    } catch (error) { setNotice(error.message); }
  };
  useEffect(() => { loadPosts(); }, [search, category]);
  useEffect(() => {
    if (!token) return;
    api("/api/auth/me", {}, token).then(data => setUser(data.user)).catch(() => logout());
  }, [token]);

  const logout = () => {
    localStorage.removeItem("fieldnotes_token");
    setToken(""); setUser(null); setAuthOpen(false);
    setNotice("You've signed out.");
  };
  const categories = useMemo(() => ["All", ...new Set(posts.map(post => post.category))], [posts]);
  const authenticate = async event => {
    event.preventDefault();
    setBusy(true);
    try {
      const endpoint = authMode === "register" ? "/api/auth/register" : "/api/auth/login";
      const data = await api(endpoint, { method: "POST", body: JSON.stringify(authForm) });
      localStorage.setItem("fieldnotes_token", data.token);
      setToken(data.token); setUser(data.user); setAuthOpen(false);
      setAuthForm({ name: "", email: "", password: "" });
      setNotice("Welcome to Fieldnotes, " + data.user.name + ".");
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };
  const startNewStory = () => {
    if (!user) { setAuthMode("login"); setAuthOpen(true); setNotice("Sign in before publishing a story."); return; }
    setPostForm({ title: "", excerpt: "", category: "Journal", body: "" });
    setEditorMode("new"); setEditorOpen(true);
  };
  const editStory = () => {
    setPostForm({ title: activePost.title, excerpt: activePost.excerpt || "", category: activePost.category, body: activePost.body });
    setEditorMode("edit"); setEditorOpen(true);
  };
  const saveStory = async event => {
    event.preventDefault(); setBusy(true);
    try {
      const endpoint = editorMode === "new" ? "/api/posts" : "/api/posts/" + activePost.id;
      const data = await api(endpoint, { method: editorMode === "new" ? "POST" : "PATCH", body: JSON.stringify(postForm) }, token);
      setEditorOpen(false); await loadPosts();
      if (editorMode === "edit") await openPost(data.post.id);
      else await openPost(data.post.id);
      setNotice(editorMode === "new" ? "Your story is published." : "Your changes are saved.");
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };
  const deleteStory = async () => {
    if (!activePost || !confirm("Delete this story and its comments?")) return;
    try {
      await api("/api/posts/" + activePost.id, { method: "DELETE" }, token);
      setActivePost(null); setComments([]); await loadPosts(); setNotice("Story deleted.");
    } catch (error) { setNotice(error.message); }
  };
  const addComment = async event => {
    event.preventDefault();
    if (!user) { setAuthMode("login"); setAuthOpen(true); setNotice("Sign in to join the conversation."); return; }
    try {
      const data = await api("/api/posts/" + activePost.id + "/comments", { method: "POST", body: JSON.stringify({ body: commentText }) }, token);
      setComments(items => [...items, data.comment]);
      setCommentText("");
      await loadPosts();
    } catch (error) { setNotice(error.message); }
  };
  const deleteComment = async id => {
    try {
      await api("/api/comments/" + id, { method: "DELETE" }, token);
      setComments(items => items.filter(item => item.id !== id));
      await loadPosts();
    } catch (error) { setNotice(error.message); }
  };

  return <div className="site">
    <header className="nav">
      <a className="wordmark" href="#"><span className="mark">f.</span><span>fieldnotes<small>STORIES WORTH SHARING</small></span></a>
      <div className="nav-right">
        <label className="searchbox"><span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Find a thought..." /></label>
        {user ? <><span className="signed-in">Writing as <b>{user.name}</b></span><button className="nav-link" onClick={startNewStory}>+ Write</button><button className="nav-link" onClick={logout}>Sign out</button></> :
          <button className="nav-link" onClick={() => { setAuthMode("login"); setAuthOpen(true); }}>Sign in <span>↗</span></button>}
      </div>
    </header>

    {notice && <button className="notice" onClick={() => setNotice("")}>{notice}<span>×</span></button>}

    <section className="hero">
      <div className="hero-copy"><p className="eyebrow">A SMALL CORNER OF THE INTERNET</p><h1>Ideas grow<br/>when <em>shared.</em></h1><p className="hero-desc">A home for curious minds, unfinished thoughts, and stories that stay with you.</p><button className="discover" onClick={() => document.getElementById("stories")?.scrollIntoView({ behavior: "smooth" })}>Explore the journal <span>↓</span></button></div>
      <div className="hero-art"><div className="sun"></div><div className="paper paper-one"><span>01 — NOTE TO SELF</span><b>Stay curious.</b><i>Collect moments, not just milestones.</i></div><div className="paper paper-two"><span>02 — FIELD RECORD</span><b>Look closer.</b></div><div className="scribble">✳</div><p className="art-caption">NOTES FROM<br/>THE EVERYDAY</p></div>
      <div className="hero-foot"><span>INDEPENDENT WRITING, OPEN CONVERSATION</span><span>VOL. 01 / 2026</span></div>
    </section>

    {authOpen && <div className="overlay" onMouseDown={e => e.target === e.currentTarget && setAuthOpen(false)}><section className="auth-card"><button className="close" onClick={() => setAuthOpen(false)}>×</button><p className="eyebrow">{authMode === "login" ? "GOOD TO HAVE YOU BACK" : "PULL UP A CHAIR"}</p><h2>{authMode === "login" ? "Welcome back." : "Join the conversation."}</h2><p className="muted">Write what you're thinking. Read what others are learning.</p><form onSubmit={authenticate}>{authMode === "register" && <label>Your name<input required minLength="2" maxLength="80" value={authForm.name} onChange={e => setAuthForm({ ...authForm, name: e.target.value })} /></label>}<label>Email address<input required type="email" value={authForm.email} onChange={e => setAuthForm({ ...authForm, email: e.target.value })} /></label><label>Password<input required minLength="8" type="password" value={authForm.password} onChange={e => setAuthForm({ ...authForm, password: e.target.value })} /></label><button className="dark-button" disabled={busy}>{busy ? "One moment..." : authMode === "login" ? "Sign in" : "Create account"}</button></form><button className="switch-mode" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}>{authMode === "login" ? "New to Fieldnotes? Create an account" : "Already a member? Sign in"}</button></section></div>}

    <main id="stories" className="stories">
      <div className="section-heading"><div><p className="eyebrow">THE LATEST ENTRIES</p><h2>A few good reads<span>®</span></h2></div><p className="story-count">{posts.length} {posts.length === 1 ? "story" : "stories"} in the journal</p></div>
      <div className="filters">{categories.map(item => <button key={item} className={category === item ? "filter active" : "filter"} onClick={() => setCategory(item)}>{item}</button>)}</div>
      {posts.length ? <div className="post-grid">{posts.map((post, index) => <article className={"post-card card-" + (index % 3)} key={post.id}><div className="card-top"><span>{post.category.toUpperCase()}</span><span>{String(index + 1).padStart(2, "0")}</span></div><button className="post-open" onClick={() => openPost(post.id)}><h3>{post.title}</h3><p className="excerpt">{post.excerpt || post.body.slice(0, 140) + "…"}</p><p className="read-more">Read story <span>↗</span></p></button><div className="card-bottom"><span>{post.author_name} · {prettyDate(post.created_at)}</span><span>{readingTime(post.body)} min read</span></div><div className="comment-count">◌ {post.comment_count}</div></article>)}</div> : <div className="empty"><div className="empty-mark">f.</div><h3>No stories here just yet.</h3><p>{search ? "Try a different search term." : "The first page is waiting to be written."}</p>{user && <button className="dark-button" onClick={startNewStory}>Write the first story</button>}</div>}
    </main>

    <footer><a className="wordmark" href="#"><span className="mark">f.</span><span>fieldnotes<small>STORIES WORTH SHARING</small></span></a><p>Made for ideas, made for people.</p><span>© 2026 FIELDNOTES</span></footer>

    {editorOpen && <div className="overlay" onMouseDown={e => e.target === e.currentTarget && setEditorOpen(false)}><section className="editor-card"><div className="modal-head"><div><p className="eyebrow">{editorMode === "new" ? "MAKE SOMETHING REAL" : "BACK TO THE DRAFT"}</p><h2>{editorMode === "new" ? "Write a story." : "Edit your story."}</h2></div><button className="close" onClick={() => setEditorOpen(false)}>×</button></div><form className="story-form" onSubmit={saveStory}><label>Title<input required minLength="4" maxLength="140" placeholder="A thought worth keeping..." value={postForm.title} onChange={e => setPostForm({ ...postForm, title: e.target.value })}/></label><div className="form-row"><label>Category<input maxLength="40" placeholder="Journal" value={postForm.category} onChange={e => setPostForm({ ...postForm, category: e.target.value })}/></label><label>Short introduction<input maxLength="240" placeholder="One line to draw us in..." value={postForm.excerpt} onChange={e => setPostForm({ ...postForm, excerpt: e.target.value })}/></label></div><label>Your story<textarea required minLength="30" maxLength="30000" rows="8" placeholder="Start anywhere. Follow the thought..." value={postForm.body} onChange={e => setPostForm({ ...postForm, body: e.target.value })}/></label><div className="editor-bottom"><span>{postForm.body.length} characters</span><button className="dark-button" disabled={busy}>{busy ? "Saving..." : editorMode === "new" ? "Publish story ↗" : "Save changes ↗"}</button></div></form></section></div>}

    {activePost && <div className="overlay story-overlay" onMouseDown={e => e.target === e.currentTarget && setActivePost(null)}><article className="story-modal"><button className="close story-close" onClick={() => setActivePost(null)}>×</button><p className="story-category">{activePost.category} / FIELDNOTES</p><div className="story-meta"><span className="author-dot">{activePost.author_name.slice(0,1).toUpperCase()}</span><span>{activePost.author_name}　·　{prettyDate(activePost.created_at)}　·　{readingTime(activePost.body)} min read</span></div><h2>{activePost.title}</h2>{activePost.excerpt && <p className="story-excerpt">{activePost.excerpt}</p>}<div className="story-body">{activePost.body.split("\\n").map((line, i) => <p key={i}>{line || "\\u00a0"}</p>)}</div>
      {user && user.id === activePost.author_id && <div className="owner-tools"><button onClick={editStory}>Edit story</button><button onClick={deleteStory}>Delete story</button></div>}
      <section className="conversation"><div className="conversation-head"><div><p className="eyebrow">THE CONVERSATION</p><h3>Comments <span>({comments.length})</span></h3></div><span>Be kind. Be curious.</span></div><form className="comment-form" onSubmit={addComment}><span className="author-dot">{user ? user.name.slice(0,1).toUpperCase() : "·"}</span><div><textarea required minLength="2" maxLength="2000" rows="3" value={commentText} onChange={e => setCommentText(e.target.value)} placeholder={user ? "Add something thoughtful..." : "Sign in to add to the conversation."}/><button className="dark-button" type="submit">Post comment ↗</button></div></form>{comments.length ? <div className="comment-list">{comments.map(comment => <div className="comment" key={comment.id}><span className="author-dot">{comment.author_name.slice(0,1).toUpperCase()}</span><div className="comment-copy"><div className="comment-author"><b>{comment.author_name}</b><span>{prettyDate(comment.created_at)}</span></div><p>{comment.body}</p></div>{user && user.id === comment.author_id && <button className="delete-comment" onClick={() => deleteComment(comment.id)}>Delete</button>}</div>)}</div> : <p className="no-comments">No comments yet. Be the first to say something thoughtful.</p>}</section>
    </article></div>}
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
