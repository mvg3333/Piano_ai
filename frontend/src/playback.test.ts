import {it,expect,vi,afterEach} from 'vitest'
import {Playback} from './playback'
import type {Piece} from './types'
const stop=vi.fn()
function engine(){
 const p=new Playback();const context={currentTime:0,state:'running',resume:async()=>{},destination:{},createGain:()=>({gain:{setValueAtTime:vi.fn(),linearRampToValueAtTime:vi.fn(),exponentialRampToValueAtTime:vi.fn()},connect:vi.fn().mockReturnThis(),disconnect:vi.fn()}),createBufferSource:()=>({playbackRate:{value:1},connect:vi.fn().mockReturnThis(),start:vi.fn(),stop})}
 p.context=context as unknown as AudioContext
 for(let i=1;i<=7;i++)p.buffers.set(12*(i+1),{duration:10} as AudioBuffer)
 p.setPiece({duration:10,notes:[{id:'a',pitch:60,start:0,end:1,hand:'right'},{id:'b',pitch:60,start:1,end:2,hand:'right'},{id:'c',pitch:64,start:0,end:2,hand:'left'}],raw:{pedals:[]},settings:{numerator:4,denominator:4,downbeat:0},score:{anchors:[{time:0,beat:0,bpm:120}]}} as unknown as Piece)
 vi.useFakeTimers();return {p,context}
}
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers();stop.mockClear()})
it('flushes old voices and rebuilds repeated/chord notes at seek',async()=>{const {p}=engine();await p.play();expect([...p.voices.keys()]).toEqual(['a','c']);p.seek(1.2);expect(stop).toHaveBeenCalled();expect([...p.voices.keys()]).toEqual(['b','c']);p.pause();expect(p.voices.size).toBe(0)})
it('keeps position continuous across speed changes',async()=>{const {p,context}=engine();await p.play();context.currentTime=1;p.rate(.5);expect(p.time()).toBe(1);context.currentTime=3;expect(p.time()).toBe(2);p.pause()})
it('wraps at the loop boundary with a fresh schedule',async()=>{const {p,context}=engine();p.loop=true;p.loopA=0;p.loopB=1;await p.play();context.currentTime=1.03;p.tick();expect(p.time()).toBeCloseTo(.03);expect([...p.pending]).toEqual(['a','c']);p.pause()})
it('mutes selected hands without changing source notes',async()=>{const {p}=engine();p.setHands('left');await p.play();expect([...p.pending]).toEqual(['c']);expect(p.piece!.notes).toHaveLength(3);p.pause()})
it('follows assigned hands when middle C belongs to different hands in separate phrases',async()=>{
 const {p}=engine()
 p.setPiece({...p.piece!,notes:[
  {id:'accompaniment-e3',pitch:52,start:0,end:1,hand:'left'},
  {id:'accompaniment-c4',pitch:60,start:0,end:1,hand:'left'},
  {id:'upper-melody',pitch:74,start:0,end:1,hand:'right'},
  {id:'melody-c4',pitch:60,start:2,end:3,hand:'right'},
  {id:'melody-d4',pitch:62,start:3,end:4,hand:'right'},
 ]})
 const original=structuredClone(p.piece!.notes)
 p.setHands('left');await p.play()
 expect([...p.voices.keys()]).toEqual(['accompaniment-e3','accompaniment-c4'])
 p.setHands('right')
 expect([...p.voices.keys()]).toEqual(['upper-melody'])
 p.seek(2.2)
 expect([...p.voices.keys()]).toEqual(['melody-c4'])
 p.setHands('left')
 expect(p.voices.size).toBe(0)
 p.setHands('both')
 expect([...p.voices.keys()]).toEqual(['melody-c4'])
 expect(p.piece!.notes).toEqual(original)
 p.pause()
})
it('follows a buffered external clock without synthetic voices',async()=>{const {p,context}=engine();let current=2;const pause=vi.fn();p.configureMode('audio',{currentTime:()=>current,play:vi.fn(),pause,seek:t=>{current=t},rate:vi.fn(),isPlaying:()=>false});await p.play();current=2;context.currentTime=20;p.tick();expect(p.time()).toBe(2);expect(p.voices.size).toBe(0);p.configureMode('synth');expect(pause).toHaveBeenCalled();expect(p.playing).toBe(false)})
it('switches arrangements at the same position, speed and loop without count-in or old voices',async()=>{
 const {p,context}=engine();await p.play();context.currentTime=.5;p.rate(.75)
 p.loop=true;p.loopA=.2;p.loopB=3;p.countIn=true;p.transpose=2;p.hands='right'
 const source=p.piece!,arranged={...source,notes:source.notes.filter(n=>n.id==='a')}
 p.replacePerformance(arranged)
 expect(p.time()).toBe(.5);expect(p.speed).toBe(.75);expect(p.playing).toBe(true)
 expect(p.countEnd).toBe(0);expect(p.transpose).toBe(2);expect(p.hands).toBe('right')
 expect([p.loopA,p.loopB,p.loop]).toEqual([.2,3,true]);expect([...p.voices.keys()]).toEqual(['a'])
 p.replacePerformance(source);expect(p.time()).toBe(.5);expect(stop).toHaveBeenCalled()
 p.pause();p.seek(2.99);p.replacePerformance(arranged);expect(p.playing).toBe(false);expect(p.time()).toBe(2.99)
})
it('comparison switches an external clock to synthesized piano without changing source position or speed',async()=>{
 const {p}=engine();let current=0;const pause=vi.fn()
 p.offset=12;p.configureMode('audio',{currentTime:()=>current,play:vi.fn(),pause,seek:t=>{current=t},rate:vi.fn(),isPlaying:()=>true})
 await p.play();current=13.5;p.rate(.5)
 p.replacePerformance(p.piece!,true)
 expect(p.mode).toBe('synth');expect(p.time()).toBe(1.5);expect(p.speed).toBe(.5);expect(pause).toHaveBeenCalled()
 expect(p.playing).toBe(true);p.pause()
})
it('reads arrangement pedal events independently of the source container',()=>{
 const {p}=engine();p.replacePerformance({...p.piece!,pedals:[{time:0,value:127},{time:3,value:0}]})
 expect(p.soundEnd(p.piece!.notes[0])).toBe(3)
})
