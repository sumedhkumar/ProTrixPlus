import { IdentityBar } from "@/components/IdentityBar";
import { MarketplaceClient } from "@/components/MarketplaceClient";
import { apiFetch, type Identity, type MarketplaceOffer, type StrategyEnrollmentView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function MarketplacePage() {
  const token = getToken();
  const offers = await apiFetch<MarketplaceOffer[]>("/api/v1/marketplace/strategies", undefined);
  let identity: Identity | null = null;
  let enrollments: StrategyEnrollmentView[] = [];
  if (token) {
    try {
      identity = await apiFetch<Identity>("/api/v1/me", token);
      enrollments = await apiFetch<StrategyEnrollmentView[]>("/api/v1/marketplace/enrollments", token);
    } catch { identity = null; }
  }
  return <><IdentityBar identity={identity} /><main id="main-content" className="container app-content"><MarketplaceClient offers={offers} enrollments={enrollments} signedIn={identity !== null} /></main></>;
}
