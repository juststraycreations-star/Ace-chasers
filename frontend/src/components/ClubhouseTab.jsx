import { useEffect, useMemo, useState, useRef } from "react";
import api from "@/lib/api";
import AuthImage from "./AuthImage";
import Lightbox from "./Lightbox";
import { toast } from "sonner";
import { PushPin, Warning, ImageSquare, Plus, Fire, TrendUp, Trash, CheckCircle, SpeakerX } from "@phosphor-icons/react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import ClubhouseFeedComposer from "./ClubhouseFeedComposer";
import { AVATAR_FALLBACK_SVG, onAvatarError } from "@/lib/avatarFallback";

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_VIDEO_BYTES = 25 * 1024 * 1024;

export default function ClubhouseTab({ leagueId, isDirector, currentUser }) {
  const [tab, setTab] = useState("feed"); // feed | lost-found
  const [stories, setStories] = useState([]);
  const [announcements, setAnnouncements] = useState([]);
  const [feed, setFeed] = useState([]);
  // Split the feed into three ordered slices so the layout reads
  // top-to-bottom as:
  //   1. Recap card(s) — the "active round" summary
  //   2. Pinned posts   — critical announcements the director wants
  //                        anchored above the fold (never scroll off)
  //   3. Clubhouse Discussion divider
  //   4. User-authored posts (chronological, per server order)
  // Preserves server-side sort order inside each slice.
  const [recaps, pinned, discussion] = useMemo(() => {
    const r = [];
    const p = [];
    const d = [];
    for (const post of feed) {
      if (post.kind === "recap") r.push(post);
      else if (post.pinned) p.push(post);
      else d.push(post);
    }
    return [r, p, d];
  }, [feed]);
  const [lostFound, setLostFound] = useState([]);
  const [uploading, setUploading] = useState(false);
  const storyInputRef = useRef(null);
  const lfImgRef = useRef(null);
  const [lfImage, setLfImage] = useState(null);
  const [newAnn, setNewAnn] = useState({ title: "", body: "", urgent: false });
  const [showAnnForm, setShowAnnForm] = useState(false);
  const [lfForm, setLfForm] = useState({ title: "", description: "" });
  const [lightbox, setLightbox] = useState(null); // {path, caption}

  const load = async () => {
    try {
      const [s, a, f, l] = await Promise.all([
        api.get(`/leagues/${leagueId}/stories`),
        api.get(`/leagues/${leagueId}/announcements`),
        api.get(`/leagues/${leagueId}/feed`),
        api.get(`/leagues/${leagueId}/lost-found`),
      ]);
      setStories(s.data); setAnnouncements(a.data); setFeed(f.data); setLostFound(l.data);
    } catch {}
  };
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [leagueId]);

  const uploadStory = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/files/upload", fd, { headers: { "Content-Type": "multipart/form-data" }});
      await api.post(`/leagues/${leagueId}/stories`, { image_path: data.path, caption: "" });
      toast.success("Story posted");
      await load();
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); if (storyInputRef.current) storyInputRef.current.value = ""; }
  };

  const uploadOne = async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const { data } = await api.post("/files/upload", fd, { headers: { "Content-Type": "multipart/form-data" }});
    return data.path;
  };

  // Bridges the new composer's `{ text, media[] }` payload to the
  // backend's `media[]` contract (iteration 51). Uploads every queued
  // file in order and posts a single feed entry with the full array.
  const submitPost = async ({ text, media }) => {
    const body = (text || "").trim();
    const list = media || [];
    if (!body && list.length === 0) return;
    for (const m of list) {
      const cap = m.isVideo ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES;
      const label = m.isVideo ? "Video" : "Image";
      const capMB = m.isVideo ? 25 : 8;
      if (m.file.size > cap) {
        toast.error(`${label} too large (max ${capMB}MB)`);
        throw new Error(`${label} too large`);
      }
    }
    try {
      const uploaded = [];
      for (const m of list) {
        const path = await uploadOne(m.file);
        uploaded.push({ kind: m.isVideo ? "video" : "image", path });
      }
      await api.post(`/leagues/${leagueId}/feed`, { body, media: uploaded });
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to post");
      throw e; // let the composer keep its queued files for retry
    }
  };

  const submitAnnouncement = async () => {
    if (!newAnn.title || !newAnn.body) return;
    try {
      await api.post(`/leagues/${leagueId}/announcements`, newAnn);
      setNewAnn({ title: "", body: "", urgent: false });
      setShowAnnForm(false);
      await load();
    } catch { toast.error("Failed"); }
  };

  const deleteAnn = async (id) => {
    try { await api.delete(`/announcements/${id}`); await load(); } catch {}
  };

  // ── Moderation actions (director or post-author) ─────────────
  const deleteFeedPost = async (id) => {
    if (!window.confirm("Delete this post?")) return;
    try {
      await api.delete(`/feed/${id}`);
      toast.success("Post removed");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to delete");
    }
  };

  const muteUser = async (userId, name) => {
    if (!window.confirm(`Mute ${name}? They won't be able to post in this league.`)) return;
    try {
      await api.post(`/leagues/${leagueId}/mute/${userId}`);
      toast.success(`${name} muted`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to mute");
    }
  };

  const uploadLFImage = async (file) => {
    if (!file) return null;
    const fd = new FormData();
    fd.append("file", file);
    const { data } = await api.post("/files/upload", fd, { headers: { "Content-Type": "multipart/form-data" }});
    return data.path;
  };

  const submitLostFound = async () => {
    if (!lfForm.title) return;
    let path = null;
    if (lfImage) {
      try { path = await uploadLFImage(lfImage); } catch { toast.error("Image upload failed"); return; }
    }
    try {
      await api.post(`/leagues/${leagueId}/lost-found`, { ...lfForm, image_path: path });
      setLfForm({ title: "", description: "" });
      setLfImage(null);
      if (lfImgRef.current) lfImgRef.current.value = "";
      toast.success("Posted to Lost & Found");
      await load();
    } catch { toast.error("Failed"); }
  };

  const resolveLF = async (id) => {
    try { await api.patch(`/lost-found/${id}/resolve`); await load(); } catch {}
  };

  // Shared post renderer used above the divider (pinned) and below the
  // divider (discussion). Kept as a plain function returning JSX so the
  // pinned + discussion loops stay a single source of truth.
  const renderPost = (p) => (
    <div key={p.id} className={`card-surface p-5 ${p.hidden ? "opacity-40" : ""} ${p.pinned ? "ring-1 ring-amber-300 bg-amber-50/40" : ""}`} data-testid={`feed-post-${p.id}`}>
      <div className="flex items-start gap-3">
        {p.author_picture ? (
          <img
            src={p.author_picture}
            onError={onAvatarError}
            className="w-9 h-9 rounded-full bg-gray-50 object-cover"
            alt={p.author_name || "Player"}
            data-testid={`feed-post-avatar-${p.id}`}
          />
        ) : (
          <img
            src={AVATAR_FALLBACK_SVG}
            className="w-9 h-9 rounded-full"
            alt={p.author_name || "Player"}
            data-testid={`feed-post-avatar-${p.id}`}
          />
        )}
        <div className="flex-1">
          <div className="text-sm font-medium flex items-center gap-2">
            {p.author_name}
            {p.pinned && (
              <span
                className="text-[9px] uppercase tracking-wider text-amber-700 bg-amber-100 border border-amber-200 rounded-full px-1.5 py-0.5 font-mono-data inline-flex items-center gap-0.5"
                data-testid={`feed-post-pinned-${p.id}`}
              >
                <PushPin size={9} weight="fill" /> Pinned
              </span>
            )}
            {p.hidden && (
              <span className="text-[9px] uppercase tracking-wider text-red-400 font-mono-data" data-testid={`feed-post-hidden-${p.id}`}>
                Removed
              </span>
            )}
          </div>
          <div className="text-[10px] font-mono-data text-zinc-500">{new Date(p.created_at).toLocaleString()}</div>
          {p.title && (
            <div className="mt-1 font-display text-base text-slate-900" data-testid={`feed-post-title-${p.id}`}>
              {p.title}
            </div>
          )}
          <div className="mt-2 text-sm text-slate-800 whitespace-pre-wrap">{p.body}</div>
          {(() => {
            // Iteration 51: posts now carry an ordered `media[]`.
            // Fall back to legacy image_path / video_path for
            // posts created before the migration.
            const items = (p.media && p.media.length)
              ? p.media
              : [
                  ...(p.image_path ? [{ kind: "image", path: p.image_path }] : []),
                  ...(p.video_path ? [{ kind: "video", path: p.video_path, poster: p.video_poster }] : []),
                ];
            if (items.length === 0) return null;
            return (
              <div className="mt-3 grid gap-2" data-testid={`feed-post-media-${p.id}`}>
                {items.map((m, i) => m.kind === "image" ? (
                  <AuthImage
                    key={i}
                    path={m.path}
                    className="max-h-96 rounded-lg border border-slate-200 cursor-zoom-in"
                    onClick={() => setLightbox({ path: m.path, caption: p.author_name })}
                    alt=""
                    data-testid={`feed-post-image-${p.id}-${i}`}
                  />
                ) : (
                  <video
                    key={i}
                    src={m.path.startsWith("http") ? m.path : `/api/files/${m.path}`}
                    poster={m.poster || undefined}
                    controls
                    preload="metadata"
                    className="max-h-96 w-full rounded-lg border border-slate-200 bg-black"
                    data-testid={`feed-post-video-${p.id}-${i}`}
                  />
                ))}
              </div>
            );
          })()}
        </div>
        {(isDirector || p.author_id === currentUser?.user_id) && !p.hidden && (
          <div className="flex items-center gap-1 shrink-0" data-testid={`feed-mod-panel-${p.id}`}>
            <button
              type="button"
              onClick={() => deleteFeedPost(p.id)}
              data-testid={`feed-delete-btn-${p.id}`}
              title="Delete post"
              className="p-1.5 rounded-md text-zinc-500 hover:text-red-500 hover:bg-red-500/10"
            >
              <Trash size={14} weight="duotone" />
            </button>
            {isDirector && p.author_id && p.author_id !== currentUser?.user_id && (
              <button
                type="button"
                onClick={() => muteUser(p.author_id, p.author_name)}
                data-testid={`feed-mute-btn-${p.id}`}
                title={`Mute ${p.author_name}`}
                className="p-1.5 rounded-md text-zinc-500 hover:text-amber-600 hover:bg-amber-500/10"
              >
                <SpeakerX size={14} weight="duotone" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6" data-testid="clubhouse-tab">
      {/* Story grid */}
      <div className="card-surface p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 mb-1">STORY GRID · 48H</div>
            <h3 className="font-display text-xl">From the Course</h3>
          </div>
          <label className="btn-primary text-xs cursor-pointer flex items-center gap-2" data-testid="story-upload-btn">
            <ImageSquare size={14} weight="bold" />
            {uploading ? "Uploading…" : "Post Story"}
            <input
              ref={storyInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => uploadStory(e.target.files?.[0])}
              data-testid="story-upload-input"
            />
          </label>
        </div>
        <div className="flex gap-3 overflow-x-auto pb-2">
          {stories.length === 0 && (
            <div className="text-zinc-500 text-sm">No stories yet — share your first shot!</div>
          )}
          {stories.map((s) => (
            <div key={s.id} className="story-ring flex-shrink-0 cursor-pointer" data-testid={`story-${s.id}`} onClick={() => setLightbox({ path: s.image_path, caption: `${s.author_name}${s.caption ? ' · ' + s.caption : ''}` })}>
              <div className="story-inner" style={{ width: 120, height: 180 }}>
                <AuthImage path={s.image_path} className="w-full h-full object-cover" />
                <div className="absolute bottom-2 left-2 right-2 pointer-events-none">
                  <div className="text-[10px] text-white/90 font-medium truncate">{s.author_name}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/5">
        <button
          data-testid="clubhouse-tab-feed"
          onClick={() => setTab("feed")}
          className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${tab === "feed" ? "border-[#F5C542] text-white" : "border-transparent text-zinc-500 hover:text-white"}`}
        >Feed</button>
        <button
          data-testid="clubhouse-tab-lostfound"
          onClick={() => setTab("lost-found")}
          className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${tab === "lost-found" ? "border-[#F5C542] text-white" : "border-transparent text-zinc-500 hover:text-white"}`}
        >Lost &amp; Found</button>
      </div>

      {tab === "feed" && (
        <div className="space-y-4" data-testid="feed-list">
          {/* Announcements */}
          {(announcements.length > 0 || isDirector) && (
            <div className="card-surface p-6" data-testid="announcements-block">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <PushPin size={16} weight="fill" className="text-[#F5C542]" />
                  <div className="font-display text-lg">Pinned Announcements</div>
                </div>
                {isDirector && (
                  <button data-testid="new-announcement-btn" onClick={() => setShowAnnForm(!showAnnForm)} className="text-xs text-zinc-400 hover:text-white">
                    {showAnnForm ? "Cancel" : "+ New"}
                  </button>
                )}
              </div>
              {showAnnForm && isDirector && (
                <div className="mb-4 space-y-2 p-4 border border-white/8 rounded-lg bg-[#111114]" data-testid="announcement-form">
                  <Input data-testid="ann-title" placeholder="Title" value={newAnn.title} onChange={(e) => setNewAnn({ ...newAnn, title: e.target.value })} className="bg-[#2a5f3d] border-white/10" />
                  <Textarea data-testid="ann-body" placeholder="Announcement details…" value={newAnn.body} onChange={(e) => setNewAnn({ ...newAnn, body: e.target.value })} className="bg-[#2a5f3d] border-white/10" />
                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-2 text-xs text-zinc-400">
                      <input data-testid="ann-urgent" type="checkbox" checked={newAnn.urgent} onChange={(e) => setNewAnn({ ...newAnn, urgent: e.target.checked })} /> Urgent
                    </label>
                    <button data-testid="ann-submit" onClick={submitAnnouncement} className="btn-primary text-xs ml-auto">Post</button>
                  </div>
                </div>
              )}
              <div className="space-y-3">
                {announcements.length === 0 && <div className="text-zinc-500 text-sm">No announcements. All quiet on the course.</div>}
                {announcements.map((a) => (
                  <div key={a.id} className={`p-4 rounded-lg border ${a.urgent ? "border-red-500/40 bg-red-500/8" : "border-white/8 bg-[#2a5f3d]"}`} data-testid={`announcement-${a.id}`}>
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        {a.urgent && <Warning size={16} weight="fill" className="text-red-400" />}
                        <div className="font-display text-base">{a.title}</div>
                      </div>
                      {isDirector && (
                        <button data-testid={`delete-ann-${a.id}`} onClick={() => deleteAnn(a.id)} className="text-zinc-500 hover:text-red-400">
                          <Trash size={14} />
                        </button>
                      )}
                    </div>
                    <div className="text-sm text-zinc-300 mt-1 whitespace-pre-wrap">{a.body}</div>
                    <div className="mt-2 text-[10px] text-zinc-500 font-mono-data">
                      {a.author_name} · {new Date(a.created_at).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* New post — polished ClubhouseFeedComposer (text + image + video). */}
          <ClubhouseFeedComposer onPostSubmit={submitPost} />

          {/* Recap card(s) — the "active round" recap block that lives
              above the divider heading. Rendered separately from the
              user-authored discussion feed below. */}
          {recaps.map((p) => (
            <div key={p.id} className="tracing-beam" data-testid={`feed-recap-${p.id}`}>
              <div className="tracing-beam-inner">
                <div className="flex items-center gap-2 mb-3">
                  <Fire weight="fill" className="text-[#F5C542]" />
                  <div className="font-display text-lg">{p.title}</div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {p.meta?.hot_round && (
                    <div className="p-4 rounded-lg bg-[#151518] border border-white/8">
                      <div className="text-[10px] font-mono-data text-[#F5C542] mb-2">🔥 HOT ROUND</div>
                      <div className="font-display text-xl">{p.meta.hot_round.name}</div>
                      <div className="text-xs text-zinc-400 mt-1 font-mono-data">
                        {p.meta.hot_round.plus_minus > 0 ? `+${p.meta.hot_round.plus_minus}` : p.meta.hot_round.plus_minus} · {p.meta.hot_round.total} strokes
                      </div>
                    </div>
                  )}
                  {p.meta?.most_improved && (
                    <div className="p-4 rounded-lg bg-[#151518] border border-white/8">
                      <div className="text-[10px] font-mono-data text-emerald-400 mb-2 flex items-center gap-1"><TrendUp size={12} weight="bold" /> MOST IMPROVED</div>
                      <div className="font-display text-xl">{p.meta.most_improved.name}</div>
                      <div className="text-xs text-zinc-400 mt-1 font-mono-data">
                        −{p.meta.most_improved.delta} strokes vs last round
                      </div>
                    </div>
                  )}
                </div>
                <div className="mt-3 text-[10px] font-mono-data text-zinc-500">{new Date(p.created_at).toLocaleString()}</div>
              </div>
            </div>
          ))}

          {/* Pinned announcements — anchored above the divider so
              critical posts never scroll off. Rendered only when the
              director (or any actor with mod rights) has actually
              pinned something. */}
          {pinned.length > 0 && (
            <div className="space-y-3" data-testid="clubhouse-pinned-block">
              <div className="text-[10px] font-mono-data uppercase tracking-widest text-amber-700 flex items-center gap-1.5 mt-6">
                <PushPin size={11} weight="fill" />
                Pinned · {pinned.length}
              </div>
              {pinned.map(renderPost)}
            </div>
          )}

          {/* Structural section divider — cleanly separates the recap
              block above from the user-authored chat feed below.
              Padding pushes the heading away from the recap card's
              dark background; the under-border line anchors the
              discussion posts to it. */}
          <div
            data-testid="clubhouse-discussion-divider"
            className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 mt-6 border-b border-gray-100 pb-2"
          >
            Clubhouse Discussion
          </div>

          {/* Discussion feed — user-authored, non-pinned posts. */}
          {discussion.map(renderPost)}

          {/* Friendly empty state below the divider when nobody's
              posted yet. Only shows when the feed already has a recap
              or a pinned post above (i.e. this is the first
              discussion post that could exist). */}
          {discussion.length === 0 && (recaps.length > 0 || pinned.length > 0) && (
            <div
              data-testid="clubhouse-discussion-empty-state"
              className="text-center py-8 px-4 rounded-2xl border border-dashed border-gray-200 bg-gray-50/60"
            >
              <div className="font-display text-lg text-slate-900 mb-1">
                Be the first to post
              </div>
              <p className="text-sm text-slate-600">
                Share a rip, a putt, or a heckle — the composer is right up top.
              </p>
            </div>
          )}
          {feed.length === 0 && <div className="text-zinc-500 text-sm text-center py-6">No posts yet</div>}
        </div>
      )}

      {tab === "lost-found" && (
        <div className="space-y-4" data-testid="lostfound-list">
          <div className="card-surface p-6">
            <div className="font-display text-lg mb-3">Report a Lost or Found Disc</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input data-testid="lf-title" placeholder="Star Destroyer · Orange · 175g" value={lfForm.title} onChange={(e) => setLfForm({ ...lfForm, title: e.target.value })} className="bg-[#2a5f3d] border-white/10" />
              <input
                ref={lfImgRef}
                data-testid="lf-image"
                type="file"
                accept="image/*"
                onChange={(e) => setLfImage(e.target.files?.[0])}
                className="text-xs text-zinc-400 file:mr-3 file:px-3 file:py-2 file:rounded-md file:border-0 file:bg-[#F5C542] file:text-black file:font-bold"
              />
            </div>
            <Textarea data-testid="lf-description" placeholder="Where / when. Any details?" value={lfForm.description} onChange={(e) => setLfForm({ ...lfForm, description: e.target.value })} className="mt-3 bg-[#2a5f3d] border-white/10" />
            <div className="mt-3 flex justify-end">
              <button data-testid="lf-submit" onClick={submitLostFound} className="btn-primary text-xs flex items-center gap-1">
                <Plus size={12} weight="bold" /> Post to Lost & Found
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {lostFound.map((it) => (
              <div key={it.id} className={`card-surface overflow-hidden ${it.resolved ? "opacity-50" : ""}`} data-testid={`lf-item-${it.id}`}>
                {it.image_path && (
                  <AuthImage path={it.image_path} className="w-full aspect-video object-cover cursor-pointer" onClick={() => setLightbox({ path: it.image_path, caption: it.title })} />
                )}
                <div className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="font-display text-base">{it.title}</div>
                    {it.resolved && <CheckCircle weight="fill" className="text-emerald-400" size={18} />}
                  </div>
                  <div className="text-xs text-zinc-400 mt-1">{it.description}</div>
                  <div className="mt-2 text-[10px] font-mono-data text-zinc-500">
                    {it.author_name} · {new Date(it.created_at).toLocaleDateString()}
                  </div>
                  {!it.resolved && (
                    <button data-testid={`lf-resolve-${it.id}`} onClick={() => resolveLF(it.id)} className="mt-3 text-xs px-3 py-1.5 rounded-full border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10">
                      Mark Resolved
                    </button>
                  )}
                </div>
              </div>
            ))}
            {lostFound.length === 0 && <div className="text-zinc-500 text-sm">No items reported</div>}
          </div>
        </div>
      )}

      {lightbox && <Lightbox path={lightbox.path} caption={lightbox.caption} onClose={() => setLightbox(null)} />}
    </div>
  );
}
