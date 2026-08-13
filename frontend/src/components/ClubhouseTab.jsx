import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";
import AuthImage from "./AuthImage";
import Lightbox from "./Lightbox";
import { toast } from "sonner";
import { PushPin, Warning, ImageSquare, Plus, Fire, TrendUp, Trash, CheckCircle, SpeakerX, VideoCamera, X as CloseIcon } from "@phosphor-icons/react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_VIDEO_BYTES = 25 * 1024 * 1024;

export default function ClubhouseTab({ leagueId, isDirector, currentUser }) {
  const [tab, setTab] = useState("feed"); // feed | lost-found
  const [stories, setStories] = useState([]);
  const [announcements, setAnnouncements] = useState([]);
  const [feed, setFeed] = useState([]);
  const [lostFound, setLostFound] = useState([]);
  const [uploading, setUploading] = useState(false);
  const storyInputRef = useRef(null);
  const lfImgRef = useRef(null);
  const [lfImage, setLfImage] = useState(null);
  const [newPost, setNewPost] = useState("");
  // Composer media state — mirrors the main Feed.jsx UX (image OR video, not both).
  const [postImage, setPostImage] = useState(null);        // File object
  const [postImagePreview, setPostImagePreview] = useState(null);
  const [postVideo, setPostVideo] = useState(null);
  const [postVideoPreview, setPostVideoPreview] = useState(null);
  const [postingMedia, setPostingMedia] = useState(false);
  const postImageRef = useRef(null);
  const postVideoRef = useRef(null);
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

  const pickImage = (file) => {
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) { toast.error("Image too large (max 8MB)"); return; }
    setPostVideo(null); setPostVideoPreview(null);
    setPostImage(file);
    setPostImagePreview(URL.createObjectURL(file));
  };

  const pickVideo = (file) => {
    if (!file) return;
    if (file.size > MAX_VIDEO_BYTES) { toast.error("Video too large (max 25MB)"); return; }
    setPostImage(null); setPostImagePreview(null);
    setPostVideo(file);
    setPostVideoPreview(URL.createObjectURL(file));
  };

  const clearComposerMedia = () => {
    setPostImage(null); setPostImagePreview(null);
    setPostVideo(null); setPostVideoPreview(null);
    if (postImageRef.current) postImageRef.current.value = "";
    if (postVideoRef.current) postVideoRef.current.value = "";
  };

  const uploadOne = async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const { data } = await api.post("/files/upload", fd, { headers: { "Content-Type": "multipart/form-data" }});
    return data.path;
  };

  const submitPost = async () => {
    const body = newPost.trim();
    if (!body && !postImage && !postVideo) return;
    setPostingMedia(true);
    try {
      let image_path = null;
      let video_path = null;
      if (postImage) image_path = await uploadOne(postImage);
      if (postVideo) video_path = await uploadOne(postVideo);
      await api.post(`/leagues/${leagueId}/feed`, { body, image_path, video_path });
      setNewPost("");
      clearComposerMedia();
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to post");
    } finally {
      setPostingMedia(false);
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

          {/* New post — composer with text + image + video attachments (1:1 with main Feed) */}
          <div
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            data-testid="new-post"
          >
            <Textarea
              data-testid="post-input"
              placeholder="Share a thought with the league…"
              value={newPost}
              onChange={(e) => setNewPost(e.target.value)}
              className="bg-white text-slate-900 placeholder:text-slate-400 border-slate-200 focus:border-emerald-500 min-h-[70px]"
            />
            {(postImagePreview || postVideoPreview) && (
              <div className="relative mt-3 inline-block" data-testid="post-media-preview">
                {postImagePreview && (
                  <img
                    src={postImagePreview}
                    alt="preview"
                    className="max-h-56 rounded-lg border border-slate-200"
                  />
                )}
                {postVideoPreview && (
                  <video
                    src={postVideoPreview}
                    controls
                    className="max-h-56 rounded-lg border border-slate-200"
                  />
                )}
                <button
                  type="button"
                  onClick={clearComposerMedia}
                  data-testid="post-media-clear"
                  className="absolute top-2 right-2 w-6 h-6 rounded-full bg-slate-900/80 text-white flex items-center justify-center hover:bg-slate-900"
                  aria-label="Remove attachment"
                >
                  <CloseIcon size={12} weight="bold" />
                </button>
              </div>
            )}
            <div className="flex items-center justify-between mt-3">
              <div className="flex items-center gap-2">
                <label
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white hover:bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 cursor-pointer"
                  data-testid="post-image-btn"
                  title="Attach an image (max 8MB)"
                >
                  <ImageSquare size={14} weight="duotone" className="text-emerald-600" />
                  Photo
                  <input
                    ref={postImageRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => pickImage(e.target.files?.[0])}
                    data-testid="post-image-input"
                  />
                </label>
                <label
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white hover:bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 cursor-pointer"
                  data-testid="post-video-btn"
                  title="Attach a video (max 25MB)"
                >
                  <VideoCamera size={14} weight="duotone" className="text-emerald-600" />
                  Video
                  <input
                    ref={postVideoRef}
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => pickVideo(e.target.files?.[0])}
                    data-testid="post-video-input"
                  />
                </label>
              </div>
              <button
                data-testid="post-submit"
                onClick={submitPost}
                disabled={postingMedia}
                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm px-4 py-2 shadow-sm transition-colors disabled:opacity-50"
              >
                {postingMedia ? "Posting…" : "Post"}
              </button>
            </div>
          </div>

          {/* Feed posts */}
          {feed.map((p) => (
            p.kind === "recap" ? (
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
            ) : (
              <div key={p.id} className={`card-surface p-5 ${p.hidden ? "opacity-40" : ""} ${p.pinned ? "ring-1 ring-amber-300 bg-amber-50/40" : ""}`} data-testid={`feed-post-${p.id}`}>
                <div className="flex items-start gap-3">
                  {p.author_picture ? (
                    <img src={p.author_picture} className="w-9 h-9 rounded-full" alt="" />
                  ) : (
                    <div className="w-9 h-9 rounded-full bg-zinc-800 flex items-center justify-center text-xs">{p.author_name?.charAt(0)}</div>
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
                    {p.image_path && (
                      <div className="mt-3" data-testid={`feed-post-image-${p.id}`}>
                        <AuthImage
                          path={p.image_path}
                          className="max-h-96 rounded-lg border border-slate-200 cursor-zoom-in"
                          onClick={() => setLightbox({ path: p.image_path, caption: p.author_name })}
                          alt=""
                        />
                      </div>
                    )}
                    {p.video_path && (
                      <div className="mt-3" data-testid={`feed-post-video-${p.id}`}>
                        <video
                          src={p.video_path.startsWith("http") ? p.video_path : `/api/files/${p.video_path}`}
                          poster={p.video_poster || undefined}
                          controls
                          preload="metadata"
                          className="max-h-96 w-full rounded-lg border border-slate-200 bg-black"
                        />
                      </div>
                    )}
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
            )
          ))}
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
