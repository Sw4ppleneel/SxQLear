/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // SxQLear design system — analytical dark theme
        surface: {
          DEFAULT: '#111111',   // Page background
          elevated: '#1a1a1a', // Cards, panels
          overlay: '#222222',  // Dropdowns, tooltips
          border: '#2a2a2a',   // Borders
          hover: '#2d2d2d',    // Hover states
        },
        text: {
          primary: '#e8e8e8',
          secondary: '#888888',
          muted: '#555555',
          inverse: '#111111',
        },
        accent: {
          DEFAULT: '#4f7ef7',   // Primary blue
          hover: '#6b93f8',
          muted: '#1e3a7a',
        },
        // Confidence tier colors
        confidence: {
          certain: '#22c55e',    // ≥0.90
          high: '#14b8a6',       // ≥0.70
          medium: '#f59e0b',     // ≥0.50
          low: '#f97316',        // ≥0.30
          speculative: '#ef4444', // <0.30
        },
        // Validation status colors
        status: {
          confirmed: '#22c55e',
          rejected: '#ef4444',
          pending: '#888888',
          deferred: '#f59e0b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        '2xs': '0.625rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.15s ease-out',
        'slide-up': 'slideUp 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
