// Stable, inlined SVG avatar used when a user's Firebase/Mongo
// `author_picture` is null, an empty string, or fails to load in the
// browser (broken CDN URL, expired token, etc.). Inlined as a
// data-URL string so it costs zero network hops and can never itself
// 404 out of the layout thread.
//
// Design brief: neutral emerald ring, gentle silhouette head+shoulders
// on a light gray fill. Matches the Ace Chasers palette.

const SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="40" height="40">' +
    '<circle cx="20" cy="20" r="20" fill="#f1f5f4"/>' +
    '<circle cx="20" cy="20" r="19" fill="none" stroke="#10b981" stroke-width="1.2" stroke-opacity="0.35"/>' +
    '<circle cx="20" cy="16" r="6" fill="#94a3b8"/>' +
    '<path d="M8 34c1.6-6.2 6.2-9 12-9s10.4 2.8 12 9v6H8z" fill="#94a3b8"/>' +
  '</svg>';

// Percent-encode the raw SVG payload (browsers reject unescaped `#`
// inside a data URL) so this string is safe to drop into an <img src>.
export const AVATAR_FALLBACK_SVG = `data:image/svg+xml,${encodeURIComponent(SVG)}`;

/**
 * onAvatarError — attach to any user avatar `<img>` so a broken URL
 * quietly swaps to the fallback SVG instead of leaving a "broken
 * image" glyph and (in some browsers) triggering onError repeatedly.
 *
 * Usage:
 *   <img src={p.author_picture || AVATAR_FALLBACK_SVG} onError={onAvatarError} />
 */
export function onAvatarError(e) {
  const img = e.currentTarget;
  // Guard against onError firing again when the fallback itself is
  // installed — some browsers still fire the handler even on data URLs
  // if the previous src was already flagged errored.
  if (img.dataset.fallbackApplied === "1") return;
  img.dataset.fallbackApplied = "1";
  img.src = AVATAR_FALLBACK_SVG;
}
