import Link from "next/link";
import { notFound } from "next/navigation";

import { MemoryStatusBadge } from "@/components/memory-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setArchived, updateConfidence } from "@/lib/actions";
import { ApiError, type Memory, somnia, unwrap } from "@/lib/api/client";
import { formatDateTime, shortId } from "@/lib/format";

export const dynamic = "force-dynamic";

function ChainList({ title, empty, items }: { title: string; empty: string; items: Memory[] }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ol className="space-y-2">
          {items.map((m) => (
            <li key={m.id} className="rounded-md border p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <Link href={`/memories/${m.id}`} className="font-mono text-xs hover:underline">
                  {shortId(m.id)}
                </Link>
                <MemoryStatusBadge memory={m} />
              </div>
              <p className="mt-1">{m.content}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default async function MemoryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let detail;
  try {
    detail = unwrap(
      await somnia().GET("/v1/admin/memories/{memory_id}", { params: { path: { memory_id: id } } }),
    );
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  const { memory, sources, supersedes, superseded_by_chain } = detail;
  const archived = memory.archived_at !== null;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link href="/memories" className="text-sm text-muted-foreground hover:underline">
          ← Memories
        </Link>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Memory {shortId(memory.id)}</h1>
          <MemoryStatusBadge memory={memory} />
        </div>
        <p className="text-lg">{memory.content}</p>
        <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
          <Badge variant="outline">{memory.type}</Badge>
          <Badge variant="outline">{memory.scope}</Badge>
          <span>
            {memory.repo ?? "global"}
            {memory.branch ? ` @ ${memory.branch}` : ""}
          </span>
          <span>· used {memory.use_count}×, last {formatDateTime(memory.last_used_at)}</span>
          <span>· created {formatDateTime(memory.created_at)}</span>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle>Curate</CardTitle>
            <CardDescription>Archiving hides it from retrieval; nothing is deleted.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form action={updateConfidence.bind(null, memory.id)} className="space-y-2">
              <Label htmlFor="confidence">Confidence (0–1)</Label>
              <div className="flex gap-2">
                <Input
                  id="confidence"
                  name="confidence"
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  defaultValue={memory.confidence.toFixed(2)}
                />
                <Button type="submit">Save</Button>
              </div>
            </form>
            <form action={setArchived.bind(null, memory.id, !archived)}>
              <Button type="submit" variant={archived ? "outline" : "destructive"} className="w-full">
                {archived ? "Restore" : "Archive"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Provenance</CardTitle>
            <CardDescription>source_session_ids: sessions this memory was consolidated from</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {sources.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-2 rounded-md border p-3">
                  <span className="font-mono text-xs">{shortId(s.id)}</span>
                  <span>
                    {s.repo} @ {s.branch}
                  </span>
                  <Badge variant="outline">{s.status}</Badge>
                  <span className="text-muted-foreground">started {formatDateTime(s.started_at)}</span>
                  {s.git_ref && <span className="font-mono text-xs text-muted-foreground">{s.git_ref}</span>}
                </li>
              ))}
              {sources.length === 0 && <li className="text-muted-foreground">No source sessions recorded.</li>}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Supersede chain</CardTitle>
          <CardDescription>Older versions this memory replaced, and newer ones that replaced it.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-2">
          <ChainList title="Supersedes (older)" empty="Nothing superseded." items={supersedes} />
          <ChainList title="Superseded by (newer)" empty="This is the latest version." items={superseded_by_chain} />
        </CardContent>
      </Card>
    </div>
  );
}
