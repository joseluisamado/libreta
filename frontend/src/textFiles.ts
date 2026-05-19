export const EXT_LANG: Record<string, string> = {
  py: 'python',
  js: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  jsx: 'javascript',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'ini',
  ini: 'ini',
  cfg: 'ini',
  conf: 'ini',
  xml: 'xml',
  html: 'xml',
  htm: 'xml',
  css: 'css',
  scss: 'scss',
  less: 'less',
  csv: 'plaintext',
  txt: 'plaintext',
  log: 'plaintext',
  md: 'markdown',
  rs: 'rust',
  go: 'go',
  java: 'java',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  hpp: 'cpp',
  cc: 'cpp',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  fish: 'fish',
  env: 'bash',
  dockerfile: 'dockerfile',
  makefile: 'makefile',
  sql: 'sql',
  rb: 'ruby',
  php: 'php',
  lua: 'lua',
  pl: 'perl',
  r: 'r',
  swift: 'swift',
  kt: 'kotlin',
  scala: 'scala',
  dart: 'dart',
  ex: 'elixir',
  exs: 'elixir',
  erl: 'erlang',
  hs: 'haskell',
  clj: 'clojure',
  edn: 'clojure',
  el: 'elisp',
}

const NOEXT_TEXT_NAMES = new Set(['dockerfile', 'makefile', '.env'])

/**
 * True for non-markdown text files that should render in TextView
 * (`.py`, `.json`, `Dockerfile`, …). Markdown stays in the page renderer.
 */
export function isTextPath(path: string): boolean {
  const last = path.split('/').pop()?.toLowerCase() ?? ''
  if (!last) return false
  if (NOEXT_TEXT_NAMES.has(last)) return true
  const dot = last.lastIndexOf('.')
  if (dot === -1) return false
  const ext = last.slice(dot + 1)
  if (ext === 'md') return false
  return ext in EXT_LANG
}
