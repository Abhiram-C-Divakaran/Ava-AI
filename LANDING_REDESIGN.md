# AvaAI landing-page redesign

## Scope and files

Modified: `index.html`.

Added:
- `assets/landing/landing.css` — landing-only design tokens, layout, responsive rules, animations, light theme, and chat styles.
- `assets/landing/landing.js` — content configuration, SVG icons, navigation, demo tabs, testimonial controls, FAQ, theme, walkthrough dialog, and existing-API chat adapter.
- `assets/landing/favicon.svg` — the existing three-circle AvaAI mark adapted as a favicon.
- `LANDING_REDESIGN.md` — this implementation and verification report.

No backend files, authentication pages, chat workspace, API routes, memory logic, adaptation logic, or other pages were changed for this task. Pre-existing modifications in configuration, LLM code, documentation, and evaluation files were left in place.

## Components

Semantic, framework-free sections: Navbar, Hero, FeatureGrid, HowItWorks, ProductDemo, StatsBar, Testimonials, FAQ, FinalCTA/Pricing, Footer, FloatingChat, and ProductWalkthrough. Content is generated from small configuration arrays where practical. No frontend build or additional runtime dependency is needed.

## Assets

- Existing `cute-ai-robot-chatbot-reading-a-book-on-transparent-background-free-png.webp` (390,096 bytes): primary hero, with explicit dimensions and high loading priority.
- Existing `pngegg.png` (856,390 bytes): FAQ robot, lazy loaded with explicit dimensions.
- Existing three-circle AvaAI logo geometry: reused in inline SVG and favicon.
- Local inline SVG interface icons; no icon package or network dependency.
- Inter and Caveat from Google Fonts, with system/cursive fallbacks.
- Planet, stars, glass panels, wave, glowing platform, and miniature planet are real CSS/HTML, not screenshot backgrounds.

## Responsive behavior and accessibility

Checked widths: 1440, 1200, 1024, 768, 480, and 360 pixels. No horizontal page overflow at these widths. Six feature columns on wide desktops, three on tablet/smaller desktop, two on intermediate narrow layouts, and one on phones. Hero text precedes artwork on narrow layouts; on phones the robot is positioned below the floating panels. Steps become vertical; demo sidebar is removed on phones while the complete conversation remains. The chat drawer is 410px wide on desktop and nearly fills a phone viewport.

Includes keyboard navigation, skip link, heading hierarchy, icon labels, visible focus, single-open FAQ with `aria-expanded`, keyboard demo tabs, theme toggle, modal Escape support, chat focus return, image alternatives, and reduced-motion rules.

## Chat integration

The landing page uses the existing signed session cookie and `neurosupport_user` identity convention. Identity is validated with the existing sessions endpoint. Signed-out users see the existing login/signup route inside the drawer. Opening the drawer does not navigate away.

Authenticated messages use `POST /api/chat/stream` with the existing payload and SSE events (`chunk`, `status`, `done`). The returned session ID is saved under a user-specific local-storage key, and history reloads through the existing session-messages endpoint. Responses are rendered as plain text for safe handling of model output. Helpful/not-helpful controls use `POST /api/feedback`. The backend remains responsible for persistence, context, memory, tools, and adaptation. Full workspace features remain available through its existing route.

The adapter handles authentication expiry, missing sessions, failed requests, rate limiting, interrupted streams, and a two-minute response timeout. Signed-in CTA routing goes to `/chat.html`; signed-out routing retains `/auth.html?mode=signup`.

## Marketing and unavailable assets

`marketingContent` in `landing.js` explicitly marks all four requested statistics and all three named testimonials as unverified marketing placeholders. Initials replace customer photos because no appropriate consented avatar assets exist. The supplied social-proof/CTA copy also remains marketing copy, not a claim verified by this implementation.

No video file or official social destinations were found. Watch Video opens an accessible product walkthrough explaining that the video is unavailable and linking to the interactive demo. Social icons are disabled with coming-soon labels until their URLs are configured. Contact uses the address already present in the existing Terms page. Pricing links to the free-start CTA.

The demo uses “Would you like to make this plan your own?” rather than implying a calendar integration that the current project does not provide.

## Verification and exact results

1. `.venv\Scripts\python.exe -m unittest test_adaptation.py test_security.py test_reliability.py -v`
   - **86 tests ran in 190.501 seconds: 85 passed, 1 failed.**
   - Failure: `test_15_chat_rate_limiting`, expected HTTP 429, got HTTP 200.
   - Its repeated requests triggered external memory extraction calls taking about 7.2 seconds each. The request sequence crossed the one-minute rate window, invalidating the test's timing assumption.
2. Re-ran only `TestSecurityHardened('test_15_chat_rate_limiting')` under `unittest.mock.patch('memory.call_llm', return_value='{}')` in a temporary runner.
   - **1 test passed in 3.076 seconds.** No application or existing test file was modified to obtain this result.
3. `node --check assets/landing/landing.js` — **passed**.
4. `git diff --check -- index.html assets/landing` — **passed** (Git emitted only its LF-to-CRLF advisory).
   - Repository-wide `git diff --check` also reported pre-existing whitespace in `llm.py`; that unrelated file was not changed.
5. HTTP checks for `/`, both new CSS/JS files, favicon, `/health`, `/ready`, `/auth.html`, `/chat.html`, `/privacy.html`, and `/terms.html` — **all HTTP 200**. Both robot images loaded successfully.
6. Browser checks — **passed**: six responsive widths, mobile menu, FAQ open/close state, signed-out drawer and hidden input, product-demo tab updates, theme toggle, walkthrough modal, signup CTA, and no captured page-console errors.
7. Isolated browser integration on port 8001 with a temporary SQLite database and synthetic test identity:
   - Actual existing streaming endpoint returned HTTP 200 and a completed streamed response.
   - Session and messages persisted and reloaded after a page refresh.
   - Existing feedback endpoint accepted a helpful vote, HTTP 200.
   - Authenticated CTA navigated to `/chat.html`, HTTP 200.
   - External LLM generation and memory extraction were stubbed for deterministic testing; this does **not** verify live Groq availability or model response quality.
   - Temporary fixture server was stopped after verification. The normal app remains running on port 8000.

No build command is applicable: FastAPI serves the HTML/CSS/JS directly. The separate legacy live-model comprehensive script was not run; it is not part of the documented 86-test regression command.

## Remaining visual differences

The existing robot is reading a book rather than walking/waving like the reference. Space/planet effects are CSS artwork and are less photographic than the supplied render. Testimonial avatars use initials. The added FAQ extends the page relative to the full-page reference. Responsive layouts intentionally rearrange the composition for legibility. No reference screenshot was used as a full-page or hero background.
