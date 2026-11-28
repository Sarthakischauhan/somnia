import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { authCookieOptions, getSupabaseConfig } from "@/lib/supabase/config";

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  const config = getSupabaseConfig();

  if (config) {
    const supabase = createServerClient(config.url, config.key, {
      cookieOptions: authCookieOptions,
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(cookiesToSet, cacheHeaders) {
          for (const { name, value } of cookiesToSet) request.cookies.set(name, value);
          // Rebuild the forwarded request so downstream code sees the refreshed cookies.
          const previousCookies = response.cookies.getAll();
          response = NextResponse.next({ request });
          for (const cookie of previousCookies) response.cookies.set(cookie);
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
          for (const [name, value] of Object.entries(cacheHeaders)) {
            response.headers.set(name, value);
          }
        },
      },
    });

    // Cookie refresh only needs the local session. Page rendering verifies the user.
    await supabase.auth.getSession();
  }

  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export const config = {
  runtime: "nodejs",
  matcher: [
    "/login",
    "/auth/error",
    "/memories/:path*",
    "/project/:path*",
    "/conflicts/:path*",
    "/dreaming/:path*",
    "/sessions/:path*",
    "/devices/:path*",
  ],
};
