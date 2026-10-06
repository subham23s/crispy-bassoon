import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: { extend: { colors: { cyber: { ink: '#080c14', blue: '#71a9ff', panel: '#111827' } } } },
  plugins: [],
};

export default config;
