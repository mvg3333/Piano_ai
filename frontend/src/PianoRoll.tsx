import {useEffect,useRef} from 'react'
import type { Piece, Note } from './types'
import {HAND_COLORS} from './types'
import {keyboardGeometry,noteName} from './timing'
import type { Playback } from './playback'

export function PianoRoll({piece,player,range,labels,octaves,zoom,onSelect}:{piece:Piece;player:Playback;range:[number,number];labels:boolean;octaves:boolean;zoom:number;onSelect:(n:Note)=>void}){
 const canvas=useRef<HTMLCanvasElement>(null),outer=useRef<HTMLDivElement>(null)
 const hitNotes=useRef<{x:number;y:number;w:number;h:number;note:Note}[]>([])
 useEffect(()=>{
  const el=canvas.current!,box=outer.current!;let frame=0
  const draw=()=>{
   const width=Math.max(box.clientWidth,(range[1]-range[0]+1)*zoom),height=box.clientHeight,dpr=window.devicePixelRatio||1
   if(el.width!==Math.round(width*dpr)||el.height!==Math.round(height*dpr)){el.width=Math.round(width*dpr);el.height=Math.round(height*dpr);el.style.width=width+'px';el.style.height=height+'px'}
   const ctx=el.getContext('2d')!;ctx.setTransform(dpr,0,0,dpr,0,0)
   ctx.fillStyle='#101f25';ctx.fillRect(0,0,width,height)
   const keyHeight=Math.min(98,Math.max(60,height*.26)),strike=height-keyHeight,pixelsPerSecond=Math.max(42,strike/4.5),time=player.time()
   const keys=keyboardGeometry(range[0],range[1],width),keyMap=new Map(keys.map(k=>[k.pitch,k]))
   for(const key of keys)if(!key.black){ctx.fillStyle=key.pitch%12===0?'#192c32':'#14252b';ctx.fillRect(key.x,0,key.width-.5,strike);ctx.strokeStyle='#24373c';ctx.beginPath();ctx.moveTo(key.x,0);ctx.lineTo(key.x,strike);ctx.stroke()}
   const beatSeconds=60/piece.settings.tempo
   for(let beat=Math.floor(time/beatSeconds);beat*beatSeconds<time+strike/pixelsPerSecond;beat++){const y=strike-(beat*beatSeconds-time)*pixelsPerSecond;ctx.strokeStyle=beat%piece.settings.numerator===0?'#385056':'#24373c';ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke()}
   const active=new Map<number,string>();hitNotes.current=[]
   for(const n of piece.notes){
    const pitch=n.pitch+(player.mode==='synth'?player.transpose:0),key=keyMap.get(pitch);if(!key)continue
    if(n.start<=time&&n.end>time)active.set(pitch,HAND_COLORS[n.hand])
    const bottom=strike-(n.start-time)*pixelsPerSecond,top=strike-(n.end-time)*pixelsPerSecond
    if(bottom<0||top>strike)continue
    const y=Math.max(0,top),h=Math.min(strike,bottom)-y;if(h<=0)continue
    ctx.fillStyle=HAND_COLORS[n.hand];ctx.globalAlpha=player.hands==='both'||player.hands===n.hand?1:.3
    const x=key.x+2,w=Math.max(3,key.width-4)
    ctx.beginPath();ctx.roundRect(x,y,w,h,Math.min(4,h/2));ctx.fill()
    ctx.fillStyle='rgba(255,255,255,.28)';ctx.fillRect(x+2,y+2,Math.max(1,w-4),2)
    if(labels&&w>22&&h>20){ctx.fillStyle='#10252c';ctx.font='600 10px system-ui';ctx.textAlign='center';ctx.fillText(noteName(pitch,octaves),x+w/2,Math.min(y+15,strike-4))}
    hitNotes.current.push({x,y,w,h,note:n});ctx.globalAlpha=1
   }
   ctx.fillStyle='#7dddd0';ctx.shadowBlur=10;ctx.shadowColor='#55d9c4';ctx.fillRect(0,strike-2,width,2);ctx.shadowBlur=0
   for(const black of [false,true])for(const key of keys.filter(k=>k.black===black)){
    const kh=black?keyHeight*.63:keyHeight,x=key.x+1,w=key.width-2
    ctx.fillStyle=active.get(key.pitch)??(black?'#172328':'#edf0ec');ctx.beginPath();ctx.roundRect(x,strike,w,kh,black?[0,0,4,4]:[0,0,3,3]);ctx.fill()
    if(!black){ctx.fillStyle=active.has(key.pitch)?'rgba(0,0,0,.12)':'#c3ccc8';ctx.fillRect(x,strike+kh-5,w,5)}
    if(labels&&w>16&&(!black||w>23)){ctx.font=`${black?9:10}px system-ui`;ctx.textAlign='center';ctx.fillStyle=black?'#d7e2de':'#596761';ctx.fillText(noteName(key.pitch,octaves),key.x+key.width/2,strike+kh-12)}
   }
   frame=requestAnimationFrame(draw)
  };frame=requestAnimationFrame(draw)
  return()=>cancelAnimationFrame(frame)
 },[piece,player,range,labels,octaves,zoom])
 return <div ref={outer} className="roll-scroll"><canvas ref={canvas} aria-label="Falling notes and piano keyboard" onClick={e=>{const r=canvas.current!.getBoundingClientRect();const x=e.clientX-r.left,y=e.clientY-r.top;const n=hitNotes.current.findLast(n=>x>=n.x&&x<=n.x+n.w&&y>=n.y&&y<=n.y+n.h);if(n)onSelect(n.note)}}/></div>
}
