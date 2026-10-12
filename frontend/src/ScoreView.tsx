import {useEffect,useRef,useState} from 'react'
import {OpenSheetMusicDisplay, VexFlowGraphicalNote, TransposeCalculator} from 'opensheetmusicdisplay'
import type {PerformanceView} from './types'
import type {Playback} from './playback'
import {secondsToBeats} from './timing'

export function ScoreView({piece,player,size,transpose,onSeek}:{piece:PerformanceView;player:Playback;size:number;transpose:number;onSeek:(t:number)=>void}){
 const host=useRef<HTMLDivElement>(null),scroll=useRef<HTMLDivElement>(null),osmd=useRef<OpenSheetMusicDisplay|null>(null)
 const positions=useRef<{beat:number;measure:number;x:number;y:number;w:number;h:number}[]>([])
 const renderedNotes=useRef<{ids:string[];elements:HTMLElement[]}[]>([])
 const cursorIndex=useRef(-1),renderVersion=useRef(0)
 const [error,setError]=useState('')
 useEffect(()=>{
  const target=host.current!;let disposed=false;let timer:ReturnType<typeof setTimeout>
  const display=new OpenSheetMusicDisplay(target,{autoResize:false,backend:'svg',drawTitle:false,drawSubtitle:false,drawComposer:false,drawPartNames:false,drawPartAbbreviations:false,drawMetronomeMarks:false,drawMeasureNumbers:true,followCursor:false,cursorsOptions:[{type:0,color:'#4db8a5',alpha:.24,follow:false}]})
  osmd.current=display
  const render=()=>{
   if(disposed||!display.Sheet)return
   display.TransposeCalculator=new TransposeCalculator();display.Sheet.Transpose=transpose
   display.Zoom=size;display.render();display.cursor.show();display.cursor.reset()
   const points=[];let guard=0
   const noteElements:{ids:string[];elements:HTMLElement[]}[]=[]
   const notesById=new Map(piece.notes.map(n=>[n.id,n]))
   while(!display.cursor.Iterator.EndReached&&guard++<20000){
    display.cursor.update();const r=display.cursor.cursorElement.getBoundingClientRect(),parent=target.getBoundingClientRect()
    points.push({beat:display.cursor.Iterator.currentTimeStamp.RealValue*4,measure:display.cursor.Iterator.CurrentMeasureIndex,x:r.left-parent.left,y:r.top-parent.top,w:r.width,h:r.height})
    for(const graphical of display.cursor.GNotesUnderCursor()){
     if(!(graphical instanceof VexFlowGraphicalNote)||!graphical.sourceNote.Pitch)continue
     const pitch=Math.round(69+12*Math.log2(graphical.sourceNote.Pitch.Frequency/440))
     const beat=graphical.sourceNote.getAbsoluteTimestamp().RealValue*4
     const hand=graphical.sourceNote.ParentStaff.idInMusicSheet===0?'right':'left'
     const matches=piece.score.fragments.filter(f=>f.beat<=beat+.02&&f.endBeat>beat+.02&&f.hand===hand&&notesById.get(f.noteId)?.pitch===pitch)
     if(matches.length){const elements=graphical.getNoteheadSVGs();const element=elements[graphical.vfnoteIndex]??elements[0];if(element){element.dataset.performanceNotes=matches.map(f=>f.noteId).join(',');noteElements.push({ids:matches.map(f=>f.noteId),elements:[element]})}}
    }
    display.cursor.next()
   }
   positions.current=points;renderedNotes.current=noteElements;cursorIndex.current=-1;renderVersion.current++;display.cursor.reset();display.cursor.show()
  }
  setError('')
  if(piece.score.musicxml)void display.load(piece.score.musicxml).then(render).catch(e=>setError(String(e)))
  const resize=new ResizeObserver(()=>{clearTimeout(timer);timer=setTimeout(render,150)});resize.observe(target)
  return()=>{disposed=true;resize.disconnect();clearTimeout(timer);display.clear();if(osmd.current===display)osmd.current=null}
 },[piece.score.musicxml,size,transpose])
 useEffect(()=>{
  let frame=0,lastMeasure=-1,version=-1,lastActive=''
  const update=()=>{
   const display=osmd.current,points=positions.current
   const beat=secondsToBeats(player.time(),piece.score.anchors)
   const index=points.findLastIndex(p=>p.beat<=beat+.001)
   if(version!==renderVersion.current){lastMeasure=-1;lastActive='';version=renderVersion.current}
   if(display?.Sheet&&index>=0&&index!==cursorIndex.current){
    if(index<cursorIndex.current||cursorIndex.current<0){display.cursor.reset();cursorIndex.current=0}
    while(cursorIndex.current<index&&!display.cursor.Iterator.EndReached){display.cursor.next();cursorIndex.current++}
    display.cursor.show();display.cursor.update()
    host.current!.dataset.cursorBeat=String(points[index].beat)
    const p=points[index]
    if(p&&p.measure!==lastMeasure){const sc=scroll.current!;if(p.y<sc.scrollTop||p.y+p.h>sc.scrollTop+sc.clientHeight)sc.scrollTo({top:Math.max(0,p.y-25),behavior:'instant'});lastMeasure=p.measure}
   }
   // Raw note times determine active-note emphasis; engraving retains hand colors.
   const active=new Set(piece.notes.filter(n=>n.start<=player.time()&&n.end>player.time()).map(n=>n.id))
   const signature=[...active].join(',')
   if(signature!==lastActive){for(const n of renderedNotes.current)for(const el of n.elements)el.classList.toggle('active-score-note',n.ids.some(id=>active.has(id)));lastActive=signature}
   frame=requestAnimationFrame(update)
  };frame=requestAnimationFrame(update);return()=>cancelAnimationFrame(frame)
 },[piece,player,size])
 return <div ref={scroll} className="score-scroll" onClick={event=>{
  const r=host.current!.getBoundingClientRect(),x=event.clientX-r.left,y=event.clientY-r.top
  const candidate=positions.current.reduce<typeof positions.current[number]|undefined>((best,p)=>{const d=Math.abs(p.x-x)+Math.abs(p.y+p.h/2-y)*4;const bd=best?Math.abs(best.x-x)+Math.abs(best.y+best.h/2-y)*4:Infinity;return d<bd?p:best},undefined)
  if(candidate){const measure=piece.score.measures[candidate.measure];if(measure)onSeek(measure.startTime)}
 }}>
  {(!piece.score.musicxml||error)&&<div className="score-empty"><strong>Your piano roll is ready.</strong><p>{error||piece.score.warning}</p><p>Set tempo and meter in Practice settings to generate a new draft score.</p></div>}
  <div ref={host} className="score-render" aria-label="Interactive sheet music; click a measure to seek"/>
 </div>
}
