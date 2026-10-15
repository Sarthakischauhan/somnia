import Link from "next/link";

import { MemoryStatusBadge } from "@/components/memory-badges";
import { cleanFilter, MemoryFilters, type MemoryFilterValues } from "@/components/memory-filters";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  MEMORY_SCOPES,
  MEMORY_TYPES,
  type MemoryScope,
  type MemoryType,
  somnia,
  unwrap,
} from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function asType(value: string | undefined): MemoryType | undefined {
  return MEMORY_TYPES.find((t) => t === value);
}

function asScope(value: string | undefined): MemoryScope | undefined {
  return MEMORY_SCOPES.find((s) => s === value);
}

export default async function MemoriesPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const values: MemoryFilterValues = {
    q: cleanFilter(first(params.q)),
    repo: cleanFilter(first(params.repo)),
    branch: cleanFilter(first(params.branch)),
    type: asType(cleanFilter(first(params.type))),
    scope: asScope(cleanFilter(first(params.scope))),
    include_superseded: first(params.include_superseded) === "true",
    include_archived: first(params.include_archived) === "true",
  };
  const api = somnia();
  const [page, repos] = await Promise.all([
    api
      .GET("/v1/admin/memories", {
        params: {
          query: {
            q: values.q,
            repo: values.repo,
            branch: values.branch,
            type: asType(values.type),
            scope: asScope(values.scope),
            include_superseded: values.include_superseded,
            include_archived: values.include_archived,
            limit: 100,
          },
        },
      })
      .then(unwrap),
    api.GET("/v1/admin/repos").then(unwrap),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Memories</h1>
        <p className="text-sm text-muted-foreground">{page.total} matching memories</p>
      </div>
      <MemoryFilters values={values} repos={repos} />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[45%]">Content</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Scope</TableHead>
            <TableHead>Repo / branch</TableHead>
            <TableHead className="text-right">Confidence</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Updated</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.items.map((memory) => (
            <TableRow key={memory.id}>
              <TableCell className="whitespace-normal">
                <Link href={`/memories/${memory.id}`} className="hover:underline">
                  {memory.content}
                </Link>
              </TableCell>
              <TableCell>
                <Badge variant="outline">{memory.type}</Badge>
              </TableCell>
              <TableCell>{memory.scope}</TableCell>
              <TableCell className="text-muted-foreground">
                {memory.repo ?? "—"}
                {memory.branch ? ` @ ${memory.branch}` : ""}
              </TableCell>
              <TableCell className="text-right tabular-nums">{memory.confidence.toFixed(2)}</TableCell>
              <TableCell>
                <MemoryStatusBadge memory={memory} />
              </TableCell>
              <TableCell className="text-muted-foreground">{formatDateTime(memory.updated_at)}</TableCell>
            </TableRow>
          ))}
          {page.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-muted-foreground">
                No memories match these filters.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
