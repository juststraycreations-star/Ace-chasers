import { create } from 'zustand';

/**
 * roundStore — client-side state layer for the "Round Detail Management"
 * feature on the Ace Chasers dashboard.
 *
 * Read-only mirror of backend state:
 *   • Rounds live in Mongo (`rounds` collection) with fields
 *     `id`, `course_location`, `holes`, `par_per_hole`, `format`.
 *   • Player progress lives in `scorecards` (`total`, `plus_minus`,
 *     `scores[]`, `player_certified`, `finalized`) joined with
 *     `league_members` (`name`, `division`).
 *
 * This store keeps the client shape decoupled from those backend
 * documents so components can consume a stable, UI-friendly view.
 * `hydrateFromBackend()` performs the mapping; no backend schema is
 * changed by this store.
 *
 * IMPORTANT: This module intentionally ships NO React components. It
 * defines the data structures, mock fixture, and state modifiers only.
 */

// Strict enum for a player's status on a round. The order here is also
// the natural progression through a round (Registered → … → Finalized).
export const ROUND_STATUS = Object.freeze({
  REGISTERED: 'Registered',
  ACTIVE_SCORING: 'Active Scoring',
  CARD_PENDING: 'Card Pending',
  FINALIZED: 'Finalized',
});
export const ROUND_STATUS_VALUES = Object.freeze([
  ROUND_STATUS.REGISTERED,
  ROUND_STATUS.ACTIVE_SCORING,
  ROUND_STATUS.CARD_PENDING,
  ROUND_STATUS.FINALIZED,
]);

// Backend `rounds.format` → UI `gameType`. Kept broad ("team") for
// Team Scramble and Match Play so the UI can render a shared badge
// instead of leaking backend format strings.
export function mapGameType(format) {
  switch (format) {
    case 'Singles':
      return 'singles';
    case 'Random-Draw Doubles':
    case 'BYOP':
      return 'doubles';
    case 'Team':
    case 'Match Play':
      return 'team';
    default:
      return 'singles';
  }
}

// Derive a UI-friendly `layout` label from the backend `rounds.holes`
// count + `par_per_hole` array. Uses a compact "18-hole · par 54" style.
export function deriveLayout(round) {
  if (!round) return '';
  const holes = round.holes ?? (round.par_per_hole || []).length ?? 0;
  const par = Array.isArray(round.par_per_hole)
    ? round.par_per_hole.reduce((a, b) => a + (Number(b) || 0), 0)
    : 0;
  if (!holes) return '';
  return par ? `${holes}-hole · par ${par}` : `${holes}-hole`;
}

// Backend scorecard + member row → UI activePlayer row.
export function deriveRoundStatus(scorecard) {
  if (!scorecard) return ROUND_STATUS.REGISTERED;
  if (scorecard.finalized) return ROUND_STATUS.FINALIZED;
  if (scorecard.player_certified) return ROUND_STATUS.CARD_PENDING;
  const hasAnyStroke = Array.isArray(scorecard.scores)
    ? scorecard.scores.some((v) => Number(v) > 0)
    : (scorecard.total || 0) > 0;
  return hasAnyStroke ? ROUND_STATUS.ACTIVE_SCORING : ROUND_STATUS.REGISTERED;
}

function deriveCurrentHole(scorecard) {
  if (!scorecard || !Array.isArray(scorecard.scores)) return 0;
  // Highest 1-indexed hole with a real stroke recorded.
  let last = 0;
  scorecard.scores.forEach((v, i) => {
    if (Number(v) > 0) last = i + 1;
  });
  return last;
}

// ── Mock data ────────────────────────────────────────────────────
// Matches the exact shape hydrateFromBackend() emits so components
// can be built against this store before the real round is wired.
export const MOCK_CURRENT_ROUND = Object.freeze({
  roundId: 'mock-round-001',
  courseName: 'Maple Hill Gold',
  location: 'Leicester, MA',
  layout: '18-hole · par 54',
  gameType: 'singles',
  totalPlayersCount: 4,
  joinCode: 'W8K3',
});

