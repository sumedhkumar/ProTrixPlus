import { AdminPaymentSubmissions } from "@/components/AdminPaymentSubmissions";
import { apiFetch, type Identity, type PaymentSubmissionView } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { canWrite } from "@/lib/roles";

export default async function AdminPaymentsPage() {
  const token = getToken()!;
  const [submissions, identity] = await Promise.all([
    apiFetch<PaymentSubmissionView[]>("/api/v1/admin/payment-submissions", token).catch(
      () => [],
    ),
    apiFetch<Identity>("/api/v1/me", token),
  ]);

  return (
    <AdminPaymentSubmissions
      submissions={submissions}
      canReview={canWrite(identity.role, "finance", identity.extra_roles)}
    />
  );
}
