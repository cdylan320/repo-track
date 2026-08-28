import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { ActivityPage } from './pages/Activity'
import { OverviewPage } from './pages/Overview'
import { RelayDetailPage } from './pages/RelayDetail'
import { RelaysPage } from './pages/Relays'
import { SettingsPage } from './pages/Settings'
import { StoreProvider } from './store'

export default function App() {
  return (
    <StoreProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/accounts" element={<RelaysPage />} />
            <Route path="/accounts/:id" element={<RelayDetailPage />} />
            <Route path="/relays" element={<Navigate to="/accounts" replace />} />
            <Route path="/relays/:id" element={<Navigate to="/accounts" replace />} />
            <Route path="/activity" element={<ActivityPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </StoreProvider>
  )
}
