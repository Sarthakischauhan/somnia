import type { Metadata } from "next";
import Link from "next/link";

import { AuthCard } from "@/components/auth-card";
import { AuthSubmit } from "@/components/auth-submit";
import { buttonVariants } from "@/components/ui/button";
import { signOut } from "@/lib/auth-actions";
import { getAuthError } from "@/lib/auth-errors";

export const metadata: Metadata = { title: "Sign-in help | Somnia", robots: { index: false } };
export const dynamic = "force-dynamic";

export default async function AuthErrorPage({ searchParams }: { searchParams: Promise<{ reason?: string | string[] }> }) {
  const { reason } = await searchParams;
  const { title, description, action } = getAuthError(reason);
  const buttonClass = buttonVariants({ size: "lg", className: "h-11 w-full" });

  return (
    <AuthCard title={title} description={description}>
      {action === "sign-out" ? (
        <form action={signOut}>
          <AuthSubmit pendingLabel="Signing out…">{reason === "sign-out" ? "Try signing out again" : "Sign out"}</AuthSubmit>
        </form>
      ) : action === "dashboard" ? (
        <Link className={buttonClass} href="/memories">Try the dashboard again</Link>
      ) : action === "configuration" ? (
        <a className={buttonClass} href="https://github.com/Sarthakischauhan/somnia/blob/main/dashboard/README.md#configure-github-and-supabase">Read the setup guide</a>
      ) : (
        <Link className={buttonClass} href="/login">Back to sign-in</Link>
      )}
    </AuthCard>
  );
}
