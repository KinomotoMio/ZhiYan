"use client";

import SourcePanel from "./SourcePanel";
import CreateForm from "./CreateForm";

export default function CreateView() {
  return (
    <div className="flex min-h-screen zy-bg-page">
      <SourcePanel />
      <CreateForm />
    </div>
  );
}
