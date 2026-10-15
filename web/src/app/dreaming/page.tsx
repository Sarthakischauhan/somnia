import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { runDreamNow } from "@/lib/actions";
import { type DreamRun, somnia, unwrap } from "@/lib/api/client";
import { formatDateTime, formatDuration } from "@/lib/format";

export const dynamic = "force-dynamic";

function statusVariant(status: DreamRun["status"]): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "succeeded":
      return "default";
    case "failed":
      return "destructive";
    case "running":
      return "secondary";
    case "requested":
      return "outline";
  }
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-lg font-medium">{value}</p>
    </div>
  );
}

export default async function DreamingPage() {
  const api = somnia();
  const [runs, schedule] = await Promise.all([
    api.GET("/v1/admin/dream-runs", { params: { query: { limit: 50 } } }).then(unwrap),
    api.GET("/v1/admin/dream-schedule").then(unwrap),
  ]);
  const hours = schedule.worker_interval_s / 3600;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Dreaming</h1>
          <p className="text-sm text-muted-foreground">
            Consolidation runs: summarize sessions, add / merge / supersede memories, decay unused ones.
          </p>
        </div>
        <form action={runDreamNow}>
          <Button type="submit">Run dream now</Button>
        </form>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Schedule</CardTitle>
          <CardDescription>The worker picks up requested runs on its next poll.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-4">
          <Stat label="Worker interval" value={hours >= 1 ? `every ${hours} h` : `every ${schedule.worker_interval_s} s`} />
          <Stat label="pg_cron" value={schedule.pg_cron_schedule ?? "not installed"} />
          <Stat label="Last success" value={formatDateTime(schedule.last_success_at)} />
          <Stat label="Pending requests" value={String(schedule.pending_requests)} />
        </CardContent>
      </Card>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Requested</TableHead>
            <TableHead>Trigger</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Sessions</TableHead>
            <TableHead className="text-right">Added</TableHead>
            <TableHead className="text-right">Merged</TableHead>
            <TableHead className="text-right">Superseded</TableHead>
            <TableHead className="text-right">Decayed</TableHead>
            <TableHead className="text-right">Duration</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.id}>
              <TableCell>{formatDateTime(run.requested_at)}</TableCell>
              <TableCell>{run.trigger}</TableCell>
              <TableCell>
                <Badge variant={statusVariant(run.status)} title={run.error ?? undefined}>
                  {run.status}
                </Badge>
              </TableCell>
              <TableCell className="text-right tabular-nums">{run.sessions_processed}</TableCell>
              <TableCell className="text-right tabular-nums">{run.memories_added}</TableCell>
              <TableCell className="text-right tabular-nums">{run.memories_merged}</TableCell>
              <TableCell className="text-right tabular-nums">{run.memories_superseded}</TableCell>
              <TableCell className="text-right tabular-nums">{run.memories_decayed}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatDuration(run.started_at, run.finished_at)}
              </TableCell>
            </TableRow>
          ))}
          {runs.length === 0 && (
            <TableRow>
              <TableCell colSpan={9} className="text-center text-muted-foreground">
                No dream runs yet.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
