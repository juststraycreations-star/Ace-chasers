import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { CheckCircle, DeviceMobile, Trophy, Users, Envelope } from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const OPT_IN_URL =
  process.env.REACT_APP_PLAY_TESTER_URL ||
  "https://play.google.com/apps/testing/acechasers.net";
const GOOGLE_GROUP_URL =
  process.env.REACT_APP_GOOGLE_GROUP_URL ||
  "https://groups.google.com/g/ace-chasers-beta-testers";

export default function Beta() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", phone: "", referral_source: "" });
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(null); // { email, alreadySignedUp, emailSent }

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim()) {
      toast.error("Please give your name and email");
      return;
    }
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/beta-testers/signup`, form);
      setSuccess({
        email: form.email,
        alreadySignedUp: !!data.already_signed_up,
        emailSent: !!data.email_sent,
      });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Signup failed. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-white flex flex-col items-center justify-center p-6" data-testid="beta-success">
        <div className="max-w-lg w-full bg-white border border-gray-200 rounded-2xl shadow-xl p-8">
          <CheckCircle size={48} weight="fill" className="text-[#1f4d2e] mb-3" />
          <h1 className="font-display text-3xl tracking-tight mb-2">
            {success.alreadySignedUp ? "You're already on the list" : "You're in"}
          </h1>
          <p className="text-gray-700 mb-5">
            {success.emailSent
              ? `We just emailed the install instructions to ${success.email}. You can also follow the two steps below right now.`
              : "Follow the two steps below to install the beta on your Android phone."}
          </p>

          <div className="mb-4 p-4 rounded-xl bg-amber-50 border border-amber-200">
            <div className="text-[10px] font-mono-data uppercase tracking-wider text-amber-800 mb-2">
              Step 1 · Join the Google Group
            </div>
            <p className="text-sm text-gray-800 mb-3">
              It's open — no approval needed. Just tap <b>Join group</b> using the same Google account signed into your Android phone.
            </p>
            <a
              href={GOOGLE_GROUP_URL}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="beta-google-group-link"
              className="inline-flex items-center justify-center gap-2 bg-[#1f4d2e] hover:bg-[#1a3f26] text-white font-bold text-sm px-4 py-2 rounded-lg transition-colors"
            >
              <Users size={16} weight="fill" /> Join the Google Group
            </a>
          </div>

          <div className="mb-2 text-[10px] font-mono-data uppercase tracking-wider text-zinc-500">
            Step 2 · Install from Google Play
          </div>
          <a
            href={OPT_IN_URL}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="beta-play-opt-in-link"
            className="w-full inline-flex items-center justify-center gap-2 bg-[#F5C542] hover:bg-[#f5cf5a] text-black font-bold px-4 py-3 rounded-lg transition-colors"
          >
            <DeviceMobile size={18} weight="fill" /> Open on my Android phone
          </a>
          <ol className="mt-4 text-sm text-gray-700 space-y-1 list-decimal list-inside">
            <li>Join the group above (step 1) using your Android Google account.</li>
            <li>Tap the yellow button (step 2) on your Android device.</li>
            <li>Tap <b>Become a tester</b>, then <b>Download it on Google Play</b>.</li>
          </ol>
          <p className="mt-3 text-[11px] text-red-700 bg-red-50 rounded-md p-2">
            If Google says "app not available in your country," you likely opened the install link before joining the group. Join the group first, then reopen the yellow button.
          </p>

          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              onClick={() => { setSuccess(null); setForm({ name: "", email: "", phone: "", referral_source: "" }); }}
              className="text-xs text-zinc-500 hover:text-gray-900 font-mono-data tracking-wider uppercase"
              data-testid="beta-signup-another-btn"
            >
              Sign up another tester
            </button>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="text-xs text-zinc-500 hover:text-gray-900 font-mono-data tracking-wider uppercase"
              data-testid="beta-back-home-btn"
            >
              Back to Ace Chasers →
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white" data-testid="beta-page">
      <div className="max-w-3xl mx-auto px-6 py-14">
        <Link
          to="/"
          className="font-mono-data text-xs text-zinc-500 hover:text-gray-900"
          data-testid="beta-back-link"
        >
          ← ACE CHASERS
        </Link>

        <div className="mt-8">
          <div className="font-mono-data text-xs tracking-wider text-[#F5C542]">CLOSED BETA · ANDROID</div>
          <h1 className="font-display text-4xl sm:text-6xl tracking-tighter mt-3">
            Try Ace Chasers on your phone.
          </h1>
          <p className="text-base text-gray-700 mt-4 max-w-xl">
            You're minutes away from the disc golf social + league app already used by dozens of players. Drop your name and email — we'll send you the two-step install (join our open Google Group, then install from Google Play).
          </p>
        </div>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-3">
          <FeatureBadge icon={<Users size={16} weight="duotone" />} title="Find players" body="Discover local disc golfers by distance." />
          <FeatureBadge icon={<Trophy size={16} weight="duotone" />} title="Run leagues" body="Scorecards, standings, bag tags, all live." />
          <FeatureBadge icon={<Envelope size={16} weight="duotone" />} title="Direct install" body="One click after email — no sideload." />
        </div>

        <form onSubmit={submit} className="mt-10 space-y-4 bg-gray-50 border border-gray-200 rounded-2xl p-6" data-testid="beta-signup-form">
          <div>
            <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Your name</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Alex Riley"
              required
              data-testid="beta-name-input"
              className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Google email <span className="text-red-500">*</span></label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="you@gmail.com"
              required
              data-testid="beta-email-input"
              className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
            />
            <p className="mt-1 text-[11px] text-zinc-500">
              Must be the Google account signed into your Android phone (Google requires this for closed testing).
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">Phone (optional)</label>
              <input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+1 704 555 0100"
                data-testid="beta-phone-input"
                className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 font-mono-data uppercase tracking-wider mb-1">How'd you hear about us?</label>
              <input
                value={form.referral_source}
                onChange={(e) => setForm({ ...form, referral_source: e.target.value })}
                placeholder="Facebook, a friend, etc."
                data-testid="beta-referral-input"
                className="w-full h-11 bg-white border border-gray-200 rounded-md px-3 text-sm"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={busy}
            data-testid="beta-submit-btn"
            className="w-full h-12 bg-[#F5C542] hover:bg-[#f5cf5a] text-black font-bold rounded-lg transition-colors disabled:opacity-50"
          >
            {busy ? "Adding you to the beta…" : "Get the beta install link"}
          </button>
          <p className="text-[11px] text-zinc-500 leading-relaxed">
            By joining, you agree to receive the install email + occasional beta-only updates. We never sell email addresses. See our{" "}
            <Link to="/legal/privacy" className="underline">Privacy & Terms</Link>.
          </p>
        </form>
      </div>
    </div>
  );
}

function FeatureBadge({ icon, title, body }) {
  return (
    <div className="rounded-xl border border-gray-200 p-3 bg-white">
      <div className="text-[#1f4d2e] mb-1">{icon}</div>
      <div className="font-bold text-sm">{title}</div>
      <div className="text-xs text-gray-600">{body}</div>
    </div>
  );
}
