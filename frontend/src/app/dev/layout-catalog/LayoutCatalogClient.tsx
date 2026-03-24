"use client";

import { Fragment, useState } from "react";
import type { ComponentType, ReactNode } from "react";

import layoutMetadataJson from "@/generated/layout-metadata.json";
import {
  buildLayoutCatalogEntries,
  type CatalogEntry,
} from "@/app/dev/layout-catalog/catalog-data";
import {
  compareLayoutRoles,
  getLayoutRoleDescription,
  getLayoutRoleLabel,
  LAYOUT_ROLE_ORDER,
  type LayoutRole,
} from "@/lib/layout-role";
import { getUsageLabel, type LayoutUsageTag } from "@/lib/layout-usage";
import { compareLayoutNames } from "@/lib/sort";
import {
  getLayoutDesignTraitDescription,
  getLayoutDesignTraitLabel,
  getLayoutSubGroupDescription,
  getLayoutSubGroupsForGroup,
  getLayoutSubGroupLabel,
  getVariantDescription,
  getVariantLabel,
  getVariantsForSubGroup,
  type LayoutSubGroup,
} from "@/lib/layout-taxonomy";

type CatalogFilter = "all" | LayoutRole;
const DESIGN_TRAIT_ORDER = ["tone", "style", "density"] as const;
const FORMAL_SUBGROUP_ROLES = LAYOUT_ROLE_ORDER.filter((role) =>
  getLayoutSubGroupsForGroup(role).some((subGroup) => subGroup !== "default"),
);
const entries = buildLayoutCatalogEntries();

const sortedEntries = [...entries].sort((left, right) => {
  const roleDelta = compareLayoutRoles(left.group, right.group);
  if (roleDelta !== 0) return roleDelta;

  const subGroups = getLayoutSubGroupsForGroup(left.group);
  const leftSubGroupIndex = subGroups.indexOf(left.subGroup);
  const rightSubGroupIndex = subGroups.indexOf(right.subGroup);

  if (leftSubGroupIndex !== rightSubGroupIndex) {
    if (leftSubGroupIndex === -1) return 1;
    if (rightSubGroupIndex === -1) return -1;
    return leftSubGroupIndex - rightSubGroupIndex;
  }

  const variantDelta = compareLayoutNames(
    left.variantLabel,
    right.variantLabel,
    left.variantId,
    right.variantId,
  );
  if (variantDelta !== 0) return variantDelta;

  return compareLayoutNames(
    left.name,
    right.name,
    left.id,
    right.id,
  );
});

const designTraitAxes = layoutMetadataJson.designTraitAxes;

function PreviewFrame({
  Component,
  data,
}: {
  Component: ComponentType<{ data: Record<string, unknown> }>;
  data: Record<string, unknown>;
}) {
  return (
    <div className="w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div
        className="origin-top-left bg-[var(--background-color,#ffffff)]"
        style={{
          width: 1280,
          height: 720,
          transform: "scale(0.25)",
          transformOrigin: "top left",
          marginBottom: -540,
          ["--primary-color" as string]: "#2563eb",
          ["--primary-text" as string]: "#ffffff",
          ["--background-color" as string]: "#ffffff",
          ["--background-text" as string]: "#0f172a",
        }}
      >
        <Component data={data} />
      </div>
    </div>
  );
}

