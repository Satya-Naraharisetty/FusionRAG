/**
 * Ambient types for shiki's per-language / per-theme subpath modules
 * (`shiki/langs/*.mjs`, `shiki/themes/*.mjs`). The package exports a barrel
 * for these but does not ship resolvable type declarations for the wildcard
 * paths, so we declare them here. We only ever consume `default`.
 */
declare module "shiki/langs/*.mjs" {
  const lang: { default: unknown };
  export default lang;
}

declare module "shiki/themes/*.mjs" {
  const theme: { default: unknown };
  export default theme;
}
