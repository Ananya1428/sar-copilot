import type { Config } from "tailwindcss";

/**
 * Tailwind supplies layout utilities only (flex/grid/spacing/sizing).
 * Every color, font-family, font-size, and radius Tailwind would normally
 * default to is disabled below and re-pointed at the design tokens in
 * src/styles/tokens.css — so `bg-blue-500` etc. simply don't exist here,
 * and nothing from Tailwind's default palette can leak into the UI.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      paper: "var(--paper)",
      canvas: "var(--canvas)",
      panel: "var(--panel)",
      rule: "var(--rule)",
      ink: "var(--ink)",
      "ink-muted": "var(--ink-muted)",
      "ink-faint": "var(--ink-faint)",
      verified: "var(--verified)",
      "verified-bg": "var(--verified-bg)",
      caution: "var(--caution)",
      "caution-bg": "var(--caution-bg)",
      critical: "var(--critical)",
      "critical-bg": "var(--critical-bg)",
      trace: "var(--trace)",
      "trace-bg": "var(--trace-bg)",
    },
    fontFamily: {
      narrative: "var(--font-narrative)",
      ui: "var(--font-ui)",
      data: "var(--font-data)",
    },
    fontSize: {
      "2xs": "var(--text-2xs)",
      xs: "var(--text-xs)",
      sm: "var(--text-sm)",
      base: "var(--text-base)",
      lg: "var(--text-lg)",
      xl: "var(--text-xl)",
    },
    // Spacing is deliberately NOT overridden here — Tailwind's default
    // scale is already 4px-based (each step = 0.25rem = 4px), which is
    // exactly blueprint §17's "4px-base spacing scale" and numerically
    // identical to tokens.css's --space-* values at every integer step.
    // An earlier version of this file replaced the scale with a partial
    // hand-picked set of integer keys only, which silently dropped every
    // fractional utility (h-1.5, px-2.5, gap-1.5, ...) used throughout
    // the app — Tailwind emits nothing for an unrecognised key, so a bar
    // chart's `h-1.5` height quietly rendered as zero. Keeping the full
    // default scale (rather than hand-rolling a subset) avoids that
    // whole bug class going forward.
    borderRadius: {
      none: "0",
      sm: "var(--radius-sm)",
      md: "var(--radius-md)",
      full: "9999px",
    },
    extend: {
      maxWidth: {
        narrative: "720px",
      },
      transitionDuration: {
        trace: "var(--motion-duration)",
      },
    },
  },
  plugins: [],
};

export default config;
