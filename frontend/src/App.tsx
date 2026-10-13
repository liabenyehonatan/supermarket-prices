import { lazy, Suspense } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { BasketProvider } from './context/BasketContext';
import { Header } from './components/Header';
import { BottomNav } from './components/BottomNav';
import { BasketOverlays } from './components/BasketOverlays';
import { SearchPage } from './pages/SearchPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { SiteFooter } from './components/SiteFooter';

// The home page loads at once; the other pages (and the barcode scanner library inside ScanPage) are
// fetched when first visited, which keeps the first download small.
const ProductPage = lazy(() => import('./pages/ProductPage').then(m => ({ default: m.ProductPage })));
const BasketPage = lazy(() => import('./pages/BasketPage').then(m => ({ default: m.BasketPage })));
const AboutPage = lazy(() => import('./pages/AboutPage').then(m => ({ default: m.AboutPage })));
const ScanPage = lazy(() => import('./pages/ScanPage').then(m => ({ default: m.ScanPage })));
import './styles/global.css';

// Once the home page is up, fetch the product and basket pages in the background so opening one is instant.
if (typeof window !== 'undefined') {
  const prefetch = () => { void import('./pages/ProductPage'); void import('./pages/BasketPage'); };
  const idle = (window as unknown as { requestIdleCallback?: (cb: () => void) => void }).requestIdleCallback;
  window.addEventListener('load', () => (idle ? idle(prefetch) : setTimeout(prefetch, 1500)));
}

export function App() {
  return (
    <ErrorBoundary>
    <BasketProvider>
      <HashRouter>
        <Header />
        <Suspense fallback={<div className="page-loading" aria-busy="true" style={{ minHeight: '60vh' }} />}>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/search" element={<Navigate to="/" replace />} />
          <Route path="/product/:barcode" element={<ProductPage />} />
          <Route path="/scan" element={<ScanPage />} />
          <Route path="/basket" element={<BasketPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        <SiteFooter />
        <BottomNav />
        <BasketOverlays />
      </HashRouter>
    </BasketProvider>
    </ErrorBoundary>
  );
}
