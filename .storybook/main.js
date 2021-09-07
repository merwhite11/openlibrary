const webpackConfig = require( '../webpack.config' );

module.exports = {
  webpackFinal: async (config) => {
    config.module.rules = config.module.rules.concat(
      webpackConfig.module.rules
    );
    return config;
  },
  "stories": [
    "../stories/**/*.stories.mdx",
    "../stories/**/*.stories.@(js|jsx|ts|tsx)"
  ],
  "addons": [
    "@storybook/addon-links",
    "@storybook/addon-essentials"
  ]
}