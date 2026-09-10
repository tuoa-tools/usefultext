import { useCallback, useEffect, useState } from 'react';

export type Tab = 'pages' | 'editor' | 'export';
export type Route =
  { view: 'library' } | { view: 'document'; id: string; tab: Tab; pageId?: string };

const TABS: Tab[] = ['pages', 'editor', 'export'];

/** #/  ·  #/doc/<id>/<tab>  ·  #/doc/<id>/editor/<page id> */
export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (parts[0] === 'doc' && parts[1]) {
    const tab = TABS.find((t) => t === parts[2]) ?? 'pages';
    return { view: 'document', id: parts[1], tab, pageId: parts[3] };
  }
  return { view: 'library' };
}

export function routeHash(route: Route): string {
  if (route.view === 'library') return '#/';
  const base = `#/doc/${route.id}/${route.tab}`;
  return route.pageId ? `${base}/${route.pageId}` : base;
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  const navigate = useCallback((r: Route) => {
    window.location.hash = routeHash(r);
  }, []);
  return [route, navigate];
}
