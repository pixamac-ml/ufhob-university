const publicConfig = require('./tailwind.config.js');

// Authenticated UI only. Theme colors are scoped CSS variables on
// [data-app-shell]; legacy Tailwind dark: variants must not affect the public site.
module.exports = {
  ...publicConfig,
  darkMode: 'class',
};
