import { Badge } from "@/components/ui/badge";
import type { Memory } from "@/lib/api/types";

export function MemoryStatusBadge({ memory }: { memory: Memory }) {
  if (memory.archived_at) return <Badge variant="outline">archived</Badge>;
  if (memory.superseded_by) return <Badge variant="secondary">superseded</Badge>;
  return <Badge>active</Badge>;
}
