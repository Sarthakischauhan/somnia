"use client";

import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";

export function AuthSubmit({ children, pendingLabel }: { children: ReactNode; pendingLabel: string }) {
  const { pending } = useFormStatus();

  return (
    <Button type="submit" size="lg" className="h-11 w-full" disabled={pending} aria-busy={pending}>
      {pending ? <><LoaderCircle className="motion-safe:animate-spin" aria-hidden="true" />{pendingLabel}</> : children}
    </Button>
  );
}
