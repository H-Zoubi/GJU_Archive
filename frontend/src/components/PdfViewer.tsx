import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Vite bundles the worker as its own asset and gives us the URL to load it
// from -- pdf.js does the actual parsing off the main thread.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

/** Renders one page at a time with prev/next -- simpler and lighter than a
 * scrolling multi-page canvas for the phone-sized viewport this mostly opens
 * on. */
export default function PdfViewer({ url }: { url: string }) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [error, setError] = useState(false);
  const [width, setWidth] = useState(0);

  if (error) {
    return (
      <p className="p-8 text-center text-sm text-slate-500">
        This PDF could not be previewed.
      </p>
    );
  }

  return (
    <div className="flex h-full flex-col bg-slate-100">
      <div className="flex flex-1 justify-center overflow-auto">
        <div
          ref={(el) => setWidth(el?.clientWidth ?? 0)}
          className="flex w-full max-w-3xl justify-center px-2 py-4"
        >
          <Document
            file={url}
            onLoadSuccess={({ numPages }) => setNumPages(numPages)}
            onLoadError={() => setError(true)}
            loading={<p className="py-16 text-sm text-slate-400">Loading preview…</p>}
          >
            <Page
              pageNumber={pageNumber}
              width={width ? Math.min(width, 768) : undefined}
              renderAnnotationLayer={false}
            />
          </Document>
        </div>
      </div>

      {!!numPages && numPages > 1 && (
        <div className="flex shrink-0 items-center gap-4 border-t border-slate-200 bg-white px-4 py-2">
          <button
            onClick={() => setPageNumber((n) => Math.max(1, n - 1))}
            disabled={pageNumber <= 1}
            className="rounded-lg border border-slate-200 px-3 py-1 text-sm text-slate-700 disabled:opacity-30"
          >
            Previous
          </button>
          <span className="text-sm text-slate-500">
            Page {pageNumber} of {numPages}
          </span>
          <button
            onClick={() => setPageNumber((n) => Math.min(numPages, n + 1))}
            disabled={pageNumber >= numPages}
            className="rounded-lg border border-slate-200 px-3 py-1 text-sm text-slate-700 disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
