import { type ReactNode } from "react";

/**
 * A tiny markdown renderer for the release notes: `#`/`##`/`###` headings,
 * `-`/`*` bullet lists, `**bold**`, `` `code` `` and `[links](url)`. No
 * dependency — the notes are simple and we control their format (see
 * `docs/releasing.md`). Anything it doesn't recognise renders as plain text.
 */

// `**bold**` must precede `*italic*` so a `**` opener isn't eaten as italic.
const INLINE =
  /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;

/** Render a run of inline markdown (bold / italic / code / links) into nodes. */
function inline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (let m = INLINE.exec(text); m; m = INLINE.exec(text)) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const key = `${keyBase}-${i++}`;
    if (m[2] !== undefined) {
      nodes.push(<strong key={key}>{m[2]}</strong>);
    } else if (m[3] !== undefined) {
      nodes.push(<em key={key}>{m[3]}</em>);
    } else if (m[4] !== undefined) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-white/10 px-1 py-0.5 text-[0.85em] text-violet-200"
        >
          {m[4]}
        </code>,
      );
    } else {
      nodes.push(
        <a
          key={key}
          href={m[6]}
          target="_blank"
          rel="noreferrer"
          className="text-violet-400 underline hover:text-violet-300"
        >
          {m[5]}
        </a>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function Markdown({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];

  const flush = (key: string) => {
    if (!bullets.length) return;
    const items = bullets;
    bullets = [];
    blocks.push(
      <ul key={key} className="my-2 list-disc space-y-1 pl-5">
        {items.map((li, i) => (
          <li key={i}>{inline(li, `${key}-${i}`)}</li>
        ))}
      </ul>,
    );
  };

  source.split("\n").forEach((raw, idx) => {
    const line = raw.trimEnd();
    const key = `b${idx}`;
    if (/^###\s+/.test(line)) {
      flush(`${key}l`);
      blocks.push(
        <h4 key={key} className="mb-1 mt-4 text-sm font-semibold text-white">
          {inline(line.replace(/^###\s+/, ""), key)}
        </h4>,
      );
    } else if (/^##\s+/.test(line)) {
      flush(`${key}l`);
      blocks.push(
        <h3 key={key} className="mb-1.5 mt-5 text-base font-semibold text-white">
          {inline(line.replace(/^##\s+/, ""), key)}
        </h3>,
      );
    } else if (/^#\s+/.test(line)) {
      flush(`${key}l`);
      blocks.push(
        <h2 key={key} className="mb-2 mt-5 text-lg font-bold text-white">
          {inline(line.replace(/^#\s+/, ""), key)}
        </h2>,
      );
    } else if (/^\s*[-*]\s+/.test(line)) {
      bullets.push(line.replace(/^\s*[-*]\s+/, ""));
    } else if (line.trim() === "") {
      flush(`${key}l`);
    } else {
      flush(`${key}l`);
      blocks.push(
        <p key={key} className="my-2 leading-relaxed">
          {inline(line, key)}
        </p>,
      );
    }
  });
  flush("bend");

  return <div className="text-sm text-zinc-300">{blocks}</div>;
}
