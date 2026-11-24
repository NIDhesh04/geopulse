import {describe,expect,it} from 'vitest';
import {isDrawer} from './workspaceDrawers';

describe('control room panel availability',()=>{
  it('keeps all panels visible at desktop widths',()=>{
    expect(['fleet','inspector','activity'].map(panel=>isDrawer('desktop',panel as 'fleet'|'inspector'|'activity'))).toEqual([false,false,false]);
  });
  it('keeps the activity pane inline on tablet and puts every panel in a compact drawer',()=>{
    expect(isDrawer('tablet','fleet')).toBe(true);
    expect(isDrawer('tablet','inspector')).toBe(true);
    expect(isDrawer('tablet','activity')).toBe(false);
    expect(isDrawer('compact','activity')).toBe(true);
  });
});
