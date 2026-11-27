"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { authErrorPath, isAuthServiceUnavailable } from "@/lib/auth-errors";
import { getSomniaApiUrl } from "@/lib/env";
import { getSupabaseConfig } from "@/lib/supabase/config";
import { createSupabaseClient } from "@/lib/supabase/server";

async function getCallbackUrl() {
  // Next verifies a Server Action's Origin against its Host (or X-Forwarded-Host).
  // Require Origin as well, and never take the callback host from form fields or query params.
  const origin = (await headers()).get("origin");
  if (!origin) return null;

  try {
    const base = new URL(origin);
    const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(base.hostname);
    if (base.origin !== origin || !(base.protocol === "https:" || (base.protocol === "http:" && loopback))) {
      return null;
    }
    return new URL("/auth/callback", base).href;
  } catch {
    return null;
  }
}

export async function signInWithGitHub() {
  if (!getSupabaseConfig() || !getSomniaApiUrl()) redirect(authErrorPath("configuration"));
  const callbackUrl = await getCallbackUrl();
  let url: string | null = null;
  let failure = authErrorPath("sign-in");
  if (callbackUrl) {
    try {
      const supabase = await createSupabaseClient({ writable: true });
      if (supabase) {
        // createServerClient uses PKCE and writes the verifier before this action redirects.
        const { data, error } = await supabase.auth.signInWithOAuth({
          provider: "github",
          options: { redirectTo: callbackUrl, skipBrowserRedirect: true },
        });
        if (!error) url = data.url;
        else if (isAuthServiceUnavailable(error)) failure = authErrorPath("unavailable");
      }
    } catch {
      // Router errors must not include OAuth details or credentials.
      failure = authErrorPath("unavailable");
    }
  }
  redirect(url ?? failure);
}

export async function signOut() {
  let signedOut = false;
  try {
    const supabase = await createSupabaseClient({ writable: true });
    if (supabase) {
      const { error } = await supabase.auth.signOut({ scope: "local" });
      signedOut = !error;
    }
  } catch {
    // Do not report success if Supabase did not clear the session.
  }
  redirect(signedOut ? "/login" : authErrorPath("sign-out"));
}
