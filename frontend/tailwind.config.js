/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'disc-green': '#2d5016',
        'disc-gold': '#fbbf24',
        'disc-purple': '#9333ea',
      },
    },
  },
  plugins: [],
}
