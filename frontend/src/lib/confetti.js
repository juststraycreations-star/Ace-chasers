import confetti from "canvas-confetti";

/**
 * fireChampionConfetti — 2.5s cinematic burst layered above every UI
 * surface. Used when the final match of a Match-Play bracket resolves.
 * Uses the Ace Chasers gold/emerald palette so the celebration feels
 * on-brand rather than generic.
 *
 * Never throws — confetti is decorative and must not break real flows.
 */
export function fireChampionConfetti() {
  try {
    const end = Date.now() + 2200;
    const colors = ["#F5C542", "#0f2e1c", "#1f4d2e", "#fdf8ec"];
    // Centre pop for the immediate hit.
    confetti({
      particleCount: 140,
      spread: 90,
      startVelocity: 55,
      origin: { x: 0.5, y: 0.5 },
      colors,
      zIndex: 1000,
    });
    // Side cannons rain down over the next couple of seconds.
    const frame = () => {
      confetti({
        particleCount: 6,
        angle: 60,
        spread: 55,
        startVelocity: 45,
        origin: { x: 0, y: 1 },
        colors,
        zIndex: 1000,
      });
      confetti({
        particleCount: 6,
        angle: 120,
        spread: 55,
        startVelocity: 45,
        origin: { x: 1, y: 1 },
        colors,
        zIndex: 1000,
      });
      if (Date.now() < end) requestAnimationFrame(frame);
    };
    frame();
  } catch { /* silent */ }
}
