"use client";

interface SpeakerNotesProps {
  notes: string | undefined;
}

export default function SpeakerNotes({ notes }: SpeakerNotesProps) {
  if (!notes) return null;

  return (
    <div className="border-t bg-muted/30 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-medium">演讲者注释</span>
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed">{notes}</p>
    </div>
  );
}
