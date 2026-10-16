import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { resolveConflict } from "@/lib/actions";
import { type ConflictView, type Memory, type Resolution, somnia, unwrap } from "@/lib/api/client";
import { formatDateTime, shortId } from "@/lib/format";

export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

const RESOLUTIONS: readonly { value: Resolution; label: string }[] = [
  { value: "keep_existing", label: "Keep existing" },
  { value: "keep_candidate", label: "Keep new" },
  { value: "keep_both", label: "Keep both" },
];

function MemorySide({ label, memory }: { label: string; memory: Memory }) {
  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <span className="flex gap-1">
          <Badge variant="outline">{memory.scope}</Badge>
          <Badge variant="outline" className="tabular-nums">
            {memory.confidence.toFixed(2)}
          </Badge>
          {memory.superseded_by && <Badge variant="secondary">superseded</Badge>}
        </span>
      </div>
      <p className="text-sm">{memory.content}</p>
      <Link href={`/memories/${memory.id}`} className="text-xs text-muted-foreground underline-offset-4 hover:underline">
        memory {shortId(memory.id)} · {memory.source_session_ids.length} source session
        {memory.source_session_ids.length === 1 ? "" : "s"}
      </Link>
    </div>
  );
}

function ConflictCard({ view }: { view: ConflictView }) {
  const { conflict } = view;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2 text-base">
          <span>{conflict.repo ?? "global"}</span>
          <span className="flex gap-1">
            <Badge variant={conflict.outcome === "flagged" ? "destructive" : "outline"}>{conflict.outcome}</Badge>
            {conflict.resolution && <Badge variant="outline">{conflict.resolution.replace("_", " ")}</Badge>}
          </span>
        </CardTitle>
        <CardDescription>
          {formatDateTime(conflict.created_at)}
          {conflict.rationale ? ` · ${conflict.rationale}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        <MemorySide label="Existing" memory={view.existing} />
        <MemorySide label="New" memory={view.candidate} />
      </CardContent>
      {conflict.status === "open" && (
        <CardFooter className="flex flex-wrap gap-2">
          {RESOLUTIONS.map((r) => (
            <form key={r.value} action={resolveConflict.bind(null, conflict.id, r.value)}>
              <Button type="submit" size="sm" variant={r.value === "keep_both" ? "outline" : "default"}>
                {r.label}
              </Button>
            </form>
          ))}
        </CardFooter>
      )}
    </Card>
  );
}

export default async function ConflictsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const showResolved = params.status === "resolved";
  const views = unwrap(
    await somnia().GET("/v1/admin/conflicts", {
      params: { query: showResolved ? { status: ["resolved"] } : { status: ["open"], outcome: ["flagged"] } },
    }),
  );

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Conflicts</h1>
        <p className="text-sm text-muted-foreground">
          Contradictions dreaming could not settle. Both memories are kept; resolving marks one as superseded.
        </p>
      </div>
      <div className="flex gap-2">
        <Button size="sm" variant={showResolved ? "outline" : "default"} nativeButton={false}
            render={<Link href="/conflicts" />}>
          Flagged
        </Button>
        <Button
          size="sm"
          variant={showResolved ? "default" : "outline"}
          nativeButton={false}
            render={<Link href="/conflicts?status=resolved" />}
        >
          History
        </Button>
      </div>
      <div className="space-y-4">
        {views.map((view) => (
          <ConflictCard key={view.conflict.id} view={view} />
        ))}
        {views.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {showResolved ? "No resolved conflicts yet." : "No flagged conflicts."}
          </p>
        )}
      </div>
    </div>
  );
}
