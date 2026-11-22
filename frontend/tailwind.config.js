/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        // Pale sage CTA / accent ramp. 500 fills primary buttons, 600-700 are
        // the readable accent text on the dark surfaces below.
        brand: {
          50: "#0b1713",
          100: "#102019",
          200: "#1b332a",
          300: "#2a4a3d",
          400: "#4d7d6a",
          500: "#7fb39d",
          600: "#9ccdb6",
          700: "#b8dfcb",
          800: "#d3ecdf",
          900: "#eaf6f0",
        },
        // The neutral ramp is inverted: 50 is the page floor and 900 is the
        // brightest text. Every existing ink utility keeps its meaning (50 =
        // background, 900 = primary text, 200 = hairline) without rewriting the
        // thousands of class names that already use it.
        ink: {
          50: "#060b09",
          // Raised surfaces. On a near-black page the fill alone cannot carry
          // elevation, so these stay close to the floor and the hairline
          // (ink-200) does the separating work.
          100: "#0f1815",
          200: "#1e2c26",
          300: "#2b3d36",
          // Muted text clears WCAG AA (4.5:1) on both the page floor and the
          // raised card tone; #6b7f77 measured 4.42:1 and failed for small text.
          400: "#788d84",
          500: "#8fa39b",
          600: "#a8bcb4",
          700: "#c4d6ce",
          800: "#deeae4",
          900: "#f1f7f4",
        },
        card: "#0f1815",
        danger: {
          50: "#24100f",
          100: "#351716",
          200: "#542321",
          500: "#d96464",
          600: "#f08a8a",
          700: "#f7a5a5",
          800: "#fcc0c0",
        },
        warn: {
          50: "#22190b",
          100: "#2f230f",
          200: "#4a3818",
          500: "#d8a95c",
          600: "#e6bd76",
          700: "#f0cf95",
          800: "#f7dfb3",
        },
        info: {
          50: "#0b1a20",
          100: "#0f2530",
          200: "#1b3a47",
          500: "#5f9bb0",
          600: "#7fb8cc",
          700: "#9ccddd",
        },
      },
      borderRadius: {
        card: "14px",
      },
      boxShadow: {
        card: "0 1px 0 rgba(255, 255, 255, 0.03) inset, 0 8px 24px rgba(0, 0, 0, 0.28)",
        pop: "0 24px 64px rgba(0, 0, 0, 0.55), 0 2px 8px rgba(0, 0, 0, 0.4)",
        rail: "1px 0 0 rgba(255, 255, 255, 0.05)",
        glow: "0 0 60px rgba(127, 179, 157, 0.18)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        drift: {
          "0%, 100%": { transform: "translate3d(0, 0, 0) scale(1)" },
          "50%": { transform: "translate3d(2%, -1.5%, 0) scale(1.06)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out both",
        drift: "drift 26s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
