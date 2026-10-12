import type { Anchor, Note } from './types'
export function secondsToBeats(time:number, anchors:Anchor[]) { const a=anchors.findLast(a=>a.time<=time)??anchors[0]; return a ? a.beat+(time-a.time)*a.bpm/60 : 0 }
export function beatsToSeconds(beat:number, anchors:Anchor[]) { const a=anchors.findLast(a=>a.beat<=beat)??anchors[0]; return a ? a.time+(beat-a.beat)*60/a.bpm : 0 }
export function noteName(pitch:number, octave=true) { return ['C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B'][((pitch%12)+12)%12]+(octave?Math.floor(pitch/12)-1:'') }
export function isBlack(pitch:number) {return [1,3,6,8,10].includes(pitch%12)}
export function keyboardGeometry(low:number, high:number, width:number) {
  const whites:number[]=[]; for(let p=low;p<=high;p++) if(!isBlack(p)) whites.push(p)
  const w=width/whites.length
  return Array.from({length:high-low+1},(_,i)=>{const pitch=low+i;const black=isBlack(pitch);const before=whites.filter(p=>p<pitch).length;return {pitch,black,x:(before-(black?.31:0))*w,width:w*(black?.62:1)}})
}
export function songRange(notes:Note[]) {const pitches=notes.map(n=>n.pitch);let low=Math.max(21,Math.min(...pitches)-2),high=Math.min(108,Math.max(...pitches)+2);if(isBlack(low))low--;if(isBlack(high))high++;return [low,high] as [number,number]}
export function activeNotes(notes:Note[],time:number) {return notes.filter(n=>n.start<=time&&n.end>time)}
export function advanceLoop(time:number,a:number,b:number,enabled:boolean) {return enabled&&b>a&&time>=b?a+(time-b)%(b-a):time}
