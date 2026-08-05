param(
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tempRoot = [System.IO.Path]::GetTempPath()
$runDirectory = Join-Path $tempRoot ("vmed-auth-curl-" + [guid]::NewGuid().ToString("N"))
$null = New-Item -ItemType Directory -Path $runDirectory

$databasePath = Join-Path $runDirectory "auth.db"
$requestPath = Join-Path $runDirectory "request.json"
$responsePath = Join-Path $runDirectory "response.json"
$stdoutPath = Join-Path $runDirectory "server.out.log"
$stderrPath = Join-Path $runDirectory "server.err.log"
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$baseUrl = "http://127.0.0.1:$Port"

$env:APP_ENV = "test"
$env:DATABASE_URL = "sqlite:///" + $databasePath.Replace("\", "/")
$env:JWT_SECRET_KEY = "curl-test-secret-that-is-long-and-local-only"
$env:NURSE_REGISTRATION_CODE = "curl-nurse-code"

function Invoke-StatusCurl {
    param(
        [string]$Url,
        [string]$Method = "GET",
        [string]$Json = "",
        [string]$Token = ""
    )

    $arguments = @("-s", "-o", $responsePath, "-w", "%{http_code}", "-X", $Method, $Url)
    if ($Json) {
        [System.IO.File]::WriteAllText($requestPath, $Json, [System.Text.UTF8Encoding]::new($false))
        $arguments += @("-H", "Content-Type: application/json", "--data-binary", "@$requestPath")
    }
    if ($Token) {
        $arguments += @("-H", "Authorization: Bearer $Token")
    }
    return (& curl.exe @arguments)
}

function Invoke-JsonCurl {
    param(
        [string]$Url,
        [string]$Json
    )

    [System.IO.File]::WriteAllText($requestPath, $Json, [System.Text.UTF8Encoding]::new($false))
    $rawResponse = & curl.exe -s -X POST $Url -H "Content-Type: application/json" --data-binary "@$requestPath"
    return ($rawResponse | ConvertFrom-Json)
}

$server = $null
try {
    $server = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", $Port `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $healthStatus = & curl.exe -s -o NUL -w "%{http_code}" "$baseUrl/health"
        if ($healthStatus -eq "200") {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) {
        throw "Server không khởi động. Xem log: $stderrPath"
    }

    $patientRegister = '{"email":"curl.patient@example.com","password":"StrongPass123!","full_name":"Curl Patient","role":"patient"}'
    $patientLogin = '{"email":"curl.patient@example.com","password":"StrongPass123!"}'
    $nurseRegister = '{"email":"curl.nurse@example.com","password":"StrongPass123!","full_name":"Curl Nurse","role":"nurse","nurse_registration_code":"curl-nurse-code"}'
    $nurseLogin = '{"email":"curl.nurse@example.com","password":"StrongPass123!"}'

    $patientRegisterStatus = Invoke-StatusCurl -Url "$baseUrl/api/v1/register" -Method "POST" -Json $patientRegister
    $patientSession = Invoke-JsonCurl -Url "$baseUrl/api/v1/login" -Json $patientLogin
    $nurseRegisterStatus = Invoke-StatusCurl -Url "$baseUrl/api/v1/register" -Method "POST" -Json $nurseRegister
    $nurseSession = Invoke-JsonCurl -Url "$baseUrl/api/v1/login" -Json $nurseLogin

    $correctRoleStatus = Invoke-StatusCurl -Url "$baseUrl/api/v1/nurse/queue" -Token $nurseSession.access_token
    $wrongRoleStatus = Invoke-StatusCurl -Url "$baseUrl/api/v1/nurse/queue" -Token $patientSession.access_token
    $missingTokenStatus = Invoke-StatusCurl -Url "$baseUrl/api/v1/nurse/queue"

    Write-Output "register patient: $patientRegisterStatus"
    Write-Output "login patient: $(if ($patientSession.access_token) { '200, token issued' } else { 'failed' })"
    Write-Output "register nurse: $nurseRegisterStatus"
    Write-Output "login nurse: $(if ($nurseSession.access_token) { '200, token issued' } else { 'failed' })"
    Write-Output "middleware correct role: $correctRoleStatus"
    Write-Output "middleware wrong role: $wrongRoleStatus"
    Write-Output "middleware missing token: $missingTokenStatus"

    if (
        $patientRegisterStatus -ne "201" -or
        $nurseRegisterStatus -ne "201" -or
        $correctRoleStatus -ne "200" -or
        $wrongRoleStatus -ne "403" -or
        $missingTokenStatus -ne "401"
    ) {
        throw "Một hoặc nhiều kiểm tra curl không đạt kết quả mong đợi."
    }
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id
        Wait-Process -Id $server.Id -ErrorAction SilentlyContinue
    }

    $resolvedRunDirectory = (Resolve-Path $runDirectory).Path
    if ($resolvedRunDirectory.StartsWith($tempRoot) -and (Split-Path $resolvedRunDirectory -Leaf).StartsWith("vmed-auth-curl-")) {
        Remove-Item -LiteralPath $resolvedRunDirectory -Recurse -Force
    }
}
