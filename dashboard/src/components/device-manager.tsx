"use client";

import { useState, useTransition } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { createDevice, revokeDevice } from "@/lib/actions";
import type { Device } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

export function DeviceManager({ devices }: { devices: Device[] }) {
  const [name, setName] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function submit() {
    const trimmed = name.trim();
    if (!trimmed || trimmed.length > 80) {
      setError("Use a device name between 1 and 80 characters.");
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        setToken(await createDevice(trimmed));
        setName("");
      } catch {
        setError("Could not create the device. Check the name and try again.");
      }
    });
  }

  return (
    <div className="space-y-6">
      <form
        className="flex flex-col gap-3 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <Input
          value={name}
          maxLength={80}
          placeholder="Device name, such as laptop"
          aria-label="Device name"
          onChange={(event) => setName(event.target.value)}
        />
        <Button type="submit" disabled={pending}>Create device token</Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {token && (
        <div className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-4">
          <p className="text-sm font-medium">Copy this token now. It will not be shown again.</p>
          <code className="block break-all text-sm">{token}</code>
          <p className="text-sm text-muted-foreground">
            Run <code>somnia-agent login --api-url &lt;your-api&gt;</code> and paste it when prompted.
          </p>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {devices.map((device) => (
            <TableRow key={device.id}>
              <TableCell>{device.name}</TableCell>
              <TableCell>
                <Badge variant={device.revoked_at ? "outline" : "secondary"}>
                  {device.revoked_at ? "Revoked" : "Active"}
                </Badge>
              </TableCell>
              <TableCell>{formatDateTime(device.created_at)}</TableCell>
              <TableCell className="text-right">
                {!device.revoked_at && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={pending}
                    onClick={() => startTransition(() => revokeDevice(device.id))}
                  >
                    Revoke
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
          {devices.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} className="text-muted-foreground">No devices yet.</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
