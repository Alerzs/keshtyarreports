/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './panel/**/*.py',
    './static/panel/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: { vazir: ['Vazirmatn', 'sans-serif'] },
      colors: {
        canvas: '#f8fafc',
        ink: '#0f172a',
        muted: '#64748b',
        faint: '#94a3b8',
        line: '#e2e8f0',
        primary: { DEFAULT: '#0e7490', hover: '#164e63', soft: '#f0f9ff' },
        skybtn: '#0ea5e9',
      },
      boxShadow: {
        card: '0 10px 30px -5px rgba(0,0,0,0.05)',
        lift: '0 20px 25px -5px rgba(0,0,0,0.1)',
      },
      borderRadius: { card: '20px' },
    },
  },
  plugins: [],
}
