import Link from "next/link";

type AuthShellProps = {
  title: string;
  subtitle: string;
  footerText: string;
  footerLinkText: string;
  footerLinkHref: string;
  children: React.ReactNode;
};

export function AuthShell({
  title,
  subtitle,
  footerText,
  footerLinkText,
  footerLinkHref,
  children,
}: AuthShellProps) {
  return (
    <main className="auth-root">
      <div className="auth-bg">
        <div className="aurora aurora-1" />
        <div className="aurora aurora-2" />
        <div className="aurora aurora-3" />
        <div className="grid-overlay" />
        <div className="vignette" />
      </div>

      <div className="auth-stage">
        <header className="auth-brand">
          <Link href="/" className="auth-brand-link">
            <span className="auth-brand-mark">{"⚡"}</span>
            <span className="auth-brand-name">AI Builder</span>
          </Link>
          <span className="auth-brand-sub">prompt &rarr; runnable app</span>
        </header>

        <section className="auth-card">
          <div className="auth-card-glow" aria-hidden />
          <div className="auth-card-inner">
            <div className="auth-heading">
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>

            <div className="auth-form-wrap">{children}</div>

            <p className="auth-footer">
              {footerText}{" "}
              <Link href={footerLinkHref} className="auth-footer-link">
                {footerLinkText}
              </Link>
            </p>
          </div>
        </section>

        <footer className="auth-legal">
          <span>&copy; {new Date().getFullYear()} AI Builder</span>
          <span className="dot">&middot;</span>
          <a href="#" className="muted-link">Terms</a>
          <span className="dot">&middot;</span>
          <a href="#" className="muted-link">Privacy</a>
        </footer>
      </div>
    </main>
  );
}
