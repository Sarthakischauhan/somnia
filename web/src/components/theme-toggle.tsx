"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { SidebarMenuButton } from "@/components/ui/sidebar";

/** Icons switch via the `dark` class, so server and client markup match (no hydration flash). */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <SidebarMenuButton
      tooltip="Toggle theme"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      <Sun className="dark:hidden" />
      <Moon className="hidden dark:block" />
      <span className="dark:hidden">Dark mode</span>
      <span className="hidden dark:inline">Light mode</span>
    </SidebarMenuButton>
  );
}
