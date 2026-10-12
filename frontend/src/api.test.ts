import {afterEach, expect, it, vi} from 'vitest'
import {api} from './api'

afterEach(()=>vi.unstubAllGlobals())

it('distinguishes a score failure from an unreachable server',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Could not generate the score. Your saved piece and original notes are unchanged.'}),{status:500})))
 await expect(api('/pieces/test/revisions')).rejects.toThrow('Could not generate the score')
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
 await expect(api('/health')).rejects.toThrow('Cannot reach Piano AI')
})

it('reports non-JSON server errors without claiming the server is offline',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('Internal Server Error',{status:500})))
 await expect(api('/pieces/test/revisions')).rejects.toThrow('HTTP 500')
})
