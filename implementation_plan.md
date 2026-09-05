# VoiceGuard UI Overhaul Plan

You requested an exact match of the provided UI mockup. This involves a complete visual refactoring of the main dashboard to match the sizes, fonts, colors, and design down to the pixel. 

## Proposed Changes

### 1. Global Styles (`frontend/src/app/globals.css`)
- **Theme Adjustments:** Shift the background to a deeper, flatter dark tone (`#0f0f11`) to match the mockup.
- **Card Backgrounds:** Update panels and cards to use the exact `#1c1c1f` color with softer, rounded borders (`border-radius: 12px`).
- **Typography:** Ensure global usage of `Inter` for standard text and a crisp monospace font (`JetBrains Mono` or similar) for all technical data (Call IDs, timestamps, logs).

### 2. Main Dashboard Layout (`frontend/src/app/page.tsx`)
- **Header:** Remove the centered statistics from the top bar. Keep only the "VoiceGuard" title on the left, and the "SYSTEM ACTIVE" pill on the right (alongside the View Reports button).
- **Right Panel Split:** The rightmost panel will be split vertically. The top 60% will house the `DetectionLog`, and the bottom 40% will be a new `StatisticsPanel` to replace the stats removed from the header.

### 3. Active Calls Panel (`ActiveCallsList.tsx`)
- **Card Redesign:** 
  - Arrange the Phone Number and Timer (e.g., `00:04:03`) vertically on the left.
  - Position the risk badge (e.g., `MEDIUM RISK`) on the top right.
  - Implement the specific glowing amber border for medium-risk calls exactly as shown.
  - Render a mini-waveform spanning the entire bottom width of the card.

### 4. Call Analysis Panel (`CallAnalysis.tsx`)
- **Header:** Display the Call ID prominently at the top in a large monospace font.
- **Waveform (Oscilloscope):** Add a subtle grid background to the waveform container. Ensure the wave renders in a crisp white/light-gray color.
- **Chunk Timeline:** 
  - Redesign the blocks from squares to tall, rounded pills (teal for safe, red for AI).
  - Add an X-axis below the timeline showing `0s 1s 2s ... 20`.
- **Confidence Bar:** Create a custom progress bar (orange for medium risk) that matches the exact thickness and style of the mockup, including the "73%" marker at the end of the fill.

### 5. Detection Log (`DetectionLog.tsx`)
- Change the log format to match exactly: `[2:23.768] chunk 1: 😐 Confidence 73%`.
- Use specific emojis based on the risk level (😐 for medium, 😠/🔴 for high).

## Verification Plan
1. I will execute all CSS and component changes.
2. We will run the mock simulation (`SIMULATE DEMO CALL`).
3. We will visually compare the rendered dashboard side-by-side with your provided mockup to ensure 100% accuracy.
