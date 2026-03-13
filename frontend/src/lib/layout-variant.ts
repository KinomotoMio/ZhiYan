import layoutMetadataJson from "@/generated/layout-metadata.json";
import type { LayoutRole } from "@/lib/layout-role";
import { compareLayoutNames } from "@/lib/sort";

// Keep this union in sync with shared/layout-metadata.json when new variants land.
export type LayoutVariant =
  | "default"
  | "icon-points"
  | "visual-explainer"
  | "capability-grid";

type VariantDefinition = {
  label: string;
  description: string;
};

type SharedLayoutMetadata = {
  subGroupsByGroup: Record<LayoutRole, Record<string, VariantDefinition>>;
  layouts: Record<
    string,
    {
      group: LayoutRole;
      subGroup: string;
      variant: {
        composition: string;
        tone: string;
        style: string;
        density: string;
      };
      usage: string[];
    }
  >;
};

const layoutMetadata = layoutMetadataJson as SharedLayoutMetadata;

const VARIANTS_BY_ROLE: Record<LayoutRole, Record<LayoutVariant, VariantDefinition>> =
  Object.fromEntries(
    (
      Object.entries(layoutMetadata.subGroupsByGroup) as Array<
        [LayoutRole, Record<string, VariantDefinition>]
      >
    ).map(([group, subGroups]) => {
      const compatibilityVariants =
        group === "narrative"
          ? subGroups
          : {
              default:
                subGroups.default ?? {
                  label: "默认变体",
                  description: "当前组尚未展开正式的结构型兼容变体。",
                },
            };

      return [group, compatibilityVariants];
    }),
  ) as Record<LayoutRole, Record<LayoutVariant, VariantDefinition>>;

const LAYOUT_ID_TO_VARIANT: Record<string, LayoutVariant> = Object.fromEntries(
  Object.entries(layoutMetadata.layouts).map(([layoutId, metadata]) => [
    layoutId,
    metadata.group === "narrative" ? metadata.subGroup : "default",
  ]),
) as Record<string, LayoutVariant>;

export function getLayoutVariant(layoutId: string): LayoutVariant {
  return LAYOUT_ID_TO_VARIANT[layoutId] ?? "default";
}

export function getLayoutVariantLabel(
  role: LayoutRole,
  variant: LayoutVariant,
): string {
  return VARIANTS_BY_ROLE[role]?.[variant]?.label ?? variant;
}

export function getLayoutVariantDescription(
  role: LayoutRole,
  variant: LayoutVariant,
): string {
  return VARIANTS_BY_ROLE[role]?.[variant]?.description ?? "";
}

export function getLayoutVariantsForRole(role: LayoutRole): LayoutVariant[] {
  return Object.keys(VARIANTS_BY_ROLE[role] ?? {}) as LayoutVariant[];
}

export function compareLayoutVariants(
  role: LayoutRole,
  leftVariant: LayoutVariant,
  rightVariant: LayoutVariant,
): number {
  const variants = getLayoutVariantsForRole(role);
  const leftIndex = variants.indexOf(leftVariant);
  const rightIndex = variants.indexOf(rightVariant);

  if (leftIndex !== rightIndex) {
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  }

  return compareLayoutNames(leftVariant, rightVariant, leftVariant, rightVariant);
}

export function isDefaultLayoutVariant(variant: LayoutVariant): boolean {
  return variant === "default";
}
