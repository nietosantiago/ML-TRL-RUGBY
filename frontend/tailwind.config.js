/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        rugby: {
          green:     '#1a5c2e',
          'green-light': '#2d8a49',
          dark:      '#0f2417',
          gold:      '#d4af37',
          'gold-light': '#f0d060',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
