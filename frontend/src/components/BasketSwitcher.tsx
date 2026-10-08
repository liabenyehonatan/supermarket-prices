import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Check, Pencil, Trash2, Plus, X } from 'lucide-react';
import { useBasket } from '../context/BasketContext';
import { timeAgo } from '../lib/basketCompare';

function fmt(p: number) { return `₪${p.toFixed(2)}`; }

/** Header control on the basket page: shows the active basket and opens the list of all baskets. */
export function BasketSwitcher({ variant = 'title' }: { variant?: 'title' | 'pill' }) {
  const { baskets, active, setActive, createBasket, renameBasket, deleteBasket } = useBasket();
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  function close() { setOpen(false); setEditingId(null); setCreating(false); }

  function commitRename(id: string) {
    renameBasket(id, draft);
    setEditingId(null);
  }

  function commitCreate() {
    createBasket(draft);
    setDraft(''); setCreating(false); close();
  }

  return (
    <>
      <button className={variant === 'pill' ? 'basket-pill' : 'basket-switcher'} onClick={() => setOpen(true)} aria-label={`סל פעיל: ${active.name}. החלפה`}>
        <span className="basket-dot" style={{ background: active.color }} />
        <span className={variant === 'pill' ? 'basket-pill-name' : 'basket-switcher-name'}>{active.name}</span>
        <ChevronDown size={variant === 'pill' ? 13 : 16} strokeWidth={2} />
      </button>

      {open && createPortal(
        <div className="sheet-backdrop" onClick={close}>
          <div className="location-sheet basket-sheet" role="dialog" aria-label="הסלים שלי" onClick={e => e.stopPropagation()}>
            <div className="sheet-grab"><span className="sheet-handle" /></div>
            <div className="location-sheet-head">
              <strong>הסלים שלי</strong>
              <button className="location-sheet-close" onClick={close} aria-label="סגור"><X size={18} strokeWidth={2.5} /></button>
            </div>

            <div className="location-list">
              {baskets.map(b => {
                const count = b.items.reduce((s, i) => s + i.quantity, 0);
                const isActive = b.id === active.id;
                return (
                  <div key={b.id} className={`basket-row${isActive ? ' active' : ''}`}>
                    {editingId === b.id ? (
                      <input
                        className="basket-name-input"
                        autoFocus
                        value={draft}
                        onChange={e => setDraft(e.target.value)}
                        onBlur={() => commitRename(b.id)}
                        onKeyDown={e => { if (e.key === 'Enter') commitRename(b.id); if (e.key === 'Escape') setEditingId(null); }}
                        maxLength={30}
                        aria-label="שם הסל"
                      />
                    ) : (
                      <button className="basket-row-main" onClick={() => { setActive(b.id); close(); }}>
                        <span className="basket-dot" style={{ background: b.color }} />
                        <span className="basket-row-text">
                          <span className="basket-row-name">{b.name}</span>
                          <span className="basket-row-meta">
                            {count === 1 ? 'פריט אחד' : `${count} פריטים`}{b.lastCompare ? ` · ${fmt(b.lastCompare.total)} ${timeAgo(b.lastCompare.at)}` : ''}
                          </span>
                        </span>
                        {isActive && <Check size={17} strokeWidth={2.5} />}
                      </button>
                    )}
                    <button className="basket-icon-btn" aria-label={`שינוי שם ${b.name}`}
                      onMouseDown={e => e.preventDefault()}
                      onClick={() => { setDraft(b.name); setEditingId(b.id); }}>
                      <Pencil size={15} strokeWidth={1.8} />
                    </button>
                    <button className="basket-icon-btn danger" aria-label={`מחיקת ${b.name}`} onClick={() => deleteBasket(b.id)}>
                      <Trash2 size={15} strokeWidth={1.8} />
                    </button>
                  </div>
                );
              })}

              {creating ? (
                <div className="basket-row">
                  <input
                    className="basket-name-input"
                    autoFocus
                    placeholder="שם הסל, למשל: קניות לשישי"
                    value={draft}
                    onChange={e => setDraft(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') commitCreate(); if (e.key === 'Escape') setCreating(false); }}
                    maxLength={30}
                    aria-label="שם הסל החדש"
                  />
                  <button className="btn btn-primary btn-sm" onClick={commitCreate}>יצירה</button>
                </div>
              ) : (
                <button className="basket-row-new" onClick={() => { setDraft(''); setCreating(true); }}>
                  <Plus size={17} strokeWidth={2.2} /> סל חדש
                </button>
              )}
            </div>
          </div>
        </div>,
        document.body
      )}

    </>
  );
}

