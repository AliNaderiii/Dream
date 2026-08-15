import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';

function CopyCode({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="absolute end-2 top-2 rounded-sm bg-surface-raised p-1.5 text-fg-muted opacity-0 transition-opacity group-hover/code:opacity-100 focus:opacity-100"
      aria-label="Copy code"
      onClick={() => {
        void navigator.clipboard?.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1_500);
      }}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  );
}

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="message-markdown selectable min-w-0 break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        urlTransform={(url) => defaultUrlTransform(url)}
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          img: ({ alt, ...props }) => (
            <img
              {...props}
              alt={alt ?? ''}
              loading="lazy"
              className="my-3 max-h-96 max-w-full rounded-lg border border-border-default object-contain"
            />
          ),
          pre: ({ children }) => {
            const codeChild = (children as { props?: { children?: unknown } })?.props?.children;
            const text = typeof codeChild === 'string' ? codeChild.replace(/\n$/, '') : '';
            return (
              <div className="group/code relative my-3 overflow-hidden rounded-lg border border-border-default bg-sunken">
                <pre className="ltr-island overflow-x-auto p-4 text-code">{children}</pre>
                <CopyCode value={text} />
              </div>
            );
          },
          code: ({ className, children, ...props }) =>
            className ? (
              <code {...props} className={className}>
                {children}
              </code>
            ) : (
              <code {...props} className="ltr-island rounded-xs bg-sunken px-1.5 py-0.5 text-code">
                {children}
              </code>
            ),
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
