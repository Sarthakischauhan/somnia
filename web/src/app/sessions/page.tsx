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
  const api = somnia();
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
          <h1 className="text-2xl font-semibold">Sessions &amp; checkpoints</h1>
          <p className="text-sm text-muted-foreground">Latest checkpoint for each repo and branch.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {checkpoints.map((cp) => (
            <Card key={cp.id}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between gap-2 text-base">
                  <span>
                    {cp.repo} @ {cp.branch}
                  </span>
                  <span className="flex gap-1">
                    <Badge variant={cp.status === "open" ? "default" : "outline"}>{cp.status}</Badge>
                    <Badge variant="outline">{cp.source}</Badge>
                  </span>
                </CardTitle>
                <CardDescription>
                  {formatDateTime(cp.created_at)}
                  {cp.git_ref ? ` · ${cp.git_ref}` : ""}
                  {cp.pushed ? " · pushed" : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p>
                  <span className="font-medium">Goal:</span> {cp.goal}
                </p>
                <p>
                  <span className="font-medium">State:</span> {cp.state}
                </p>
                {cp.next_steps.length > 0 && (
                  <ul className="list-disc pl-5 text-muted-foreground">
                    {cp.next_steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ul>
                )}
                {cp.files_touched.length > 0 && (
                  <p className="font-mono text-xs text-muted-foreground">{cp.files_touched.join(", ")}</p>
                )}
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
