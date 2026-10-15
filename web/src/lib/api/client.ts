import "server-only";

import createClient from "openapi-fetch";

import { serverEnv } from "@/lib/env";

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

/** Typed client for the somnia FastAPI service. Server-only: the token never reaches the browser. */
export function somnia() {
  const env = serverEnv();
  return createClient<paths>({
    baseUrl: env.apiUrl,
    headers: { Authorization: `Bearer ${env.adminToken}` },
    cache: "no-store",
  });
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    detail: string,
  ) {
    super(`somnia API ${status}: ${detail}`);
  }
}

/** Unwrap an openapi-fetch result or throw with the HTTP status. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    throw new ApiError(result.response.status, JSON.stringify(result.error ?? null));
  }
  return result.data;
}
