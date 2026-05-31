/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0a0a0f",
        surface: "#11131b",
        "surface-hover": "#171923",
      },
    },
  },
  plugins: [],
};
