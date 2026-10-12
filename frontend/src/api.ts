import type { Piece, Source, Job, Settings, Note } from './types'
export async function api<T>(path:string,init?:RequestInit):Promise<T> {
 let res:Response
 try{res=await fetch('/api'+path,init)}catch{throw new Error('Cannot reach Piano AI. Check that the server is running and try again.')}
 if(!res.ok){
  let detail:unknown
  try{detail=(await res.json()).detail}catch{/* Some server/proxy errors are plain text. */}
  const fallback=`The server could not complete this request (HTTP ${res.status}). Please try again.`
  throw new Error(typeof detail==='string'?detail:Array.isArray(detail)?detail.map(d=>d.msg??'Invalid input').join('; '):fallback)
 }
 return res.json()
}
export const jsonPost=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const loadPiece=(id:string)=>api<Piece>('/pieces/'+id)
export const revisePiece=(piece:Piece,settings:Settings,edits:Note[])=>api<Piece>(`/pieces/${piece.id}/revisions`,jsonPost({settings,edits}))
export const createJob=(source:Source,start:number,end:number|null)=>api<Job>('/jobs',jsonPost({sourceId:source.id,start,end}))
export const retranscribePiece=(piece:Piece,settings:Settings)=>api<Job>(`/pieces/${piece.id}/transcriptions`,jsonPost({settings}))
