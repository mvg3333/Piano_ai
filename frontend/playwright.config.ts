import {defineConfig} from '@playwright/test'
import path from 'node:path'
export default defineConfig({testDir:'./e2e',timeout:45000,use:{baseURL:'http://127.0.0.1:8001',headless:true},workers:1,reporter:'list',
 webServer:{command:'..\\.venv\\Scripts\\python.exe -m uvicorn backend.app:app --app-dir .. --host 127.0.0.1 --port 8001',url:'http://127.0.0.1:8001/api/health',reuseExistingServer:false,env:{PIANO_DATA_DIR:path.resolve('../data/browser-tests')}}
})
