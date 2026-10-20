"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const navigation = [
  { label: "Dashboard", href: "/", icon: "▦", available: true },
  { label: "Stock screener", href: "/screener", icon: "⌕", available: true },
  { label: "Stock analysis", icon: "⌁", available: false },
  { label: "Charts & patterns", href: "/charts", icon: "◫", available: true },
  { label: "Backtesting", href: "/backtesting", icon: "↗", available: true },
  { label: "Portfolio & risk", href: "/portfolio", icon: "◉", available: true },
  { label: "Watchlists & alerts", href: "/watchlists", icon: "☆", available: true },
  { label: "News & intelligence", href: "/news", icon: "▤", available: true },
  { label: "AI assistant", icon: "✳", available: false },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const pageLabel =
    navigation.find((item) => item.href === pathname)?.label ?? "Dashboard";
  const [email, setEmail] = useState<string | null>(null);
  const [accountError, setAccountError] = useState("");
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBase}/auth/me`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.ok) {
          const user = (await response.json()) as { email: string };
          setEmail(user.email);
        }
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== "AbortError") {
          setEmail(null);
        }
      });
    return () => controller.abort();
  }, [apiBase, pathname]);

  async function signOut() {
    setAccountError("");
    try {
      const response = await fetch(`${apiBase}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`Sign out failed (${response.status}).`);
      }
      setEmail(null);
    } catch (error) {
      setAccountError(
        error instanceof Error ? error.message : "Unable to sign out.",
      );
    }
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="FinSight AI home">
          <span className="brand-mark">F</span>
          <span className="brand-text">FinSight<span>AI</span></span>
        </Link>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="nav-list" aria-label="Main navigation">
          {navigation.map((item) => (
            item.available ? (
              <Link
                className={`nav-item ${pathname === item.href ? "active" : ""}`}
                href={item.href!}
                key={item.label}
                aria-current={pathname === item.href ? "page" : undefined}
              >
                <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            ) : (
              <div
                className="nav-item nav-disabled"
                key={item.label}
                aria-disabled="true"
                title="Not available in this development build"
              >
                <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
                <span className="nav-soon">Soon</span>
              </div>
            )
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="data-mode"><span /> Illustrative demo data</div>
          <div className="profile">
            <div className="avatar">D</div>
            <div><strong>Demo workspace</strong><small>Local preview</small></div>
          </div>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <span className="breadcrumb">Workspace <span>/</span> {pageLabel}</span>
          <div className="topbar-right">
            <span className="market-pill"><span /> Market data: demo</span>
            {email ? (
              <button className="account-button" onClick={() => void signOut()} type="button">
                {email} · Sign out
              </button>
            ) : (
              <Link className="account-button" href="/login">Sign in</Link>
            )}
            {accountError && <span className="account-error" role="alert">{accountError}</span>}
          </div>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
