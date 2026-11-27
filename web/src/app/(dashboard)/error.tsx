"use client";

import { Button } from "@/components/ui/button";

export default function DashboardError({ reset }: { reset: () => void }) {
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Dashboard request failed</h1>
      <p role="alert" className="text-sm text-muted-foreground">
        The request could not be completed. Refresh to check the current state and try again.
      </p>
      <Button onClick={reset} variant="outline">Try again</Button>
    </div>
  );
}
