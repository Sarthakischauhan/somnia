import { cookies } from "next/headers";

import { AppSidebar } from "@/components/app-sidebar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { signOut } from "@/lib/auth-actions";
import { requireSession } from "@/lib/supabase/session";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const { user } = await requireSession();
  // Persisted by the shadcn sidebar; read server-side so the collapsed state doesn't flash.
  const sidebarOpen = (await cookies()).get("sidebar_state")?.value !== "false";

  return (
    <TooltipProvider>
      <SidebarProvider defaultOpen={sidebarOpen}>
        <AppSidebar />
        <SidebarInset>
          <header className="flex h-12 items-center gap-2 border-b px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
            <span className="text-sm text-muted-foreground">somnia admin</span>
            <form action={signOut} className="ml-auto flex min-w-0 items-center gap-3">
              <span className="hidden truncate text-xs text-muted-foreground sm:block">{user.email}</span>
              <Button size="sm" variant="outline" type="submit">Sign out</Button>
            </form>
          </header>
          <main className="mx-auto w-full max-w-6xl px-6 py-8">{children}</main>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
