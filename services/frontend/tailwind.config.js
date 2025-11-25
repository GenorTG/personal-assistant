/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#f0f4ff",
          100: "#e0e9ff",
          200: "#c7d7fe",
          300: "#a4b8fc",
          400: "#818ef8",
          500: "#667eea",
          600: "#5568d3",
          700: "#4751b0",
          800: "#3d4490",
          900: "#383d75",
        },
      },
    },
  },
  plugins: [],
};
