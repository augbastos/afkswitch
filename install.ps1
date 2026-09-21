# Installs broadcast / afk / back as personal skills, so they answer to the bare
# /broadcast, /afk and /back in every Claude Code session on this machine.
#
#   pwsh -File install.ps1            # install or update
#   pwsh -File install.ps1 -Uninstall # remove
#
# Copies, deliberately: a junction or symlink would need admin or Developer Mode, and
# this is three markdown files.

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'

$source = Join-Path $PSScriptRoot 'skills'
$target = Join-Path $HOME '.claude/skills'
$names  = @('broadcast', 'afk', 'back')

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
    "Restart Claude Code (or /clear) to pick them up, then: /broadcast, /afk, /back"
}
