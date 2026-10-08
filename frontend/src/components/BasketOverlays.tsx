import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, X } from 'lucide-react';
import { useBasket } from '../context/BasketContext';

/** App-root UI for baskets: the bottom notice and the "which basket?" picker. */
export function BasketOverlays() {
  const { notice, dismissNotice, picker, closePicker, baskets, activeId, pickBasket, pickNew } = useBasket();
  const [name, setName] = useState('');
  const [naming, setNaming] = useState(false);

  useEffect(() => { if (picker) { setName(''); setNaming(picker.mode === 'create'); } }, [picker]);
  useEffect(() => {
    if (!picker) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closePicker(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [picker, closePicker]);

  const title = picker?.mode === 'create' ? 'סל חדש' : picker?.mode === 'move' ? 'להעביר לאיזה סל?' : 'להוסיף לאיזה סל?';

  return (
    <>
      {notice && (
        <div className="undo-toast" role="status" onClick={dismissNotice}>
          <span>{notice.text}</span>
          {notice.actionLabel && (
            <button onClick={e => { e.stopPropagation(); notice.onAction?.(); }}>{notice.actionLabel}</button>
          )}
        </div>
      )}

      {picker && createPortal(
        <div className="sheet-backdrop" onClick={closePicker}>
          <div className="location-sheet basket-sheet" role="dialog" aria-label={title} onClick={e => e.stopPropagation()}>
            <div className="sheet-grab"><span className="sheet-handle" /></div>
            <div className="location-sheet-head">
              <strong>{title}</strong>
              <button className="location-sheet-close" onClick={closePicker} aria-label="סגור"><X size={18} strokeWidth={2.5} /></button>
            </div>
            <div className="location-list">
              {picker.mode !== 'create' && baskets.filter(b => picker.mode !== 'move' || b.id !== picker.fromId).map(b => {
                const count = b.items.reduce((s, i) => s + i.quantity, 0);
                return (
                  <button key={b.id} className="basket-row basket-row-main" onClick={() => pickBasket(b.id)}>
                    <span className="basket-row-text">
                      <span className="basket-row-name">{b.name}</span>
                      <span className="basket-row-meta">
                        {count === 1 ? 'פריט אחד' : `${count} פריטים`}{b.id === activeId ? ' · פעיל' : ''}
                      </span>
                    </span>
                  </button>
                );
              })}

              {naming ? (
                <div className="basket-row">
                  <input
                    className="basket-name-input"
                    autoFocus
                    placeholder="שם הסל, למשל: קניות לשישי"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') pickNew(name); }}
                    maxLength={30}
                    aria-label="שם הסל החדש"
                  />
                  <button className="btn btn-primary btn-sm" onClick={() => pickNew(name)}>יצירה</button>
                </div>
              ) : (
                <button className="basket-row-new" onClick={() => setNaming(true)}>
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
