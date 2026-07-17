import { Bug } from "@phosphor-icons/react";

/**
 * "Report a bug" button that opens the user's email client with a
 * pre-filled bug report addressed to juststraycreations@gmail.com.
 * Includes the current page URL + user-agent so we can reproduce
 * without a back-and-forth.
 */
export default function ReportBugButton() {
  const openReport = () => {
    const subject = encodeURIComponent("Ace Chasers · Bug report");
    const pageUrl = typeof window !== "undefined" ? window.location.href : "";
    const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
    const body = encodeURIComponent(
      "Describe the bug:\n\n\n" +
        "Steps to reproduce:\n1.\n2.\n3.\n\n" +
        "Expected behavior:\n\n\n" +
        "Screenshots (attach below):\n\n\n" +
        "-----\n" +
        `Page: ${pageUrl}\n` +
        `Browser: ${ua}\n` +
        `Timestamp: ${new Date().toISOString()}`
    );
    window.location.href = `mailto:juststraycreations@gmail.com?subject=${subject}&body=${body}`;
  };

  return (
    <button
      type="button"
      onClick={openReport}
      data-testid="report-bug-btn"
      className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-gray-200 text-zinc-600 hover:text-gray-900 hover:border-gray-300 transition-colors font-mono-data uppercase tracking-wider"
      title="Report a bug — opens your email"
    >
      <Bug size={14} weight="duotone" />
      Report a bug
    </button>
  );
}
