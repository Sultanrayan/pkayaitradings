/**
 * Class-name helper.
 *
 * shadcn's `radix-nova` registry imports `cn` from the official `cn` package,
 * while most third-party registries import it from `@/lib/utils`. Re-exporting
 * here keeps both conventions working.
 */
export { cn } from "cn";
