import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#ECFEFF",
          100: "#CFFAFE",
          200: "#A5F3FC",
          400: "#22D3EE",
          500: "#06B6D4",
          600: "#0891B2",
          700: "#0E7490",
          800: "#155E75",
        },
      },
      fontFamily: {
        sans:   ["var(--font-assistant)", "system-ui", "sans-serif"],
        hebrew: ["var(--font-heebo)", "system-ui", "sans-serif"],
        mono:   ["var(--font-dm-mono)", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
