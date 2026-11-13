[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'build', 'server', 'client', 'test')]
    [string]$Action = 'build',
    [string]$Name,
    [string]$HostName = '127.0.0.1',
    [int]$Port = 9000,
    [string]$Filter = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
if ($Action -eq 'setup') { & (Join-Path $projectRoot 'tools\setup-sdk.ps1'); exit $LASTEXITCODE }
$dotnetExe = Join-Path $projectRoot '.dotnet\dotnet.exe'
if (-not (Test-Path -LiteralPath $dotnetExe)) { throw '请先运行：.\run.ps1 setup' }
$env:DOTNET_ROOT = Join-Path $projectRoot '.dotnet'
$env:DOTNET_CLI_HOME = Join-Path $projectRoot '.cli-home'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:DOTNET_NOLOGO = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_ADD_GLOBAL_TOOLS_TO_PATH = '0'
$env:DOTNET_CLI_USE_MSBUILD_SERVER = '0'
$env:MSBUILDDISABLENODEREUSE = '1'
$env:NUGET_PACKAGES = Join-Path $projectRoot '.nuget\packages'
$env:NUGET_HTTP_CACHE_PATH = Join-Path $projectRoot '.nuget\http-cache'
$env:A3_DOTNET_PATH = $dotnetExe
$previousAppData = $env:APPDATA
# 仅在脚本运行期间使用项目自己的 NuGet 用户配置目录。
$env:APPDATA = Join-Path $projectRoot '.cli-home\AppData\Roaming'
New-Item -ItemType Directory -Force -Path $env:APPDATA | Out-Null
Push-Location $projectRoot
try {
    if ($Action -eq 'build' -or $Action -eq 'test') {
        & $dotnetExe build 'ChatDemo.sln' --configuration Debug --nologo
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    switch ($Action) {
        'build' { exit 0 }
        'server' { & $dotnetExe (Join-Path $projectRoot 'src\Chat.Server\bin\Debug\net10.0\Chat.Server.dll') --host $HostName --port $Port }
        'client' {
            if ([string]::IsNullOrWhiteSpace($Name)) { throw '客户端需要用户名，例如：.\run.ps1 client -Name Alice' }
            & $dotnetExe (Join-Path $projectRoot 'src\Chat.Client\bin\Debug\net10.0\Chat.Client.dll') --host $HostName --port $Port --name $Name
        }
        'test' {
            $testArguments = @((Join-Path $projectRoot 'tests\Chat.Tests\bin\Debug\net10.0\Chat.Tests.dll'), '--output-dir', (Join-Path $projectRoot 'output'))
            if (-not [string]::IsNullOrWhiteSpace($Filter)) { $testArguments += @('--filter', $Filter) }
            & $dotnetExe @testArguments
        }
    }
    exit $LASTEXITCODE
} finally { Pop-Location; $env:APPDATA = $previousAppData }
