import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { signInWithGitHub, signOut } from "@/lib/auth-actions";
import { getSomniaApiUrl } from "@/lib/env";
import { getSupabaseConfig } from "@/lib/supabase/config";

const errors: Record<string, string> = {
  "sign-in": "Could not start GitHub sign-in. Try again.",
  callback: "GitHub sign-in did not complete. Start sign-in again from this page.",
  "sign-out": "Could not sign out. Try again before leaving this browser unattended.",
  "api-session": "The Somnia API did not accept your session. Sign out and back in. If this continues, contact the dashboard administrator.",
  forbidden: "Your GitHub account does not have access to the Somnia API. Contact the dashboard administrator or sign in with another account.",
};

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string | string[] }> }) {
  const { error } = await searchParams;
  const configured = Boolean(getSupabaseConfig() && getSomniaApiUrl());
  const message = !configured
    ? "The dashboard is not configured. Contact the dashboard administrator."
    : typeof error === "string" && Object.hasOwn(errors, error) ? errors[error] : null;
  const showSignOut = error === "sign-out" || error === "api-session" || error === "forbidden";

  return (
    <main className="grid min-h-svh place-items-center px-6 py-8">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Somnia dashboard</CardTitle>
          <CardDescription>Sign in with GitHub to continue.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {message && <p role="alert" className="text-sm text-destructive">{message}</p>}
          <form action={signInWithGitHub}>
            <Button className="w-full" disabled={!configured} type="submit">Continue with GitHub</Button>
          </form>
          {showSignOut && (
            <form action={signOut}>
              <Button className="w-full" type="submit" variant="outline">Sign out</Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
