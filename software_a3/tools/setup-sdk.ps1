[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$sdkVersion = (Get-Content -LiteralPath (Join-Path $projectRoot 'global.json') -Raw | ConvertFrom-Json).sdk.version
$installDir = Join-Path $projectRoot '.dotnet'
$dotnetExe = Join-Path $installDir 'dotnet.exe'
if (Test-Path -LiteralPath (Join-Path $installDir "sdk\$sdkVersion")) {
    Write-Output "本项目 .NET SDK $sdkVersion 已安装：$dotnetExe"
    exit 0
}
if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw '此安装脚本用于 Windows。其他系统请安装 .NET 10 SDK 后使用 dotnet 命令。'
}
$cacheDir = Join-Path $projectRoot '.cache'
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
$metadataUrl = 'https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json'
function Receive-OfficialFile([string]$Uri, [string]$Destination) {
    try {
        Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing
    } catch {
        # 某些受限 Windows 环境无法使用系统 TLS；Python 仍正常校验证书。
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $pythonCommand) { throw }
        Write-Output '系统下载方式不可用，改用本机 Python HTTPS 下载。'
        $downloadCode = @'
import shutil, sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=60) as source, open(sys.argv[2], 'wb') as target:
    shutil.copyfileobj(source, target, length=1024*1024)
'@
        & $pythonCommand.Source -c $downloadCode $Uri $Destination
        if ($LASTEXITCODE -ne 0) { throw '官方文件下载失败。' }
    }
}
Write-Output '读取微软官方 SDK 发布信息……'
$metadataPath = Join-Path $cacheDir 'releases.json'
Receive-OfficialFile $metadataUrl $metadataPath
$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$sdk = @($metadata.releases | ForEach-Object { $_.sdks } | Where-Object { $_.version -eq $sdkVersion }) | Select-Object -First 1
if ($null -eq $sdk) { throw "未在官方发布信息中找到 SDK $sdkVersion。" }
$rid = if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq [System.Runtime.InteropServices.Architecture]::Arm64) { 'win-arm64' } else { 'win-x64' }
$package = $sdk.files | Where-Object { $_.rid -eq $rid -and $_.name.EndsWith('.zip') } | Select-Object -First 1
if ($null -eq $package) { throw "未找到 $rid 的 SDK ZIP。" }
$archivePath = [System.IO.Path]::GetFullPath((Join-Path $cacheDir "dotnet-sdk-$sdkVersion-$rid.zip"))
if (-not $archivePath.StartsWith($cacheDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw '下载路径超出项目缓存目录。' }
Write-Output "下载 .NET SDK $sdkVersion ($rid)，请等待……"
Receive-OfficialFile $package.url $archivePath
$actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA512).Hash
if (-not $actualHash.Equals($package.hash, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'SDK SHA-512 校验失败，未安装。' }
Write-Output '校验通过，解压到项目的 .dotnet 目录……'
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
# 解压前检查每一个归档路径，目标都必须位于本项目 SDK 目录内。
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($entry in $archive.Entries) {
        $target = [System.IO.Path]::GetFullPath((Join-Path $installDir $entry.FullName))
        if (-not $target.StartsWith($installDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'SDK 归档包含越界路径。' }
    }
} finally { $archive.Dispose() }
Expand-Archive -LiteralPath $archivePath -DestinationPath $installDir -Force
if (-not (Test-Path -LiteralPath $dotnetExe)) { throw '未找到解压后的 dotnet.exe。' }
Remove-Item -LiteralPath $archivePath
Write-Output "SDK 已安装：$dotnetExe"
