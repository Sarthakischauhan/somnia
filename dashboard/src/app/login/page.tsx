import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AuthCard } from "@/components/auth-card";
import { AuthSubmit } from "@/components/auth-submit";
import { signInWithGitHub } from "@/lib/auth-actions";
import { authErrorPath } from "@/lib/auth-errors";
import { getSomniaApiUrl } from "@/lib/env";
import { getSupabaseConfig } from "@/lib/supabase/config";

export const metadata: Metadata = { title: "Sign in | Somnia", robots: { index: false } };
export const dynamic = "force-dynamic";

export default function LoginPage() {
  if (!getSupabaseConfig() || !getSomniaApiUrl()) redirect(authErrorPath("configuration"));

  return (
    <AuthCard title="Sign in to Somnia" description="Use your GitHub account to open your memory dashboard.">
      <form action={signInWithGitHub}>
        <AuthSubmit pendingLabel="Connecting to GitHub…">Continue with GitHub</AuthSubmit>
      </form>
      <p className="text-sm text-muted-foreground">
        Connecting a coding agent instead? <Link className="text-foreground underline underline-offset-4" href="/#setup">See agent setup</Link>.
      </p>
    </AuthCard>
  );
}
