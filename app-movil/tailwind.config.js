/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        // Naranja/rojo de hamburguesería: color principal de BurgerYa.
        marca: {
          50: '#FFF4ED',
          100: '#FFE6D5',
          200: '#FECBAA',
          500: '#F05A28',
          600: '#DC4316',
          700: '#B7330F',
        },
      },
    },
  },
  plugins: [],
};
