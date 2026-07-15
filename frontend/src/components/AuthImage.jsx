import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";

// Fetches an authenticated image as a blob and displays it.
export default function AuthImage({ path, alt = "", className = "", onClick }) {
  const [src, setSrc] = useState(null);
  const urlRef = useRef(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      if (!path) return;
      try {
        const res = await api.get(`/files/${path}`, { responseType: "blob" });
        if (!alive) return;
        const url = URL.createObjectURL(res.data);
        urlRef.current = url;
        setSrc(url);
      } catch (e) {
        // ignore
      }
    };
    load();
    return () => {
      alive = false;
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [path]);

  if (!src) {
    return <div className={`bg-zinc-900 animate-pulse ${className}`} />;
  }
  return <img src={src} alt={alt} className={className} onClick={onClick} />;
}
