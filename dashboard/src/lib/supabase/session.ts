import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { authErrorPath, isAuthServiceUnavailable } from "@/lib/auth-errors";
import { getSomniaApiUrl } from "@/lib/env";
import { createSupabaseClient } from "./server";

async function getVerifiedSession() {
  try {
    const supabase = await createSupabaseClient();
    if (!supabase || !getSomniaApiUrl()) return { location: authErrorPath("configuration") };

    // Read only the token from cookie-backed storage, never the unverified session user.
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();
    if (isAuthServiceUnavailable(sessionError)) return { location: authErrorPath("unavailable") };
    const token = session?.access_token;
    if (sessionError || !token) return { location: "/login" };

    // Verify the exact Supabase access token that will be forwarded to the API.
    const { data: { user }, error } = await supabase.auth.getUser(token);
    if (isAuthServiceUnavailable(error)) return { location: authErrorPath("unavailable") };
    if (error || !user || user.is_anonymous) return { location: "/login" };
    return { session: { user, token } };
  } catch {
    return { location: authErrorPath("unavailable") };
  }
}

// Dedupe the layout and data checks during one server render, never across requests.
export const requireSession = cache(async () => {
  const { session, location } = await getVerifiedSession();
  if (!session) redirect(location);
  return session;
});
