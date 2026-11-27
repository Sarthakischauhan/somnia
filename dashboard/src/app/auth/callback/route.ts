import { type NextRequest, NextResponse } from "next/server";

import { authErrorPath, isAuthServiceUnavailable } from "@/lib/auth-errors";
import { createSupabaseClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const [code, ...extraCodes] = params.getAll("code");
  const cancelled = params.get("error") === "access_denied" || params.get("error_code") === "access_denied";
  let location = authErrorPath(cancelled ? "cancelled" : "callback");

  if (code && extraCodes.length === 0 && !params.has("error") && !params.has("error_code") && !params.has("error_description")) {
    try {
      const supabase = await createSupabaseClient({ writable: true });
      if (supabase) {
        const { data, error } = await supabase.auth.exchangeCodeForSession(code);
        if (!error && data.session) location = "/memories";
        else if (isAuthServiceUnavailable(error)) location = authErrorPath("unavailable");
      } else {
        location = authErrorPath("configuration");
      }
    } catch {
      // Do not expose the code or provider response in an error page or redirect.
      location = authErrorPath("unavailable");
    }
  }

  // Fixed local paths: never redirect to a query parameter or forwarded host.
  return new NextResponse(null, {
    status: 303,
    headers: { Location: location, "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" },
  });
}
