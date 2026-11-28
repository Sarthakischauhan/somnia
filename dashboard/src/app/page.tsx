import type { Metadata } from "next";
import Link from "next/link";
import { ArrowDown, ArrowRight, ArrowUpRight, CircleCheck, GitBranch, Layers3, MoonStar, Radio } from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { Integrations, ProductGallery } from "./landing-interactive";
import styles from "./landing.module.css";

const repository = "https://github.com/Sarthakischauhan/somnia";
const title = "Somnia | Shared memory for coding agents";
const description = "Carry project decisions, active work, and tracked tasks across coding agents. Somnia captures session events and prepares a handoff for the same repo and branch.";

export const metadata: Metadata = {
  title,
  description,
  openGraph: { title, description, type: "website" },
  twitter: { card: "summary_large_image", title, description },
};

const workflow = [
  { icon: Radio, title: "Capture while you work", detail: "Installed hooks send prompts, completed tools, and assistant turns. Rolling checkpoints record where the agent left off." },
  { icon: MoonStar, title: "Consolidate in the background", detail: "The worker redacts and embeds captured events. Scheduled dreaming turns new session history into searchable decisions, conventions, and gotchas, and merges or supersedes related memories." },
  { icon: GitBranch, title: "Resume on the same branch", detail: "The next agent can retrieve the latest checkpoint, tracked open tasks, and relevant memories ranked within a token budget." },
];

const questions = [
  { question: "What does a handoff include?", answer: "The goal, last recorded result, next steps, touched paths, and Git ref. Use the same worktree or transfer uncommitted changes separately." },
  { question: "Can I self-host Somnia?", answer: "Yes. Somnia runs as an API, a background worker, and a Next.js dashboard, with Supabase Postgres and pgvector for storage." },
  { question: "How do I connect an agent to my account?", answer: "Sign in to the dashboard with GitHub. To connect an agent, sign in through the CLI with a device token issued by your Somnia operator for the same account." },
];

function Wordmark() {
  return <a className={styles.wordmark} href="#home"><BrandMark />Somnia</a>;
}

function HandoffExample() {
  return (
    <figure className={styles.example} aria-label="Example handoff from Claude Code to Codex">
      <div className={styles.examplePanel}>
        <div className={styles.exampleTop}><span><GitBranch size={15} aria-hidden="true" /> feature/webhook-signing</span><span>Example handoff</span></div>
        <div className={styles.exampleBody}>
          <div className={styles.exampleAgents}><span>Claude Code</span><ArrowRight size={16} aria-hidden="true" /><span>Codex</span></div>
          <h2>Finish webhook signing</h2>
          <dl>
            <div><dt><CircleCheck size={16} aria-hidden="true" /> Last checkpoint</dt><dd>Signature validation is implemented.</dd></div>
            <div><dt><Layers3 size={16} aria-hidden="true" /> Project decision</dt><dd>Retry only when the receiver returns 5xx.</dd></div>
            <div><dt><ArrowRight size={16} aria-hidden="true" /> Open task</dt><dd>Add a test for an invalid signature.</dd></div>
          </dl>
        </div>
      </div>
    </figure>
  );
}

export default function Home() {
  return (
    <div className={styles.site} id="home">
      <header className={styles.topbar}>
        <Wordmark />
        <nav aria-label="Main navigation">
          <a href="#product">Dashboard preview</a>
          <a href="#how-it-works">How it works</a>
          <a href="#setup">Agent setup</a>
          <a href={repository}>GitHub <ArrowUpRight size={13} aria-hidden="true" /></a>
        </nav>
        <Link className={`${styles.dashboard} ${styles.secondary}`} href="/memories">Open dashboard <ArrowUpRight size={14} aria-hidden="true" /></Link>
      </header>

      <main className={styles.main}>
        <header className={styles.hero}>
          <div>
            <p className={styles.kicker}>Shared memory for coding agents</p>
            <h1>Switch agents.<br /><em>Keep the context.</em></h1>
            <p className={styles.lede}>Somnia saves project decisions and where work stopped. Open the same repo and branch in another agent and pick up with a checkpoint, relevant memories, and tracked open tasks.</p>
            <div className={styles.actions}>
              <a className={styles.primary} href="#setup">Connect an agent <ArrowDown size={16} aria-hidden="true" /></a>
              <a className={styles.secondary} href={`${repository}#setup`}>Self-host Somnia <ArrowUpRight size={15} aria-hidden="true" /></a>
            </div>
          </div>
          <HandoffExample />
        </header>

        <section id="product" className={styles.section} aria-labelledby="product-title">
          <p className={styles.kicker}>Somnia dashboard</p>
          <h2 id="product-title">See what your agents remember.</h2>
          <p className={styles.sectionIntro}>Browse saved decisions and their evidence, inspect session checkpoints, and review conflicts and dreaming runs.</p>
          <ProductGallery />
        </section>

        <section className={styles.section} id="how-it-works" aria-labelledby="workflow-title">
          <p className={styles.kicker}>How it works</p>
          <h2 id="workflow-title">From session events to a handoff.</h2>
          <ul className={styles.workflow} role="list">
            {workflow.map(({ icon: Icon, title, detail }) => (
              <li key={title}><Icon size={22} aria-hidden="true" /><h3>{title}</h3><p>{detail}</p></li>
            ))}
          </ul>
          <a className={styles.textLink} href={`${repository}#dreaming`}>Read how dreaming works <ArrowUpRight size={15} aria-hidden="true" /></a>
        </section>

        <section className={styles.section} id="setup" aria-labelledby="setup-title">
          <p className={styles.kicker}>Integrations</p>
          <h2 id="setup-title">Connect the agent you already use.</h2>
          <p className={styles.sectionIntro}>Start with a <a href={`${repository}#setup`}>running Somnia backend</a> and a per-device token issued by its operator. Install the CLI once per device, then connect your agent.</p>
          <Integrations />
        </section>

        <section className={styles.section} id="faq" aria-labelledby="faq-title">
          <h2 id="faq-title">Frequently asked questions</h2>
          <div className={styles.faq}>
            {questions.map(({ question, answer }) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}
          </div>
        </section>

        <footer className={styles.footer}>
          <Wordmark />
          <div><a href={repository}>GitHub <ArrowUpRight size={14} aria-hidden="true" /></a><Link href="/memories">Open dashboard <ArrowUpRight size={14} aria-hidden="true" /></Link></div>
        </footer>
      </main>
    </div>
  );
}
