import {describe,expect,it} from 'vitest';
import {queuedRoad,sampleRoad} from './mapGeometry';
import type {Coordinate} from './types';

describe('road geometry',()=>{
  const bend:Coordinate[]=[[0,0],[0,1],[1,1]];
  it('moves along the polyline rather than cutting the corner',()=>{
    const beforeTurn=sampleRoad(bend,.25);
    const afterTurn=sampleRoad(bend,.75);
    expect(beforeTurn[0]).toBe(0);
    expect(afterTurn[1]).toBe(1);
    expect(sampleRoad(bend,1)).toEqual(bend[2]);
  });
  it('keeps the final bend when a queue spans it',()=>{
    expect(queuedRoad(bend,.75).slice(1)).toEqual(bend.slice(1));
  });
});
