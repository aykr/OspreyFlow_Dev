# The toolbar's key: T on the graph's canvas (the owner's ruling, 16 November 2026)

The first key, Alt+Shift+T, was found by the lane review to be Chrome's own key on Windows and Linux ("focus the first
item in the toolbar"). The owner: do not override a browser's accessibility shortcut; pick a free combination, checked
against Chrome, Edge, Firefox and Safari on Windows, macOS and Linux, and NVDA, JAWS and VoiceOver.

**Ruled: T, with no modifier, active only while the graph's canvas has focus**, as the canvas's F, L and G are. The Map
has the buttons only; T on the map's container is on v0.6.1's list for the platform lane.

## Why no combination with a modifier

- Shift+Alt+T: Chrome's (and Edge's) focus-the-toolbar on Windows and Linux; Alt+letter opens browser menus on Windows.
- Alt+Shift+letter: Firefox's modifier for a page's access keys on Windows and Linux.
- Ctrl+Alt: AltGr on European layouts (it types characters); Ctrl+Alt+T opens a terminal on Ubuntu.
- Ctrl+Option: VoiceOver's own modifier on the Mac.
- Ctrl+Shift and Cmd+Shift letters: crowded across Chrome, Edge, Firefox and Safari (Ctrl+Shift+T and Shift-Command-T
  reopen a tab), and any found free today can be taken by a later release.

## Why T on the canvas

1. No browser binds a bare letter while a page element has focus. Firefox's find-as-you-type is off by default and is
   pre-empted where the page handles the key (the canvas prevents it); its Quick Find keys are / and '.
2. The canvas is `role="application"`: NVDA and JAWS pass keys to it rather than using them as quick keys, as the canvas's
   F, L, G and arrows already depend on. Elsewhere T stays the screen readers' "next table". VoiceOver's single-key Quick
   Nav (VO-Q) applies outside application regions.
3. WCAG 2.1.4 (A) allows a single-character shortcut that is active only on focus of its component.
4. The canvas's own keys (F, L, G, \, Enter, Esc, Delete, Backspace, arrows, Shift+F10, ContextMenu) leave T free; the
   Glass's global keys are / and ?.

**Cost:** with focus elsewhere the key does nothing; the buttons are always one Tab stop away.

**Caveat:** found from the vendors' help pages and accessibility guides as indexed by a web search, not tested with a live
NVDA, JAWS or VoiceOver. One report says some JAWS versions keep some keys even inside `role="application"`; that holds
for every existing canvas key too.

## Sources

- Chrome keyboard shortcuts (Shift+Alt+T, F10): https://support.google.com/chrome/answer/157179
- Microsoft Edge keyboard shortcuts: https://support.microsoft.com/en-us/edge/microsoft-edge-keyboard-shortcuts
- Firefox keyboard shortcuts: https://support.mozilla.org/kb/Keyboard+shortcuts
- Firefox Quick Find (/ and ', find as you type off by default): https://support.mozilla.org/en-US/kb/search-contents-current-page-text-or-links
- Safari keyboard shortcuts (Shift-Command-T): https://support.apple.com/guide/safari/cpsh003/mac
- NVDA commands quick reference: https://api.nvaccess.org/documentation/keyCommands.html
- JAWS navigation quick keys: https://support.freedomscientific.com/SurfsUp/QuickKeys.htm and
  https://support.freedomscientific.com/content/html/jawshq/JAWS-Keystrokes.html
- VoiceOver Quick Nav (VO-Q) and the VO modifier: https://support.apple.com/guide/voiceover/vo27943/mac
- Browse, focus and application modes: https://www.accessibility-developer-guide.com/knowledge/screen-readers/desktop/browse-focus-modes/
- WCAG 2.1.4 Character Key Shortcuts: https://www.w3.org/WAI/WCAG21/Understanding/character-key-shortcuts

**Held by:** `keyboard.spec.ts` *t-on-the-canvas-hides-and-shows-the-toolbar* (T on the focused canvas both ways, focus
kept; T on a toolbar button, on the case line, in the Layout picker, and Alt+Shift+T, each doing nothing),
`App.chrome.test.tsx`, `canvas/toolbarVisibility.test.ts`, `welcome/WorkspaceWelcome.test.tsx`.
