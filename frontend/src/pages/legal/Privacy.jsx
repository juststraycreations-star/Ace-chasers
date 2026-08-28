import { Link } from "react-router-dom";

export default function Privacy() {
  return (
    <div className="min-h-screen bg-white" data-testid="legal-privacy-page">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="mb-8">
          <Link
            to="/leagues"
            data-testid="legal-privacy-back-link"
            className="font-mono-data text-xs text-zinc-500 hover:text-gray-900"
          >
            ← BACK TO LEAGUES
          </Link>
          <h1 className="font-display text-4xl tracking-tighter mt-3">
            Privacy, Terms & Fair Play
          </h1>
          <p className="text-sm text-zinc-500 mt-2">Last updated: February 2026</p>
        </div>

        <section className="space-y-4 mb-10" data-testid="legal-ledger-section">
          <h2 className="font-display text-2xl">Ledger Utility Disclosure</h2>
          <p className="text-base text-gray-700">
            Ace Chasers provides an automated calculation ledger utility. Real-world
            financial pool management and payouts are the sole responsibility of the
            League Director. The application records credits, debits, and running
            balances for informational purposes only. Ace Chasers does not custody,
            transfer, or otherwise handle any funds; all cash, digital transfers,
            payouts, taxes, and legal obligations are managed off-platform by the
            League Director and participants.
          </p>
        </section>

        <section className="space-y-4 mb-10" data-testid="legal-audit-section">
          <h2 className="font-display text-2xl">Proof of Score Audit Trail</h2>
          <p className="text-base text-gray-700">
            When a player or card captain finalizes a scorecard, the certification
            action logs the certifying user ID, hole-by-hole strokes, and a
            timestamp to a tamper-evident Proof of Score audit trail. This audit
            trail feeds the automated digital Bag Tag matrix and any downstream
            standings, handicaps, or payout calculations. Certifying a score
            without accurately verifying it is a violation of these terms.
          </p>
        </section>

        <section className="space-y-4 mb-10" data-testid="legal-fairplay-section">
          <h2 className="font-display text-2xl">Fair Play Terms · Private Clubhouse</h2>
          <p className="text-base text-gray-700">
            The Clubhouse is a private league feed. By joining, you agree to keep
            score logs transparent, refrain from harassment, and maintain
            respectful community interactions. League Directors may remove
            content, remove members, or archive rounds for violations. Repeated
            or severe violations may result in an account-level suspension from
            Ace Chasers.
          </p>
        </section>

        <section className="space-y-4" data-testid="legal-data-section">
          <h2 className="font-display text-2xl">Data & Privacy</h2>
          <p className="text-base text-gray-700">
            Ace Chasers stores your profile, league memberships, scorecards,
            ledger entries, and clubhouse posts to operate the service. Data is
            not sold. You may request deletion of your account via the profile
            settings; League Directors may retain aggregate anonymized standings
            for historical purposes.
          </p>
        </section>
      </div>
    </div>
  );
}
