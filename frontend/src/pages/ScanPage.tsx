import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, Barcode } from 'lucide-react';
import type { BrowserMultiFormatReader } from '@zxing/browser';
import {
  CAMERA_MESSAGES, SCAN_CONSTRAINTS, cameraSupportProblem, classifyCameraError,
  createBarcodeReader, isTransientScanError,
} from '../lib/scanner';
import { compareProduct } from '../api/client';

export function ScanPage() {
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<{ stop: () => void } | null>(null);
  const readerRef = useRef<BrowserMultiFormatReader | null>(null);
  const started = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<string | null>(null);
  const [manual, setManual] = useState('');

  const stop = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
    readerRef.current = null;
  }, []);

  // Product barcodes only identify one product, so go straight to its page; unknown codes stay here.
  const handleCode = useCallback(async (code: string) => {
    stop();
    try {
      await compareProduct(code);
      navigate(`/product/${code}`, { replace: true });
    } catch {
      setNotFound(code);
    }
  }, [navigate, stop]);

  const start = useCallback(async () => {
    setError(null);
    setNotFound(null);
    const unsupported = cameraSupportProblem();
    if (unsupported) { setError(CAMERA_MESSAGES[unsupported]); return; }
    try {
      const reader = createBarcodeReader();
      readerRef.current = reader;
      controlsRef.current = await reader.decodeFromConstraints(
        SCAN_CONSTRAINTS,
        videoRef.current!,
        (result, err) => {
          if (result) {
            void handleCode(result.getText());
          } else if (err && !isTransientScanError(err)) {
            setError(CAMERA_MESSAGES.unavailable);
            stop();
          }
        }
      );
    } catch (err) {
      setError(CAMERA_MESSAGES[classifyCameraError(err)]);
    }
  }, [handleCode, stop]);

  useEffect(() => {
    if (!started.current) { started.current = true; void start(); }
    return stop;
  }, [start, stop]);

  const submitManual = () => { if (manual) void handleCode(manual); };

  return (
    <div className="scan-page">
      <video ref={videoRef} className="scan-video" autoPlay muted playsInline />
      <div className="scan-shade"><div className="scan-frame" /></div>

      <button className="scan-close" onClick={() => navigate('/', { replace: true })} aria-label="סגור">
        <X size={22} strokeWidth={2.5} />
      </button>

      <div className="scan-bottom">
        {error ? (
          <p className="scan-msg scan-msg-error">{error}</p>
        ) : notFound ? (
          <p className="scan-msg">
            לא מצאנו מוצר עם הברקוד {notFound}{' '}
            <button className="scan-retry" onClick={() => void start()}>סרקי שוב</button>
          </p>
        ) : (
          <p className="scan-msg">כוונו את המצלמה אל הברקוד</p>
        )}
        <div className="scan-manual">
          <input
            type="number"
            inputMode="numeric"
            className="scan-manual-input"
            placeholder="או הקלידו מספר ברקוד"
            value={manual}
            onChange={e => setManual(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submitManual()}
            aria-label="ברקוד מוצר"
          />
          <button className="scan-manual-btn" disabled={!manual} onClick={submitManual} aria-label="חיפוש">
            <Barcode size={18} strokeWidth={2} />
          </button>
        </div>
      </div>
    </div>
  );
}
