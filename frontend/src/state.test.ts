import {describe,it,expect} from 'vitest';
import {newerSnapshot,mergeEvents} from './state';
import type {Snapshot} from './types';
describe('server stream reconciliation',()=>{
 const snapshot=(id:string,revision:string)=>({runId:id,stateRevision:revision} as Snapshot);
 it('ignores old and duplicate revisions, including values beyond JS integer precision',()=>{
  const current=snapshot('a','9007199254740993');
  expect(newerSnapshot(current,snapshot('a','9007199254740992'),'a')).toBe(current);
  expect(newerSnapshot(current,snapshot('b','9007199254740994'),'a')).toBe(current);
  expect(newerSnapshot(current,snapshot('a','9007199254740994'),'a')?.stateRevision).toBe('9007199254740994');
 });
 it('deduplicates and orders recovered events',()=>{
  const e=(sequence:string)=>({sequence,time:0,type:'TEST',data:{message:'x'}});
  expect(mergeEvents([e('2')],[e('3'),e('1'),e('2')]).map(e=>e.sequence)).toEqual(['1','2','3']);
 });
});
