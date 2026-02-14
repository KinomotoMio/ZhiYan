import { Suspense } from "react";
import AssetsView from "@/components/assets/AssetsView";

export default function AssetsPage() {
  return (
    <Suspense>
      <AssetsView />
    </Suspense>
  );
}
