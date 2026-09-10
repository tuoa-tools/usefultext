export default function HelpPanel() {
  return (
    <div className="space-y-4 text-sm leading-relaxed text-slate-700">
      <section>
        <h3 className="font-semibold text-slate-900">What this does</h3>
        <p>
          UsefulText turns photos of document pages into text, entirely on this computer. Nothing is
          sent anywhere. Each document is a folder in your library with the photos, the text and
          your corrections side by side.
        </p>
      </section>
      <section>
        <h3 className="font-semibold text-slate-900">Reading a document</h3>
        <ol className="list-decimal space-y-1 pl-5">
          <li>
            Drop a folder or the page photos onto the library; the document is named after them.
          </li>
          <li>
            Check the order: drag pages, or sort by name, time, or the page numbers found on the
            pages once they are read. Pages that look blurry are marked before you start.
          </li>
          <li>Start. Pause any time; Resume carries on where it stopped.</li>
          <li>
            In the editor, fix what the engine got wrong. Your changes are saved as you type and
            kept apart from the machine’s text — Revert brings a line back.
          </li>
          <li>Export as Markdown, plain text, Word or the individual pages, or copy it all.</li>
        </ol>
      </section>
      <section>
        <h3 className="font-semibold text-slate-900">Read quality</h3>
        <p>
          The number next to each page is the engine’s own certainty, not a measure of accuracy. A
          blurry photo can read with high certainty and still contain mistakes — so the blur warning
          matters. Retake a page by replacing its photo; it keeps its place.
        </p>
      </section>
      <section>
        <h3 className="font-semibold text-slate-900">Suspect words</h3>
        <p>
          Words the dictionary doesn’t know are marked in the editor: a misread, a name, or fine as
          it is. The « » buttons step through them, page after page. “Ignore” under a line teaches
          the library a word for good.
        </p>
      </section>
      <section>
        <h3 className="font-semibold text-slate-900">Where things are</h3>
        <p>
          Everything lives in your library folder (Settings). “Open folder” on a document shows its
          files. Removing a document sends its folder to the trash, so it can be recovered.
        </p>
      </section>
    </div>
  );
}
