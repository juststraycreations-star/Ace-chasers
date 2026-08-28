/**
 * Default avatar for users who haven't uploaded a profile picture yet.
 * Renders as an inline SVG data URI of a disc golf disc — no external
 * fetch, no Cloudinary cost, and matches the app's identity.
 */
const DISC_AVATAR_SVG = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
  <defs>
    <radialGradient id="g" cx="50%" cy="40%" r="60%">
      <stop offset="0%" stop-color="#4ade80"/>
      <stop offset="55%" stop-color="#22a06b"/>
      <stop offset="100%" stop-color="#155e3a"/>
    </radialGradient>
  </defs>
  <rect width="200" height="200" fill="#0f2a1f"/>
  <ellipse cx="100" cy="105" rx="78" ry="20" fill="#000" opacity="0.25"/>
  <ellipse cx="100" cy="95" rx="78" ry="22" fill="url(#g)" stroke="#0f2a1f" stroke-width="2"/>
  <ellipse cx="100" cy="93" rx="60" ry="16" fill="none" stroke="#86efac" stroke-width="1.5" opacity="0.7"/>
  <ellipse cx="100" cy="91" rx="42" ry="11" fill="none" stroke="#bbf7d0" stroke-width="1.2" opacity="0.6"/>
  <text x="100" y="96" text-anchor="middle" font-family="ui-sans-serif,system-ui,sans-serif" font-size="14" font-weight="700" fill="#fef9c3">ACE</text>
</svg>`;

// Pre-encode to avoid running btoa at every render.
export const DEFAULT_AVATAR = `data:image/svg+xml;utf8,${encodeURIComponent(DISC_AVATAR_SVG)}`;
