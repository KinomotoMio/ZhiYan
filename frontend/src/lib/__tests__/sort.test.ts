import assert from "node:assert/strict";
import test from "node:test";

import { compareLayoutNames, compareUpdatedAt } from "@/lib/sort";
import { compareLayoutVariants } from "@/lib/layout-variant";

test("compareLayoutNames uses explicit Chinese collation with a stable id fallback", () => {
  const entries = [
    { id: "bullet-icons-only", name: "纯图标网格" },
    { id: "bullet-with-icons", name: "图标要点" },
    { id: "image-and-description", name: "图文混排" },
  ];

  const stableOrder = [...entries]
    .sort((left, right) =>
      compareLayoutNames(left.name, right.name, left.id, right.id)
    )
    .map((entry) => entry.id);

  const englishOrder = [...entries]
    .sort((left, right) => left.name.localeCompare(right.name, "en"))
    .map((entry) => entry.id);

  assert.deepEqual(stableOrder, [
    "bullet-icons-only",
    "bullet-with-icons",
    "image-and-description",
  ]);
  assert.notDeepEqual(stableOrder, englishOrder);
});

test("compareUpdatedAt sorts ISO timestamps by actual time instead of locale-sensitive strings", () => {
  const sessions = [
    { id: "invalid", updated_at: "not-a-date" },
    { id: "march", updated_at: "2026-03-12T09:30:00Z" },
    { id: "january", updated_at: "2026-01-05T09:30:00Z" },
  ];

  const sorted = [...sessions]
    .sort((left, right) => compareUpdatedAt(left.updated_at, right.updated_at))
    .map((session) => session.id);

  assert.deepEqual(sorted, ["march", "january", "invalid"]);
});

test("compareUpdatedAt uses the ASCII fallback for invalid and equal timestamp ties", () => {
  const invalidTies = [
    { id: "beta", updated_at: "not-a-date-beta" },
    { id: "alpha", updated_at: "not-a-date-alpha" },
  ];

  const invalidDesc = [...invalidTies]
    .sort((left, right) => compareUpdatedAt(left.updated_at, right.updated_at))
    .map((session) => session.id);
  const invalidAsc = [...invalidTies]
    .sort((left, right) =>
      compareUpdatedAt(left.updated_at, right.updated_at, "asc")
    )
    .map((session) => session.id);

  assert.deepEqual(invalidDesc, ["beta", "alpha"]);
  assert.deepEqual(invalidAsc, ["alpha", "beta"]);

  const equalValidTies = [
    { id: "beta", updated_at: "2026-03-12T09:30:00Z" },
    { id: "alpha", updated_at: "2026-03-12T09:30:00.000Z" },
  ];

  const equalValidDesc = [...equalValidTies]
    .sort((left, right) => compareUpdatedAt(left.updated_at, right.updated_at))
    .map((session) => session.id);
  const equalValidAsc = [...equalValidTies]
    .sort((left, right) =>
      compareUpdatedAt(left.updated_at, right.updated_at, "asc")
    )
    .map((session) => session.id);

  assert.deepEqual(equalValidDesc, ["beta", "alpha"]);
  assert.deepEqual(equalValidAsc, ["alpha", "beta"]);
});

test("compareLayoutVariants follows metadata order instead of localized labels", () => {
  const variants = [
    "capability-grid",
    "icon-points",
    "visual-explainer",
  ] as const;

  const sorted = [...variants].sort((left, right) =>
    compareLayoutVariants("narrative", left, right)
  );

  assert.deepEqual(sorted, [
    "icon-points",
    "visual-explainer",
    "capability-grid",
  ]);
});

test("compareLayoutVariants falls back to a stable ASCII order for unknown variants", () => {
  const sorted = ["zeta", "alpha"].sort((left, right) =>
    compareLayoutVariants(
      "narrative",
      left as never,
      right as never,
    )
  );

  assert.deepEqual(sorted, ["alpha", "zeta"]);
});
