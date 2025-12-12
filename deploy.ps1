Param(
    [string]$PROJECT_NUMBER = "",
    [string]$PROJECT_ID = "",
    [string]$REGION = "asia-northeast3",
    [string]$REPO = "smartnotam-repo",
    [string]$SERVICE = "smartnotam",
    [string]$IMAGE_NAME = "smartnotam",
    [switch]$AllowUnauthenticated = $true
)

# Helper: write status
function Write-Step($msg) { Write-Host "[STEP] $msg" -ForegroundColor Cyan }
function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Gray }
function Write-ErrorMsg($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Step "Checking gcloud CLI..."
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-ErrorMsg "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
    exit 1
}

Write-Step "Authenticating (if needed)..."
gcloud auth login | Out-Null

if (-not $PROJECT_ID -and $PROJECT_NUMBER) {
    Write-Step "Resolving PROJECT_ID from PROJECT_NUMBER=$PROJECT_NUMBER"
    $PROJECT_ID = gcloud projects describe $PROJECT_NUMBER --format="value(projectId)"
}

if (-not $PROJECT_ID) {
    Write-ErrorMsg "PROJECT_ID is required. Provide -PROJECT_ID or -PROJECT_NUMBER."
    exit 1
}

Write-Step "Setting project: $PROJECT_ID"
gcloud config set project $PROJECT_ID | Out-Null

Write-Step "Enabling required APIs (Run, Artifact Registry, Cloud Build)"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com | Out-Null

Write-Step "Ensuring Artifact Registry repo exists: $REPO in $REGION"
$repoExists = gcloud artifacts repositories describe $REPO --location=$REGION --format="value(name)" 2>$null
if (-not $repoExists) {
    gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION --description="SmartNOTAM images" | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$IMAGE_URI = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:${timestamp}"

Write-Step "Building and pushing image via Cloud Build: $IMAGE_URI"
gcloud builds submit --tag $IMAGE_URI .
if ($LASTEXITCODE -ne 0) { Write-ErrorMsg "Build failed"; exit 1 }

Write-Step "Deploying to Cloud Run service: $SERVICE in $REGION"
# Build env vars from .env if present
$envVarsMap = @{}
$envFile = Join-Path (Get-Location) ".env"
if (Test-Path $envFile) {
    Write-Step "Loading environment variables from .env"
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $kv = $line -split '=',2
        if ($kv.Length -eq 2) {
            $k = $kv[0].Trim()
            $v = $kv[1].Trim()
            # include only known keys or non-empty
            if ($v) { $envVarsMap[$k] = $v }
        }
    }
}

# Ensure FLASK_ENV=production
$envVarsMap['FLASK_ENV'] = 'production'
# Set API keys
$envVarsMap['GOOGLE_API_KEY'] = 'AIzaSyA7rf9lPi2h_0ff7hg2OpheObhhbRXRkxI'
$envVarsMap['GOOGLE_MAPS_API_KEY'] = 'AIzaSyA7rf9lPi2h_0ff7hg2OpheObhhbRXRkxI'
$envVarsMap['GEMINI_API_KEY'] = 'AIzaSyA7rf9lPi2h_0ff7hg2OpheObhhbRXRkxI'

# Compose --set-env-vars argument
$envPairs = $envVarsMap.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
$envVarsArg = ($envPairs -join ',')

$args = @(
    "run","deploy",$SERVICE,
    "--image",$IMAGE_URI,
    "--platform","managed",
    "--region",$REGION,
    "--cpu","2",
    "--memory","2Gi",
    "--timeout","900",
    "--max-instances","10",
    "--port","8080",
    "--set-env-vars",$envVarsArg
)
if ($AllowUnauthenticated) { $args += "--allow-unauthenticated" }
gcloud @args
if ($LASTEXITCODE -ne 0) { Write-ErrorMsg "Deploy failed"; exit 1 }

Write-Step "Fetching service URL"
$url = gcloud run services describe $SERVICE --region $REGION --format "value(status.url)"
Write-Host "Deployed URL: $url" -ForegroundColor Green

Write-Info "If you need a fixed hostname like https://$SERVICE-<PROJECT_NUMBER>.$REGION.run.app, it will be shown above."
