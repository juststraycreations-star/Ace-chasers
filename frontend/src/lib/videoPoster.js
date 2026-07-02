/**
 * Extract a poster frame from a local video File and return it as a
 * data-URL JPEG suitable for use as a `<video poster="…">` attribute.
 *
 * Runs entirely client-side using an off-screen `<video>` + `<canvas>` —
 * no bytes leave the browser. We seek to a small offset (~0.4s) so the
 * frame isn't the black lead-in most cameras record.
 *
 * Resolves to `null` if the browser can't decode the file (e.g. iPhone
 * HEVC on a desktop Chrome that lacks the codec). Caller should fall
 * back to a solid poster tile in that case.
 */
export function extractVideoPoster(file, { seekSeconds = 0.4, maxWidth = 640 } = {}) {
  return new Promise((resolve) => {
    if (!file || !(file instanceof Blob)) {
      resolve(null);
      return;
    }
    const url = URL.createObjectURL(file);
    const video = document.createElement('video');
    video.preload = 'metadata';
    video.muted = true;
    video.playsInline = true;
    video.src = url;

    let settled = false;
    const done = (result) => {
      if (settled) return;
      settled = true;
      URL.revokeObjectURL(url);
      video.remove();
      resolve(result);
    };

    // Hard cap so we never hang the UI on a stuck decode.
    const timeout = setTimeout(() => done(null), 4000);

    video.addEventListener('error', () => {
      clearTimeout(timeout);
      done(null);
    });

    video.addEventListener('loadedmetadata', () => {
      const target = Math.min(seekSeconds, Math.max(0, (video.duration || 0) - 0.05));
      try {
        video.currentTime = target;
      } catch {
        clearTimeout(timeout);
        done(null);
      }
    });

    video.addEventListener('seeked', () => {
      try {
        const w = video.videoWidth;
        const h = video.videoHeight;
        if (!w || !h) {
          clearTimeout(timeout);
          done(null);
          return;
        }
        const scale = Math.min(1, maxWidth / w);
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(w * scale);
        canvas.height = Math.round(h * scale);
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        clearTimeout(timeout);
        done(canvas.toDataURL('image/jpeg', 0.75));
      } catch {
        clearTimeout(timeout);
        done(null);
      }
    });
  });
}
