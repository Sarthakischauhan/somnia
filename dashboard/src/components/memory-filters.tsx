"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MEMORY_SCOPES, MEMORY_TYPES, type RepoBranch } from "@/lib/api/types";

export interface MemoryFilterValues {
  q?: string;
  repo?: string;
  branch?: string;
  type?: string;
  scope?: string;
  include_superseded?: boolean;
  include_archived?: boolean;
}

export const ANY_FILTER = "__any__";

function FilterSelect(props: {
  label: string;
  value: string | undefined;
  options: readonly string[];
  onChange: (value: string | undefined) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <Label>{props.label}</Label>
      <Select
        value={props.value ?? ANY_FILTER}
        onValueChange={(value) => props.onChange(!value || value === ANY_FILTER ? undefined : value)}
      >
        <SelectTrigger className="w-36">
          <SelectValue placeholder="Any" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY_FILTER}>Any</SelectItem>
          {props.options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function MemoryFilters({ values, repos }: { values: MemoryFilterValues; repos: RepoBranch[] }) {
  const router = useRouter();
  const [query, setQuery] = useState(values.q ?? "");
  const repoNames = [...new Set(repos.map((repo) => repo.repo))];
  const branches = [...new Set(repos.filter((repo) => !values.repo || repo.repo === values.repo).map((repo) => repo.branch))];

  function apply(next: MemoryFilterValues) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(next)) {
      if (typeof value === "string" && value) params.set(key, value);
      if (value === true) params.set(key, "true");
    }
    const queryString = params.toString();
    router.replace(queryString ? `/memories?${queryString}` : "/memories");
  }

  const current = useRef(values);
  current.current = values;
  useEffect(() => {
    const handle = window.setTimeout(() => {
      const trimmed = query.trim();
      if ((current.current.q ?? "") !== trimmed) apply({ ...current.current, q: trimmed || undefined });
    }, 300);
    return () => window.clearTimeout(handle);
  }, [query]);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor="memory-search">Search</Label>
        <Input id="memory-search" value={query} placeholder="Search content" className="w-64" onChange={(event) => setQuery(event.target.value)} />
      </div>
      <FilterSelect label="Repo" value={values.repo} options={repoNames} onChange={(repo) => apply({ ...values, repo, branch: undefined })} />
      <FilterSelect label="Branch" value={values.branch} options={branches} onChange={(branch) => apply({ ...values, branch })} />
      <FilterSelect label="Type" value={values.type} options={MEMORY_TYPES} onChange={(type) => apply({ ...values, type })} />
      <FilterSelect label="Scope" value={values.scope} options={MEMORY_SCOPES} onChange={(scope) => apply({ ...values, scope })} />
      <label className="flex h-8 items-center gap-2 text-sm">
        <input type="checkbox" checked={values.include_superseded ?? false} onChange={(event) => apply({ ...values, include_superseded: event.target.checked })} />
        Superseded
      </label>
      <label className="flex h-8 items-center gap-2 text-sm">
        <input type="checkbox" checked={values.include_archived ?? false} onChange={(event) => apply({ ...values, include_archived: event.target.checked })} />
        Archived
      </label>
    </div>
  );
}


