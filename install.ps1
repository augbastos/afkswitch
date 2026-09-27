# Installs AFKSwitch's two Claude Code skills as personal skills so the bare
# /afk and /back commands are available from every Claude Code session on this machine.
#
#   pwsh -File install.ps1            # install or update
#   pwsh -File install.ps1 -Uninstall # remove
#
# Copies deliberately: symlinks/junctions can require extra Windows configuration.

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'

$source = Join-Path $PSScriptRoot 'skills'
$target = Join-Path $HOME '.claude/skills'
$names  = @('afk', 'back')

foreach ($name in $names) {
    $dest = Join-Path $target $name

    if ($Uninstall) {
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force; "removed  $dest" }
        else { "absent   $dest" }
        continue
    }

    $src = Join-Path $source $name
    if (-not (Test-Path (Join-Path $src 'SKILL.md'))) { throw "missing source skill: $src" }

    $verb = if (Test-Path $dest) { 'updated ' } else { 'installed' }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $src '*') $dest -Recurse -Force
    "$verb $dest"
}

if (-not $Uninstall) {
    ""
    "Restart Claude Code (or /clear) to pick up AFKSwitch, then use /afk and /back."
}
