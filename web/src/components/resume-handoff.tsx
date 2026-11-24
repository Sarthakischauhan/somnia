"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

const prompt =
  "Run somnia-agent resume in this checkout (or call somnia_resume in Symphony). " +
  "Use the saved checkpoint as reference, verify it against the working tree, and pick up the next unfinished step.";

export function ResumeHandoff() {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" onClick={copy}>
        {status === "copied" ? <Check /> : <Copy />}
        {status === "copied" ? "Prompt copied" : "Copy resume prompt"}
      </Button>
      {status === "failed" && (
        <span role="status" className="text-xs text-muted-foreground">
          Run <code>somnia-agent resume</code> from the matching checkout.
        </span>
      )}
    </div>
  );
}
