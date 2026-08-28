/**
 * Single source of truth for the "Interested in" chip set.
 *
 * The Profile edit form uses these as toggleable tags that get written into
 * the user's free-text `interestedIn` field, and the Discovery filter bar
 * uses the same keywords as case-insensitive substring matches against that
 * same field. Keeping the list here prevents one side from drifting from
 * the other (a real risk noted in the iter-8 review).
 */
export const INTEREST_TAG_OPTIONS = [
  { label: 'Casual rounds', value: 'casual' },
  { label: 'Doubles', value: 'doubles' },
  { label: 'League', value: 'league' },
  { label: 'Tournaments', value: 'tournament' },
  { label: 'Putting', value: 'putt' },
];

/** Discovery filter chips include an explicit "Any" sentinel that resets
 *  the filter, which the Profile chips don't need. */
export const DISCOVERY_INTEREST_OPTIONS = [
  { label: 'Any', value: null },
  ...INTEREST_TAG_OPTIONS,
];

/** Return the set of chip values currently active in a free-text string. */
export function activeInterestTags(text) {
  const haystack = (text || '').toLowerCase();
  return new Set(
    INTEREST_TAG_OPTIONS
      .filter((opt) => haystack.includes(opt.value))
      .map((opt) => opt.value),
  );
}

/** Toggle a tag inside a free-text interestedIn string, preserving custom
 *  prose around the label. */
export function toggleInterestTag(text, opt) {
  const current = text || '';
  const set = activeInterestTags(current);
  if (set.has(opt.value)) {
    const pattern = new RegExp(`\\b${opt.label}\\b[,;]?\\s*`, 'gi');
    return current.replace(pattern, '').replace(/^[,;\s]+|[,;\s]+$/g, '').trim();
  }
  return current.trim().length
    ? `${current.trim()}, ${opt.label}`
    : opt.label;
}
