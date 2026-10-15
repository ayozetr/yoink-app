// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Self-hosted fonts (bundled, no network): Gloock for display, Inter for UI.
import '@fontsource/gloock/400.css'
import '@fontsource-variable/inter'
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
