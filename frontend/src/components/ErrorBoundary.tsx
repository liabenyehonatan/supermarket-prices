import { Component, type ReactNode } from 'react';
import { reloadOnceForNewVersion } from '../lib/staleChunk';

/** Catches a rendering error anywhere below it, so a bug shows a message and a way out instead of a white screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error('Unhandled UI error', error);
    // A page opened before a new version went live asks for files that no longer exist: load the new version.
    if (/dynamically imported module|Importing a module script failed|Loading chunk/i.test(String((error as Error)?.message ?? error))) {
      reloadOnceForNewVersion();
    }
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="empty-state" role="alert" style={{ paddingTop: 80 }}>
        <div className="empty-state-title">משהו השתבש</div>
        <div className="empty-state-desc">אירעה שגיאה בלתי צפויה. אפשר לרענן את הדף ולנסות שוב.</div>
        <button className="btn btn-primary" onClick={() => window.location.assign('/')}>
          חזרה לדף הבית
        </button>
      </div>
    );
  }
}
