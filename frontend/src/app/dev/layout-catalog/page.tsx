import { notFound } from "next/navigation";

import { LayoutCatalogClientPage } from "./LayoutCatalogClient";

export default function LayoutCatalogPage() {
  if (process.env.NODE_ENV !== "development") {
    notFound();
  }

  return <LayoutCatalogClientPage />;
}
