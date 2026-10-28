/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./projects/public-site/src/**/*.{html,ts}",
    "./projects/super-admin/src/**/*.{html,ts}",
    "./projects/tenant-workspace/src/**/*.{html,ts}",
    "./projects/pbms-shared/src/**/*.{html,ts}"
  ],
  theme: {
    extend: {}
  },
  plugins: []
};
