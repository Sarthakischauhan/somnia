import { type NextRequest, NextResponse } from "next/server";

import { createSupabaseClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const [code, ...extraCodes] = params.getAll("code");
  let location = "/login?error=callback";

  if (code && extraCodes.length === 0 && !params.has("error") && !params.has("error_code")) {
    try {
      const supabase = await createSupabaseClient({ writable: true });
      if (supabase) {
        const { data, error } = await supabase.auth.exchangeCodeForSession(code);
        if (!error && data.session) location = "/memories";
      }
    } catch {
      // Do not expose the code or provider response in an error page or redirect.
    }
  }

  // Fixed local paths: never redirect to a query parameter or forwarded host.
  return new NextResponse(null, {
    status: 303,
    headers: { Location: location, "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" },
  });
}
