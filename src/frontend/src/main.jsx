import React from 'react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { trackViewportHeight } from './viewport.js'
import './styles.css'

// Before the first render, so the first layout uses a measured height rather
// than whatever `svh` resolves to while the toolbar is still moving.
trackViewportHeight()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
