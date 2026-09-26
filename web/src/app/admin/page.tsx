import { notFound } from "next/navigation";

/**
 * Operator-only admin (web track B5). Until it is built — with Google
 * sign-in and an ADMIN_EMAILS allowlist — it answers 404 to everyone, so
 * the route exists without exposing anything.
 */
export default function AdminPage() {
  notFound();
}
