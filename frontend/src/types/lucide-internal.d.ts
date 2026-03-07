declare module "lucide-react/dist/esm/icons/*.js" {
  import type { ComponentType } from "react";

  export type InternalLucideIconNode = Array<[string, Record<string, string>]>;

  export const __iconNode: InternalLucideIconNode;

  const component: ComponentType<{ className?: string }>;
  export default component;
}
