import { useEffect, useRef } from "react";
import { DownloadSimple, Trophy, Share } from "@phosphor-icons/react";
import { toast } from "sonner";

/**
 * Automated post-round Victory Card generator.
 * Renders a shareable 1080x1350 canvas with brand overlay + winner info.
 */
export default function VictoryCard({ winnerName, division, finalScore, roundName, leagueName, plusMinus, onClose }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;

    // Background gradient
    const grad = ctx.createLinearGradient(0, 0, W, H);
    grad.addColorStop(0, "#0a0a0b");
    grad.addColorStop(0.5, "#1a1a1e");
    grad.addColorStop(1, "#0a0a0b");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    // Course-green wedge
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(0, H * 0.75);
    ctx.lineTo(W, H * 0.55);
    ctx.lineTo(W, H);
    ctx.lineTo(0, H);
    ctx.closePath();
    ctx.fillStyle = "rgba(22,101,52,0.35)";
    ctx.fill();
    ctx.restore();

    // Hyper-orange diagonal beam
    ctx.save();
    ctx.translate(W * 0.5, H * 0.5);
    ctx.rotate(-Math.PI / 12);
    ctx.fillStyle = "rgba(245,197,66,0.15)";
    ctx.fillRect(-W, -60, W * 3, 120);
    ctx.restore();

    // Grid dots
    ctx.fillStyle = "rgba(255,255,255,0.03)";
    for (let x = 0; x < W; x += 24) {
      for (let y = 0; y < H; y += 24) {
        ctx.fillRect(x, y, 1, 1);
      }
    }

    // Border stroke
    ctx.strokeStyle = "rgba(245,197,66,0.6)";
    ctx.lineWidth = 6;
    ctx.strokeRect(30, 30, W - 60, H - 60);

    // Brand mark
    ctx.fillStyle = "#F5C542";
    ctx.beginPath();
    ctx.roundRect(80, 80, 92, 92, 18);
    ctx.fill();
    ctx.fillStyle = "#0a0a0a";
    ctx.font = "bold 56px 'Anton', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("A", 126, 128);

    ctx.textAlign = "left";
    ctx.font = "800 44px 'Outfit', sans-serif";
    ctx.fillStyle = "#F4F4F5";
    ctx.fillText("ACE CHASERS", 190, 116);
    ctx.font = "600 20px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#A1A1AA";
    ctx.fillText("LEAGUE  ·  VICTORY  CARD", 190, 148);

    // Small label
    ctx.textAlign = "center";
    ctx.font = "600 24px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#FF9E00";
    ctx.letterSpacing = "8px";
    ctx.fillText((roundName || "Round").toUpperCase(), W / 2, 300);

    // League name
    ctx.font = "600 26px 'Manrope', sans-serif";
    ctx.fillStyle = "#a1a1aa";
    ctx.fillText(leagueName || "", W / 2, 340);

    // "WINNER" pill
    ctx.fillStyle = "rgba(245,197,66,0.15)";
    ctx.strokeStyle = "rgba(245,197,66,0.6)";
    ctx.lineWidth = 2;
    const pillW = 260;
    ctx.beginPath();
    ctx.roundRect((W - pillW) / 2, 400, pillW, 54, 27);
    ctx.fill();
    ctx.stroke();
    ctx.font = "700 22px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#FF9E00";
    ctx.textBaseline = "middle";
    ctx.fillText("🏆 CHAMPION", W / 2, 428);

    // Winner Name
    ctx.font = "900 96px 'Outfit', sans-serif";
    ctx.fillStyle = "#F4F4F5";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(winnerName || "Winner", W / 2, 580);

    // Division
    ctx.font = "600 30px 'Manrope', sans-serif";
    ctx.fillStyle = "#71717a";
    ctx.fillText(`${division || "Open"} Division`, W / 2, 630);

    // Score block
    ctx.font = "800 260px 'Anton', sans-serif";
    ctx.fillStyle = "#F5C542";
    ctx.textBaseline = "middle";
    ctx.fillText(String(finalScore ?? ""), W / 2, 900);

    // vs par
    if (plusMinus !== undefined && plusMinus !== null) {
      ctx.font = "700 40px 'JetBrains Mono', monospace";
      ctx.fillStyle = plusMinus < 0 ? "#86efac" : plusMinus > 0 ? "#fecaca" : "#F4F4F5";
      const pm = plusMinus > 0 ? `+${plusMinus}` : `${plusMinus}`;
      ctx.fillText(`${pm} vs course rating`, W / 2, 1050);
    }

    // Footer
    ctx.font = "600 20px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#71717a";
    ctx.fillText("#ACECHASERS  ·  DISC GOLF LEAGUE OPS", W / 2, H - 90);
  }, [winnerName, division, finalScore, roundName, leagueName, plusMinus]);

  const download = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const url = canvas.toDataURL("image/png");
    const a = document.createElement("a");
    a.href = url;
    a.download = `victory-${(winnerName || "champion").replace(/\s+/g, "-").toLowerCase()}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast.success("Victory card downloaded");
  };

  const share = async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const file = new File([blob], "victory.png", { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], title: "Ace Chasers Victory" });
        } catch {}
      } else {
        download();
      }
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose} data-testid="victory-card-modal">
      <div className="max-w-md w-full flex flex-col items-center gap-4" onClick={(e) => e.stopPropagation()}>
        <canvas
          ref={canvasRef}
          width={1080}
          height={1350}
          style={{ width: "min(360px, 90vw)", height: "auto", borderRadius: 16, boxShadow: "0 30px 60px -20px rgba(0,0,0,0.9)" }}
          data-testid="victory-card-canvas"
        />
        <div className="flex gap-2">
          <button data-testid="victory-download-btn" onClick={download} className="btn-primary flex items-center gap-2">
            <DownloadSimple size={16} weight="bold" /> Download PNG
          </button>
          <button data-testid="victory-share-btn" onClick={share} className="px-4 py-2 rounded-full border border-white/15 text-white flex items-center gap-2 hover:bg-white/5">
            <Share size={16} weight="bold" /> Share
          </button>
          <button data-testid="victory-close-btn" onClick={onClose} className="px-4 py-2 rounded-full text-zinc-400 hover:text-white">Close</button>
        </div>
      </div>
    </div>
  );
}
