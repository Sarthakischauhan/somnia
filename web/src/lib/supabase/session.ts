import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { createSupabaseClient } from "./server";

async function getVerifiedSession() {
  try {
    const supabase = await createSupabaseClient();
    if (!supabase) return null;

    // Read only the token from cookie-backed storage, never the unverified session user.
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (sessionError || !token) return null;

    // Verify the exact Supabase access token that will be forwarded to the API.
    const { data: { user }, error } = await supabase.auth.getUser(token);
    return !error && user && !user.is_anonymous ? { user, token } : null;
  } catch {
    return null;
  }
}

// Dedupe the layout and data checks during one server render, never across requests.
export const requireSession = cache(async () => {
  const session = await getVerifiedSession();
  if (!session) redirect("/login");
  return session;
});
