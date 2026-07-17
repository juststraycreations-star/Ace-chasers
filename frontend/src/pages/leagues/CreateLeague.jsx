import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { CaretLeft, CaretRight, Check, MapPin, Calendar, Coins } from "@phosphor-icons/react";
import LedgerDisclaimer from "@/components/LedgerDisclaimer";

const FORMATS = [
  { key: "Singles", desc: "Every player plays their own card." },
  { key: "Random-Draw Doubles", desc: "Random pairs at check-in." },
  { key: "BYOP", desc: "Bring Your Own Partner doubles." },
  { key: "Team", desc: "Structured team play." },
];

export default function CreateLeague() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    name: "",
    location: "",
    format: "Singles",
    description: "",
    win_points: 10,
    points_step: 2,
    weeks: 8,
    start_date: new Date().toISOString().slice(0, 10),
    course_rating: 54,
    entry_fee: 10,
    divisions: "Open, MPO, FPO",
  });
  const [creating, setCreating] = useState(false);

  const canNext = () => {
    if (step === 1) return form.name.trim().length > 1 && form.location.trim().length > 1;
    return true;
  };

  const submit = async () => {
    setCreating(true);
    try {
      const { data } = await api.post("/leagues", {
        name: form.name,
        location: form.location,
        format: form.format,
        description: form.description,
        win_points: Number(form.win_points),
        points_step: Number(form.points_step),
        entry_fee: Number(form.entry_fee || 0),
        divisions: form.divisions.split(",").map((d) => d.trim()).filter(Boolean),
        schedule: {
          weeks: Number(form.weeks),
          start_date: new Date(form.start_date).toISOString(),
          course_rating: Number(form.course_rating),
        },
      });
      toast.success("League created");
      navigate(`/leagues/${data.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create league");
    } finally { setCreating(false); }
  };

  const steps = ["Identity", "Format", "Season", "Payouts"];

  return (
    <div className="min-h-screen bg-white">
      <AppHeader />
      <main className="max-w-3xl mx-auto px-6 py-10" data-testid="create-league-page">
        <div className="mb-8">
          <div className="font-mono-data text-xs text-zinc-500 mb-2">CREATE LEAGUE · STEP {step} / 4</div>
          <h1 className="font-display text-4xl tracking-tighter">Set Up Your League</h1>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-2 mb-10">
          {steps.map((label, i) => {
            const s = i + 1;
            const active = s === step;
            const done = s < step;
            return (
              <div key={label} className="flex-1 flex items-center gap-2">
                <div className={`h-1.5 rounded-full flex-1 ${done ? "bg-[#F5C542]" : active ? "bg-[#F5C542]/60" : "bg-white/8"}`}></div>
                <div className={`font-mono-data text-[10px] ${active ? "text-[#F5C542]" : done ? "text-gray-900" : "text-zinc-600"}`}>{label}</div>
              </div>
            );
          })}
        </div>

        <div className="card-surface p-8">
          {step === 1 && (
            <div className="space-y-6" data-testid="wizard-step-identity">
              <div>
                <Label className="font-mono-data text-xs text-zinc-400">LEAGUE NAME</Label>
                <Input
                  data-testid="wizard-league-name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Thursday Night Ace Chasers"
                  className="mt-2 h-12 bg-white border border-gray-200 border-gray-200 text-lg font-display"
                />
              </div>
              <div>
                <Label className="font-mono-data text-xs text-zinc-400">HOME COURSE / LOCATION</Label>
                <div className="relative mt-2">
                  <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
                  <Input
                    data-testid="wizard-league-location"
                    value={form.location}
                    onChange={(e) => setForm({ ...form, location: e.target.value })}
                    placeholder="Blue Ribbon Pines DGC, MN"
                    className="h-12 pl-9 bg-white border border-gray-200 border-gray-200"
                  />
                </div>
              </div>
              <div>
                <Label className="font-mono-data text-xs text-zinc-400">DESCRIPTION (OPTIONAL)</Label>
                <Textarea
                  data-testid="wizard-league-description"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Weekly casual league. All skill levels welcome."
                  className="mt-2 bg-white border border-gray-200 border-gray-200 min-h-[100px]"
                />
              </div>
            </div>
          )}

          {step === 2 && (
            <div data-testid="wizard-step-format">
              <Label className="font-mono-data text-xs text-zinc-400 mb-4 block">CHOOSE FORMAT</Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {FORMATS.map((f) => (
                  <button
                    key={f.key}
                    data-testid={`wizard-format-${f.key.replace(/[^a-z]/gi, '').toLowerCase()}`}
                    onClick={() => setForm({ ...form, format: f.key })}
                    className={`p-5 rounded-lg text-left border transition-all ${form.format === f.key ? "border-[#F5C542] bg-[#F5C542]/10" : "border-gray-200 hover:border-white/25 bg-white border border-gray-200"}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="font-display text-lg">{f.key}</div>
                      {form.format === f.key && <Check size={20} weight="bold" className="text-[#F5C542]" />}
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">{f.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6" data-testid="wizard-step-season">
              <div className="flex items-center gap-2 text-zinc-400">
                <Calendar size={18} weight="duotone" />
                <div className="font-mono-data text-xs">RECURRING SEASON SCHEDULE</div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs text-zinc-500">Start Date</Label>
                  <Input
                    data-testid="wizard-start-date"
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    className="mt-2 h-12 bg-white border border-gray-200 border-gray-200"
                  />
                </div>
                <div>
                  <Label className="text-xs text-zinc-500">Weekly Rounds</Label>
                  <Input
                    data-testid="wizard-weeks"
                    type="number"
                    min={1}
                    max={52}
                    value={form.weeks}
                    onChange={(e) => setForm({ ...form, weeks: e.target.value })}
                    className="mt-2 h-12 bg-white border border-gray-200 border-gray-200"
                  />
                </div>
              </div>
              <div>
                <Label className="text-xs text-zinc-500 flex items-center gap-1">
                  Course Rating (SSA)
                  <span className="text-zinc-600 text-[10px]">— Scratch Scoring Average, drives PDGA-style ratings</span>
                </Label>
                <Input
                  data-testid="wizard-course-rating"
                  type="number"
                  step="0.1"
                  min={30}
                  max={90}
                  value={form.course_rating}
                  onChange={(e) => setForm({ ...form, course_rating: e.target.value })}
                  className="mt-2 h-12 bg-white border border-gray-200 border-gray-200 font-mono-data max-w-[220px]"
                />
              </div>
              <div className="terminal">
                <div className="ts">// GENERATED SCHEDULE (WEEKLY)</div>
                {Array.from({ length: Math.min(Number(form.weeks) || 0, 6) }).map((_, i) => {
                  const d = new Date(form.start_date);
                  d.setDate(d.getDate() + i * 7);
                  return (
                    <div key={i}><span className="ts">[{d.toISOString().slice(0,10)}]</span> Week {i + 1} → <span className="val">Round Scheduled</span></div>
                  );
                })}
                {Number(form.weeks) > 6 && <div className="ts">...+ {Number(form.weeks) - 6} more rounds</div>}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6" data-testid="wizard-step-payouts">
              <LedgerDisclaimer testid="wizard-ledger-disclaimer" />
              <div className="flex items-center gap-2 text-zinc-400">
                <Coins size={18} weight="duotone" />
                <div className="font-mono-data text-xs">WIN ALLOCATION FORMULA</div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs text-zinc-500">Winner Points</Label>
                  <Input
                    data-testid="wizard-win-points"
                    type="number"
                    min={1}
                    value={form.win_points}
                    onChange={(e) => setForm({ ...form, win_points: e.target.value })}
                    className="mt-2 h-12 bg-white border border-gray-200 border-gray-200 font-mono-data"
                  />
                </div>
                <div>
                  <Label className="text-xs text-zinc-500">Points Step / Place</Label>
                  <Input
                    data-testid="wizard-points-step"
                    type="number"
                    min={0}
                    value={form.points_step}
                    onChange={(e) => setForm({ ...form, points_step: e.target.value })}
                    className="mt-2 h-12 bg-white border border-gray-200 border-gray-200 font-mono-data"
                  />
                </div>
              </div>
              <div className="terminal">
                <div className="ts">// PREVIEW · POINTS ALLOCATION</div>
                {[1,2,3,4,5].map((place) => (
                  <div key={place}>
                    <span className="ts">[PLACE {place}]</span> → <span className="val">
                      {Math.max(Number(form.win_points) - (place - 1) * Number(form.points_step), 1)} pts
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-4 pt-4 border-t border-gray-100 space-y-4">
                <div className="flex items-center gap-2 text-zinc-400">
                  <Coins size={18} weight="duotone" />
                  <div className="font-mono-data text-xs">ENTRY FEE ESCROW · AUTO-SPLIT 70 / 20 / 10</div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs text-zinc-500">Entry Fee ($)</Label>
                    <Input
                      data-testid="wizard-entry-fee"
                      type="number"
                      min={0}
                      step="0.5"
                      value={form.entry_fee}
                      onChange={(e) => setForm({ ...form, entry_fee: e.target.value })}
                      className="mt-2 h-12 bg-white border border-gray-200 border-gray-200 font-mono-data max-w-[220px]"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-zinc-500">Divisions (comma-separated)</Label>
                    <Input
                      data-testid="wizard-divisions"
                      value={form.divisions}
                      onChange={(e) => setForm({ ...form, divisions: e.target.value })}
                      placeholder="Open, MPO, FPO"
                      className="mt-2 h-12 bg-white border border-gray-200 border-gray-200"
                    />
                  </div>
                </div>
                {Number(form.entry_fee) > 0 && (
                  <div className="terminal">
                    <div className="ts">// PER-PLAYER SPLIT · ${Number(form.entry_fee).toFixed(2)}</div>
                    <div><span className="ts">[WEEKLY PAYOUT]</span> → <span className="val">${(Number(form.entry_fee) * 0.7).toFixed(2)} (70%)</span></div>
                    <div><span className="ts">[ROLLING ACE POOL]</span> → <span className="val">${(Number(form.entry_fee) * 0.2).toFixed(2)} (20%)</span></div>
                    <div><span className="ts">[CLUB FUND]</span> → <span className="val">${(Number(form.entry_fee) * 0.1).toFixed(2)} (10%)</span></div>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between mt-10 pt-6 border-t border-gray-100">
            <button
              data-testid="wizard-back-btn"
              disabled={step === 1}
              onClick={() => setStep(step - 1)}
              className="flex items-center gap-2 text-sm text-zinc-400 hover:text-gray-900 disabled:opacity-30"
            >
              <CaretLeft size={16} /> Back
            </button>
            {step < 4 ? (
              <button
                data-testid="wizard-next-btn"
                disabled={!canNext()}
                onClick={() => setStep(step + 1)}
                className="btn-primary flex items-center gap-2 disabled:opacity-40"
              >
                Continue <CaretRight size={16} weight="bold" />
              </button>
            ) : (
              <button
                data-testid="wizard-submit-btn"
                disabled={creating}
                onClick={submit}
                className="btn-primary flex items-center gap-2 disabled:opacity-50"
              >
                {creating ? "Creating…" : "Create League"} <Check size={16} weight="bold" />
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
