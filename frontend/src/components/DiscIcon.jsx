/**
 * Small red disc / frisbee icon used in the app header. Inline SVG so it
 * renders consistently across browsers (emoji rendering varies by OS).
 *
 * Pass `className` to control size (default 1.5em tall).
 */
export default function DiscIcon({ className = 'inline-block align-middle h-7 w-7', title = 'Ace Chasers disc' }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      role="img"
      aria-label={title}
      className={className}
    >
      <defs>
        <radialGradient id="discRed" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stopColor="#fca5a5" />
          <stop offset="55%" stopColor="#dc2626" />
          <stop offset="100%" stopColor="#7f1d1d" />
        </radialGradient>
      </defs>
      <ellipse cx="32" cy="36" rx="26" ry="6" fill="#000" opacity="0.25" />
      <ellipse cx="32" cy="32" rx="26" ry="7" fill="url(#discRed)" stroke="#7f1d1d" strokeWidth="1" />
      <ellipse cx="32" cy="31" rx="20" ry="5" fill="none" stroke="#fecaca" strokeWidth="1" opacity="0.7" />
      <ellipse cx="32" cy="30" rx="14" ry="3.5" fill="none" stroke="#fee2e2" strokeWidth="0.9" opacity="0.6" />
    </svg>
  );
}
