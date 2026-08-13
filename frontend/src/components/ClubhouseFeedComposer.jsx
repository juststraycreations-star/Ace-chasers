import { useState, useRef } from 'react';
import { Image, Video, MessageSquare, Send, X } from 'lucide-react';

/**
 * ClubhouseFeedComposer — polished feed composer surface for the League
 * Clubhouse tab. Palette matches the emerald/white unification pass
 * (iteration 46-49) — white card, slate borders, emerald primary CTA.
 *
 * The parent owns backend wiring via `onPostSubmit({ text, media })`
 * where `media` is an ordered array of
 *   `{ file, id, preview, isVideo }`.
 * The composer only clears its local state after the promise resolves.
 * The parent is expected to `throw` on failure so we can keep the
 * queued files visible for retry.
 */
export default function ClubhouseFeedComposer({ onPostSubmit }) {
  const [commentText, setCommentText] = useState('');
  const [attachedFiles, setAttachedFiles] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fileInputRef = useRef(null);
  const [uploadFilter, setUploadFilter] = useState('*');

  const handleMediaTrigger = (filterType) => {
    setUploadFilter(filterType);
    setTimeout(() => fileInputRef.current?.click(), 30);
  };

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || []);
    const mapped = files.map(file => ({
      file,
      id: Math.random().toString(36).substr(2, 9),
      preview: URL.createObjectURL(file),
      isVideo: file.type.startsWith('video/')
    }));
    setAttachedFiles(prev => [...prev, ...mapped]);
  };

  const removeAttachment = (id) => {
    setAttachedFiles(prev => {
      const match = prev.find(f => f.id === id);
      if (match) URL.revokeObjectURL(match.preview);
      return prev.filter(f => f.id !== id);
    });
  };

  const handlePublish = async (e) => {
    e.preventDefault();
    if (!commentText.trim() && attachedFiles.length === 0) return;

    setIsSubmitting(true);
    try {
      await onPostSubmit({
        text: commentText,
        media: attachedFiles
      });
      setCommentText('');
      setAttachedFiles([]);
    } catch (err) {
      console.error("Feed syncing failed", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="w-full bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden mb-6"
      data-testid="new-post"
    >
      {/* Visual Zone 1: Section Header consistent with Leaderboard/Round cards */}
      <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-emerald-600" />
          <h3 className="font-semibold text-sm text-slate-800 tracking-tight">Create Feed Update</h3>
        </div>
        <span className="text-[11px] font-medium text-slate-400 bg-slate-200/60 px-2 py-0.5 rounded-full">
          Clubhouse Broadcast
        </span>
      </div>

      <form onSubmit={handlePublish} className="p-4 space-y-4">
        {/* Visual Zone 2: Rich Text Input */}
        <div>
          <textarea
            data-testid="post-input"
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder="What's happening in the league? Post an ace photo, share video highlights, or leave a update..."
            className="w-full min-h-[85px] text-slate-800 placeholder-slate-400 bg-slate-50/50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/10 focus:border-emerald-500 transition-all resize-none"
          />
        </div>

        {/* Horizontal Attachment Strip (Only renders when media is queued) */}
        {attachedFiles.length > 0 && (
          <div
            className="flex flex-wrap gap-2.5 p-2 bg-slate-50 border border-slate-200 rounded-lg"
            data-testid="post-media-preview"
          >
            {attachedFiles.map((item) => (
              <div key={item.id} className="relative w-20 h-20 rounded-md overflow-hidden bg-slate-900 border border-slate-200 shadow-sm group">
                {item.isVideo ? (
                  <video src={item.preview} className="w-full h-full object-cover" muted />
                ) : (
                  <img src={item.preview} alt="Upload asset preview" className="w-full h-full object-cover" />
                )}
                <button
                  type="button"
                  onClick={() => removeAttachment(item.id)}
                  data-testid={`post-media-clear-${item.id}`}
                  className="absolute top-1 right-1 p-1 bg-slate-950/80 hover:bg-red-600 text-white rounded-full transition-colors duration-150 shadow"
                >
                  <X className="w-3 h-3" />
                </button>
                <div className="absolute bottom-0 inset-x-0 bg-slate-950/40 text-[9px] text-white py-0.5 text-center font-medium capitalize tracking-wider">
                  {item.isVideo ? 'Video' : 'Photo'}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Hidden System Input */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept={uploadFilter}
          multiple
          className="hidden"
          data-testid="post-file-input"
        />

        {/* Visual Zone 3: Standard Layout Actions Footer */}
        <div className="flex items-center justify-between pt-3 border-t border-slate-100">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => handleMediaTrigger('image/*')}
              data-testid="post-image-btn"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-all"
            >
              <Image className="w-4 h-4 text-emerald-600" />
              <span>Add Photo</span>
            </button>

            <button
              type="button"
              onClick={() => handleMediaTrigger('video/*')}
              data-testid="post-video-btn"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-all"
            >
              <Video className="w-4 h-4 text-emerald-600" />
              <span>Add Video</span>
            </button>
          </div>

          <button
            type="submit"
            data-testid="post-submit"
            disabled={isSubmitting || (!commentText.trim() && attachedFiles.length === 0)}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-100 disabled:text-slate-400 text-white text-xs font-semibold rounded-lg shadow-sm transition-all cursor-pointer"
          >
            {isSubmitting ? (
              <span className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
            <span>Publish to Feed</span>
          </button>
        </div>
      </form>
    </div>
  );
}
