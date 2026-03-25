/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],

  theme: {
    extend: {
      colors: {

        // 🟠 Primary - Orange Côte d'Ivoire (Bergère)
        primary: {
          50:  '#fff7ed',
          100: '#ffedd5',
          200: '#fed7aa',
          300: '#fdba74',
          400: '#fb923c',
          500: '#f77f00',   // ✅ Orange institutionnel UFHOB
          600: '#ea580c',
          700: '#c2410c',
          800: '#9a3412',
          900: '#7c2d12',
        },

        // 🔵 Secondary - Turquoise UFHOB
        secondary: {
          50:  '#f0fdfb',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#60B7B1',   // Turquoise logo
          500: '#60B7B1',   // ✅ Turquoise institutionnel
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
          DEFAULT: '#60B7B1',
        },

        // 🟡 Accent - Or/Doré (bannière logo)
        accent: {
          DEFAULT: '#FDBE54',
          light: '#FED680',
          dark: '#E5A93C',
        },

        // ⚪ Fond doux - Turquoise menthe clair
        soft: '#A8D9D5',

        // 🖤 Texte institutionnel
        'ufhob-dark': '#1a1a1a',
      },
    },
  },

  plugins: [],
};