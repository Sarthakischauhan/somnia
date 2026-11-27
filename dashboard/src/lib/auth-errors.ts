const authErrors = {
  "sign-in": {
    title: "Couldn’t start GitHub sign-in",
    description: "Try starting again. If this keeps happening, ask the dashboard administrator to check the GitHub provider in Supabase.",
    action: "sign-in",
  },
  callback: {
    title: "GitHub sign-in didn’t complete",
    description: "This sign-in attempt may have expired or started in another browser. Start a new one in this tab.",
    action: "sign-in",
  },
  cancelled: {
    title: "GitHub sign-in was cancelled",
    description: "You haven’t been signed in by this attempt. Start again when you’re ready.",
    action: "sign-in",
  },
  "api-session": {
    title: "Your session wasn’t accepted",
    description: "Sign out and back in to refresh your session. If that doesn’t help, ask the dashboard administrator to check the API’s auth configuration.",
    action: "sign-out",
  },
  forbidden: {
    title: "This account doesn’t have access",
    description: "Ask the dashboard administrator for access, or sign out and use a different GitHub account.",
    action: "sign-out",
  },
  "sign-out": {
    title: "Couldn’t sign out",
    description: "This browser may still be signed in. Try signing out again before you leave a shared device.",
    action: "sign-out",
  },
  unavailable: {
    title: "Sign-in is temporarily unavailable",
    description: "Somnia couldn’t reach its sign-in service. Give it a moment, then try the dashboard again.",
    action: "dashboard",
  },
  configuration: {
    title: "Dashboard sign-in isn’t set up",
    description: "The dashboard administrator needs to connect Somnia to Supabase and enable GitHub sign-in before you can continue.",
    action: "configuration",
  },
} as const;

type AuthErrorReason = keyof typeof authErrors;

export function authErrorPath(reason: AuthErrorReason) {
  return `/auth/error?reason=${reason}`;
}

export function getAuthError(reason: string | string[] | undefined) {
  if (typeof reason === "string" && Object.hasOwn(authErrors, reason)) {
    return authErrors[reason as AuthErrorReason];
  }
  return {
    title: "Something went wrong with sign-in",
    description: "Return to sign-in to start a new attempt.",
    action: "sign-in",
  } as const;
}

export function isAuthServiceUnavailable(error: { status?: number } | null) {
  return error?.status === 0 || error?.status === 429 || (error?.status ?? 0) >= 500;
}
