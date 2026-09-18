import { AdminPaymentSubmissions } from "@/components/AdminPaymentSubmissions";
import { apiFetch, type PaymentSubmissionView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default async function AdminPaymentsPage() {
  const token = getToken()!;
  const submissions = await apiFetch<PaymentSubmissionView[]>(
    "/api/v1/admin/payment-submissions",
    token,
  ).catch(() => []);

  return <AdminPaymentSubmissions submissions={submissions} />;
}
