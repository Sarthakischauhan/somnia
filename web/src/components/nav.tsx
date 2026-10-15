import Link from "next/link";

const LINKS = [
  { href: "/memories", label: "Memories" },
  { href: "/dreaming", label: "Dreaming" },
  { href: "/sessions", label: "Sessions" },
] as const;

export function Nav() {
  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
        <Link href="/memories" className="font-semibold">
          somnia admin
        </Link>
        <nav className="flex gap-4 text-sm text-muted-foreground">
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="hover:text-foreground">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
