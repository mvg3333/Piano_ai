import {useEffect,useRef} from 'react'
import type {ExternalClock} from './playback'
type YTPlayer={getCurrentTime:()=>number;playVideo:()=>void;pauseVideo:()=>void;seekTo:(t:number,allow:boolean)=>void;setPlaybackRate:(n:number)=>void;getPlayerState:()=>number;getAvailablePlaybackRates:()=>number[];getPlaybackRate:()=>number;destroy:()=>void}
declare global {interface Window {YT?:{Player:new(el:HTMLElement,options:unknown)=>YTPlayer};onYouTubeIframeAPIReady?:()=>void}}
let ready:Promise<void>|undefined
function loadYouTube(){if(window.YT)return Promise.resolve();if(!ready)ready=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://www.youtube.com/iframe_api';script.onerror=()=>{ready=undefined;reject(new Error('YouTube could not load. Check your connection.'))};window.onYouTubeIframeAPIReady=resolve;document.head.appendChild(script)});return ready}
export function YouTubePlayer({videoId,clipStart,onReady,onError,onRate,onState}:{videoId:string;clipStart:number;onReady:(clock:ExternalClock,rates:number[])=>void;onError:(s:string)=>void;onRate:(n:number)=>void;onState:(state:number)=>void}){
 const container=useRef<HTMLDivElement>(null),callbacks=useRef({onReady,onError,onRate,onState});callbacks.current={onReady,onError,onRate,onState}
 useEffect(()=>{let disposed=false;let player:YTPlayer|undefined
  void loadYouTube().then(()=>{if(disposed)return;const host=document.createElement('div');container.current!.replaceChildren(host)
   player=new window.YT!.Player(host,{videoId,width:'100%',height:'100%',playerVars:{playsinline:1,origin:window.location.origin},events:{
    onReady:()=>{if(!player||disposed)return;const p=player;callbacks.current.onReady({currentTime:()=>p.getCurrentTime()-clipStart,play:()=>p.playVideo(),pause:()=>p.pauseVideo(),seek:t=>p.seekTo(t+clipStart,true),rate:r=>p.setPlaybackRate(r),isPlaying:()=>p.getPlayerState()===1},p.getAvailablePlaybackRates())},
    onPlaybackRateChange:()=>{if(player)callbacks.current.onRate(player.getPlaybackRate())},
    onStateChange:(e:{data:number})=>callbacks.current.onState(e.data),
    onError:(e:{data:number})=>callbacks.current.onError(`YouTube player error ${e.data}. This video may restrict embedding. Use synthesized or uploaded audio playback.`)
   }})
  }).catch(e=>callbacks.current.onError(String(e)))
  return()=>{disposed=true;player?.destroy()}
 },[videoId,clipStart])
 return <div className="youtube-player" ref={container}/>
}
