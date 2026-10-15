import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MEMORY_SCOPES, MEMORY_TYPES, type RepoBranch } from "@/lib/api/client";

export interface MemoryFilterValues {
  q?: string;
  repo?: string;
  branch?: string;
  type?: string;
  scope?: string;
  include_superseded?: boolean;
  include_archived?: boolean;
}

const ANY = "__any__";

function FilterSelect(props: {
  name: string;
  label: string;
  value: string | undefined;
  options: readonly string[];
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={props.name}>{props.label}</Label>
      <Select name={props.name} defaultValue={props.value}>
        <SelectTrigger id={props.name} className="w-40">
          <SelectValue placeholder="Any" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
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

export function MemoryFilters({
  values,
  repos,
}: {
  values: MemoryFilterValues;
  repos: RepoBranch[];
}) {
  const repoNames = [...new Set(repos.map((r) => r.repo))];
  const branches = [...new Set(repos.map((r) => r.branch))];
  return (
    <form method="get" className="flex flex-wrap items-end gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor="q">Search</Label>
        <Input id="q" name="q" defaultValue={values.q} placeholder="Search content" className="w-64" />
      </div>
      <FilterSelect name="repo" label="Repo" value={values.repo} options={repoNames} />
      <FilterSelect name="branch" label="Branch" value={values.branch} options={branches} />
      <FilterSelect name="type" label="Type" value={values.type} options={MEMORY_TYPES} />
      <FilterSelect name="scope" label="Scope" value={values.scope} options={MEMORY_SCOPES} />
      <label className="flex h-9 items-center gap-2 text-sm">
        <input type="checkbox" name="include_superseded" value="true" defaultChecked={values.include_superseded} />
        Superseded
      </label>
      <label className="flex h-9 items-center gap-2 text-sm">
        <input type="checkbox" name="include_archived" value="true" defaultChecked={values.include_archived} />
        Archived
      </label>
      <Button type="submit">Apply</Button>
    </form>
  );
}

export function cleanFilter(value: string | undefined): string | undefined {
  return value && value !== ANY ? value : undefined;
}
