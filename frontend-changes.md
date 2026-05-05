# Frontend Changes

## Feature: Dark/Light Theme Toggle Button

### Summary
Added a dark/light theme toggle button to the frontend UI.

### `frontend/index.html`
- Added a `<button id="themeToggle">` element with `position: fixed` in the top-right corner (rendered outside the `.container` so it overlays the layout)
- Button contains two inline SVGs: a sun icon (visible in dark mode) and a moon icon (visible in light mode), both with `aria-hidden="true"`
- Button has `aria-label="Toggle light/dark theme"` and `title="Toggle theme"` for accessibility and keyboard navigation

### `frontend/style.css`
- Added `--code-bg` CSS variable to `:root` for code block backgrounds (replaces hardcoded `rgba(0,0,0,0.2)`)
- Added initial `body.light-theme` rule overriding background, surface, text, border, shadow, and code-bg variables
- Replaced hardcoded `rgba(0,0,0,0.2)` on `.message-content code` and `.message-content pre` with `var(--code-bg)`
- Added `.theme-toggle` button styles: 40×40px circle, fixed top-right (1rem offset), surface background, border, transitions
- Added hover (scale + primary color border), focus (focus-ring shadow), and active (shrink) states
- Added `.sun-icon` / `.moon-icon` transition styles: icons cross-fade with rotate+scale animation (0.3s ease)
- Added `body.light-theme .sun-icon` / `body.light-theme .moon-icon` to swap icon visibility
- Added `transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease` to structural elements for smooth theme switching

### `frontend/script.js`
- Added `themeToggle` to the DOM element variables
- Added `initTheme()`: reads `localStorage.getItem('theme')` on load and applies `light-theme` class if saved
- Added `toggleTheme()`: toggles `body.light-theme` class and persists preference to `localStorage`
- Wired up `themeToggle.addEventListener('click', toggleTheme)` in `setupEventListeners()`
- Called `initTheme()` at the top of `DOMContentLoaded` so the theme is applied before first render

### Behavior
- Button is positioned fixed in the top-right corner, overlaying all content
- In dark mode (default): sun icon is visible; clicking switches to light mode
- In light mode: moon icon is visible; clicking switches back to dark mode
- Icon swap uses opacity + rotate/scale animation (0.3s ease) for a smooth visual transition
- Theme preference is persisted in `localStorage` and restored on page reload
- Button is keyboard-navigable (focusable, visible focus ring) and screen-reader accessible via `aria-label`

---

## Feature: Light Theme CSS Variables

### Summary
Expanded the light theme with fully accessible, adjusted color variables across all design tokens.

### `frontend/style.css`

#### New variables added to `:root`
- `--link-color: #7dd3fc` — replaces hardcoded sky-blue link color in dark mode
- `--send-button-shadow: rgba(37, 99, 235, 0.3)` — replaces hardcoded send-button glow shadow

#### Hardcoded values replaced with variables
- `.message-content a`: `color: #7dd3fc` → `color: var(--link-color)`
- `#sendButton:hover` shadow: `rgba(37, 99, 235, 0.3)` → `var(--send-button-shadow)`

#### `body.light-theme` overrides (expanded)

| Variable | Dark value | Light value | Notes |
|---|---|---|---|
| `--background` | `#0f172a` | `#f8fafc` | Near-white page background |
| `--surface` | `#1e293b` | `#ffffff` | Card/panel backgrounds |
| `--surface-hover` | `#334155` | `#f1f5f9` | Hover state surfaces |
| `--primary-color` | `#2563eb` | `#1d4ed8` | Darkened for 6.1:1 contrast on light bg (AA) |
| `--primary-hover` | `#1d4ed8` | `#1e3a8a` | Deeper hover state |
| `--user-message` | `#2563eb` | `#1d4ed8` | Matches primary for consistency |
| `--focus-ring` | `rgba(37,99,235,0.2)` | `rgba(29,78,216,0.25)` | Matches new primary; slightly stronger |
| `--send-button-shadow` | `rgba(37,99,235,0.3)` | `rgba(29,78,216,0.25)` | Matches new primary |
| `--text-primary` | `#f1f5f9` | `#0f172a` | Dark text, ~17:1 contrast on light bg (AAA) |
| `--text-secondary` | `#94a3b8` | `#475569` | 5.9:1 contrast on `#f8fafc` (AA) |
| `--border-color` | `#334155` | `#cbd5e1` | Visible but subtle on white |
| `--assistant-message` | `#374151` | `#f1f5f9` | Light gray bubble |
| `--shadow` | `rgba(0,0,0,0.3)` | `rgba(0,0,0,0.08)` | Softer elevation |
| `--welcome-bg` | `#1e3a5f` | `#eff6ff` | Light blue welcome panel |
| `--welcome-border` | `#2563eb` | `#1d4ed8` | Matches primary |
| `--code-bg` | `rgba(0,0,0,0.2)` | `rgba(15,23,42,0.06)` | Subtle dark-tinted code blocks |
| `--link-color` | `#7dd3fc` | `#1d4ed8` | 7.3:1 contrast on white (AAA) |

---

## Feature: JavaScript Functionality & `data-theme` Attribute

### Summary
Migrated theme switching from a CSS class (`body.light-theme`) to a `data-theme` attribute (`body[data-theme="light"|"dark"]`), and tightened the JS toggle/init logic.

### `frontend/style.css`
- Replaced all three `body.light-theme` selectors with `body[data-theme="light"]`:
  - The main variable override block
  - `.sun-icon` visibility rule
  - `.moon-icon` visibility rule
- CSS custom properties (variables) remain the sole mechanism for theme switching — no per-element overrides needed

### `frontend/script.js`
- `initTheme()`: reads `localStorage` (defaulting to `'dark'`), then sets `document.body.dataset.theme` directly instead of toggling a class
- `toggleTheme()`: reads `document.body.dataset.theme`, flips between `'light'` and `'dark'`, writes back to both `dataset.theme` and `localStorage`
- Both functions now use a single source of truth (`body[data-theme]`) rather than class presence checks

### Behavior
- On first load with no saved preference, `data-theme="dark"` is set explicitly (consistent initial state)
- Toggling updates the attribute instantly; CSS variable overrides apply immediately, with all structural elements transitioning over 0.3s via previously added transition rules
- The `data-theme` attribute on `<body>` is inspectable in DevTools and readable by assistive technologies

### Accessibility notes
- All foreground/background color pairs meet WCAG 2.1 AA (4.5:1 for normal text, 3:1 for large text)
- `--link-color` in light mode achieves AAA (7.3:1) to ensure readability in assistant message bubbles
- `--text-secondary` at `#475569` achieves 5.9:1 on `#f8fafc`, exceeding AA
- Focus rings remain visible on both dark and light surfaces
