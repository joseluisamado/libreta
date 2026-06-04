import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
  type RouterScrollBehavior,
} from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('./views/DashboardView.vue'),
  },
  {
    path: '/pdf-source/:sourceId/:path(.*)*',
    name: 'pdf-source',
    component: () => import('./views/PdfView.vue'),
  },
  {
    path: '/pdf-watch/:label/:path(.*)*',
    name: 'pdf-watch',
    component: () => import('./views/PdfView.vue'),
  },
  {
    path: '/text-source/:sourceId/:path(.*)*',
    name: 'text-source',
    component: () => import('./views/TextView.vue'),
  },
  {
    path: '/text-watch/:label/:path(.*)*',
    name: 'text-watch',
    component: () => import('./views/TextView.vue'),
  },
  {
    path: '/html-source/:sourceId/:path(.*)*',
    name: 'html-source',
    component: () => import('./views/HtmlView.vue'),
  },
  {
    path: '/html-watch/:label/:path(.*)*',
    name: 'html-watch',
    component: () => import('./views/HtmlView.vue'),
  },
  {
    path: '/img-source/:sourceId/:path(.*)*',
    name: 'img-source',
    component: () => import('./views/ImageView.vue'),
  },
  {
    path: '/img-watch/:label/:path(.*)*',
    name: 'img-watch',
    component: () => import('./views/ImageView.vue'),
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('./views/SearchView.vue'),
  },
  {
    path: '/watch/:label/:path(.*)*',
    name: 'watched-page',
    component: () => import('./views/WatchedPageView.vue'),
  },
  {
    path: '/edit-watch/:label/:path(.*)*',
    name: 'watched-editor',
    component: () => import('./views/WatchedEditorView.vue'),
  },
  {
    path: '/source/:sourceId/:path(.*)*',
    name: 'source-page',
    component: () => import('./views/SourcePageView.vue'),
  },
  {
    path: '/edit-source/:sourceId/:path(.*)*',
    name: 'source-editor',
    component: () => import('./views/SourceEditorView.vue'),
  },
  {
    path: '/-/admin',
    name: 'admin',
    component: () => import('./views/AdminView.vue'),
  },
]

// The real scroll container is <main id="main-scroll"> (see App.vue), not
// the window, so Vue Router's built-in savedPosition can't help — and a
// one-shot restore loses to async content (markdown render, mermaid,
// images) that keeps growing the page after we set scrollTop. We track
// scrollTop per history entry ourselves and keep re-applying the target
// until the container's height stops changing.
const MAIN_ID = 'main-scroll'
const STORAGE_KEY = 'libreta:scrollPositions'

const scrollPositions = new Map<string, number>(
  (() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY)
      if (!raw) return []
      return Object.entries(JSON.parse(raw) as Record<string, number>)
    } catch {
      return []
    }
  })(),
)

let persistPending = false
function persistScrollPositions(): void {
  if (persistPending) return
  persistPending = true
  queueMicrotask(() => {
    persistPending = false
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(scrollPositions)))
    } catch {
      // sessionStorage may be full or disabled; ignore.
    }
  })
}

function readKey(): string {
  const s = window.history.state as { key?: string } | null
  return s?.key ?? window.location.href
}

function mainEl(): HTMLElement | null {
  return document.getElementById(MAIN_ID)
}

// The key of the entry the user is *currently* viewing. We need this
// because by the time Vue Router's guards fire, history.state already
// reflects the destination — so we'd otherwise save the outgoing scroll
// under the incoming entry's key.
let currentKey = readKey()

// Live snapshot: capture scrollTop continuously so we always have a fresh
// value for the current entry, regardless of when navigation starts.
function installScrollTracker(): void {
  const el = mainEl()
  if (!el) {
    // App.vue not mounted yet; try again on next tick.
    queueMicrotask(installScrollTracker)
    return
  }
  el.addEventListener(
    'scroll',
    () => {
      scrollPositions.set(currentKey, el.scrollTop)
      persistScrollPositions()
    },
    { passive: true },
  )
}
installScrollTracker()

// Repeatedly set scrollTop while the container is still growing. Resolves
// once two consecutive height readings match (content settled) or we hit
// the cap.
function restoreScroll(el: HTMLElement, target: number, maxMs = 1500): Promise<void> {
  return new Promise((resolve) => {
    const start = performance.now()
    let last = -1
    let stable = 0
    const tick = (): void => {
      el.scrollTop = target
      const h = el.scrollHeight
      if (h === last) {
        stable += 1
        if (stable >= 3) {
          el.scrollTop = target
          resolve()
          return
        }
      } else {
        stable = 0
        last = h
      }
      if (performance.now() - start >= maxMs) {
        el.scrollTop = target
        resolve()
        return
      }
      setTimeout(tick, 50)
    }
    tick()
  })
}

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (async (to, _from, savedPosition) => {
    const el = mainEl()
    if (!el) return false

    if (savedPosition) {
      // popstate: history.state.key now points at the destination entry.
      const top = scrollPositions.get(readKey()) ?? 0
      currentKey = readKey()
      await restoreScroll(el, top)
      return false
    }
    if (to.hash) {
      currentKey = readKey()
      return false
    }
    el.scrollTop = 0
    currentKey = readKey()
    return false
  }) as RouterScrollBehavior,
})

// Rendered markdown emits plain <a href="/watch/..."> anchors, which the
// browser would treat as full-page navigations — wiping our in-memory
// scrollPositions and breaking back-restore. Intercept same-origin,
// app-route clicks and route them through Vue Router instead.
function isAppPath(path: string): boolean {
  return (
    path === '/' ||
    path.startsWith('/watch/') ||
    path.startsWith('/source/') ||
    path.startsWith('/edit-watch/') ||
    path.startsWith('/edit-source/') ||
    path.startsWith('/pdf-watch/') ||
    path.startsWith('/pdf-source/') ||
    path.startsWith('/text-watch/') ||
    path.startsWith('/text-source/') ||
    path.startsWith('/html-watch/') ||
    path.startsWith('/html-source/') ||
    path.startsWith('/img-watch/') ||
    path.startsWith('/img-source/') ||
    path.startsWith('/search') ||
    path.startsWith('/-/')
  )
}

document.addEventListener('click', (e) => {
  if (e.defaultPrevented || e.button !== 0) return
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  const a = (e.target as Element | null)?.closest('a')
  if (!a) return
  if (a.target && a.target !== '' && a.target !== '_self') return
  if (a.hasAttribute('download')) return
  const href = a.getAttribute('href')
  if (!href) return
  let url: URL
  try {
    url = new URL(href, window.location.origin)
  } catch {
    return
  }
  if (url.origin !== window.location.origin) return
  if (!isAppPath(url.pathname)) return
  e.preventDefault()
  router.push({ path: url.pathname, hash: url.hash, query: Object.fromEntries(url.searchParams) })
})
