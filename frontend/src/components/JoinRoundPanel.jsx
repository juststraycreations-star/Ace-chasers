import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { ArrowRight } from "@phosphor-icons/react";

// The generator on the server picks from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`
// (uppercase A–Z + digits minus O/0/I/1). We mirror that filter in the
// input so a player can't submit a code the server will never match.
const CODE_ALPHABET = /[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]/;

/**
 * JoinRoundPanel — mounted at the top of both the League Dashboard
 * (LeagueList surface) and the League Detail Rounds tab (RoundList
 * surface). Players who can't scan the QR type the 4-char code shown
 * on the round's QR panel here and land straight in the scorecard.
 *
 * On submit → `GET /api/rounds/join/{code}`:
 *   • Idempotent — repeated taps just re-enroll them into the same
 *     scorecard.
 *   • On success we `navigate('/rounds/{roundId}')` so the player
 *     lands directly in the live scoring view.
 */
export default function JoinRoundPanel({ compact = false }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  // Force uppercase, strip anything outside the code alphabet, cap at 4.
  const onChange = (e) => {
    const clean = e.target.value
      .toUpperCase()
      .split("")
      .filter((ch) => CODE_ALPHABET.test(ch))
      .slice(0, 4)
      .join("");
    setCode(clean);
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy || code.length !== 4) return;
    setBusy(true);
    try {
      const { data } = await api.get(`/rounds/join/${code}`);
      // Backend response shape: { round: {...}, auto_joined_league, already_enrolled, card, scorecard }
      const roundId = data?.round?.id;
      if (!roundId) throw new Error("Missing round id in response");
      if (data.auto_joined_league) toast.success(`Joined ${data.round?.name || "round"}`);
      // Instant land inside the live scoring card view.
      navigate(`/rounds/${roundId}`);
    } catch (err) {
      const status = err?.response?.status;
      const msg =
        status === 404
          ? "No active round matches that code"
          : err?.response?.data?.detail || "Could not join round";
      toast.error(msg);
      setBusy(false);
    }
  };

  return (
    <section
      data-testid="join-round-panel"
      className={`bg-white border border-emerald-100 rounded-2xl shadow-sm ${
        compact ? "p-4" : "p-4 sm:p-5"
      } mb-6`}
    >
      <form
        onSubmit={submit}
        className="flex flex-col sm:flex-row sm:items-center gap-3"
      >
        <label
          htmlFor="join-round-code-input"
          className="text-sm font-bold text-gray-700 whitespace-nowrap"
        >
          Have a Join Code?
        </label>
        <input
          id="join-round-code-input"
          data-testid="join-round-code-input"
          value={code}
          onChange={onChange}
          onKeyDown={(e) => e.key === "Enter" && submit(e)}
          maxLength={4}
          inputMode="text"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          placeholder="W8K3"
          aria-label="Round join code (4 uppercase alphanumeric characters)"
          className="flex-1 min-w-0 sm:w-40 rounded-lg border-2 border-emerald-100 bg-emerald-50/40 focus:border-emerald-600 focus:bg-white focus:ring-2 focus:ring-emerald-500/10 focus:outline-none px-3 py-2 text-center text-lg uppercase tracking-widest font-mono font-bold text-emerald-700 placeholder:text-emerald-200 placeholder:font-normal transition-colors"
        />
        <button
          type="submit"
          disabled={busy || code.length !== 4}
          data-testid="join-round-submit-btn"
          className={`inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold shadow-sm transition-colors whitespace-nowrap ${
            busy || code.length !== 4
              ? "bg-gray-100 text-gray-400 cursor-not-allowed"
              : "bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer"
          }`}
        >
          {busy ? "Joining…" : "Join Round"}
          {!busy && <ArrowRight size={14} weight="bold" />}
        </button>
      </form>
    </section>
  );
}
