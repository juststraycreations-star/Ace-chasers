import { useEffect, useState } from 'react';
import { api } from '../lib/api';

/**
 * Modal form for adding a new course to the community list.
 * Any signed-in user can submit; the backend de-dupes on name + location.
 */
export default function AddCourseModal({ open, onClose, onAdded }) {
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [holes, setHoles] = useState('');
  const [description, setDescription] = useState('');
  const [aceClub, setAceClub] = useState(false);
  const [aceClubCount, setAceClubCount] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape' && !submitting) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, submitting]);

  // Reset form whenever the modal is reopened.
  useEffect(() => {
    if (open) {
      setName('');
      setLocation('');
      setHoles('');
      setDescription('');
      setAceClub(false);
      setAceClubCount('');
      setError('');
    }
  }, [open]);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!name.trim()) {
      setError('Course name is required.');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name: name.trim(),
        location: location.trim() || null,
        description: description.trim() || null,
        holes: holes ? Number(holes) : null,
        aceClub,
        aceClubCount: aceClub && aceClubCount ? Number(aceClubCount) : null,
      };
      const res = await api.post('/courses', payload);
      onAdded?.(res.data);
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Could not add course');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] bg-black/60 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-course-title"
      onClick={() => !submitting && onClose()}
      data-testid="add-course-modal"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-md w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 pt-6 pb-4 border-b border-gray-100 flex items-center justify-between">
          <h2 id="add-course-title" className="text-xl font-bold text-disc-green">
            ⛳ Add a course
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-700 text-xl leading-none disabled:opacity-50"
            data-testid="add-course-close"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {error && (
            <div
              className="bg-red-50 border border-red-300 text-red-700 px-3 py-2 rounded text-sm"
              data-testid="add-course-error"
            >
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
              required
              placeholder="e.g. Maple Hill"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
              data-testid="add-course-name"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Location
            </label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              maxLength={200}
              placeholder="City, State"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
              data-testid="add-course-location"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Holes
            </label>
            <input
              type="number"
              min={1}
              max={99}
              value={holes}
              onChange={(e) => setHoles(e.target.value)}
              placeholder="18"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
              data-testid="add-course-holes"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="What's it like? Wooded, technical, par/length, anything riders should know."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green resize-none"
              data-testid="add-course-description"
            />
          </div>

          <div className="border-t border-gray-100 pt-4">
            <label className="flex items-center gap-2 text-sm font-semibold text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={aceClub}
                onChange={(e) => setAceClub(e.target.checked)}
                className="w-4 h-4 text-disc-gold focus:ring-disc-gold"
                data-testid="add-course-ace-club"
              />
              🏆 Runs an Ace Club / ace pot
            </label>
            {aceClub && (
              <div className="mt-3">
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Ace Club size / buy-in (optional)
                </label>
                <input
                  type="number"
                  min={0}
                  max={10000}
                  value={aceClubCount}
                  onChange={(e) => setAceClubCount(e.target.value)}
                  placeholder="e.g. 25"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:border-disc-green"
                  data-testid="add-course-ace-club-count"
                />
              </div>
            )}
          </div>

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="flex-1 border border-gray-300 hover:border-gray-400 text-gray-700 font-semibold py-2 rounded-lg transition disabled:opacity-50"
              data-testid="add-course-cancel"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 bg-disc-green hover:bg-disc-green/90 text-white font-semibold py-2 rounded-lg transition disabled:opacity-50"
              data-testid="add-course-submit"
            >
              {submitting ? 'Adding…' : 'Add course'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
