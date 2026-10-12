import { beatsToSeconds, secondsToBeats, advanceLoop } from './timing'
import type { PerformanceView, Piece, Note, Mode } from './types'

export interface ExternalClock { currentTime():number; play():void|Promise<void>; pause():void; seek(t:number):void; rate(r:number):void; isPlaying():boolean }
type Voice = {source:AudioBufferSourceNode; gain:GainNode; end:number}

/** Audio-context time is the sole synthetic clock. Each note owns its voice. */
export class Playback {
  context?:AudioContext
  buffers=new Map<number,AudioBuffer>()
  voices=new Map<string,Voice>()
  pending=new Set<string>()
  piece?:PerformanceView
  mode:Mode='synth'
  external?:ExternalClock
  playing=false
  loading=false
  position=0
  anchorTime=0
  anchorPosition=0
  speed=1
  transpose=0
  hands='both'
  offset=0
  loop=false
  loopA=0
  loopB=0
  metronome=false
  countIn=false
  countEnd=0
  countDestination=0
  lastBeat=-Infinity
  timer?:ReturnType<typeof setInterval>
  onChange:()=>void=()=>{}
  onError:(message:string)=>void=()=>{}
  loadingPromise?:Promise<void>

  async unlock() {
    if(!this.context)this.context=new AudioContext({latencyHint:'interactive'})
    await this.context.resume()
    if(this.buffers.size===7)return
    if(!this.loadingPromise) {
      this.loading=true
      this.loadingPromise=Promise.all([1,2,3,4,5,6,7].map(async octave=>{
        const res=await fetch(`/samples/C${octave}.mp3`)
        if(!res.ok)throw new Error('Piano samples are unavailable. Reconnect and reload the app.')
        this.buffers.set(12*(octave+1),await this.context!.decodeAudioData(await res.arrayBuffer()))
      })).then(()=>{}).finally(()=>{this.loading=false;this.loadingPromise=undefined})
    }
    return this.loadingPromise
  }
  setPiece(piece:PerformanceView) {this.pause();this.piece=piece;this.position=0;this.loopA=0;this.loopB=piece.duration;this.loop=false;this.onChange()}
  replacePerformance(piece:PerformanceView, synth=false) {
    const now=this.time(),wasPlaying=this.playing
    this.flush();this.piece=piece
    if(synth){this.external?.pause();this.external=undefined;this.mode='synth'}
    this.position=Math.min(now,piece.duration);this.anchorPosition=this.position;this.anchorTime=this.context?.currentTime??0
    this.lastBeat=-Infinity
    if(wasPlaying)this.tick()
    this.onChange()
  }
  configureMode(mode:Mode,external?:ExternalClock) {this.pause();this.mode=mode;this.external=external;this.external?.seek(this.position+this.offset)}
  followExternal(playing:boolean) {
    if(this.mode==='synth'||this.countEnd)return
    if(playing&&!this.playing){this.playing=true;this.flush();if(this.timer)clearInterval(this.timer);this.timer=setInterval(()=>this.tick(),20)}
    else if(!playing&&this.playing){this.position=this.time();this.playing=false;this.flush();if(this.timer)clearInterval(this.timer);this.timer=undefined}
    this.onChange()
  }
  time() {
    if(!this.playing)return this.position
    if(this.countEnd>0)return this.countDestination
    if(this.mode!=='synth')return Math.max(0,(this.external?.currentTime()??this.position)-this.offset)
    return this.anchorPosition+((this.context?.currentTime??0)-this.anchorTime)*this.speed
  }
  async play() {
    if(!this.piece)return
    await this.unlock()
    if(this.position>=this.piece.duration-.01)this.position=0
    if(this.loop&&(this.position<this.loopA||this.position>=this.loopB))this.position=this.loopA
    this.flush()
    this.anchorTime=this.context!.currentTime
    this.anchorPosition=this.position
    this.playing=true
    this.lastBeat=-Infinity
    if(this.countIn) {
      const beat=secondsToBeats(this.position,this.piece.score.anchors)
      const beatDuration=(beatsToSeconds(beat+1,this.piece.score.anchors)-beatsToSeconds(beat,this.piece.score.anchors))/this.speed
      const unit=4/this.piece.settings.denominator
      const count=this.piece.settings.numerator
      const begin=this.context!.currentTime+.05
      for(let i=0;i<count;i++)this.click(begin+i*beatDuration*unit,i===0)
      this.countEnd=begin+count*beatDuration*unit
      this.countDestination=this.position
      this.external?.pause()
    } else if(this.mode!=='synth') {
      this.external?.seek(this.position+this.offset)
      await this.external?.play()
    }
    if(this.timer)clearInterval(this.timer)
    this.timer=setInterval(()=>this.tick(),20)
    this.tick();this.onChange()
  }
  pause() {
    this.position=Math.min(this.piece?.duration??Infinity,this.time())
    this.playing=false;this.countEnd=0
    this.external?.pause()
    if(this.timer)clearInterval(this.timer)
    this.timer=undefined
    this.flush();this.onChange()
  }
  seek(time:number) {
    const wasPlaying=this.playing
    this.position=Math.max(0,Math.min(this.piece?.duration??0,time))
    this.countEnd=0
    this.anchorPosition=this.position;this.anchorTime=this.context?.currentTime??0
    this.flush();this.lastBeat=-Infinity
    this.external?.seek(Math.max(0,this.position+this.offset))
    if(wasPlaying)this.tick()
    this.onChange()
  }
  rate(speed:number) {const now=this.time();this.speed=speed;this.external?.rate(speed);this.seek(now)}
  setTranspose(value:number){this.transpose=value;this.seek(this.time())}
  setHands(value:string){this.hands=value;this.seek(this.time())}
  flush() {
    this.voices.forEach(v=>{try{v.source.stop()}catch{/* already stopped */}v.gain.disconnect()})
    this.voices.clear();this.pending.clear()
  }
  click(when:number,strong:boolean) {
    const ctx=this.context;if(!ctx)return
    const osc=ctx.createOscillator(),gain=ctx.createGain()
    osc.frequency.value=strong?1300:900;gain.gain.setValueAtTime(.12,when);gain.gain.exponentialRampToValueAtTime(.001,when+.05)
    osc.connect(gain).connect(ctx.destination);osc.start(when);osc.stop(when+.06)
    const key=`click-${when}`;this.voices.set(key,{source:osc as unknown as AudioBufferSourceNode,gain,end:when+.06})
  }
  soundEnd(n:Note) {
    const events=(this.piece?.pedals??(this.piece as Piece|undefined)?.raw?.pedals??[]).filter(p=>(p.channel??0)===(n.channel??0))
    const down=events.findLast(p=>p.time<=n.end)
    if(!down||down.value<64)return n.end
    const up=events.find(p=>p.time>n.end&&p.value<64)
    return up?.time??this.piece!.duration
  }
  sound(n:Note,now:number) {
    const ctx=this.context!;const pitch=n.pitch+this.transpose
    if(pitch<0||pitch>127)return
    const base=[...this.buffers.keys()].reduce((a,b)=>Math.abs(b-pitch)<Math.abs(a-pitch)?b:a)
    const buffer=this.buffers.get(base)!
    const when=ctx.currentTime+Math.max(0,(n.start-now)/this.speed)
    const finish=Math.min(this.soundEnd(n),this.loop?this.loopB:Infinity)
    const duration=Math.max(.005,(finish-Math.max(n.start,now))/this.speed)
    const src=ctx.createBufferSource(),gain=ctx.createGain()
    src.buffer=buffer;src.playbackRate.value=2**((pitch-base)/12)
    const volume=(n.velocity??80)/127*.42
    gain.gain.setValueAtTime(0,when);gain.gain.linearRampToValueAtTime(volume,when+.006)
    gain.gain.setValueAtTime(volume,when+duration);gain.gain.exponentialRampToValueAtTime(.0001,when+duration+.16)
    src.connect(gain).connect(ctx.destination)
    // Seeking into a held note resumes its sample envelope instead of retriggering its attack.
    const sampleOffset=Math.max(0,(now-n.start))*src.playbackRate.value
    if(sampleOffset<buffer.duration)src.start(when,sampleOffset)
    src.stop(when+duration+.18)
    this.voices.set(n.id,{source:src,gain,end:when+duration+.18})
  }
  tick() {
    if(!this.playing||!this.piece)return
    const ctx=this.context
    if(ctx)for(const [id,v] of this.voices)if(v.end<ctx.currentTime){v.gain.disconnect();this.voices.delete(id)}
    if(this.countEnd) {
      if(!ctx||ctx.currentTime<this.countEnd)return
      this.anchorTime=this.countEnd;this.anchorPosition=this.countDestination;this.countEnd=0
      if(this.mode!=='synth'){this.external?.seek(this.position+this.offset);void this.external?.play()}
    }
    let now=this.time()
    if(this.loop&&now>=this.loopB){this.seek(advanceLoop(now,this.loopA,this.loopB,true));return}
    if(now>=this.piece.duration){this.pause();this.position=this.piece.duration;return}
    if(this.mode!=='synth'&&!this.external?.isPlaying())return
    if(this.mode==='synth'&&ctx)for(const n of this.piece.notes){
      if(this.pending.has(n.id)||this.soundEnd(n)<=now||n.start>now+.12*this.speed)continue
      if(this.hands!=='both'&&this.hands!==n.hand)continue
      if(this.loop&&n.start>=this.loopB)continue
      this.pending.add(n.id);this.sound(n,now)
    }
    if(this.metronome&&ctx?.state==='running') {
      const unit=4/this.piece.settings.denominator
      const phase=secondsToBeats(this.piece.settings.downbeat,this.piece.score.anchors)
      const beat=Math.floor((secondsToBeats(now,this.piece.score.anchors)-phase)/unit)
      if(beat!==this.lastBeat){this.click(ctx.currentTime,beat%this.piece.settings.numerator===0);this.lastBeat=beat}
    }
  }
  dispose(){this.pause();void this.context?.close()}
}
