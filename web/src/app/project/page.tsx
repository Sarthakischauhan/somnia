import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  PROFILE_SECTIONS,
  type ProfileEntry,
  type ProjectProfile,
  somnia,
  unwrap,
} from "@/lib/api/client";
import { formatDateTime, shortId } from "@/lib/format";

export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

async function loadProfile(repo: string): Promise<ProjectProfile | null> {
  const result = await somnia().GET("/v1/admin/project-profile", { params: { query: { repo } } });
  if (result.response.status === 404) return null;
  return unwrap(result);
}

function Provenance({ entry }: { entry: ProfileEntry }) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
      <Badge variant="outline" className="tabular-nums">
        {entry.confidence.toFixed(2)}
      </Badge>
      {entry.source_memory_id && (
        <Link href={`/memories/${entry.source_memory_id}`} className="underline-offset-4 hover:underline">
          memory {shortId(entry.source_memory_id)}
        </Link>
      )}
      {entry.source_checkpoint_id && <span>checkpoint {shortId(entry.source_checkpoint_id)}</span>}
      <span>
        {entry.source_session_ids.length} session{entry.source_session_ids.length === 1 ? "" : "s"}
      </span>
    </span>
  );
}

export default async function ProjectPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const repos = [...new Set(unwrap(await somnia().GET("/v1/admin/repos")).map((r) => r.repo))];
  const requested = Array.isArray(params.repo) ? params.repo[0] : params.repo;
  const repo = requested && repos.includes(requested) ? requested : repos[0];
  const profile = repo ? await loadProfile(repo) : null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Project profile</h1>
        <p className="text-sm text-muted-foreground">
          What dreaming has learned about a repo. Each entry links back to the memory or checkpoint it
          came from.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {repos.map((name) => (
          <Button
            key={name}
            size="sm"
            variant={name === repo ? "default" : "outline"}
            nativeButton={false}
            render={<Link href={`/project?repo=${encodeURIComponent(name)}`} />}
          >
            {name}
          </Button>
        ))}
      </div>
      {!profile && (
        <p className="text-sm text-muted-foreground">
          {repo ? `No profile for ${repo} yet. It is built on the next dream.` : "No repos yet."}
        </p>
      )}
      {profile && (
        <>
          <p className="text-sm text-muted-foreground">
            {profile.repo} · version {profile.version} · updated {formatDateTime(profile.updated_at)}
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {PROFILE_SECTIONS.map(({ key, title }) => {
              const entries = profile.entries.filter((e) => e.section === key);
              return (
                <Card key={key}>
                  <CardHeader>
                    <CardTitle className="text-base">{title}</CardTitle>
                    <CardDescription>
                      {entries.length} entr{entries.length === 1 ? "y" : "ies"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {entries.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Nothing yet.</p>
                    ) : (
                      <ul className="space-y-3">
                        {entries.map((entry) => (
                          <li key={entry.id} className="space-y-1">
                            <p className="text-sm">{entry.content}</p>
                            <Provenance entry={entry} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
