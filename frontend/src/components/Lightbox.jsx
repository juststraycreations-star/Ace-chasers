import { useEffect } from "react";
import AuthImage from "./AuthImage";
import { X } from "@phosphor-icons/react";

export default function Lightbox({ path, caption, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!path) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="lightbox"
    >
      <button
        data-testid="lightbox-close-btn"
        onClick={onClose}
        className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white"
        aria-label="Close"
      >
        <X size={20} weight="bold" />
      </button>
      <div className="max-w-[90vw] max-h-[85vh] flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
        <AuthImage path={path} className="max-w-[90vw] max-h-[80vh] object-contain rounded-lg" alt={caption || ""} />
        {caption && <div className="mt-4 text-sm text-zinc-300 font-medium">{caption}</div>}
      </div>
    </div>
  );
}
