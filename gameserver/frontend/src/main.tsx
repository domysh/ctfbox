import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { setAutoFreeze } from 'immer'
import App from './App.tsx'

// recharts 3.x's Brush stores the chart `data` array by reference in its Redux
// Toolkit store; immer's default auto-freeze then makes that array read-only,
// and a later mutation attempt by recharts throws. Disable it globally.
setAutoFreeze(false)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
