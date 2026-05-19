# AI.DEN stack verification — pipeline, llama.cpp, MCP path
$ErrorActionPreference = "Continue"
$base = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (Test-Path (Join-Path $PSScriptRoot "..\models")) { $base = Split-Path -Parent $PSScriptRoot }

Write-Host "`n=== AI.DEN Stack Verification ===`n" -ForegroundColor Cyan

# 1. Pipeline config
Write-Host "[1] Pipeline stages (GET /_aiden/pipeline)"
$p = curl.exe -s -m 5 http://localhost:8765/_aiden/pipeline
Write-Host "    $p"

# 2. Pipeline preview
Write-Host "`n[2] Pipeline preview (claw + caveman markers)"
$prev = curl.exe -s -m 5 http://localhost:8765/_aiden/pipeline/preview | python -c @"
import sys,json
d=json.load(sys.stdin)
print('    stages:', d.get('stages'))
print('    claw:', '[AIDEN-CLAW]' in d.get('injected_block',''))
print('    caveman:', '[AIDEN-CAVEMAN]' in d.get('injected_block',''))
print('    backend:', d.get('inference_backend'))
"@

# 3. Chat through router (pipeline injection headers)
Write-Host "`n[3] Chat via router :8765 (expect X-AIDEN-Pipeline-Injected: true)"
$json = Join-Path $PSScriptRoot "test-pipeline-chat.json"
curl.exe -s -D - -m 120 -o (Join-Path $env:TEMP "aiden-chat-out.json") `
  http://localhost:8765/v1/chat/completions `
  -H "Content-Type: application/json" `
  --data-binary "@$json" 2>&1 | Select-String -Pattern "HTTP/|X-AIDEN"

# 4. MCP container path
Write-Host "`n[4] MCP -> router (docker exec chat path)"
docker exec mcp-server python -c @"
import asyncio, httpx
async def main():
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post('http://model-router:8765/v1/chat/completions', json={
            'model': 'Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf',
            'messages': [{'role':'user','content':'One word: OK'}],
            'stream': False, 'max_tokens': 8
        })
        print('    status:', r.status_code)
        print('    pipeline:', r.headers.get('x-aiden-pipeline-injected'))
        print('    stages:', r.headers.get('x-aiden-pipeline-stages'))
asyncio.run(main())
"@ 2>&1

Write-Host "`n[5] Containers"
docker ps --filter "name=llamacpp|model-router|mcp-server" --format "    {{.Names}}: {{.Status}}"

Write-Host "`nDone.`n" -ForegroundColor Green
