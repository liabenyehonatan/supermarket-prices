import { CloudOff } from 'lucide-react';

/** "Something went wrong, try again": kept apart from the "nothing found" empty state, which looks the same but means something else. */
export function ErrorState({ title = 'משהו השתבש', text, onRetry, compact = false }: {
  title?: string;
  text: string;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div className="empty-state" role="alert" style={compact ? { padding: '24px 0' } : undefined}>
      <div className="empty-state-icon"><CloudOff size={28} strokeWidth={1.5} /></div>
      <div className="empty-state-title">{title}</div>
      <div className="empty-state-desc">{text}</div>
      {onRetry && <button className="btn btn-secondary btn-sm" onClick={onRetry}>נסו שוב</button>}
    </div>
  );
}
