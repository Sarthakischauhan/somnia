"use client";

import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function DashboardError() {
  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle><h1>Dashboard request failed</h1></CardTitle>
        <CardDescription role="alert">
          Somnia couldn’t complete the request. Reload to check the current state before trying again.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => window.location.reload()}>Reload page</Button>
        <Link className={buttonVariants({ variant: "outline" })} href="/">Back to Somnia</Link>
      </CardContent>
    </Card>
  );
}
