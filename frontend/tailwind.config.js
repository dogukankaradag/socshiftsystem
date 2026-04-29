/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  // 'class' stratejisi: <html class="dark"> eklenince dark: varyantları aktif olur.
  // ThemeContext bu sınıfı kullanıcı seçimine göre runtime'da yönetir.
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff6ff',
          400: '#60a5fa',
          500: '#2563eb',
          700: '#1d4ed8',
          900: '#1e3a8a',
        },
      },
    },
  },
  plugins: [],
};
