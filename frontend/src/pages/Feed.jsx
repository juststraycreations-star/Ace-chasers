import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { api } from '../lib/api';
import { compressImage } from '../lib/compressImage';
import { resolveImageUrl as fullImageUrl } from '../lib/images';
import { DEFAULT_AVATAR } from '../lib/defaultAvatar';
import AlphaBanner from '../components/AlphaBanner';
import DismissibleBanner from '../components/DismissibleBanner';
import NewsSidebar from '../components/NewsSidebar';
import PostInteractions from '../components/PostInteractions';

const MAX_RAW_IMAGE_BYTES = 30 * 1024 * 1024;
const MAX_VIDEO_BYTES = 25 * 1024 * 1024;
const ACCEPTED_VIDEO_TYPES = ['video/mp4', 'video/webm', 'video/quicktime'];

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function Feed() {
  const profile = useAuthStore((s) => s.profile);
  const [posts, setPosts] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [body, setBody] = useState('');
  const [visibility, setVisibility] = useState('public');
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [videoFile, setVideoFile] = useState(null);
  const [videoPreview, setVideoPreview] = useState(null);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState('');
  // The single post with the most 👍 Nice reactions in the past 7 days — null
  // when no qualifying post exists yet (e.g. brand-new community).
  const [topNiced, setTopNiced] = useState(null);
  const fileInputRef = useRef(null);
  const videoInputRef = useRef(null);

  const fetchFeed = async () => {
    try {
      const res = await api.get('/feed');
      setPosts(res.data.posts);
      setNextCursor(res.data.next_cursor);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchTopNiced = async () => {
    try {
      const res = await api.get('/feed/top-niced-this-week');
      setTopNiced(res.data || null);
    } catch (err) {
      // Non-critical — silently skip if the backend hiccups.
      console.warn('top-niced fetch failed', err);
      setTopNiced(null);
    }
  };

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await api.get('/feed', { params: { before: nextCursor } });
      setPosts((prev) => [...prev, ...res.data.posts]);
      setNextCursor(res.data.next_cursor);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    // Intentionally runs once on mount. `fetchFeed` is declared inside the
    // component (recreated each render) so listing it in deps would cause
    // an infinite refetch loop.
    fetchFeed();
    fetchTopNiced();
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) {
      setImageFile(null);
      setImagePreview(null);
      return;
    }
    if (!file.type.startsWith('image/')) {
      setError(`That doesn't look like an image (got ${file.type || 'unknown type'}).`);
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    if (file.size > MAX_RAW_IMAGE_BYTES) {
      setError('Image is huge (>30MB). Pick a smaller file or take a fresh photo.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    setError('');
    // Photo replaces any pending video.
    setVideoFile(null);
    setVideoPreview(null);
    if (videoInputRef.current) videoInputRef.current.value = '';
    try {
      const compressed = await compressImage(file, 'post');
      setImageFile(compressed);
      setImagePreview(URL.createObjectURL(compressed));
    } catch (err) {
      setError(err?.message || 'Could not process that image.');
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleVideoChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) {
      setVideoFile(null);
      setVideoPreview(null);
      return;
    }
    if (!ACCEPTED_VIDEO_TYPES.includes(file.type) && !file.name.match(/\.(mp4|webm|mov)$/i)) {
      setError(`Unsupported video format (got ${file.type || 'unknown type'}). Use mp4, webm, or mov.`);
      if (videoInputRef.current) videoInputRef.current.value = '';
      return;
    }
    if (file.size > MAX_VIDEO_BYTES) {
      setError(`Video is too large (max ${Math.round(MAX_VIDEO_BYTES / 1024 / 1024)}MB).`);
      if (videoInputRef.current) videoInputRef.current.value = '';
      return;
    }
    setError('');
    // Video replaces any pending photo.
    setImageFile(null);
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setVideoFile(file);
    setVideoPreview(URL.createObjectURL(file));
  };

  const clearImage = () => {
    setImageFile(null);
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const clearVideo = () => {
    setVideoFile(null);
    setVideoPreview(null);
    if (videoInputRef.current) videoInputRef.current.value = '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!body.trim() && !imageFile && !videoFile) {
      setError('Add some text, a photo, or a video first.');
      return;
    }
    setPosting(true);
    try {
      const form = new FormData();
      form.append('body', body);
      form.append('visibility', visibility);
      if (imageFile) form.append('image', imageFile);
      if (videoFile) form.append('media', videoFile);
      const res = await api.post('/posts', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPosts((prev) => [res.data, ...prev]);
      setBody('');
      setVisibility('public');
      clearImage();
      clearVideo();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setPosting(false);
    }
  };

  const handleDelete = async (postId) => {
    if (!window.confirm('Delete this post?')) return;
    try {
      await api.delete(`/posts/${postId}`);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
    } catch (err) {
      setError(err?.response?.data?.detail || err.message);
    }
  };

  return (
    <div
      className="max-w-7xl mx-auto px-4 py-8 flex gap-6 items-start"
      data-testid="feed-view"
    >
      <main className="flex-1 max-w-2xl mx-auto xl:mx-0 w-full min-w-0">
      <AlphaBanner />
      <DismissibleBanner
        storageKey="ace_welcome_v2_dismissed"
        title="We've upgraded! Let's get you re-connected:"
        body={'Update your location for local matching, drop in a profile photo, and share a quick "hi" on the feed.'}
        testId="feed-welcome-banner"
      />
      <h1 className="text-4xl font-bold text-disc-green mb-6">Feed</h1>

      {topNiced && (
        <a
          href={`#post-${topNiced.id}`}
          className="block mb-6 bg-gradient-to-r from-disc-gold/30 via-white to-disc-gold/30 border-2 border-disc-gold rounded-2xl shadow-sm hover:shadow-md transition p-4"
          data-testid="top-niced-banner"
          aria-label="Jump to the most niced post this week"
        >
          <div className="flex items-center gap-3">
            <img
              src={fullImageUrl(topNiced.author?.profilePictureUrl) || DEFAULT_AVATAR}
              alt={topNiced.author?.name || 'Player'}
              className="w-12 h-12 rounded-full object-cover border-2 border-white shadow ring-2 ring-disc-gold flex-shrink-0"
            />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-disc-gold uppercase tracking-wider">
                🏆 Most niced this week
              </p>
              <p
                className="font-bold text-gray-800 truncate"
                data-testid="top-niced-author"
              >
                {topNiced.author?.name || 'Player'}
              </p>
              <p
                className="text-sm text-gray-600 line-clamp-1"
                data-testid="top-niced-body"
              >
                {topNiced.body || '(media post)'}
              </p>
            </div>
            <div className="flex flex-col items-end flex-shrink-0">
              <span
                className="bg-disc-gold text-white font-bold text-sm px-3 py-1 rounded-full"
                data-testid="top-niced-count"
              >
                👍 {topNiced.nice_count}
              </span>
              <span className="text-[10px] text-gray-500 mt-1">{timeAgo(topNiced.created_at)}</span>
            </div>
          </div>
        </a>
      )}

      {/* Compose box */}
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-lg p-5 mb-8"
        data-testid="compose-form"
      >
        {error && (
          <div
            className="mb-4 flex items-start gap-3 bg-red-50 border-2 border-red-300 rounded-lg px-4 py-3 text-sm text-red-800"
            role="alert"
            data-testid="compose-error"
          >
            <span className="text-lg leading-none" aria-hidden="true">⚠️</span>
            <div className="flex-1">
              <p className="font-semibold">Couldn&apos;t post</p>
              <p>{error}</p>
            </div>
            <button
              type="button"
              onClick={() => setError('')}
              className="text-red-700 hover:text-red-900 font-bold leading-none"
              aria-label="Dismiss"
              data-testid="compose-error-dismiss"
            >
              ✕
            </button>
          </div>
        )}

        <div className="flex gap-3">
          <Link
            to="/profile"
            aria-label="Open your profile"
            className="flex-shrink-0 rounded-full ring-offset-2 hover:ring-2 hover:ring-disc-green transition"
            data-testid="compose-avatar-link"
          >
            <img
              src={
                profile?.profilePictureUrl
                  ? (profile.profilePictureUrl.startsWith('http')
                      ? profile.profilePictureUrl
                      : fullImageUrl(profile.profilePictureUrl))
                  : DEFAULT_AVATAR
              }
              alt="You"
              className="w-12 h-12 rounded-full object-cover"
            />
          </Link>
          <div className="flex-1">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Looking for my Disc"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green resize-none"
              rows={3}
              maxLength={1000}
              data-testid="compose-body-input"
            />

            {imagePreview && (
              <div className="relative mt-3 inline-block" data-testid="compose-image-preview">
                <img
                  src={imagePreview}
                  alt="preview"
                  className="max-h-48 rounded-lg border border-gray-200"
                />
                <button
                  type="button"
                  onClick={clearImage}
                  className="absolute top-1 right-1 bg-black/70 hover:bg-black text-white rounded-full w-6 h-6 text-xs"
                  data-testid="compose-remove-image-btn"
                  aria-label="Remove image"
                >
                  ✕
                </button>
              </div>
            )}

            {videoPreview && (
              <div className="relative mt-3 inline-block" data-testid="compose-video-preview">
                <video
                  src={videoPreview}
                  controls
                  className="max-h-60 rounded-lg border border-gray-200 bg-black"
                />
                <button
                  type="button"
                  onClick={clearVideo}
                  className="absolute top-1 right-1 bg-black/70 hover:bg-black text-white rounded-full w-6 h-6 text-xs"
                  data-testid="compose-remove-video-btn"
                  aria-label="Remove video"
                >
                  ✕
                </button>
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
                  onChange={handleFileChange}
                  className="hidden"
                  data-testid="compose-image-input"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="text-disc-green hover:text-disc-green/80 font-semibold text-sm flex items-center gap-1"
                  data-testid="compose-add-photo-btn"
                >
                  📷 Photo
                </button>

                <input
                  ref={videoInputRef}
                  type="file"
                  accept="video/mp4,video/webm,video/quicktime"
                  onChange={handleVideoChange}
                  className="hidden"
                  data-testid="compose-video-input"
                />
                <button
                  type="button"
                  onClick={() => videoInputRef.current?.click()}
                  className="text-disc-green hover:text-disc-green/80 font-semibold text-sm flex items-center gap-1"
                  data-testid="compose-add-video-btn"
                >
                  🎬 Video
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setBody((curr) => {
                      const tag = curr.trim().length === 0 ? 'Nice! 🥏' : `${curr.trimEnd()} Nice! 🥏`;
                      return tag.slice(0, 1000);
                    });
                  }}
                  className="text-disc-green hover:text-disc-green/80 font-semibold text-sm flex items-center gap-1"
                  data-testid="compose-add-nice-btn"
                  title="Insert a quick Nice! tag"
                >
                  👍 Nice
                </button>

                <select
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value)}
                  className="border border-gray-200 rounded-md px-2 py-1 text-sm focus:outline-none focus:border-disc-green"
                  data-testid="compose-visibility-select"
                >
                  <option value="public">🌎 Public</option>
                  <option value="friends_only">👥 Friends only</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={posting}
                className="bg-disc-green hover:bg-disc-green/90 text-white font-bold py-2 px-6 rounded-lg transition disabled:opacity-50"
                data-testid="compose-submit-btn"
              >
                {posting ? 'Posting…' : 'Post'}
              </button>
            </div>
          </div>
        </div>
      </form>

      {/* Feed list */}
      {loading ? (
        <p className="text-center text-gray-500" data-testid="feed-loading">Loading feed…</p>
      ) : posts.length === 0 ? (
        <div
          className="bg-white rounded-xl shadow p-12 text-center text-gray-500"
          data-testid="feed-empty"
        >
          No posts yet — be the first to say hi.
        </div>
      ) : (
        <div className="space-y-5">
          {posts.map((post) => (
            <article
              key={post.id}
              id={`post-${post.id}`}
              className="bg-white rounded-2xl shadow-lg p-5 scroll-mt-24"
              data-testid={`post-${post.id}`}
            >
              <header className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <Link
                    to={post.is_mine ? '/profile' : `/players/${post.author.uid}`}
                    aria-label={`Open ${post.author.name || 'player'}'s profile`}
                    className="rounded-full hover:ring-2 hover:ring-disc-green transition"
                    data-testid={`post-avatar-link-${post.id}`}
                  >
                    <img
                      src={
                        post.author.profilePictureUrl
                          ? (post.author.profilePictureUrl.startsWith('http')
                              ? post.author.profilePictureUrl
                              : fullImageUrl(post.author.profilePictureUrl))
                          : DEFAULT_AVATAR
                      }
                      alt={post.author.name || 'Player'}
                      className="w-10 h-10 rounded-full object-cover"
                    />
                  </Link>
                  <div>
                    <Link
                      to={post.is_mine ? '/profile' : `/players/${post.author.uid}`}
                      className="font-semibold text-gray-800 hover:text-disc-green transition"
                      data-testid={`post-author-${post.id}`}
                    >
                      {post.author.name || 'Player'}
                    </Link>
                    <p className="text-xs text-gray-500 flex items-center gap-2">
                      <span>{timeAgo(post.created_at)}</span>
                      <span aria-hidden="true">·</span>
                      <span
                        className="uppercase tracking-wide"
                        data-testid={`post-visibility-${post.id}`}
                      >
                        {post.visibility === 'friends_only' ? '👥 Friends' : '🌎 Public'}
                      </span>
                    </p>
                  </div>
                </div>
                {post.is_mine && (
                  <button
                    type="button"
                    onClick={() => handleDelete(post.id)}
                    className="text-xs text-gray-400 hover:text-red-600 transition"
                    data-testid={`post-delete-btn-${post.id}`}
                  >
                    Delete
                  </button>
                )}
              </header>

              {post.body && (
                <p className="text-gray-800 whitespace-pre-wrap mb-3" data-testid={`post-body-${post.id}`}>
                  {post.body}
                </p>
              )}
              {post.image_url && (
                <img
                  src={fullImageUrl(post.image_url)}
                  alt="post"
                  className="rounded-lg max-h-[480px] w-full object-cover"
                  data-testid={`post-image-${post.id}`}
                />
              )}
              {post.video_url && (
                <video
                  src={fullImageUrl(post.video_url)}
                  controls
                  preload="metadata"
                  className="rounded-lg max-h-[520px] w-full bg-black"
                  data-testid={`post-video-${post.id}`}
                />
              )}
              <PostInteractions post={post} />
            </article>
          ))}

          {nextCursor && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className="border-2 border-disc-green text-disc-green hover:bg-disc-green hover:text-white font-semibold px-6 py-2 rounded-lg transition disabled:opacity-50"
                data-testid="feed-load-more-btn"
              >
                {loadingMore ? 'Loading…' : 'Load more posts'}
              </button>
            </div>
          )}
        </div>
      )}
      </main>

      <aside className="hidden xl:block w-80 flex-shrink-0 sticky top-24" data-testid="feed-news-rail">
        <NewsSidebar />
      </aside>
    </div>
  );
}
