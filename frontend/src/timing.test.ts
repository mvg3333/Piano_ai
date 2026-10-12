import {describe,it,expect} from 'vitest'
import {secondsToBeats,beatsToSeconds,keyboardGeometry,activeNotes,advanceLoop} from './timing'
import type {Note} from './types'
describe('performance mapping',()=>{
 it('round-trips expressive times through a changing tempo map',()=>{const a=[{time:0,beat:0,bpm:120},{time:2,beat:4,bpm:60},{time:6,beat:8,bpm:90}];for(const t of [0,.03,1.9,2,3.51,6,10])expect(beatsToSeconds(secondsToBeats(t,a),a)).toBeCloseTo(t,10)})
 it('keeps repeated attacks and simultaneous notes distinct',()=>{const notes:Note[]=[{id:'a',pitch:60,start:0,end:1,hand:'right'},{id:'b',pitch:60,start:1,end:2,hand:'right'},{id:'c',pitch:64,start:0,end:2,hand:'right'}];expect(activeNotes(notes,.5).map(n=>n.id)).toEqual(['a','c']);expect(activeNotes(notes,1).map(n=>n.id)).toEqual(['b','c'])})
 it('does not accumulate loop overshoot',()=>{expect(advanceLoop(4.03,2,4,true)).toBeCloseTo(2.03);expect(advanceLoop(12.03,2,4,true)).toBeCloseTo(2.03);expect(advanceLoop(4.03,2,4,false)).toBe(4.03)})
 it('centers black notes on the boundary of white keys',()=>{const k=keyboardGeometry(60,71,700);expect(k[0].width).toBe(100);expect(k[1].x+k[1].width/2).toBe(100);expect(k.find(n=>n.pitch===65)!.x).toBe(300)})
})
