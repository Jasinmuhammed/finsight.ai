"use client";

import { useEffect, useState } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export function ApiStatus() {
  const [status, setStatus] = useState<"checking" | "connected" | "offline">(
    "checking",
  );

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBase}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        setStatus("connected");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setStatus("offline");
      });
    return () => controller.abort();
  }, []);

  const label = {
    checking: "Checking API",
    connected: "API connected",
    offline: "API offline",
  }[status];

  return (
    <div className={`api-badge ${status}`} role="status">
      <span />
      {label}
    </div>
  );
}
