import { ResumeHandoff } from "@/components/resume-handoff";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { somnia, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function SessionsPage() {
  const api = await somnia();
  const [checkpoints, queue] = await Promise.all([
    api.GET("/v1/admin/checkpoints/latest").then(unwrap),
    api.GET("/v1/admin/tasks", { params: { query: { limit: 50 } } }).then(unwrap),
  ]);
  const counts = [
    ["Queued", queue.counts.queued],
    ["Running", queue.counts.running],
    ["Done", queue.counts.done],
    ["Failed", queue.counts.failed],
  ] as const;

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Session handoffs</h1>
          <p className="text-sm text-muted-foreground">
            Open the same repo and branch in another agent to pick up a saved checkpoint.
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {checkpoints.map((cp) => (
            <Card key={cp.id}>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-start justify-between gap-2 text-base">
                  <span className="break-all">{cp.repo}</span>
                  <Badge variant="outline" className="font-mono">{cp.branch}</Badge>
                </CardTitle>
                <CardDescription>
                  {cp.source === "agent" ? "Agent checkpoint" : "Dream checkpoint"}
                  {" · "}{formatDateTime(cp.created_at)}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div>
                  <h2 className="font-medium">{cp.goal}</h2>
                  <p className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">
                    {cp.state}
                  </p>
                </div>
                {cp.next_steps.length > 0 && (
                  <div>
                    <h3 className="font-medium">Next steps</h3>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
                      {cp.next_steps.map((step, index) => <li key={index}>{step}</li>)}
                    </ul>
                  </div>
                )}
                {cp.files_touched.length > 0 && (
                  <div>
                    <h3 className="font-medium">Files touched</h3>
                    <ul className="mt-1 space-y-1 break-all font-mono text-xs text-muted-foreground">
                      {cp.files_touched.map((file, index) => <li key={index}>{file}</li>)}
                    </ul>
                  </div>
                )}
                <div className="space-y-2 border-t pt-3">
                  {cp.git_ref && (
                    <p className="text-xs text-muted-foreground">
                      Git ref <code>{cp.git_ref}</code>{cp.pushed ? " · pushed" : ""}
                    </p>
                  )}
                  {!cp.pushed && (
                    <p className="text-xs text-muted-foreground">
                      If changes are local, use the original worktree or transfer the changes first.
                    </p>
                  )}
                  {cp.status === "open" && <ResumeHandoff />}
                </div>
              </CardContent>
            </Card>
          ))}
          {checkpoints.length === 0 && <p className="text-sm text-muted-foreground">No checkpoints yet.</p>}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Task queue</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {counts.map(([label, value]) => (
            <Card key={label}>
              <CardHeader>
                <CardDescription>{label}</CardDescription>
                <CardTitle className="text-2xl tabular-nums">{value}</CardTitle>
              </CardHeader>
            </Card>
          ))}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Repo</TableHead>
              <TableHead className="text-right">Priority</TableHead>
              <TableHead className="text-right">Attempts</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queue.items.map((task) => (
              <TableRow key={task.id}>
                <TableCell>{task.title}</TableCell>
                <TableCell>
                  <Badge variant={task.status === "failed" ? "destructive" : "outline"}>{task.status}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {task.repo ?? "—"}
                  {task.branch ? ` @ ${task.branch}` : ""}
                </TableCell>
                <TableCell className="text-right tabular-nums">{task.priority}</TableCell>
                <TableCell className="text-right tabular-nums">{task.attempts}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(task.updated_at)}</TableCell>
              </TableRow>
            ))}
            {queue.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No tasks.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
