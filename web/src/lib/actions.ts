"use server";

import { revalidatePath } from "next/cache";

import { somnia, unwrap } from "@/lib/api/client";

export async function updateConfidence(memoryId: string, formData: FormData): Promise<void> {
  const confidence = Number(formData.get("confidence"));
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    throw new Error("confidence must be between 0 and 1");
  }
  unwrap(
    await somnia().PATCH("/v1/admin/memories/{memory_id}", {
      params: { path: { memory_id: memoryId } },
      body: { confidence },
    }),
  );
  revalidatePath(`/memories/${memoryId}`);
  revalidatePath("/memories");
}

export async function setArchived(memoryId: string, archived: boolean): Promise<void> {
  unwrap(
    await somnia().PATCH("/v1/admin/memories/{memory_id}", {
      params: { path: { memory_id: memoryId } },
      body: { archived },
    }),
  );
  revalidatePath(`/memories/${memoryId}`);
  revalidatePath("/memories");
}

export async function runDreamNow(): Promise<void> {
  unwrap(await somnia().POST("/v1/admin/dream-runs"));
  revalidatePath("/dreaming");
}
