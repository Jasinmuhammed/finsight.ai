"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const navigation = [
  { label: "Dashboard", href: "/", icon: "▦", available: true },
  { label: "Stock screener", href: "/screener", icon: "⌕", available: true },
  { label: "Stock analysis", href: "/analysis", icon: "⌁", available: true },
  { label: "Chart analysis", href: "/charts", icon: "◫", available: true },
  { label: "Backtesting", href: "/backtesting", icon: "↗", available: true },
  { label: "Portfolio & risk", href: "/portfolio", icon: "◉", available: true },
  { label: "Watchlists & alerts", href: "/watchlists", icon: "☆", available: true },
  { label: "News & intelligence", href: "/news", icon: "▤", available: true },
  { label: "AI assistant", icon: "✳", available: false },
];

type MarketDataStatus = {
  provider: string;
  status: string;
  configured: boolean;
  universe_configured?: boolean;
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const pageLabel =
    navigation.find((item) => item.href === pathname)?.label ??
    (pathname === "/login"
      ? "Sign in"
      : pathname === "/register"
        ? "Create account"
        : "Dashboard");
  const [email, setEmail] = useState<string | null>(null);
  const [accountError, setAccountError] = useState("");
  const [marketDataStatus, setMarketDataStatus] = useState<MarketDataStatus | null>(null);
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBase}/market-data/status`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Market-data status failed (${response.status}).`);
        }
        setMarketDataStatus((await response.json()) as MarketDataStatus);
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== "AbortError") {
          setMarketDataStatus({
            provider: "unavailable",
            status: "UNAVAILABLE",
            configured: false,
          });
        }
      });
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
          <div className={`data-mode ${marketDataStatus?.configured ? "data-mode-historical" : ""}`}>
            <span />
            {marketDataStatus?.configured
              ? `Historical data · ${marketDataStatus.provider}`
              : marketDataStatus
                ? "Historical data unavailable"
                : "Checking data source"}
          </div>
          <div className="profile">
            <div className="avatar">{email?.[0]?.toUpperCase() ?? "F"}</div>
            <div>
              <strong>{email ?? "FinSight workspace"}</strong>
              <small>{email ? "Signed in" : "Sign in for private data"}</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <span className="breadcrumb">Workspace <span>/</span> {pageLabel}</span>
          <div className="topbar-right">
            <span
              className={`market-pill ${marketDataStatus?.configured ? "historical" : ""}`}
              title="Daily historical data is not a live quote."
            >
              <span />
              {!marketDataStatus
                ? "Checking data source"
                : marketDataStatus.configured
                  ? `Historical data · ${marketDataStatus.provider}`
                  : "Market data unavailable"}
            </span>
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
