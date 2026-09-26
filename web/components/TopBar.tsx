"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Identity, StrategyView } from "@/lib/api";

import { ExecutionEngineStatus, type EngineStats } from "./ExecutionEngineStatus";
import { SimulateSignalModal } from "./SimulateSignalModal";
import { SubscriptionCountdownPill } from "./SubscriptionStatus";

const ROLE_LABEL: Record<Identity["role"], string> = {
  USER: "Client Subscriber",
  SUPER_ADMIN: "System Admin",
};

export function TopBar({
  identity,
  strategies,
  engineStats,
}: {
  identity: Identity;
  strategies: StrategyView[];
  engineStats: EngineStats;
}) {
  const subscription = identity.subscription;
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  function closeModal() {
    setModalOpen(false);
    router.refresh();
  }

  const initials = identity.display_name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <>
      <header className="appshell-header">
        <div className="appshell-header-inner">
        <div className="brand">
          <div className="brand-mark">⚡</div>
          <div className="brand-text">
            <h1>
              ProTrixPlus <span className="badge-pill badge-gradient">AI-EVOLVED</span>
            </h1>
            <p>TradingView to MT5 Multi-User AI Router</p>
          </div>
        </div>

        <ExecutionEngineStatus stats={engineStats} onTestIngestion={() => setModalOpen(true)} />
        <SubscriptionCountdownPill subscription={subscription} />

        <div style={{ flex: 1 }} />

        <button className="btn-primary" onClick={() => setModalOpen(true)}>
          ▲ Simulate TV Signal
        </button>

        <div style={{ position: "relative" }}>
          <button
            type="button"
            className="identity-chip"
            style={{ border: "1px solid var(--panel-border)", cursor: "pointer" }}
            onClick={() => setMenuOpen((v) => !v)}
          >
            <div className="avatar">{initials}</div>
            <div className="identity-text">
              <div className="name" data-testid="identity">
                {identity.display_name}
              </div>
              <div className="role" data-testid="identity-role">
                {ROLE_LABEL[identity.role]}
              </div>
            </div>
            <span aria-hidden style={{ color: "var(--dim)", fontSize: 10 }}>
              {menuOpen ? "▴" : "▾"}
            </span>
          </button>

          {menuOpen ? (
            <>
              <div
                style={{ position: "fixed", inset: 0, zIndex: 29 }}
                onClick={() => setMenuOpen(false)}
              />
              <div
                className="card"
                style={{
                  position: "absolute",
                  top: "calc(100% + 8px)",
                  right: 0,
                  zIndex: 30,
                  padding: 8,
                  minWidth: 160,
                }}
              >
                <a
                  href="/logout"
                  style={{
                    display: "block",
                    fontSize: 13,
                    fontWeight: 600,
                    textDecoration: "none",
                    color: "var(--fg)",
                    borderRadius: 6,
                    padding: "8px 10px",
                    whiteSpace: "nowrap",
                  }}
                >
                  ⏻ Sign out
                </a>
              </div>
            </>
          ) : null}
        </div>
        </div>
      </header>

      {modalOpen ? <SimulateSignalModal strategies={strategies} onClose={closeModal} /> : null}
    </>
  );
}
