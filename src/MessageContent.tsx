import { Fragment, ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function prose(text: string, keyPrefix: string) {
  const lines = text.replace(/\r/g, "").split("\n");
  const nodes: ReactNode[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | undefined;
  const flushParagraph = () => { if (paragraph.length) { nodes.push(<p key={`${keyPrefix}-p-${nodes.length}`}>{inline(paragraph.join(" "))}</p>); paragraph = []; } };
  const flushList = () => { if (!list) return; const Tag = list.ordered ? "ol" : "ul"; nodes.push(<Tag key={`${keyPrefix}-l-${nodes.length}`}>{list.items.map((item, index) => <li key={index}>{inline(item)}</li>)}</Tag>); list = undefined; };

  lines.forEach(line => {
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    const bullet = line.match(/^\s*[-*]\s+(.+)/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.+)/);
    const quote = line.match(/^>\s?(.+)/);
    if (!line.trim()) { flushParagraph(); flushList(); return; }
    if (heading) { flushParagraph(); flushList(); const Tag = `h${Math.min(heading[1].length + 2, 5)}` as "h3" | "h4" | "h5"; nodes.push(<Tag key={`${keyPrefix}-h-${nodes.length}`}>{inline(heading[2])}</Tag>); return; }
    if (bullet || numbered) { flushParagraph(); const ordered = !!numbered; if (!list || list.ordered !== ordered) flushList(); list ||= { ordered, items: [] }; list.items.push((bullet || numbered)![1]); return; }
    if (quote) { flushParagraph(); flushList(); nodes.push(<blockquote key={`${keyPrefix}-q-${nodes.length}`}>{inline(quote[1])}</blockquote>); return; }
    paragraph.push(line.trim());
  });
  flushParagraph(); flushList(); return nodes;
}

export function MessageContent({ content }: { content: string }) {
  const blocks: ReactNode[] = [];
  const pattern = /```([\w-]*)\s*\n?([\s\S]*?)```/g;
  let cursor = 0; let match: RegExpExecArray | null;
  while ((match = pattern.exec(content))) {
    if (match.index > cursor) blocks.push(...prose(content.slice(cursor, match.index), `text-${cursor}`));
    blocks.push(<div className="message-code" key={`code-${match.index}`}><span>{match[1] || "code"}</span><pre><code>{match[2].trim()}</code></pre></div>);
    cursor = pattern.lastIndex;
  }
  if (cursor < content.length) blocks.push(...prose(content.slice(cursor), `text-${cursor}`));
  return <div className="message-content">{blocks}</div>;
}