export const MOCK_ACTIVE_PLAYERS = Object.freeze([
  {
    playerId: 'mock-p-1',
    fullName: 'Riley Chen',
    division: 'MPO',
    currentScore: -3,
    currentHole: 12,
    roundStatus: ROUND_STATUS.ACTIVE_SCORING,
  },
  {
    playerId: 'mock-p-2',
    fullName: 'Jordan Alvarez',
    division: 'MPO',
    currentScore: 0,
    currentHole: 0,
    roundStatus: ROUND_STATUS.REGISTERED,
  },
  {
    playerId: 'mock-p-3',
    fullName: 'Sam Patel',
    division: 'FA',
    currentScore: 4,
    currentHole: 18,
    roundStatus: ROUND_STATUS.CARD_PENDING,
  },
  {
    playerId: 'mock-p-4',
    fullName: 'Devin Woods',
    division: 'Amateur',
    currentScore: 2,
    currentHole: 18,
    roundStatus: ROUND_STATUS.FINALIZED,
  },
]);

export const useRoundStore = create((set, get) => ({
  // ── State ──────────────────────────────────────────────────────
  currentRound: null,       // { roundId, courseName, location, layout, gameType, totalPlayersCount }
  activePlayers: [],        // [{ playerId, fullName, division, currentScore, currentHole, roundStatus }]
  lastHydratedAt: null,     // ISO timestamp of the last successful backend hydrate

  // ── Setters ────────────────────────────────────────────────────
  setCurrentRound: (round) => set({ currentRound: round }),
  setActivePlayers: (players) => set({ activePlayers: Array.isArray(players) ? players : [] }),

  clear: () => set({ currentRound: null, activePlayers: [], lastHydratedAt: null }),

  loadMock: () =>
    set({
      currentRound: { ...MOCK_CURRENT_ROUND },
      activePlayers: MOCK_ACTIVE_PLAYERS.map((p) => ({ ...p })),
      lastHydratedAt: new Date().toISOString(),
    }),

  // ── Actions ────────────────────────────────────────────────────

  /**
   * updatePlayerStatus(playerId, newStatus)
   *
   * Immutably updates a single player's `roundStatus`. Throws on an
   * unknown status so an incorrect string never leaks into state.
   * Returns the updated player (or undefined if the id wasn't found).
   */
  updatePlayerStatus: (playerId, newStatus) => {
    if (!ROUND_STATUS_VALUES.includes(newStatus)) {
      throw new Error(
        `updatePlayerStatus: invalid status "${newStatus}". Must be one of ${ROUND_STATUS_VALUES.join(', ')}.`
      );
    }
    let updated;
    set((state) => ({
      activePlayers: state.activePlayers.map((p) => {
        if (p.playerId !== playerId) return p;
        updated = { ...p, roundStatus: newStatus };
        return updated;
      }),
    }));
    return updated;
  },

  /**
   * hydrateFromBackend({ round, members, scorecards })
   *
   * Maps existing backend shapes onto this store without mutating any
   * server document. Safe to call repeatedly (e.g. on every poll).
   */
  hydrateFromBackend: ({ round, members = [], scorecards = [] } = {}) => {
    if (!round) {
      get().clear();
      return;
    }
    const memberById = new Map(members.map((m) => [m.id, m]));

    const activePlayers = scorecards.map((sc) => {
      const mem = memberById.get(sc.member_id) || {};
      return {
        playerId: sc.member_id,
        fullName: mem.name || 'Player',
        division: mem.division || 'Open',
        currentScore: sc.plus_minus ?? 0,
        currentHole: deriveCurrentHole(sc),
        roundStatus: deriveRoundStatus(sc),
      };
    });

    const currentRound = {
      roundId: round.id,
      courseName: round.course_location || round.name || '',
      location: round.course_location || '',
      layout: deriveLayout(round),
      gameType: mapGameType(round.format),
      totalPlayersCount: activePlayers.length || members.length || 0,
      // Backend `rounds.join_code` — 4-char uppercase alphanumeric code
      // for players who can't scan the QR (see leagues_router
      // `_generate_round_join_code`). Null on legacy rounds created
      // before the code was added.
      joinCode: round.join_code || null,
    };

    set({
      currentRound,
      activePlayers,
      lastHydratedAt: new Date().toISOString(),
    });
  },
}));
