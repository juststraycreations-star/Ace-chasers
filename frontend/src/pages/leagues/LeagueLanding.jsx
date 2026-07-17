import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { Trophy, Target, Lightning, ChatCircle, MapPin } from "@phosphor-icons/react";

const HERO_IMG = "https://images.unsplash.com/photo-1725724767938-26e57f67a12c";

export default function Landing() {
  const { user, login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (user) navigate("/leagues", { replace: true });
  }, [user, navigate]);

  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Hero background */}
      <div className="absolute inset-0 -z-10">
        <img src={HERO_IMG} alt="" className="w-full h-full object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/70 via-black/80 to-[#1f4d2e]" />
      </div>

      <div className="max-w-7xl mx-auto px-6 pt-8 pb-24">
        {/* Nav */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#F5C542] flex items-center justify-center shadow-[0_0_32px_-4px_rgba(245,197,66,0.7)]">
              <Trophy size={22} weight="fill" color="#0a0a0a" />
            </div>
            <div>
              <div className="font-display text-xl tracking-tight">Ace Chasers</div>
              <div className="font-mono-data text-[10px] text-zinc-500 mt-1">LEAGUE OPS · v1</div>
            </div>
          </div>
          <button
            data-testid="landing-signin-btn"
            onClick={login}
            className="btn-primary text-sm"
          >
            Sign In with Google
          </button>
        </div>

        {/* Hero */}
        <div className="mt-24 sm:mt-32 max-w-4xl">
          <div className="chip-orange inline-flex px-3 py-1 rounded-full text-xs font-mono-data mb-6">
            NEW · REAL-TIME SCORECARDS
          </div>
          <h1 className="font-display text-5xl sm:text-6xl lg:text-7xl tracking-tighter leading-[0.95]">
            Run your <span className="text-[#F5C542]">disc golf league</span><br />
            like a pro tour.
          </h1>
          <p className="mt-8 text-lg text-zinc-400 max-w-2xl font-medium">
            Live scorecards, rolling bag tags, automated handicaps, a private clubhouse feed,
            and a debit/credit ledger — all wired into one dashboard for league directors and players.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <button
              data-testid="landing-get-started-btn"
              onClick={login}
              className="btn-primary text-base px-8 py-3"
            >
              Get Started — It's Free
            </button>
            <a
              href="#features"
              data-testid="landing-features-link"
              className="px-6 py-3 rounded-full border border-white/15 text-sm hover:bg-white/5 transition-colors"
            >
              Explore Features
            </a>
          </div>
        </div>

        {/* Feature grid */}
        <div id="features" className="mt-32 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { icon: <MapPin size={22} weight="duotone" />, title: "League Ops", desc: "Multi-step wizard. Schedule generator. Debit/credit ledger for Ace Pool, CTP cash & payouts." },
            { icon: <Target size={22} weight="duotone" />, title: "Digital Scorecard", desc: "Live multiplayer. Proof-of-score audit log. QR check-in. In-card emoji chat." },
            { icon: <Lightning size={22} weight="duotone" />, title: "Handicap Engine", desc: "Rolling average across last 5 rounds. Auto-swap bag tags. Points formulas you customize." },
            { icon: <ChatCircle size={22} weight="duotone" />, title: "Private Clubhouse", desc: "Pinned announcements, story grid, lost & found, and auto-generated Hot Round recaps." },
          ].map((f, i) => (
            <div key={i} className="card-surface p-6" data-testid={`landing-feature-${i}`}>
              <div className="w-10 h-10 rounded-lg bg-[#F5C542]/12 border border-[#F5C542]/30 flex items-center justify-center text-[#F5C542] mb-4">
                {f.icon}
              </div>
              <div className="font-display text-lg mb-2">{f.title}</div>
              <div className="text-sm text-zinc-400 leading-relaxed">{f.desc}</div>
            </div>
          ))}
        </div>

        <div className="mt-16 font-mono-data text-[10px] text-zinc-600 tracking-widest">
          BUILT FOR CLUB DIRECTORS · READY OUT OF THE BOX
        </div>
      </div>
    </div>
  );
}
