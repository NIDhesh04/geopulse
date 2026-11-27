import {useEffect, useRef, useState, useSyncExternalStore} from 'react';

export type Drawer = 'fleet' | 'inspector' | 'activity';
export type Layout = 'desktop' | 'tablet' | 'compact';

export function isDrawer(layout:Layout, panel:Drawer) {
  return layout==='compact' || (layout==='tablet' && panel!=='activity');
}

const tablet = '(min-width: 900px)';
const desktop = '(min-width: 1280px)';
function readLayout():Layout {
  return matchMedia(desktop).matches?'desktop':matchMedia(tablet).matches?'tablet':'compact';
}
function subscribe(listener:()=>void) {
  const queries = [matchMedia(tablet),matchMedia(desktop)];
  queries.forEach(query=>query.addEventListener('change',listener));
  return ()=>queries.forEach(query=>query.removeEventListener('change',listener));
}

export function useWorkspaceDrawers() {
  const layout = useSyncExternalStore(subscribe,readLayout);
  const [open,setOpen] = useState<Drawer|null>(null);
  const triggers = useRef<Partial<Record<Drawer, HTMLButtonElement>>>({});
  const closeButtons = useRef<Partial<Record<Drawer, HTMLButtonElement>>>({});
  const active = open && isDrawer(layout,open) ? open : null;
  const close = (panel:Drawer) => {
    setOpen(null);
    triggers.current[panel]?.focus({preventScroll:true});
  };

  useEffect(()=>{
    if (!active) return;
    closeButtons.current[active]?.focus({preventScroll:true});
    const escape = (event:KeyboardEvent) => {
      if(event.key==='Escape' && !event.defaultPrevented){
        event.preventDefault();
        close(active);
      }
    };
    document.addEventListener('keydown',escape);
    return ()=>document.removeEventListener('keydown',escape);
  },[active]);

  return {
    layout,active,
    show(panel:Drawer) {if(isDrawer(layout,panel))setOpen(panel);},
    visible(panel:Drawer) {return !isDrawer(layout,panel)||active===panel;},
    toggle(panel:Drawer) {if(active===panel)close(panel);else setOpen(panel);},
    close,
    triggerRef(panel:Drawer, element:HTMLButtonElement|null) {triggers.current[panel]=element??undefined;},
    closeRef(panel:Drawer, element:HTMLButtonElement|null) {closeButtons.current[panel]=element??undefined;},
  };
}
