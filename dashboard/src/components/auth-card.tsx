import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function AuthCard({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <main className="grid min-h-svh place-items-center px-4 py-10 sm:px-6">
      <div className="w-full max-w-md space-y-4">
        <Link href="/" className="inline-flex items-center gap-2 rounded-sm text-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
          <ArrowLeft size={15} aria-hidden="true" /> Back to Somnia
        </Link>
        <Card className="[--card-spacing:--spacing(6)]">
          <CardHeader className="gap-2">
            <BrandMark size={36} />
            <CardTitle className="text-xl font-semibold tracking-tight"><h1>{title}</h1></CardTitle>
            <CardDescription className="leading-relaxed">{description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">{children}</CardContent>
        </Card>
      </div>
    </main>
  );
}
