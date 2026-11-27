import type { Metadata } from "next";
import Link from "next/link";
import { ArrowDown, ArrowUpRight, GitBranch, Layers3 } from "lucide-react";

import { Integrations, ProductGallery } from "./landing-interactive";
import styles from "./landing.module.css";

const repository = "https://github.com/Sarthakischauhan/somnia";
const title = "Somnia — Shared memory for coding agents";
const description = "Somnia saves what your coding agent learned and where it stopped. Pick up the same repo and branch in Claude Code, Codex, Grok Build, or Symphony.";

export const metadata: Metadata = { title, description, openGraph: { title, description, type: "website" } };

const workflow = [
  { title: "Capture a session", detail: "Agent hooks record prompts, completed tools, and assistant turns while you work. Somnia saves rolling checkpoints, not just the final answer." },
  { title: "Keep the decisions", detail: "A background worker turns session history into searchable decisions, conventions, and gotchas. Inspect memories and review conflicts in the dashboard." },
  { title: "Resume in another agent", detail: "Open the same repo and branch to get the last checkpoint and relevant memories. The receiving agent gets a handoff, not a transcript dump." },
];

const questions = [
  { question: "Does Somnia move my files?", answer: "No. A handoff includes the goal, last recorded result, touched paths, and Git ref. Use the same worktree or transfer uncommitted changes separately." },
  { question: "Can I self-host it?", answer: "Yes. Somnia runs as an API, background worker, and Next.js dashboard, with Supabase Postgres and pgvector for storage. The setup guide covers local development and deployment." },
  { question: "Does dashboard sign-in connect my agents?", answer: "Not yet. Dashboard sign-in uses GitHub through Supabase. Each agent device needs its own Somnia token, issued by the operator for the same account." },
];

function Wordmark() {
  return <a className={styles.wordmark} href="#home"><span className={styles.brandMark} aria-hidden="true">s</span>somnia</a>;
}

export default function Home() {
  return (
    <div className={styles.site} id="home">
      <header className={styles.topbar}>
        <Wordmark />
        <nav aria-label="Main navigation">
          <a href="#product">Product</a>
          <a href="#how-it-works">How it works</a>
          <a href="#setup">Agent setup</a>
          <a href="#faq">FAQ</a>
          <a href={repository}>GitHub <ArrowUpRight size={13} aria-hidden="true" /></a>
        </nav>
        <Link className={`${styles.dashboard} ${styles.primary}`} href="/memories">Dashboard <ArrowUpRight size={14} aria-hidden="true" /></Link>
      </header>

      <main className={styles.main}>
        <header className={styles.hero}>
          <p className={styles.kicker}>Shared memory for coding agents</p>
          <h1><span>Switch agents.</span> <span>Keep the thread.</span></h1>
          <p className={styles.lede}>Somnia saves what your coding agent learned and where it stopped. Pick up in another agent without re-explaining the repo.</p>
          <div className={styles.actions}>
            <a className={styles.primary} href="#setup">Set up an agent <ArrowDown size={16} aria-hidden="true" /></a>
            <a className={styles.secondary} href="#product">Explore the dashboard</a>
          </div>
        </header>

        <section id="product" aria-label="Explore the Somnia dashboard">
          <ProductGallery />
        </section>

        <section className={styles.section} id="how-it-works" aria-labelledby="workflow-title">
          <p className={styles.kicker}>How it works</p>
          <h2 id="workflow-title">A handoff, not a history dump.</h2>
          <ul className={styles.workflow} role="list">
            {workflow.map(({ title, detail }) => <li key={title}><h3>{title}</h3><p>{detail}</p></li>)}
          </ul>
          <div className={styles.handoff}>
            <GitBranch size={22} aria-hidden="true" />
            <div><h3>Same repo. Same branch. Different agent.</h3><p>Claude Code stops after implementing webhook signing. Codex opens the branch, sees why only 5xx responses get retried, and picks up the missing test.</p></div>
          </div>
        </section>

        <section className={styles.section} id="setup" aria-labelledby="setup-title">
          <p className={styles.kicker}>Integrations</p>
          <h2 id="setup-title">Set up the agent you already use.</h2>
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
          <div><Layers3 size={23} aria-hidden="true" /><h2>Give your next session a head start.</h2></div>
          <div className={styles.actions}><a className={styles.primary} href="#setup">Set up Somnia <ArrowUpRight size={15} aria-hidden="true" /></a><a className={styles.secondary} href={repository}>View the source</a></div>
          <div className={styles.footerBottom}><Wordmark /><Link href="/memories">Open dashboard <ArrowUpRight size={14} aria-hidden="true" /></Link></div>
        </footer>
      </main>
    </div>
  );
}
