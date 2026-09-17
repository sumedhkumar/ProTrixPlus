"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Identity, StrategyView } from "@/lib/api";

import { ExecutionEngineStatus, type EngineStats } from "./ExecutionEngineStatus";
import { SimulateSignalModal } from "./SimulateSignalModal";

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
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);

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
        <span className="pill" title="Demo indicator - no real AI/market-data integration exists yet">
          <span className="dot green" />
          AI Copilot: Online <span className="badge-pill badge-demo">DEMO</span>
        </span>

        <div style={{ flex: 1 }} />

        <button className="btn-primary" onClick={() => setModalOpen(true)}>
          ▲ Simulate TV Signal
        </button>

        <div className="identity-chip">
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
            ▾
          </span>
        </div>
        <a href="/logout" style={{ fontSize: 12 }}>
          Sign out
        </a>
        </div>
      </header>

      {modalOpen ? <SimulateSignalModal strategies={strategies} onClose={closeModal} /> : null}
    </>
  );
}
