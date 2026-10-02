/**
 * The ALFRED server rewrites this marker when it serves the console from its own origin.
 * Any other host (Vite preview, the offline standalone file) is the labelled demonstration.
 * The mode is never inferred from a failed request, so an unreachable server cannot
 * silently turn the connected console back into fixtures.
 */
export type ConsoleMode='demo'|'connected';
export function consoleMode(doc:Document=document):ConsoleMode{
  return doc.querySelector('meta[name="alfred-mode"]')?.getAttribute('content')==='connected'?'connected':'demo';
}
