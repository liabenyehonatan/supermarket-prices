import { BrowserMultiFormatReader } from '@zxing/browser';
import {
  BarcodeFormat, ChecksumException, DecodeHintType, FormatException, NotFoundException,
} from '@zxing/library';

// zxing reports "no barcode in this frame" through the scan callback as an error.
// Match by class, not `err.name`: minified production builds mangle class names, so
// a name check treats every empty frame as a camera failure and kills the scan.
export function isTransientScanError(err: unknown): boolean {
  return (
    err instanceof NotFoundException ||
    err instanceof ChecksumException ||
    err instanceof FormatException
  );
}

// Product barcodes only — skipping QR/Code128/etc. makes decoding faster and more reliable.
export function createBarcodeReader(): BrowserMultiFormatReader {
  const hints = new Map<DecodeHintType, unknown>([
    [DecodeHintType.POSSIBLE_FORMATS, [
      BarcodeFormat.EAN_13, BarcodeFormat.EAN_8, BarcodeFormat.UPC_A, BarcodeFormat.UPC_E,
    ]],
    [DecodeHintType.TRY_HARDER, true],
  ]);
  return new BrowserMultiFormatReader(hints, { delayBetweenScanAttempts: 150 });
}

// iOS Safari defaults to 640x480, too soft to resolve thin EAN bars.
export const SCAN_CONSTRAINTS: MediaStreamConstraints = {
  audio: false,
  video: {
    facingMode: { ideal: 'environment' },
    width: { ideal: 1280 },
    height: { ideal: 720 },
  },
};

export type CameraProblem = 'insecure' | 'unsupported' | 'denied' | 'unavailable';

export function classifyCameraError(err: unknown): CameraProblem {
  const name = (err as { name?: string } | null)?.name;
  return name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : 'unavailable';
}

// getUserMedia only exists in secure contexts (HTTPS or localhost) — on an iPhone
// opening the dev server over http://192.168.x.x, navigator.mediaDevices is undefined.
export function cameraSupportProblem(): CameraProblem | null {
  if (typeof window !== 'undefined' && !window.isSecureContext) return 'insecure';
  if (!navigator.mediaDevices?.getUserMedia) return 'unsupported';
  return null;
}

export const CAMERA_MESSAGES: Record<CameraProblem, string> = {
  insecure: 'הסריקה דורשת חיבור מאובטח (https). פתחי את האתר בכתובת https',
  unsupported: 'הדפדפן לא תומך בגישה למצלמה',
  denied: 'אין הרשאה למצלמה — אשרי גישה בהגדרות Safari ונסי שוב',
  unavailable: 'לא הצלחנו לגשת למצלמה',
};
