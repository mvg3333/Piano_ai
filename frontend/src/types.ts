export type Hand = 'left' | 'right'
export interface Note { id:string; pitch:number; start:number; end:number; velocity?:number; hand:Hand; channel?:number; deleted?:boolean }
export interface Anchor { time:number; beat:number; bpm:number }
export interface Settings { tempo:number; numerator:number; denominator:number; quantization:string; downbeat:number; useMidiTempo:boolean; cleanup?:'off'|'balanced'|'strong' }
export interface Source { id?:string; kind:string; videoId?:string; url?:string; duration?:number; suggestedStart?:number; title?:string; mediaClip?:boolean; youtubeReference?:{videoId:string;url:string} }
export interface Score { musicxml:string; anchors:Anchor[]; measures:{index:number;number:number;startBeat:number;endBeat:number;startTime:number}[]; fragments:{noteId:string;measure:number;beat:number;endBeat:number;hand:Hand;xmlId:string}[]; warning:string }
export interface Piece { id:string; title:string; subtitle:string; notes:Note[]; raw:{notes:Note[]; pedals:{time:number;value:number;channel?:number}[]; duration:number; provenance:Record<string,unknown>}; edits:Note[]; settings:Settings; score:Score; duration:number; clipStart:number; source:Source; processingSeconds?:number; cleanup?:{profile:string;hiddenNoteIds:string[];hasOnsetEvidence:boolean}; noteEvidence?:Record<string,{onset:number}> }
export interface Job { id:string; status:string; stage:string; error?:string; piece_id?:string; created:number; updated:number }
export type Mode = 'synth' | 'audio' | 'youtube'
export const HAND_COLORS = {left:'#43c5b5',right:'#c88bdc'}
