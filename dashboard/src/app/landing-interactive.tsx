"use client";

import { useState } from "react";
import Image from "next/image";
import { Tabs } from "@base-ui/react/tabs";
import { ArrowUpRight, AudioLines, CodeXml, Copy, ExternalLink, Terminal, Zap } from "lucide-react";

import styles from "./landing.module.css";

const repo = "https://github.com/Sarthakischauhan/somnia";
const screenshots = [
  { id: "memories", title: "Memory dashboard", file: "/landing/memories.webp", alt: "Somnia dashboard listing searchable project decisions, conventions and gotchas", caption: "Browse and filter what your agents learned across sessions." },
  { id: "memory-detail", title: "Memory detail", file: "/landing/memory-detail.webp", alt: "Somnia memory detail showing a saved decision and its supporting evidence", caption: "Inspect a single decision and the evidence behind it." },
  { id: "sessions", title: "Session handoffs", file: "/landing/sessions.webp", alt: "Somnia session handoffs showing a repository, branch, and saved agent checkpoint", caption: "See where the last agent stopped before you pick up the branch." },
];

const agents = [
  { id: "claude-code", title: "Claude Code", icon: Terminal, install: "claude plugin marketplace add Sarthakischauhan/somnia\nclaude plugin install somnia@somnia", next: "In Claude Code, check /hooks and /mcp. Use /somnia:continue to inspect the last handoff; the session-start hook also loads context." },
  { id: "codex", title: "Codex", icon: CodeXml, install: "./plugins/codex/install.sh", next: "Run the installer from your Somnia checkout. In Codex, run /hooks to review and approve the Somnia hooks. Reopen the repo to load context, or ask Codex to call continue_session." },
  { id: "grok", title: "Grok Build", icon: Zap, install: "./plugins/grok/install.sh", next: "Run the installer from your Somnia checkout. It installs capture hooks and configures MCP. Ask Grok to call continue_session; its hooks cannot inject context." },
  { id: "symphony", title: "Symphony", icon: AudioLines, install: "symphony plugins add ./plugins/symphony\nsymphony plugins enable somnia", next: "Run these commands from your Somnia checkout. Restart Symphony or run /reload, check /addons, then use /somnia-resume on the same repo and branch." },
];

const bootstrap = "uv tool install 'somnia-agent[mcp] @ git+https://github.com/Sarthakischauhan/somnia#subdirectory=agent'\nsomnia-agent login --api-url https://your-somnia-api.example";

function Snippet({ label, code }: { label: string; code: string }) {
  const [status, setStatus] = useState("");

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setStatus("Copied");
    } catch {
      setStatus("Copy unavailable; select the commands manually.");
    }
  }

  return (
    <div className={styles.snippet}>
      <div className={styles.snippetBar}>
        <span>{label}</span>
        <button type="button" aria-label={`Copy ${label} commands`} onClick={copy}><Copy size={13} aria-hidden="true" /> Copy</button>
      </div>
      <pre tabIndex={0} aria-label={`${label} commands`}><code>{code}</code></pre>
      <span role="status" className={status ? styles.copyStatus : "sr-only"}>{status}</span>
    </div>
  );
}

export function ProductGallery() {
  return (
    <Tabs.Root defaultValue="memories" className={styles.gallery}>
      <Tabs.List className={styles.tabs} aria-label="Dashboard screenshots">
        {screenshots.map(({ id, title }) => <Tabs.Tab className={styles.tab} key={id} value={id}>{title}</Tabs.Tab>)}
      </Tabs.List>
      {screenshots.map(({ id, file, title, alt, caption }) => (
        <Tabs.Panel key={id} value={id}>
          <figure>
            <div className={styles.stage}>
              <a href={file} target="_blank" rel="noopener noreferrer" aria-label={`Open full-size ${title} screenshot (new tab)`}>
                <Image src={file} width={1280} height={800} sizes="(max-width: 380px) calc(100vw - 32px), (max-width: 1200px) 92vw, 1100px" alt={alt} priority={id === "memories"} />
              </a>
            </div>
            <figcaption className={styles.caption}><span>{caption} Demo data.</span><a href={file} target="_blank" rel="noopener noreferrer">Full size <ExternalLink size={13} aria-hidden="true" /><span className="sr-only"> (new tab)</span></a></figcaption>
          </figure>
        </Tabs.Panel>
      ))}
    </Tabs.Root>
  );
}

export function Integrations() {
  return (
    <div className={styles.setup}>
      <Snippet label="Install the CLI and sign in" code={bootstrap} />
      <p className={styles.setupNote}>Replace the URL with your backend. The CLI prompts for your device token.</p>
      <Tabs.Root defaultValue="claude-code" className={styles.agents}>
        <Tabs.List className={styles.tabs} aria-label="Agent setup">
          {agents.map(({ id, title, icon: Icon }) => <Tabs.Tab className={styles.tab} key={id} value={id}><Icon size={15} aria-hidden="true" />{title}</Tabs.Tab>)}
        </Tabs.List>
        {agents.map(({ id, title, install, next }) => (
          <Tabs.Panel className={styles.agentPanel} key={id} value={id}>
            {id !== "claude-code" && <p className={styles.checkout}>Need the checkout? <code>git clone {repo}.git &amp;&amp; cd somnia</code></p>}
            <Snippet label={`Connect ${title}`} code={install} />
            <p>{next}</p>
            <a href={`${repo}/tree/main/plugins/${id}`}>Read the {title} guide <ArrowUpRight size={14} aria-hidden="true" /></a>
          </Tabs.Panel>
        ))}
      </Tabs.Root>
    </div>
  );
}
