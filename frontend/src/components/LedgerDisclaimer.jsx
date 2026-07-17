import { Link } from "react-router-dom";
import { Info } from "@phosphor-icons/react";

/**
 * Compact informational banner shown inside the Create League wizard
 * (payout step) and the Ledger dashboard, disclosing that the ledger is
 * an automated calculation utility only. Links to /legal/privacy.
 */
export default function LedgerDisclaimer({ compact = false, testid = "ledger-disclaimer" }) {
  return (
    <div
      data-testid={testid}
      className={`rounded-lg border border-[#F5C542]/40 bg-[#F5C542]/8 flex items-start gap-2 ${
        compact ? "px-3 py-2" : "p-4"
      }`}
    >
      <Info
        size={compact ? 14 : 18}
        weight="fill"
        className="text-[#F5C542] flex-shrink-0 mt-0.5"
      />
      <div className={compact ? "text-[11px]" : "text-xs"}>
        <p className="text-gray-800 leading-snug">
          Ace Chasers provides an automated calculation ledger utility. Real-world
          financial pool management and payouts are the sole responsibility of the
          League Director.
        </p>
        <Link
          to="/legal/privacy"
          data-testid={`${testid}-link`}
          className="inline-block mt-1 font-mono-data text-[10px] text-[#F5C542] hover:underline uppercase tracking-wider"
        >
          Read the full Privacy & Terms →
        </Link>
      </div>
    </div>
  );
}
