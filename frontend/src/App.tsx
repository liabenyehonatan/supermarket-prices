import { lazy, Suspense, useLayoutEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigationType } from 'react-router-dom';
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
const DealsPage = lazy(() => import('./pages/DealsPage').then(m => ({ default: m.DealsPage })));
const ScanPage = lazy(() => import('./pages/ScanPage').then(m => ({ default: m.ScanPage })));
import './styles/global.css';
import './styles/redesign.css';

// Once the home page is up, fetch the product and basket pages in the background so opening one is instant.
if (typeof window !== 'undefined') {
  const prefetch = () => { void import('./pages/ProductPage'); void import('./pages/BasketPage'); };
  const idle = (window as unknown as { requestIdleCallback?: (cb: () => void) => void }).requestIdleCallback;
  window.addEventListener('load', () => (idle ? idle(prefetch) : setTimeout(prefetch, 1500)));
}

/** A new page starts at its top. Going back to the home page is left alone: it restores its own search and scroll. */
function ScrollToTopOnNavigate() {
  const { pathname } = useLocation();
  const type = useNavigationType();
  useLayoutEffect(() => {
    if (type === 'POP' && pathname === '/') return;
    // 'instant': the page scrolls smoothly (html has scroll-behavior: smooth), which would play out over the new page
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' as ScrollBehavior });
  }, [pathname, type]);
  return null;
}

export function App() {
  return (
    <ErrorBoundary>
    <BasketProvider>
      {/* startTransition: the page you are on stays until the next one (its code included) is ready, so there is no blank frame between them */}
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ScrollToTopOnNavigate />
        <Header />
        <Suspense fallback={<div className="page-loading" aria-busy="true" style={{ minHeight: '60vh' }} />}>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/search" element={<Navigate to="/" replace />} />
          <Route path="/product/:barcode" element={<ProductPage />} />
          <Route path="/scan" element={<ScanPage />} />
          <Route path="/basket" element={<BasketPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/promotions" element={<DealsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        <SiteFooter />
        <BottomNav />
        <BasketOverlays />
      </BrowserRouter>
    </BasketProvider>
    </ErrorBoundary>
  );
}
