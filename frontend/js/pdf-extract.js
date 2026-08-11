// Vendored locally (frontend/vendor/pdfjs/, pdfjs-dist@4.9.155, Apache-2.0) so PDF parsing
// works without a CDN - the app must keep running with no network beyond this machine's
// own asr/frontend containers (docs/instructions-developer-f1-f2.md, WI-9).
import * as pdfjsLib from '../vendor/pdfjs/pdf.min.js';

pdfjsLib.GlobalWorkerOptions.workerSrc = './vendor/pdfjs/pdf.worker.min.js';

export const MAX_PORTFOLIO_CHARS = 30000;

export function truncateText(text, maxChars = MAX_PORTFOLIO_CHARS) {
  if (text.length <= maxChars) return { text, truncated: false };
  return { text: text.slice(0, maxChars), truncated: true };
}

export async function extractPdfText(file) {
  const buf = await file.arrayBuffer();

  let doc;
  try {
    doc = await pdfjsLib.getDocument({ data: buf }).promise;
  } catch {
    throw new Error('PDF tidak bisa dibuka — file rusak atau bukan PDF yang valid.');
  }

  const pageTexts = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    pageTexts.push(content.items.map((it) => it.str).join(' ').trim());
  }

  const full = pageTexts.join('\n\n').trim();
  if (!full) {
    // Scanned/image-only PDF: pdf.js returns zero text items per page, not an error - the
    // guide requires this to surface as a clear message, not a silently empty textarea.
    throw new Error(
      'PDF tidak memuat teks yang bisa diekstrak (kemungkinan hasil scan/gambar). ' +
        'Salin-tempel isi CV secara manual ke kolom di bawah.'
    );
  }

  const { text, truncated } = truncateText(full);
  return { text, truncated, pages: doc.numPages };
}
