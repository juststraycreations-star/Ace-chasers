import { motion, AnimatePresence } from "framer-motion";
import { Medal } from "@phosphor-icons/react";

export default function BagTagMatrix({ members }) {
  const sorted = [...members].sort((a, b) => a.bag_tag - b.bag_tag);
  return (
    <div className="card-surface p-6 sm:p-8" data-testid="bagtag-matrix">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="font-mono-data text-xs text-zinc-500 mb-1">ROLLING BAG TAGS</div>
          <h3 className="font-display text-2xl">The Matrix</h3>
        </div>
        <div className="chip-orange px-3 py-1 rounded-full text-[10px] font-mono-data">LIVE</div>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-4">
        <AnimatePresence>
          {sorted.map((m, i) => (
            <motion.div
              key={m.id}
              layout
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.35, delay: i * 0.03 }}
              className="flex flex-col items-center gap-2"
              data-testid={`bagtag-${m.bag_tag}`}
            >
              <div className={`bag-tag ${m.bag_tag === 1 ? "tag-elite" : ""}`}>
                {m.bag_tag === 1 && (
                  <Medal size={12} weight="fill" className="absolute top-2 right-2 text-black/70" />
                )}
                {m.bag_tag}
              </div>
              <div className="text-xs text-zinc-300 truncate max-w-[80px] text-center font-medium">{m.name}</div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
      {members.length === 0 && (
        <div className="text-zinc-500 text-sm">No members yet.</div>
      )}
    </div>
  );
}
