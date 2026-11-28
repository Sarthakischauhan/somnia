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
import { formatTokens, formatUsd } from "@/lib/format";

export const dynamic = "force-dynamic";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-lg font-medium">{value}</p>
    </div>
  );
}

export default async function UsagePage() {
  const api = await somnia();
  const usage = await api.GET("/v1/usage", { params: { query: { days: 30 } } }).then(unwrap);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Usage</h1>
        <p className="text-sm text-muted-foreground">
          Gemini calls recorded since usage accounting was enabled. Costs use Google&apos;s published catalog rates and are estimates, not an invoice.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Last 30 days</CardTitle>
          <CardDescription>Provider credential: Gemini Developer API. Calls made before accounting started are not included.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-4">
          <Stat label="Estimated cost" value={formatUsd(usage.cost_usd)} />
          <Stat label="Requests" value={usage.requests.toLocaleString("en-US")} />
          <Stat label="Input tokens" value={formatTokens(usage.input_tokens)} />
          <Stat label="Output tokens" value={formatTokens(usage.output_tokens)} />
        </CardContent>
      </Card>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Model</TableHead>
            <TableHead>Operation</TableHead>
            <TableHead className="text-right">Requests</TableHead>
            <TableHead className="text-right">Input</TableHead>
            <TableHead className="text-right">Output</TableHead>
            <TableHead className="text-right">Estimated cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {usage.models.map((model) => (
            <TableRow key={`${model.provider}:${model.model}:${model.operation}`}>
              <TableCell>{model.model}</TableCell>
              <TableCell>{model.operation}</TableCell>
              <TableCell className="text-right tabular-nums">{model.requests.toLocaleString("en-US")}</TableCell>
              <TableCell className="text-right tabular-nums">{formatTokens(model.input_tokens)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatTokens(model.output_tokens)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatUsd(model.cost_usd)}</TableCell>
            </TableRow>
          ))}
          {usage.models.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-muted-foreground">
                No recorded provider calls yet.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
