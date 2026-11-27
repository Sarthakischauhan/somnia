"use server";

import { revalidatePath } from "next/cache";

import { type Resolution, somnia, unwrap } from "@/lib/api/client";

export async function updateConfidence(memoryId: string, formData: FormData): Promise<void> {
  const api = await somnia();
  const confidence = Number(formData.get("confidence"));
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    throw new Error("confidence must be between 0 and 1");
  }
  unwrap(
    await api.PATCH("/v1/memories/{memory_id}", {
      params: { path: { memory_id: memoryId } },
      body: { confidence },
    }),
  );
  revalidatePath(`/memories/${memoryId}`);
  revalidatePath("/memories");
}

export async function setArchived(memoryId: string, archived: boolean): Promise<void> {
  const api = await somnia();
  unwrap(
    await api.PATCH("/v1/memories/{memory_id}", {
      params: { path: { memory_id: memoryId } },
      body: { archived },
    }),
  );
  revalidatePath(`/memories/${memoryId}`);
  revalidatePath("/memories");
}

export async function runDreamNow(): Promise<void> {
  const api = await somnia();
  unwrap(await api.POST("/v1/dream-runs"));
  revalidatePath("/dreaming");
}

export async function resolveConflict(conflictId: string, resolution: Resolution): Promise<void> {
  const api = await somnia();
  unwrap(
    await api.POST("/v1/conflicts/{conflict_id}/resolve", {
      params: { path: { conflict_id: conflictId } },
      body: { resolution },
    }),
  );
  revalidatePath("/conflicts");
  revalidatePath("/memories");
}
