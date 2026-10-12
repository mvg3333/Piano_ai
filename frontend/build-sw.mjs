import {readFileSync,writeFileSync,readdirSync} from 'node:fs'
import {createHash} from 'node:crypto'
const assets=readdirSync('dist/assets').map(name=>'/assets/'+name)
const hash=createHash('sha256').update(assets.map(p=>readFileSync('dist'+p)).join('')).update(readFileSync('dist/demo.json')).digest('hex').slice(0,12)
const source=readFileSync('public/sw.js','utf8').replace("const CACHE='piano-ai-v1';",`const CACHE='piano-ai-${hash}';`).replace('const CORE=[',`const CORE=[${assets.map(p=>JSON.stringify(p)).join(',')},`)
writeFileSync('dist/sw.js',source)
