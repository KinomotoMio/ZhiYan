"use client";

import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

function omitNodeProp<T extends object>(props: T): Omit<T, "node"> {
  const { node: _node, ...rest } = props as T & { node?: unknown };
  return rest as Omit<T, "node">;
}

const markdownComponents: Components = {
  p: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <p className={cn("my-0 whitespace-pre-wrap", className)} {...domProps} />;
  },
  ul: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <ul className={cn("my-3 list-disc space-y-1 pl-5", className)} {...domProps} />;
  },
  ol: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <ol className={cn("my-3 list-decimal space-y-1 pl-5", className)} {...domProps} />;
  },
  li: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <li className={cn("pl-1", className)} {...domProps} />;
  },
  h1: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <h1 className={cn("mb-3 mt-1 text-xl font-semibold leading-8", className)} {...domProps} />;
  },
  h2: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <h2 className={cn("mb-3 mt-1 text-lg font-semibold leading-8", className)} {...domProps} />;
  },
  h3: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <h3 className={cn("mb-2 mt-1 text-base font-semibold leading-7", className)} {...domProps} />;
  },
  h4: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <h4 className={cn("mb-2 mt-1 text-sm font-semibold leading-6", className)} {...domProps} />;
  },
  strong: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <strong className={cn("font-semibold text-slate-900", className)} {...domProps} />;
  },
  em: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <em className={cn("italic", className)} {...domProps} />;
  },
  hr: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <hr className={cn("my-5 border-slate-200/80", className)} {...domProps} />;
  },
  blockquote: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return (
      <blockquote
        className={cn(
          "my-4 border-l-2 border-slate-300/90 pl-4 text-slate-600",
          className
        )}
        {...domProps}
      />
    );
  },
  table: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return (
      <div className="my-4 overflow-x-auto">
        <table className={cn("min-w-full border-collapse text-left text-sm", className)} {...domProps} />
      </div>
    );
  },
  thead: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <thead className={cn("bg-slate-100/80", className)} {...domProps} />;
  },
  tbody: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <tbody className={cn("[&_tr:last-child]:border-b-0", className)} {...domProps} />;
  },
  tr: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <tr className={cn("border-b border-slate-200/80", className)} {...domProps} />;
  },
  th: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <th className={cn("px-3 py-2 font-semibold text-slate-900", className)} {...domProps} />;
  },
  td: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return <td className={cn("px-3 py-2 align-top text-slate-700", className)} {...domProps} />;
  },
  pre: ({ className, ...props }) => {
    const domProps = omitNodeProp(props);
    return (
      <pre
        className={cn(
          "my-4 overflow-x-auto rounded-2xl bg-slate-900 px-4 py-3 text-sm leading-6 text-slate-100",
          className
        )}
        {...domProps}
      />
    );
  },
  code: ({
    className,
    children,
    inline,
    ...props
  }: ComponentPropsWithoutRef<"code"> & { inline?: boolean }) => {
    const domProps = omitNodeProp(props);
    if (inline) {
      return (
        <code
          className={cn(
            "rounded-md bg-slate-100/90 px-1.5 py-0.5 font-mono text-[0.92em] text-slate-800",
            className
          )}
          {...domProps}
        >
          {children}
        </code>
      );
    }
    const hasLanguageClass = typeof className === "string" && className.includes("language-");
    if (hasLanguageClass) {
      return (
        <code className={cn("bg-transparent p-0 text-inherit", className)} {...domProps}>
          {children}
        </code>
      );
    }
    return (
      <code
        className={cn("bg-transparent p-0 font-mono text-inherit", className)}
        {...domProps}
      >
        {children}
      </code>
    );
  },
};

export default function MarkdownMessage({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 text-[15px] leading-8 text-slate-700", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
