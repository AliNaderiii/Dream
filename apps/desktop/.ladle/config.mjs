/** Ladle is intentionally used instead of heavyweight Storybook. */
export default {
  viteConfig: '.ladle/vite.config.mjs',
  stories: 'src/**/*.stories.{ts,tsx}',
  addons: {
    a11y: { enabled: true },
  },
};