function UsageChips({ usage }: { usage: LayoutUsageTag[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {usage.map((tag) => (
        <span
          key={tag}
          className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"
        >
          {getUsageLabel(tag)}
        </span>
      ))}
    </div>
  );
}

function MetaBlock({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
        {label}
      </h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function SubGroupBadge({
  group,
  subGroup,
}: {
  group: LayoutRole;
  subGroup: CatalogEntry["subGroup"];
}) {
  return (
    <div>
      <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-700">
        {getLayoutSubGroupLabel(group, subGroup)}
      </span>
      <code className="mt-2 block text-xs text-slate-500">{subGroup}</code>
      <p className="mt-2 text-sm leading-6 text-slate-700">
        {getLayoutSubGroupDescription(group, subGroup)}
      </p>
    </div>
  );
}

function VariantCard({
  entry,
}: {
  entry: Pick<
    CatalogEntry,
    "variantId" | "variantLabel" | "variantDescription" | "designTraits" | "isVariantDefault"
  >;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-violet-100 bg-violet-50/40 p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-700">
            Variant
          </span>
          {entry.isVariantDefault ? (
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-medium text-violet-700">
              baseline
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-sm font-medium text-slate-900">{entry.variantLabel}</div>
        <code className="mt-1 block text-xs text-violet-700">{entry.variantId}</code>
        <p className="mt-2 text-sm leading-6 text-slate-700">{entry.variantDescription}</p>
      </div>
      {DESIGN_TRAIT_ORDER.map((axis) => (
        <div
          key={axis}
          className="rounded-lg border border-violet-100 bg-violet-50/40 p-3"
        >
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-700">
              {axis}
            </span>
            <code className="text-xs text-violet-700">{entry.designTraits[axis] || "n/a"}</code>
          </div>
          <div className="mt-1 text-sm font-medium text-slate-900">
            {entry.designTraits[axis]
              ? getLayoutDesignTraitLabel(axis, entry.designTraits[axis]!)
              : "Not specified"}
          </div>
          {entry.designTraits[axis] ? (
            <p className="mt-2 text-sm leading-6 text-slate-700">
              {getLayoutDesignTraitDescription(axis, entry.designTraits[axis]!)}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

const NOTES_SLOT_LABELS: Array<{
  key: keyof CatalogEntry["notes"];
  label: string;
}> = [
  { key: "purpose", label: "Purpose" },
  { key: "structure_signal", label: "Structure" },
  { key: "design_signal", label: "Design" },
  { key: "use_when", label: "Use when" },
  { key: "avoid_when", label: "Avoid when" },
  { key: "usage_bias", label: "Usage bias" },
];

function NotesCard({ notes }: { notes: CatalogEntry["notes"] }) {
  return (
    <div className="rounded-xl border border-sky-200 bg-sky-50/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-700">
          Runtime notes
        </span>
        <span className="text-xs text-sky-800">
          shared metadata six-slot contract
        </span>
      </div>
      <dl className="mt-3 space-y-3">
        {NOTES_SLOT_LABELS.map(({ key, label }) => (
          <div key={key}>
            <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-700">
              {label}
            </dt>
            <dd className="mt-1 text-sm leading-6 text-slate-700">
              {notes[key]}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function TogglePill({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
          : "rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-200"
      }
    >
      {children}
    </button>
  );
}

export function LayoutCatalogClientPage() {
  const [activeFilter, setActiveFilter] = useState<CatalogFilter>("all");
  const [expandedLayoutId, setExpandedLayoutId] = useState<string | null>(null);

  const visibleEntries = sortedEntries.filter(
    (entry) => activeFilter === "all" || entry.group === activeFilter,
  );

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-8 text-slate-900">
      <div className="mx-auto max-w-[1880px]">
        <header className="mb-8">
          <p className="mb-2 text-sm font-medium uppercase tracking-[0.2em] text-slate-500">
            Local Catalog
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">
            Built-in slide layouts
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            This page renders every built-in TSX layout with sample data so you
            can compare previews, inspect file locations, and review the schema
            fields each template expects. The taxonomy reference below defines
            the shared vocabulary, and the main table applies that same
            `group / sub-group / variant / layout` contract to each built-in template.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-medium text-white">
              Issue 102 variant delivery
            </span>
            {FORMAL_SUBGROUP_ROLES.map((role) => (
              <span
                key={role}
                className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200"
              >
                {getLayoutRoleLabel(role)}: {getLayoutSubGroupsForGroup(role).length} formal
                {" "}
                sub-groups
              </span>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <TogglePill
              active={activeFilter === "all"}
              onClick={() => setActiveFilter("all")}
            >
              All layouts
            </TogglePill>
            {LAYOUT_ROLE_ORDER.map((role) => (
              <TogglePill
                key={role}
                active={activeFilter === role}
                onClick={() => setActiveFilter(role)}
              >
                {getLayoutRoleLabel(role)}
              </TogglePill>
            ))}
          </div>
        </header>

        <section className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="max-w-3xl">
            <h2 className="text-lg font-semibold text-slate-900">
              Taxonomy reference
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              This quick reference lists the current `group`, `sub-group`,
              formal `variant` nodes, and helper design traits used by the
              built-in layouts. A single structure can now expose multiple
              official variants, and each variant can map to one or more real
              layouts.
            </p>
          </div>
          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
                Group
              </h3>
              <div className="mt-4 space-y-4">
                {LAYOUT_ROLE_ORDER.map((role) => (
                  <div key={role} className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                        {getLayoutRoleLabel(role)}
                      </span>
                      <code className="text-xs text-slate-500">{role}</code>
                      {getLayoutSubGroupsForGroup(role).some((subGroup) => subGroup !== "default") ? (
                        <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
                          formal sub-groups
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-700">
                      {getLayoutRoleDescription(role)}
                    </p>
                  </div>
                ))}
              </div>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
                Sub-group
              </h3>
              <div className="mt-4 space-y-4">
                {LAYOUT_ROLE_ORDER.map((role) => (
                  <div key={role} className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                        {getLayoutRoleLabel(role)}
                      </span>
                      <code className="text-xs text-slate-500">{role}</code>
                    </div>
                    <div className="mt-3 space-y-3">
                      {Object.keys(layoutMetadataJson.subGroupsByGroup[role]).map((subGroup) => (
                        <div
                          key={`${role}-${subGroup}`}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-3"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold text-slate-900">
                              {getLayoutSubGroupLabel(role, subGroup as LayoutSubGroup)}
                            </span>
                            <code className="text-xs text-slate-500">{subGroup}</code>
                            {subGroup !== "default" ? (
                              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
                                formal structure
                              </span>
                            ) : null}
                          </div>
                          <p className="mt-2 text-sm leading-6 text-slate-700">
                            {getLayoutSubGroupDescription(role, subGroup as LayoutSubGroup)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">
                Variant definitions
              </h3>
              <div className="mt-4 space-y-4">
                {LAYOUT_ROLE_ORDER.map((role) => (
                  <div key={role} className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                        {getLayoutRoleLabel(role)}
                      </span>
                      <code className="text-xs text-slate-500">{role}</code>
                    </div>
                    <div className="mt-3 space-y-3">
                      {getLayoutSubGroupsForGroup(role).map((subGroup) => (
                        <div key={`${role}-${subGroup}`} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold text-slate-900">
                              {getLayoutSubGroupLabel(role, subGroup)}
                            </span>
                            <code className="text-xs text-slate-500">{subGroup}</code>
                          </div>
                          <div className="mt-3 space-y-3">
                            {getVariantsForSubGroup(role, subGroup).map((variantId) => (
                              <div key={`${role}-${subGroup}-${variantId}`} className="rounded-lg border border-violet-100 bg-white p-3">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-sm font-semibold text-slate-900">
                                    {getVariantLabel(role, subGroup, variantId)}
                                  </span>
                                  <code className="text-xs text-slate-500">{variantId}</code>
                                </div>
                                <p className="mt-2 text-sm leading-6 text-slate-700">
                                  {getVariantDescription(role, subGroup, variantId)}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </div>
        </section>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-[1780px] table-fixed border-collapse">
              <thead className="bg-slate-100 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                <tr>
                  <th className="w-[360px] px-5 py-4">Preview</th>
                  <th className="w-[220px] px-5 py-4">Layout</th>
                  <th className="w-[160px] px-5 py-4">Group</th>
                  <th className="w-[240px] px-5 py-4">Structure sub-group</th>
                  <th className="w-[300px] px-5 py-4">Variant</th>
                  <th className="w-[250px] px-5 py-4">Usage</th>
                  <th className="px-5 py-4">Details</th>
                </tr>
              </thead>
              <tbody>
                {visibleEntries.map((entry) => {
                  const isExpanded = expandedLayoutId === entry.id;
                  const Component = entry.component;

                  return (
                    <Fragment key={entry.id}>
                      <tr
                        className="border-t border-slate-200 align-top"
                      >
                        <td className="px-5 py-5">
                          <PreviewFrame Component={Component} data={entry.data} />
                        </td>
                        <td className="px-5 py-5">
                          <div className="text-sm font-semibold text-slate-900">
                            {entry.name}
                          </div>
                          <code className="mt-2 block rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">
                            {entry.id}
                          </code>
                          <code className="mt-3 block rounded bg-slate-50 px-2 py-2 text-xs text-slate-600 ring-1 ring-slate-200">
                            frontend/src/components/slide-layouts/{entry.fileName}
                          </code>
                        </td>
                        <td className="px-5 py-5">
                          <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                            {getLayoutRoleLabel(entry.group)}
                          </span>
                          <code className="mt-2 block text-xs text-slate-500">
                            {entry.group}
                          </code>
                        </td>
                        <td className="px-5 py-5">
                          <SubGroupBadge
                            group={entry.group}
                            subGroup={entry.subGroup}
                          />
                        </td>
                        <td className="px-5 py-5">
                          <VariantCard
                            entry={{
                              variantId: entry.variantId,
                              variantLabel: entry.variantLabel,
                              variantDescription: entry.variantDescription,
                              designTraits: entry.designTraits,
                              isVariantDefault: entry.isVariantDefault,
                            }}
                          />
                        </td>
                        <td className="px-5 py-5">
                          <UsageChips usage={entry.usage} />
                        </td>
                        <td className="px-5 py-5">
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedLayoutId((current) =>
                                current === entry.id
                                  ? null
                                  : entry.id,
                              )
                            }
                            className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700"
                          >
                            {isExpanded ? "Hide details" : "Show details"}
                          </button>
                          <p className="mt-3 text-sm leading-6 text-slate-600">
                            {entry.notes.purpose}
                          </p>
                        </td>
                      </tr>
                      {isExpanded ? (
                        <tr className="border-t border-slate-100 bg-slate-50/60">
                          <td colSpan={7} className="px-5 py-5">
                            <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                              <MetaBlock label="Schema">
                                <div className="rounded-xl border border-slate-200 bg-white p-4">
                                  <div className="text-sm font-semibold text-slate-900">
                                    {entry.schemaName}
                                  </div>
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {entry.keyFields.map((field) => (
                                      <span
                                        key={field}
                                        className="rounded-full bg-slate-50 px-2.5 py-1 text-xs text-slate-600 ring-1 ring-slate-200"
                                      >
                                        {field}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              </MetaBlock>
                              <MetaBlock label="Notes">
                                <NotesCard notes={entry.notes} />
                              </MetaBlock>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  );
}
