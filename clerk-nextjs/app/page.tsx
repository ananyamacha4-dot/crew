import Link from "next/link";
import { Show, UserButton } from "@clerk/nextjs";

export default function Home() {
  return (
    <div className="home-root">
      <div className="auth-bg" aria-hidden>
        <div className="aurora aurora-1" />
        <div className="aurora aurora-2" />
        <div className="aurora aurora-3" />
        <div className="grid-overlay" />
        <div className="vignette" />
      </div>

      <header className="home-topbar">
        <Link href="/" className="home-brand">
          <span style={{ fontSize: 18, filter: "drop-shadow(0 0 10px rgba(168,85,247,0.6))" }}>
            {"⚡"}
          </span>
          <span className="home-brand-name">AI Builder</span>
        </Link>

        <div className="home-actions">
          <Show when="signed-out">
            <Link href="/sign-in" className="btn-ghost">
              Sign in
            </Link>
            <Link href="/sign-up" className="btn-primary">
              Get started
            </Link>
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </div>
      </header>

      <main className="home-hero">
        <span className="home-eyebrow">
          <span>{"✦"}</span> Multi-agent code generation
        </span>
        <h1 className="home-title">
          From a single prompt
          <br />
          to a runnable app.
        </h1>
        <p className="home-subtitle">
          Describe what you want. AI Builder plans, generates, and previews
          a full multi-page React app in seconds.
        </p>

        <div className="home-cta">
          <Show when="signed-out">
            <Link href="/sign-up" className="btn-primary">
              Create your account
            </Link>
            <Link href="/sign-in" className="btn-ghost">
              I already have one &rarr;
            </Link>
          </Show>
          <Show when="signed-in">
            <Link href="/" className="btn-primary">
              Open dashboard
            </Link>
          </Show>
        </div>
      </main>
    </div>
  );
}
