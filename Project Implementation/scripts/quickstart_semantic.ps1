# Quickstart for the Semantic Web part on Windows (PowerShell).
# Same steps as quickstart_semantic.sh. Usage:  .\scripts\quickstart_semantic.ps1 [-Full] [-NoUi]
param([switch]$Full, [switch]$NoUi)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$endpoint = if ($env:VIRTUOSO_ENDPOINT) { $env:VIRTUOSO_ENDPOINT } else { "http://localhost:8890/sparql" }
$fullArg = if ($Full) { "--full" } else { "" }

Write-Host "== 1/4 Python environment"
if (-not (Test-Path .venv)) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt

Write-Host "== 2/4 Ontology and knowledge graph files"
python main.py kg-ontology
python main.py kg-build $fullArg

function Up { try { (Invoke-WebRequest -UseBasicParsing -Method Post -Body @{query="ASK {}"} $endpoint).StatusCode -eq 200 } catch { $false } }
Write-Host "== 3/4 Triple store"
$env:KG_BACKEND = "virtuoso"
if (Up) { Write-Host "Virtuoso is running at $endpoint" }
elseif (Get-Command docker -ErrorAction SilentlyContinue) {
  docker start csc501-virtuoso 2>$null; if ($LASTEXITCODE -ne 0) {
    docker run -d --name csc501-virtuoso -p 8890:8890 -p 1111:1111 -e DBA_PASSWORD=dba openlink/virtuoso-opensource-7:latest | Out-Null }
  for ($i = 0; $i -lt 60 -and -not (Up); $i++) { Start-Sleep 2 }
  docker exec csc501-virtuoso isql 1111 dba dba "exec=GRANT SPARQL_UPDATE TO `"SPARQL`"; DB.DBA.RDF_DEFAULT_USER_PERMS_SET ('nobody', 7);" | Out-Null
} else { Write-Host "No Virtuoso and no Docker: using the embedded store."; $env:KG_BACKEND = "local" }

Write-Host "== 4/4 Load, demonstrate, serve"
python main.py kg-load $fullArg
python main.py kg-demo
python main.py kg-check
if (-not $NoUi) { Write-Host "Web UI: http://127.0.0.1:5001"; python main.py kg-ui }
