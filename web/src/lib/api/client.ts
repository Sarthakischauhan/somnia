import "server-only";

import { redirect } from "next/navigation";
import createClient from "openapi-fetch";

import { getSomniaApiUrl } from "@/lib/env";
import { requireSession } from "@/lib/supabase/session";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Memory = Schemas["MemoryRecord"];
export type MemoryDetail = Schemas["MemoryDetail"];
export type MemoryPage = Schemas["MemoryPage"];
export type DreamRun = Schemas["DreamRunRecord"];
export type DreamSchedule = Schemas["DreamSchedule"];
export type Checkpoint = Schemas["CheckpointRecord"];
export type TaskQueue = Schemas["TaskQueue"];
export type RepoBranch = Schemas["RepoBranch"];
export type ProjectProfile = Schemas["ProjectProfileOut"];
export type ProfileEntry = Schemas["ProfileEntryOut"];
export type ProfileSection = ProfileEntry["section"];
export type ConflictView = Schemas["ConflictView"];
export type Resolution = Schemas["ConflictResolution"]["resolution"];
export type MemoryType = Memory["type"];
export type MemoryScope = Memory["scope"];

export const MEMORY_TYPES: readonly MemoryType[] = [
  "fact",
  "decision",
  "convention",
  "gotcha",
  "todo",
];
export const MEMORY_SCOPES: readonly MemoryScope[] = ["global", "repo", "branch"];

export const PROFILE_SECTIONS: readonly { key: ProfileSection; title: string }[] = [
  { key: "stack", title: "Stack" },
  { key: "conventions", title: "Conventions" },
  { key: "architecture", title: "Architecture notes" },
  { key: "decisions", title: "Key decisions" },
  { key: "open_work", title: "Open work" },
  { key: "pitfalls", title: "Known pitfalls" },
];

/** A fresh server-only client, scoped to a verified dashboard user. */
export async function somnia() {
  const { token } = await requireSession();
  const apiUrl = getSomniaApiUrl();
  if (!apiUrl) redirect("/login");

  const api = createClient<paths>({
    baseUrl: apiUrl,
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    redirect: "error",
  });
  api.use({
    onResponse({ response }) {
      if (response.status === 401) redirect("/login?error=api-session");
      if (response.status === 403) redirect("/login?error=forbidden");
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
