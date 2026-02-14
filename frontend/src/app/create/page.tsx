import { Suspense } from "react";
import CreateView from "@/components/create/CreateView";

export default function CreatePage() {
  return (
    <Suspense>
      <CreateView />
    </Suspense>
  );
}
