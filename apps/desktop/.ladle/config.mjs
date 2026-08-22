/** Ladle is intentionally used instead of heavyweight Storybook. */
export default {
  stories: 'src/**/*.stories.{ts,tsx}',
  addons: {
    a11y: { enabled: true },
  },
};
