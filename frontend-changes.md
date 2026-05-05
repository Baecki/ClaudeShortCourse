# Frontend Changes: Dark/Light Theme Toggle Button

## Summary

Added a dark/light theme toggle button to the frontend UI.

## Files Modified

### `frontend/index.html`
- Added a `<button id="themeToggle">` element with `position: fixed` in the top-right corner (rendered outside the `.container` so it overlays the layout)
- Button contains two inline SVGs: a sun icon (visible in dark mode) and a moon icon (visible in light mode), both with `aria-hidden="true"`
- Button has `aria-label="Toggle light/dark theme"` and `title="Toggle theme"` for accessibility and keyboard navigation

### `frontend/style.css`
- Added `--code-bg` CSS variable to `:root` for code block backgrounds (replaces hardcoded `rgba(0,0,0,0.2)`)
- Added `body.light-theme` rule overriding key CSS variables: `--background`, `--surface`, `--surface-hover`, `--text-primary`, `--text-secondary`, `--border-color`, `--assistant-message`, `--shadow`, `--welcome-bg`, `--code-bg`
- Replaced hardcoded `rgba(0,0,0,0.2)` on `.message-content code` and `.message-content pre` with `var(--code-bg)`
- Added `.theme-toggle` button styles: 40×40px circle, fixed top-right (1rem offset), surface background, border, transitions
- Added hover (scale + primary color border), focus (focus-ring shadow), and active (shrink) states
- Added `.sun-icon` / `.moon-icon` transition styles: icons cross-fade with rotate+scale animation (0.3s ease)
- Added `body.light-theme .sun-icon` / `body.light-theme .moon-icon` to swap icon visibility
- Added `transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease` to structural elements (`body`, `.sidebar`, `.main-content`, `.chat-main`, `.chat-container`, `.chat-messages`, `.chat-input-container`, `.message.assistant .message-content`, `.message.welcome-message .message-content`, `.stat-item`) for smooth theme switching

### `frontend/script.js`
- Added `themeToggle` to the DOM element variables
- Added `initTheme()`: reads `localStorage.getItem('theme')` on load and applies `light-theme` class if saved
- Added `toggleTheme()`: toggles `body.light-theme` class and persists preference to `localStorage`
- Wired up `themeToggle.addEventListener('click', toggleTheme)` in `setupEventListeners()`
- Called `initTheme()` at the top of `DOMContentLoaded` (before other setup) so the theme is applied before first render

## Behavior

- Button is positioned fixed in the top-right corner, overlaying all content
- In dark mode (default): sun icon is visible; clicking switches to light mode
- In light mode: moon icon is visible; clicking switches back to dark mode
- Icon swap uses opacity + rotate/scale animation (0.3s ease) for a smooth visual transition
- Theme preference is persisted in `localStorage` and restored on page reload
- Button is keyboard-navigable (focusable, visible focus ring) and screen-reader accessible via `aria-label`
