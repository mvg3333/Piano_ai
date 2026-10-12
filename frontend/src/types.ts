export type Hand = 'left' | 'right'
export interface Note { id:string; pitch:number; start:number; end:number; velocity?:number; hand:Hand; channel?:number; deleted?:boolean }
export interface Anchor { time:number; beat:number; bpm:number }
export interface Settings { tempo:number; numerator:number; denominator:number; quantization:string; downbeat:number; useMidiTempo:boolean; cleanup?:'off'|'balanced'|'strong' }
export interface Source { id?:string; kind:string; videoId?:string; url?:string; duration?:number; suggestedStart?:number; title?:string; mediaClip?:boolean; youtubeReference?:{videoId:string;url:string} }
export interface Score { musicxml:string; anchors:Anchor[]; measures:{index:number;number:number;startBeat:number;endBeat:number;startTime:number}[]; fragments:{noteId:string;measure:number;beat:number;endBeat:number;hand:Hand;xmlId:string}[]; warning:string }
export interface PerformanceView { notes:Note[]; pedals?:{time:number;value:number;channel?:number}[]; settings:Settings; score:Score; duration:number; clipStart:number }
export interface Piece extends PerformanceView { id:string; title:string; subtitle:string; raw:{notes:Note[]; pedals:{time:number;value:number;channel?:number}[]; duration:number; provenance:Record<string,unknown>}; edits:Note[]; source:Source; guidance?:Guidance; processingSeconds?:number; cleanup?:{profile:string;hiddenNoteIds:string[];hasOnsetEvidence:boolean}; noteEvidence?:Record<string,{onset:number}> }
export type Difficulty = 'melody'|'beginner'|'easy'|'full'
export interface HandDifficulty {level:Difficulty;maxNotes:number;maxSpan:number;activity:'none'|'changes'|'light'}
export interface ArrangementSettings {left:HandDifficulty;right:HandDifficulty}
export interface Guidance {roles:Record<string,'melody'|'accompaniment'>;protectedNoteIds:string[]}
export interface ArrangementSummary {id:string;name:string;settings:ArrangementSettings;created:number;outdated:boolean;sourceFingerprint:string;predecessorId?:string}
export interface Demand {noteCount:number;maxSimultaneous:number;maxSpan:number;largeJumps:number;accompanimentAttacksPerSecond:number}
export interface Arrangement extends ArrangementSummary {pieceId:string;performance:PerformanceView;sourcePerformance:PerformanceView;sourceGuidance:Guidance;engineVersion:number;sourceSnapshotId:string;sourceNoteMap:Record<string,string[]>;melodyNoteIds:string[];operations:{type:string;sourceNoteIds:string[];reason:string;message:string;before?:number;after?:number}[];reviewFlags:{code:string;start:number;end:number;noteIds:string[];message:string}[];metrics:{before:Record<Hand,Demand>;after:Record<Hand,Demand>}}
export interface ArrangementList {sourceFingerprint:string;guidance:Guidance;arrangements:ArrangementSummary[]}
export interface Job { id:string; status:string; stage:string; error?:string; piece_id?:string; created:number; updated:number }
export type Mode = 'synth' | 'audio' | 'youtube'
export const HAND_COLORS = {left:'#43c5b5',right:'#c88bdc'}
