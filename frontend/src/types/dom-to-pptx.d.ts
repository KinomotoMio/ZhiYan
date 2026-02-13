declare module "dom-to-pptx" {
  interface ExportOptions {
    fileName?: string;
    skipDownload?: boolean;
    listConfig?: Record<string, unknown>;
    svgAsVector?: boolean;
  }

  export function exportToPptx(
    target: HTMLElement | string | Array<HTMLElement | string>,
    options?: ExportOptions,
  ): Promise<Blob>;
}
