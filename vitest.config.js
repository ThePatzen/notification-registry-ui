import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["frontend-tests/**/*.test.js"],
    globals: true,
    restoreMocks: true,
  },
});
