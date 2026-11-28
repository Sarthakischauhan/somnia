import "server-only";

import { redirect } from "next/navigation";
import createClient from "openapi-fetch";

import { authErrorPath } from "@/lib/auth-errors";
import { getSomniaApiUrl } from "@/lib/env";
import { requireSession } from "@/lib/supabase/session";

import type { paths } from "./schema";

export type {
  Checkpoint,
  ConflictView,
  CreatedDevice,
  Device,
  DreamRun,
  DreamSchedule,
  Memory,
  MemoryDetail,
  MemoryPage,
  MemoryScope,
  MemoryType,
  ProfileEntry,
  ProfileSection,
  ProjectProfile,
  RepoBranch,
  Resolution,
  Schemas,
  TaskQueue,
} from "./types";
export { MEMORY_SCOPES, MEMORY_TYPES, PROFILE_SECTIONS } from "./types";

/** A fresh server-only client, scoped to a verified dashboard user. */
export async function somnia() {
  const { token } = await requireSession();
  const apiUrl = getSomniaApiUrl();
  if (!apiUrl) redirect(authErrorPath("configuration"));

  const api = createClient<paths>({
    baseUrl: apiUrl,
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    redirect: "error",
  });
  api.use({
    async onResponse({ response }) {
      if (response.status === 401) {
        const detail = await response.clone().text();
        console.error(`Somnia API auth failed: segments=${token.split(".").length} length=${token.length} body=${detail.slice(0, 300)}`);
        redirect(authErrorPath("api-session"));
      }
      if (response.status === 403) redirect(authErrorPath("forbidden"));
    },
  });
  return api;
}

export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`Somnia API request failed (${status})`);
  }
}

/** Unwrap an openapi-fetch result or throw with the HTTP status. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    throw new ApiError(result.response.status);
  }
  return result.data;
}
