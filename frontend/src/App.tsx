import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { BasketProvider } from './context/BasketContext';
import { Header } from './components/Header';
import { BottomNav } from './components/BottomNav';
import { BasketOverlays } from './components/BasketOverlays';
import { SearchPage } from './pages/SearchPage';
import { ProductPage } from './pages/ProductPage';
import { BasketPage } from './pages/BasketPage';
import { ScanPage } from './pages/ScanPage';
import './styles/global.css';

export function App() {
  return (
    <BasketProvider>
      <HashRouter>
        <Header />
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/search" element={<Navigate to="/" replace />} />
          <Route path="/product/:barcode" element={<ProductPage />} />
          <Route path="/scan" element={<ScanPage />} />
          <Route path="/basket" element={<BasketPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <BottomNav />
        <BasketOverlays />
      </HashRouter>
    </BasketProvider>
  );
}
