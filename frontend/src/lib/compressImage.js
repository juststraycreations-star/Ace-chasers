/**
 * Client-side image compression using Canvas — no external dependencies.
 *
 * Phones routinely produce 8–20 MB JPEG/HEIC files. The backend caps uploads
 * at 5 MB, so we down-scale + re-encode before sending. Animated GIFs are
 * passed through untouched (Canvas can't preserve frames).
 */

const DEFAULT_OPTIONS = {
  maxWidth: 2000,
  maxHeight: 2000,
  // Output JPEG at this quality. Range 0–1; 0.82 is a good "looks identical
  // unless you zoom in" sweet spot.
  quality: 0.82,
  mimeType: 'image/jpeg',
};

const PRESETS = {
  banner: { maxWidth: 1600, maxHeight: 600, quality: 0.85 },
  avatar: { maxWidth: 800, maxHeight: 800, quality: 0.88 },
  post: { maxWidth: 1600, maxHeight: 1600, quality: 0.82 },
};

const MAX_RAW_BYTES = 30 * 1024 * 1024; // 30 MB sanity limit

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Could not read this image. Try a different file.'));
    img.src = src;
  });
}

/**
 * Compress an image file. Returns a new File (or the original if no work
 * was needed, e.g. for GIFs or already-small images).
 *
 * @param {File} file
 * @param {('banner'|'avatar'|'post')} [preset]
 */
export async function compressImage(file, preset = 'post') {
  if (!file) throw new Error('No file provided');
  if (file.size > MAX_RAW_BYTES) {
    throw new Error('Image is huge (>30MB). Pick a smaller file or take a fresh photo.');
  }

  // GIFs lose their animation if redrawn on a canvas — skip compression and
  // hope they're small enough.
  if (file.type === 'image/gif') {
    return file;
  }

  const options = { ...DEFAULT_OPTIONS, ...(PRESETS[preset] || {}) };

  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Couldn't read that file."));
    reader.readAsDataURL(file);
  });

  const img = await loadImage(dataUrl);

  // Compute output dimensions, preserving aspect ratio.
  const ratio = Math.min(
    options.maxWidth / img.naturalWidth,
    options.maxHeight / img.naturalHeight,
    1
  );
  const w = Math.round(img.naturalWidth * ratio);
  const h = Math.round(img.naturalHeight * ratio);

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  // Fill white in case we drop a PNG with transparency into JPEG.
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, options.mimeType, options.quality)
  );

  if (!blob) {
    // Browser refused to encode (rare) — fall back to original.
    return file;
  }

  // If compression somehow ballooned the file (tiny image, weird format),
  // keep the original.
  if (blob.size >= file.size) {
    return file;
  }

  const ext = options.mimeType === 'image/jpeg' ? 'jpg' : 'png';
  const baseName = (file.name || 'image').replace(/\.[^.]+$/, '');
  return new File([blob], `${baseName}.${ext}`, { type: options.mimeType });
}

export default compressImage;
