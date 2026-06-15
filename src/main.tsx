import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n'
import App from './App.tsx'
import { resolveApiBase } from './lib/apiBase'

// Learn the backend's real port (the desktop app may fall back off 8756 when
// it's taken) before the first request fires, so every call — REST and the
// download WebSocket — targets the right port from the start.
await resolveApiBase()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
