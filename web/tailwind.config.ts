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
    spacing: {
      0: "0",
      1: "var(--space-1)",
      2: "var(--space-2)",
      3: "var(--space-3)",
      4: "var(--space-4)",
      5: "var(--space-5)",
      6: "var(--space-6)",
      8: "var(--space-8)",
      10: "var(--space-10)",
      12: "var(--space-12)",
      16: "var(--space-16)",
    },
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
